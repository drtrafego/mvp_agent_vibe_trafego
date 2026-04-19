import logging
from datetime import datetime, timezone
from supabase import create_client, Client
from config.settings import settings

logger = logging.getLogger(__name__)

VALID_STAGES = [
    "novo",
    "qualificando",
    "interesse",
    "agendado",
    "realizada",
    "sem_interesse",
    "perdido",
    "bloqueado",
]

_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


async def get_contact(phone: str) -> dict:
    """Retorna dados do contato. Cria registro basico se nao existir."""
    supabase = _get_supabase()
    result = supabase.table("contacts").select("*").eq("phone", phone).limit(1).execute()

    if result.data:
        return result.data[0]

    # Cria registro basico
    new_row = {"phone": phone, "stage": "novo", "followup_count": 0}
    upsert_result = supabase.table("contacts").upsert(new_row, on_conflict="phone").execute()
    if upsert_result.data:
        return upsert_result.data[0]

    return new_row


async def update_contact(phone: str, **kwargs) -> None:
    """Atualiza campos do contato."""
    if not kwargs:
        return
    supabase = _get_supabase()
    supabase.table("contacts").update(kwargs).eq("phone", phone).execute()


async def append_observation(phone: str, obs: str) -> None:
    """Adiciona linha a observacoes_sdr com timestamp. Limita a 20 linhas."""
    supabase = _get_supabase()
    result = supabase.table("contacts").select("observacoes_sdr").eq("phone", phone).limit(1).execute()

    existing = ""
    if result.data:
        existing = result.data[0].get("observacoes_sdr") or ""

    now = datetime.now(timezone.utc).strftime("%H:%M")
    new_line = f"[{now}] {obs}"

    lines = existing.splitlines() if existing else []
    lines.append(new_line)
    lines = lines[-20:]  # manter ultimas 20 linhas

    updated = "\n".join(lines)
    supabase.table("contacts").update({"observacoes_sdr": updated}).eq("phone", phone).execute()


async def advance_stage(phone: str, new_stage: str) -> None:
    """Muda o stage validando contra VALID_STAGES."""
    if new_stage not in VALID_STAGES:
        logger.warning("Stage invalido: %s — ignorado para phone %s", new_stage, phone)
        return
    supabase = _get_supabase()
    supabase.table("contacts").update({"stage": new_stage}).eq("phone", phone).execute()
    logger.info("Stage atualizado: phone=%s novo_stage=%s", phone, new_stage)


async def mark_bot_message(phone: str) -> None:
    """Atualiza last_bot_msg_at = now()."""
    supabase = _get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    supabase.table("contacts").update({"last_bot_msg_at": now_iso}).eq("phone", phone).execute()
