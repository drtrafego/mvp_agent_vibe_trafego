"""
memory/chat.py

Historico de conversa com cache Redis + persistencia PostgreSQL direta.

Estrategia:
- Cache hit (Redis): retorna imediatamente sem tocar no banco.
- Cache miss: busca Postgres, popula Redis com TTL 30min, retorna.
- save_messages: grava par user/assistant no Postgres, depois atualiza Redis.
"""

import json
import logging
from typing import Optional

import asyncpg
import redis.asyncio as aioredis

from config.settings import settings

logger = logging.getLogger(__name__)

REDIS_TTL = 30 * 60  # 30 minutos em segundos
HISTORY_LIMIT = 50
CACHE_KEY_PREFIX = "history:"

_redis_client: Optional[aioredis.Redis] = None
_pool: Optional[asyncpg.Pool] = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


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


def _cache_key(phone: str) -> str:
    return f"{CACHE_KEY_PREFIX}{phone}"


async def get_history(phone: str) -> list[dict]:
    """
    Retorna ultimas 50 mensagens em ordem cronologica [{role, content}].
    Tenta Redis primeiro; se miss, busca Postgres e popula cache.
    """
    redis = _get_redis()
    key = _cache_key(phone)

    try:
        cached = await redis.get(key)
        if cached:
            logger.debug("cache hit: history:%s", phone)
            return json.loads(cached)
    except Exception as exc:
        logger.warning("redis get falhou para %s: %s", phone, exc)

    messages = await _fetch_from_db(phone)

    try:
        await redis.set(key, json.dumps(messages), ex=REDIS_TTL)
    except Exception as exc:
        logger.warning("redis set falhou para %s: %s", phone, exc)

    return messages


async def _fetch_from_db(phone: str) -> list[dict]:
    """Busca historico do Postgres. Retorna lista em ordem cronologica."""
    pool = await _get_pool()
    try:
        rows = await pool.fetch(
            """
            SELECT role, content FROM agente_vibe.chat_sessions
            WHERE phone = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            phone, HISTORY_LIMIT,
        )
        result = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
        return result
    except Exception as exc:
        logger.error("postgres fetch falhou para %s: %s", phone, exc)
        return []


async def save_messages(
    phone: str,
    user_content: str,
    assistant_content: str,
    user_message_type: str = "text",
    user_media_id: str | None = None,
) -> None:
    """
    Salva mensagem do user e resposta do assistant no Postgres.
    Apos gravacao, invalida e reconstroi o cache Redis.
    """
    pool = await _get_pool()
    try:
        await pool.executemany(
            "INSERT INTO agente_vibe.chat_sessions (phone, role, content, message_type, media_id) VALUES ($1, $2, $3, $4, $5)",
            [
                (phone, "user", user_content, user_message_type, user_media_id),
                (phone, "assistant", assistant_content, "text", None),
            ],
        )
        logger.debug("postgres: 2 mensagens gravadas para %s", phone)
    except Exception as exc:
        logger.error("postgres insert falhou para %s: %s", phone, exc)

    messages = await _fetch_from_db(phone)
    redis = _get_redis()
    key = _cache_key(phone)
    try:
        await redis.set(key, json.dumps(messages), ex=REDIS_TTL)
        logger.debug("redis cache atualizado para %s (%d msgs)", phone, len(messages))
    except Exception as exc:
        logger.warning("redis set apos save falhou para %s: %s", phone, exc)


async def save_inbound_message(
    phone: str,
    user_content: str,
    message_type: str = "text",
    media_id: str | None = None,
) -> None:
    """Salva apenas a mensagem do lead (sem resposta do bot). Usado quando bot esta inativo."""
    pool = await _get_pool()
    try:
        await pool.execute(
            "INSERT INTO agente_vibe.chat_sessions (phone, role, content, message_type, media_id) VALUES ($1, $2, $3, $4, $5)",
            phone, "user", user_content, message_type, media_id,
        )
        logger.debug("postgres: mensagem inbound gravada para %s (bot inativo)", phone)
    except Exception as exc:
        logger.error("postgres insert inbound falhou para %s: %s", phone, exc)

    messages = await _fetch_from_db(phone)
    redis = _get_redis()
    key = _cache_key(phone)
    try:
        await redis.set(key, json.dumps(messages), ex=REDIS_TTL)
    except Exception as exc:
        logger.warning("redis set apos inbound falhou para %s: %s", phone, exc)


async def create_table_if_not_exists() -> None:
    """Verifica conectividade com a tabela chat_sessions no startup."""
    pool = await _get_pool()
    try:
        await pool.fetchval("SELECT 1 FROM agente_vibe.chat_sessions LIMIT 1")
        logger.info("chat_sessions: tabela acessivel.")
    except Exception as exc:
        logger.error("chat_sessions nao acessivel: %s", exc)
