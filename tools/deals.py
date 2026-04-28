"""
tools/deals.py

Automacao de deals baseada em mudanca de stage do bot.

Fluxo:
  agendado              -> cria deal em "Contato Feito" com probabilidade calculada
  realizada             -> move deal para "Negociacao" e sobe probabilidade +20
  sem_interesse/perdido/bloqueado -> move deal para "Perdido"
"""

import logging

import asyncpg

from config.settings import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_stage_ids: dict[str, str] = {}

STAGE_PIPELINE_MAP = {
    "agendado": "Contato Feito",
    "realizada": "Negociacao",
    "sem_interesse": "Perdido",
    "perdido": "Perdido",
    "bloqueado": "Perdido",
}


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


async def _get_stage_ids() -> dict[str, str]:
    global _stage_ids
    if _stage_ids:
        return _stage_ids
    pool = await _get_pool()
    rows = await pool.fetch("SELECT id, name FROM agente_trafego.pipeline_stages")
    _stage_ids = {r["name"]: r["id"] for r in rows}
    return _stage_ids


def calculate_probability(contact: dict) -> int:
    """Calcula probabilidade de fechamento (30-90%) com base no perfil do lead."""
    score = 30

    temp = contact.get("temperature", "cold")
    if temp == "hot":
        score += 30
    elif temp == "warm":
        score += 15

    if contact.get("nicho"):
        score += 10

    followup_count = contact.get("followup_count") or 0
    if followup_count == 0:
        score += 15  # chegou organicamente sem precisar de insistencia
    elif followup_count <= 2:
        score += 5

    obs = contact.get("observacoes_sdr") or ""
    if len(obs) > 200:
        score += 5  # lead muito conversador, alto engajamento

    return min(score, 90)


async def auto_deal_on_stage_change(phone: str, new_stage: str) -> None:
    """Dispara automacao de deal quando o stage do bot muda."""
    if new_stage not in STAGE_PIPELINE_MAP:
        return

    try:
        pool = await _get_pool()
        stage_ids = await _get_stage_ids()

        pipeline_stage_name = STAGE_PIPELINE_MAP[new_stage]
        pipeline_stage_id = stage_ids.get(pipeline_stage_name)
        if not pipeline_stage_id:
            logger.warning("Stage do pipeline nao encontrado: %s", pipeline_stage_name)
            return

        contact = await pool.fetchrow(
            """
            SELECT id, name, nicho, temperature, followup_count, observacoes_sdr
            FROM agente_trafego.contacts
            WHERE phone = $1
            """,
            phone,
        )
        if not contact:
            return

        contact_dict = dict(contact)
        contact_id = contact_dict["id"]

        existing = await pool.fetchrow(
            "SELECT id FROM agente_trafego.deals WHERE contact_id = $1 LIMIT 1",
            contact_id,
        )

        if new_stage == "agendado":
            if existing:
                await pool.execute(
                    "UPDATE agente_trafego.deals SET stage_id = $2, updated_at = now() WHERE id = $1",
                    existing["id"], pipeline_stage_id,
                )
                logger.info("Deal atualizado -> Contato Feito: contact_id=%s", contact_id)
            else:
                prob = calculate_probability(contact_dict)
                nicho = contact_dict.get("nicho") or ""
                name = (contact_dict.get("name") or phone).split()[0]
                title = f"Reuniao — {nicho}" if nicho else f"Reuniao — {name}"

                await pool.execute(
                    """
                    INSERT INTO agente_trafego.deals
                      (id, title, value, stage_id, contact_id, probability)
                    VALUES
                      (gen_random_uuid()::text, $1, 0, $2, $3, $4)
                    """,
                    title, pipeline_stage_id, contact_id, prob,
                )
                logger.info(
                    "Deal criado automaticamente: contact_id=%s prob=%d%%",
                    contact_id, prob,
                )

        elif new_stage == "realizada":
            if existing:
                await pool.execute(
                    """
                    UPDATE agente_trafego.deals
                    SET stage_id = $2,
                        probability = LEAST(probability + 20, 95),
                        updated_at = now()
                    WHERE id = $1
                    """,
                    existing["id"], pipeline_stage_id,
                )
                logger.info("Deal -> Negociacao apos call realizada: contact_id=%s", contact_id)

        elif new_stage in ("sem_interesse", "perdido", "bloqueado"):
            if existing:
                await pool.execute(
                    "UPDATE agente_trafego.deals SET stage_id = $2, updated_at = now() WHERE id = $1",
                    existing["id"], pipeline_stage_id,
                )
                logger.info(
                    "Deal -> Perdido: contact_id=%s bot_stage=%s",
                    contact_id, new_stage,
                )

    except Exception as exc:
        logger.error(
            "auto_deal_on_stage_change falhou: phone=%s stage=%s: %s",
            phone, new_stage, exc,
        )
