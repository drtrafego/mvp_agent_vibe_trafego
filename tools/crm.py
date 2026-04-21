import logging
from datetime import datetime, timezone
from typing import Optional

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

_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5)
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
        INSERT INTO agente_vibe.contacts (phone, name, stage, followup_count)
        VALUES ($1, $2, 'novo', 0)
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
    """Muda o stage validando contra VALID_STAGES."""
    if new_stage not in VALID_STAGES:
        logger.warning("Stage invalido: %s ignorado para phone %s", new_stage, phone)
        return
    pool = await _get_pool()
    await pool.execute(
        "UPDATE agente_vibe.contacts SET stage = $2, updated_at = now() WHERE phone = $1",
        phone, new_stage,
    )
    logger.info("Stage atualizado: phone=%s novo_stage=%s", phone, new_stage)


async def mark_bot_message(phone: str) -> None:
    """Atualiza last_bot_msg_at = now()."""
    pool = await _get_pool()
    await pool.execute(
        "UPDATE agente_vibe.contacts SET last_bot_msg_at = now(), updated_at = now() WHERE phone = $1",
        phone,
    )
