import logging
from datetime import datetime, timezone, timedelta

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from supabase import create_client, Client

from config.settings import settings
from followup.templates import get_followup_message

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


def _calc_fu0_cutoff() -> str:
    """Retorna ISO timestamp do limite para FU0 (2h atras)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.FOLLOWUP_FU0_DELAY_HOURS)
    return cutoff.isoformat()


def _calc_fu_cutoff() -> str:
    """Retorna ISO timestamp do limite para FU1+ (24h atras)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return cutoff.isoformat()


def _calc_bot_cutoff() -> str:
    """Retorna ISO timestamp do limite de mensagem do bot (1h atras)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    return cutoff.isoformat()


async def _send_followup(lead: dict, message: str) -> bool:
    """Envia mensagem via BOT_SEND_URL. Retorna True se enviou com sucesso."""
    phone = lead["phone"]
    try:
        headers: dict = {}
        if settings.BOT_SEND_TOKEN:
            headers["Authorization"] = f"Bearer {settings.BOT_SEND_TOKEN}"

        payload = {
            "phone": phone,
            "message": message,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(settings.BOT_SEND_URL, json=payload, headers=headers)
            resp.raise_for_status()

        logger.info(
            "Follow-up enviado: phone=%s count=%s", phone, lead.get("followup_count", 0)
        )
        return True

    except Exception as exc:
        logger.error("Falha ao enviar follow-up para phone=%s: %s", phone, exc)
        return False


async def run_followup() -> None:
    """Busca leads elegiveis e envia follow-up."""
    supabase = _get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    bot_cutoff = _calc_bot_cutoff()

    # Buscar todos os leads elegiveis por stage e followup_count
    try:
        result = (
            supabase.table("contacts")
            .select(
                "phone, name, stage, nicho, observacoes_sdr, followup_count, "
                "last_lead_msg_at, last_bot_msg_at"
            )
            .in_("stage", ["qualificando", "interesse"])
            .lt("followup_count", 5)
            .not_.is_("phone", "null")
            .execute()
        )
        all_leads = result.data or []
    except Exception as exc:
        logger.error("Erro ao buscar leads para follow-up: %s", exc)
        return

    fu0_cutoff = _calc_fu0_cutoff()
    fu_cutoff = _calc_fu_cutoff()

    eligible: list[dict] = []
    for lead in all_leads:
        count = lead.get("followup_count") or 0
        last_lead = lead.get("last_lead_msg_at")
        last_bot = lead.get("last_bot_msg_at")

        # Verificar que o bot nao respondeu ha menos de 1h
        if last_bot and last_bot > bot_cutoff:
            continue

        # Delay do lead: FU0 usa 2h, FU1+ usa 24h
        delay_cutoff = fu0_cutoff if count == 0 else fu_cutoff
        if not last_lead:
            continue
        if last_lead > delay_cutoff:
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

        # Atualizar followup_count e last_bot_msg_at
        phone = lead["phone"]
        new_count = (lead.get("followup_count") or 0) + 1
        try:
            supabase.table("contacts").update(
                {"followup_count": new_count, "last_bot_msg_at": now_iso}
            ).eq("phone", phone).execute()
        except Exception as exc:
            logger.error("Falha ao atualizar followup_count para phone=%s: %s", phone, exc)

        sent_count += 1

    logger.info("Ciclo de follow-up concluido: %d mensagens enviadas", sent_count)


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
        "Scheduler iniciado: intervalo=%d min", settings.FOLLOWUP_INTERVAL_MINUTES
    )


def stop_scheduler() -> None:
    scheduler.shutdown()
    logger.info("Scheduler encerrado.")
