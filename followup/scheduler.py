"""Sistema de follow-up.

Regras:
- Janela total: 72h apos ultima mensagem do lead (CTWA garante 72h se bot respondeu em 24h).
- 6 follow-ups distribuidos: FU0 em 1h, FU1 em 4h, FU2 em 12h, FU3 em 24h, FU4 em 48h, FU5 em 60h.
- Stages elegiveis: 'novo', 'qualificando', 'interesse'.
- Bot nao envia se respondeu ao lead nas ultimas 1h (evita atropelar conversa ativa).
- Usa asyncpg direto (consistente com o restante do projeto).
"""

import logging
from datetime import datetime, timezone, timedelta

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import settings
from followup.templates import get_followup_message

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

_pool: asyncpg.Pool | None = None

# Delay por contagem de follow-up (count -> horas apos ultima msg do lead)
FU_DELAYS_HOURS = {
    0: 1,   # FU0: 1h
    1: 4,   # FU1: 4h
    2: 12,  # FU2: 12h
    3: 24,  # FU3: 24h
    4: 48,  # FU4: 48h
    5: 60,  # FU5: 60h (ultima)
}

ELIGIBLE_STAGES = ["novo", "qualificando", "interesse"]


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=1,
            max_size=3,
            statement_cache_size=0,
        )
    return _pool


async def _send_followup(phone: str, lead: dict, message: str) -> bool:
    """Envia follow-up via Meta Cloud API."""
    from output.sender import send_message
    try:
        ok = await send_message(phone, message)
        if ok:
            logger.info("Follow-up enviado: phone=%s fu=%s", phone, lead.get("followup_count", 0))
        else:
            logger.warning("Follow-up FALHOU (send_message=False): phone=%s fu=%s", phone, lead.get("followup_count", 0))
        return ok
    except Exception as exc:
        logger.error("Follow-up excecao: phone=%s: %s", phone, exc)
        return False


async def run_followup() -> None:
    """Busca leads elegiveis e envia follow-up via asyncpg."""
    now = datetime.now(timezone.utc)
    bot_cutoff = now - timedelta(hours=1)

    try:
        pool = await _get_pool()
        rows = await pool.fetch(
            """
            SELECT phone, name, stage, nicho, observacoes_sdr,
                   followup_count, last_lead_msg_at, last_bot_msg_at
            FROM agente_trafego.contacts
            WHERE stage = ANY($1)
              AND COALESCE(followup_count, 0) < 6
              AND phone IS NOT NULL
              AND last_lead_msg_at IS NOT NULL
            """,
            ELIGIBLE_STAGES,
        )
        all_leads = [dict(r) for r in rows]
    except Exception as exc:
        logger.error("Erro ao buscar leads para follow-up: %s", exc)
        return

    logger.info("Follow-up: %d leads candidatos encontrados", len(all_leads))

    eligible: list[dict] = []
    for lead in all_leads:
        count = lead.get("followup_count") or 0
        last_lead: datetime | None = lead.get("last_lead_msg_at")
        last_bot: datetime | None = lead.get("last_bot_msg_at")

        # Bot respondeu na ultima 1h — conversa ativa, pula
        if last_bot and last_bot.replace(tzinfo=timezone.utc) > bot_cutoff:
            continue

        delay_h = FU_DELAYS_HOURS.get(count)
        if delay_h is None:
            continue

        delay_cutoff = now - timedelta(hours=delay_h)

        # Lead precisa ter ficado em silencio pelo tempo minimo
        if not last_lead or last_lead.replace(tzinfo=timezone.utc) > delay_cutoff:
            continue

        eligible.append(lead)

    logger.info("Follow-up: %d leads elegiveis de %d candidatos", len(eligible), len(all_leads))

    sent_count = 0
    for lead in eligible:
        phone = lead["phone"]
        message = get_followup_message(lead)
        if message is None:
            continue

        success = await _send_followup(phone, lead, message)
        if not success:
            continue

        new_count = (lead.get("followup_count") or 0) + 1
        try:
            pool = await _get_pool()
            await pool.execute(
                "UPDATE agente_trafego.contacts SET followup_count = $2, last_bot_msg_at = $3, updated_at = now() WHERE phone = $1",
                phone, new_count, now,
            )
        except Exception as exc:
            logger.error("Falha ao atualizar followup_count para phone=%s: %s", phone, exc)

        sent_count += 1

    logger.info("Ciclo de follow-up concluido: %d enviados / %d elegiveis / %d candidatos", sent_count, len(eligible), len(all_leads))


def start_scheduler() -> None:
    scheduler.add_job(
        run_followup,
        "interval",
        minutes=settings.FOLLOWUP_INTERVAL_MINUTES,
        id="followup_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler de follow-up iniciado: intervalo=%d min", settings.FOLLOWUP_INTERVAL_MINUTES
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler encerrado.")
