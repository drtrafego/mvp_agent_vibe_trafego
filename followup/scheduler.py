"""Sistema de follow-up.

Regras:
- Janela total: 72h após última mensagem do lead.
- 5 follow-ups distribuídos: FU0 em 4h, FU1 em 24h, FU2 em 48h, FU3 em 60h, FU4 em 72h.
- Stages elegíveis: 'novo', 'qualificando', 'interesse'.
- Excluídos: 'agendado', 'realizada', 'sem_interesse', 'perdido', 'bloqueado'.
- Bot não envia se respondeu ao lead nas últimas 1h (evita atropelar conversa em andamento).
"""

import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from supabase import create_client, Client

from config.settings import settings
from followup.templates import get_followup_message

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

_supabase: Client | None = None

# Delay por contagem de follow-up (count -> horas após last_lead_msg_at)
FU_DELAYS_HOURS = {
    0: 1,   # FU0: 60 min após última msg do lead
    1: 24,  # FU1: 24h
    2: 48,  # FU2: 48h
    3: 60,  # FU3: 60h
    4: 72,  # FU4: 72h (última)
}

ELIGIBLE_STAGES = ["novo", "qualificando", "interesse"]


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


def _hours_ago_iso(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


async def _send_followup(lead: dict, message: str) -> bool:
    """Envia follow-up via Meta Cloud API."""
    from output.sender import send_message
    phone = lead["phone"]
    try:
        ok = await send_message(phone, message)
        if ok:
            logger.info(
                "Follow-up enviado: phone=%s count=%s", phone, lead.get("followup_count", 0)
            )
        return ok
    except Exception as exc:
        logger.error("Falha ao enviar follow-up para phone=%s: %s", phone, exc)
        return False


async def run_followup() -> None:
    """Busca leads elegíveis e envia follow-up."""
    supabase = _get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    bot_cutoff = _hours_ago_iso(1)  # bot não respondeu na última 1h

    try:
        result = (
            supabase.schema("agente_vibe").table("contacts")
            .select(
                "phone, name, stage, nicho, observacoes_sdr, followup_count, "
                "last_lead_msg_at, last_bot_msg_at"
            )
            .in_("stage", ELIGIBLE_STAGES)
            .lt("followup_count", 5)
            .not_.is_("phone", "null")
            .not_.is_("last_lead_msg_at", "null")
            .execute()
        )
        all_leads = result.data or []
    except Exception as exc:
        logger.error("Erro ao buscar leads para follow-up: %s", exc)
        return

    eligible: list[dict] = []
    for lead in all_leads:
        count = lead.get("followup_count") or 0
        last_lead = lead.get("last_lead_msg_at")
        last_bot = lead.get("last_bot_msg_at")

        # Bot respondeu nas últimas 1h → conversa ativa, pula
        if last_bot and last_bot > bot_cutoff:
            continue

        # Calcula cutoff do count atual
        delay_h = FU_DELAYS_HOURS.get(count)
        if delay_h is None:
            continue
        delay_cutoff = _hours_ago_iso(delay_h)

        # Lead precisa ter mandado última msg antes do cutoff
        if not last_lead or last_lead > delay_cutoff:
            continue

        eligible.append(lead)

    sent_count = 0
    for lead in eligible:
        message = get_followup_message(lead)
        if message is None:
            continue

        success = await _send_followup(lead, message)
        if not success:
            continue

        phone = lead["phone"]
        new_count = (lead.get("followup_count") or 0) + 1
        try:
            supabase.schema("agente_vibe").table("contacts").update(
                {"followup_count": new_count, "last_bot_msg_at": now_iso}
            ).eq("phone", phone).execute()
        except Exception as exc:
            logger.error("Falha ao atualizar followup_count para phone=%s: %s", phone, exc)

        sent_count += 1

    logger.info("Ciclo de follow-up concluído: %d mensagens enviadas (avaliados=%d)", sent_count, len(all_leads))


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
