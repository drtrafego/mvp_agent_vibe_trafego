import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, parse_qs

import asyncpg

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

VALID_TEMPERATURES = ["cold", "warm", "hot"]

_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=1,
            max_size=5,
            statement_cache_size=0,
        )
    return _pool


async def get_contact(phone: str) -> dict:
    """Retorna dados do contato. Cria registro basico se nao existir."""
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM agente_vibe.contacts WHERE phone = $1 LIMIT 1", phone
    )
    if row:
        return dict(row)

    result = await pool.fetchrow(
        """
        INSERT INTO agente_vibe.contacts (id, phone, name, stage, followup_count)
        VALUES (gen_random_uuid()::text, $1, $2, 'novo', 0)
        ON CONFLICT (phone) WHERE phone IS NOT NULL DO UPDATE SET phone = EXCLUDED.phone
        RETURNING *
        """,
        phone, phone,
    )
    return dict(result) if result else {"phone": phone, "stage": "novo", "followup_count": 0}


async def update_contact(phone: str, **kwargs) -> None:
    """Atualiza campos do contato."""
    if not kwargs:
        return
    pool = await _get_pool()
    sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
    values = list(kwargs.values())
    await pool.execute(
        f"UPDATE agente_vibe.contacts SET {sets}, updated_at = now() WHERE phone = $1",
        phone, *values,
    )


async def append_observation(phone: str, obs: str) -> None:
    """Adiciona linha a observacoes_sdr com timestamp. Limita a 20 linhas."""
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT observacoes_sdr FROM agente_vibe.contacts WHERE phone = $1", phone
    )
    existing = (row["observacoes_sdr"] or "") if row else ""

    now = datetime.now(timezone.utc).strftime("%H:%M")
    lines = existing.splitlines() if existing else []
    lines.append(f"[{now}] {obs}")
    lines = lines[-20:]

    await pool.execute(
        "UPDATE agente_vibe.contacts SET observacoes_sdr = $2, updated_at = now() WHERE phone = $1",
        phone, "\n".join(lines),
    )


async def advance_stage(phone: str, new_stage: str) -> None:
    """Muda o stage validando contra VALID_STAGES. Dispara automacao de deal em background."""
    if new_stage not in VALID_STAGES:
        logger.warning("Stage invalido: %s ignorado para phone %s", new_stage, phone)
        return
    pool = await _get_pool()
    await pool.execute(
        "UPDATE agente_vibe.contacts SET stage = $2, updated_at = now() WHERE phone = $1",
        phone, new_stage,
    )
    logger.info("Stage atualizado: phone=%s novo_stage=%s", phone, new_stage)
    asyncio.create_task(_trigger_deal_automation(phone, new_stage))


async def _trigger_deal_automation(phone: str, new_stage: str) -> None:
    try:
        from tools.deals import auto_deal_on_stage_change
        await auto_deal_on_stage_change(phone, new_stage)
    except Exception as exc:
        logger.warning("deal automation falhou: phone=%s stage=%s: %s", phone, new_stage, exc)


async def mark_bot_message(phone: str) -> None:
    """Atualiza last_bot_msg_at = now()."""
    pool = await _get_pool()
    await pool.execute(
        "UPDATE agente_vibe.contacts SET last_bot_msg_at = now(), updated_at = now() WHERE phone = $1",
        phone,
    )


async def save_origin(phone: str, referral: dict) -> None:
    """Salva dados de origem do lead a partir do objeto referral da Meta. Nao sobrescreve campos ja preenchidos."""
    if not referral:
        return

    updates: dict = {}

    ad_id = referral.get("source_id", "")
    if ad_id:
        updates["ad_id"] = ad_id

    placement = referral.get("source_type", "")
    if placement:
        updates["placement"] = placement

    source_url = referral.get("source_url", "")
    if source_url:
        try:
            parsed = urlparse(source_url)
            params = parse_qs(parsed.query)
            for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
                val = params.get(key, [None])[0]
                if val:
                    updates[key] = val
        except Exception:
            pass

    if not updates:
        return

    pool = await _get_pool()
    # COALESCE preserva valor existente — nao sobrescreve origem ja registrada
    sets = ", ".join(f"{k} = COALESCE({k}, ${i+2})" for i, k in enumerate(updates))
    values = list(updates.values())
    await pool.execute(
        f"UPDATE agente_vibe.contacts SET {sets}, updated_at = now() WHERE phone = $1",
        phone, *values,
    )
    logger.info("Origem salva: phone=%s updates=%s", phone, list(updates.keys()))

    if ad_id:
        asyncio.create_task(_enrich_from_meta(phone, ad_id))


async def _enrich_from_meta(phone: str, ad_id: str) -> None:
    """Busca ad_name, campaign_name e adset_name via Meta Graph API e atualiza o contato."""
    import httpx
    from config.settings import settings

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://graph.facebook.com/v20.0/{ad_id}",
                params={"fields": "id,name,campaign_id,adset_id", "access_token": settings.META_ACCESS_TOKEN},
            )
            if resp.status_code != 200:
                logger.warning("Meta API falhou para ad_id=%s: %s", ad_id, resp.status_code)
                return
            data = resp.json()

        updates: dict = {}
        if data.get("name"):
            updates["ad_name"] = data["name"]

        campaign_id = data.get("campaign_id")
        adset_id = data.get("adset_id")
        if campaign_id:
            updates["campaign_id"] = campaign_id
        if adset_id:
            updates["adset_id"] = adset_id

        async with httpx.AsyncClient(timeout=10) as client:
            if campaign_id:
                r = await client.get(
                    f"https://graph.facebook.com/v20.0/{campaign_id}",
                    params={"fields": "name", "access_token": settings.META_ACCESS_TOKEN},
                )
                if r.status_code == 200:
                    updates["campaign_name"] = r.json().get("name")

            if adset_id:
                r = await client.get(
                    f"https://graph.facebook.com/v20.0/{adset_id}",
                    params={"fields": "name", "access_token": settings.META_ACCESS_TOKEN},
                )
                if r.status_code == 200:
                    updates["adset_name"] = r.json().get("name")

        updates = {k: v for k, v in updates.items() if v}
        if updates:
            pool = await _get_pool()
            sets = ", ".join(f"{k} = COALESCE({k}, ${i+2})" for i, k in enumerate(updates))
            values = list(updates.values())
            await pool.execute(
                f"UPDATE agente_vibe.contacts SET {sets}, updated_at = now() WHERE phone = $1",
                phone, *values,
            )
            logger.info("Meta enrich ok: phone=%s updates=%s", phone, list(updates.keys()))
    except Exception as exc:
        logger.warning("Meta enrich falhou: phone=%s ad_id=%s: %s", phone, ad_id, exc)


async def update_lead_profile(
    phone: str,
    nicho: str | None = None,
    stage: str | None = None,
    temperature: str | None = None,
) -> None:
    """Atualiza perfil do lead. Stages só avançam (não regridem se ja em estado superior)."""
    updates: dict = {}
    if nicho:
        updates["nicho"] = nicho
    if stage and stage in VALID_STAGES:
        updates["stage"] = stage
    if temperature and temperature in VALID_TEMPERATURES:
        updates["temperature"] = temperature
    if not updates:
        return

    pool = await _get_pool()
    sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
    values = list(updates.values())
    await pool.execute(
        f"UPDATE agente_vibe.contacts SET {sets}, updated_at = now() WHERE phone = $1",
        phone, *values,
    )
    logger.info("Lead profile atualizado: phone=%s updates=%s", phone, updates)
