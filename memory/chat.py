"""
memory/chat.py

Historico de conversa com cache Redis + persistencia Supabase.

Estrategia:
- Cache hit (Redis): retorna imediatamente sem tocar no banco.
- Cache miss: busca Supabase, popula Redis com TTL 30min, retorna.
- save_messages: grava par user/assistant no Supabase, depois atualiza Redis.
"""

import json
import logging
from typing import Optional

import redis.asyncio as aioredis
from supabase import create_client, Client

from config.settings import settings

logger = logging.getLogger(__name__)

REDIS_TTL = 30 * 60  # 30 minutos em segundos
HISTORY_LIMIT = 50
CACHE_KEY_PREFIX = "history:"

_redis_client: Optional[aioredis.Redis] = None
_supabase_client: Optional[Client] = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


def _get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase_client


def _cache_key(phone: str) -> str:
    return f"{CACHE_KEY_PREFIX}{phone}"


async def get_history(phone: str) -> list[dict]:
    """
    Retorna ultimas 50 mensagens em ordem cronologica [{role, content}].
    Tenta Redis primeiro; se miss, busca Supabase e popula cache.
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

    # Cache miss: busca Supabase
    messages = await _fetch_from_supabase(phone)

    # Popula cache
    try:
        await redis.set(key, json.dumps(messages), ex=REDIS_TTL)
    except Exception as exc:
        logger.warning("redis set falhou para %s: %s", phone, exc)

    return messages


async def _fetch_from_supabase(phone: str) -> list[dict]:
    """Busca historico do Supabase. Retorna lista em ordem cronologica."""
    supabase = _get_supabase()
    try:
        response = (
            supabase.table("chat_sessions")
            .select("role, content")
            .eq("phone", phone)
            .order("created_at", desc=True)
            .limit(HISTORY_LIMIT)
            .execute()
        )
        rows = response.data or []
        # A query retorna DESC; reverter para ordem cronologica
        rows.reverse()
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    except Exception as exc:
        logger.error("supabase fetch falhou para %s: %s", phone, exc)
        return []


async def save_messages(phone: str, user_content: str, assistant_content: str) -> None:
    """
    Salva mensagem do user e resposta do assistant no Supabase.
    Apos gravacao, invalida e reconstroi o cache Redis.
    """
    supabase = _get_supabase()

    records = [
        {"phone": phone, "role": "user", "content": user_content},
        {"phone": phone, "role": "assistant", "content": assistant_content},
    ]

    try:
        supabase.table("chat_sessions").insert(records).execute()
        logger.debug("supabase: %d mensagens gravadas para %s", len(records), phone)
    except Exception as exc:
        logger.error("supabase insert falhou para %s: %s", phone, exc)
        # Continua para atualizar cache mesmo se Supabase falhar momentaneamente

    # Reconstroi cache a partir do Supabase para garantir consistencia
    messages = await _fetch_from_supabase(phone)
    redis = _get_redis()
    key = _cache_key(phone)
    try:
        await redis.set(key, json.dumps(messages), ex=REDIS_TTL)
        logger.debug("redis cache atualizado para %s (%d msgs)", phone, len(messages))
    except Exception as exc:
        logger.warning("redis set apos save falhou para %s: %s", phone, exc)


async def create_table_if_not_exists() -> None:
    """
    Cria tabela chat_sessions e index se nao existirem.
    Chamado no startup da aplicacao.
    """
    sql = """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
            phone text NOT NULL,
            role text NOT NULL CHECK (role IN ('user', 'assistant')),
            content text NOT NULL,
            created_at timestamptz DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_phone_created
            ON chat_sessions(phone, created_at DESC);
    """
    supabase = _get_supabase()
    try:
        # Supabase SDK nao expoe DDL direto; usar rpc ou postgrest com
        # service role. Para DDL, a forma mais simples e via rpc exec_sql
        # ou simplesmente tentar e logar. Aqui usamos o client REST com
        # postgrest (apenas SELECT/INSERT/UPDATE). Para criacao real de
        # tabela, rodar via Supabase dashboard ou migration separada.
        # Esta funcao serve como placeholder e loga orientacao para o ops.
        logger.info(
            "create_table_if_not_exists: execute o SQL abaixo no Supabase SQL Editor "
            "se a tabela chat_sessions ainda nao existir:\n%s",
            sql.strip(),
        )
        # Testa conectividade fazendo um select seguro
        supabase.table("chat_sessions").select("id").limit(1).execute()
        logger.info("chat_sessions: tabela acessivel.")
    except Exception as exc:
        logger.error(
            "chat_sessions nao acessivel. Crie a tabela manualmente. Erro: %s", exc
        )
