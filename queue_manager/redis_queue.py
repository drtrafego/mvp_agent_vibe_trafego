"""
queue_manager/redis_queue.py

Camada de acesso ao Redis para fila de mensagens por phone.

Estrutura de chaves:
  queue:{phone}       — lista FIFO de mensagens pendentes (LPUSH/RPOP)
  lock:{phone}        — lock de processamento (SET NX EX)
  queue:dead:{phone}  — mensagens que falharam apos todas as tentativas
"""

import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from config.settings import settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """
    Retorna cliente Redis singleton, criando na primeira chamada.

    Suporta automaticamente URLs Upstash (rediss://default:TOKEN@endpoint:6380)
    via redis.asyncio.from_url — o prefixo 'rediss://' habilita SSL/TLS.
    Para dev local use redis://host:port; para Vercel use rediss:// (Upstash).
    """
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def enqueue_message(phone: str, data: dict) -> None:
    """
    Enfileira mensagem para o phone.

    Usa LPUSH em queue:{phone} e publica notificacao no canal 'new_messages'
    para acordar o worker imediatamente.
    """
    r = await get_redis()
    await r.lpush(f"queue:{phone}", json.dumps(data))
    await r.publish("new_messages", phone)
    logger.debug("Mensagem enfileirada: phone=%s type=%s", phone, data.get("type"))


async def dequeue_message(phone: str) -> dict | None:
    """
    Remove e retorna o proximo item da fila do phone (RPOP).

    Retorna None se a fila estiver vazia.
    """
    r = await get_redis()
    raw = await r.rpop(f"queue:{phone}")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Item corrompido na fila de %s: %s", phone, raw[:100])
        return None


async def acquire_lock(phone: str) -> bool:
    """
    Tenta adquirir lock exclusivo para processar mensagens do phone.

    Usa SET NX EX para garantir atomicidade e evitar lock eterno.
    Retorna True se o lock foi obtido, False se ja estava travado.
    """
    r = await get_redis()
    result = await r.set(
        f"lock:{phone}",
        "1",
        ex=settings.REDIS_LOCK_TTL,
        nx=True,
    )
    return result is True


async def release_lock(phone: str) -> None:
    """Libera o lock do phone."""
    r = await get_redis()
    await r.delete(f"lock:{phone}")
    logger.debug("Lock liberado: phone=%s", phone)


async def move_to_dead_letter(phone: str, data: dict, reason: str) -> None:
    """
    Move mensagem para a dead letter queue do phone.

    Adiciona metadados de falha (_dead_reason e _dead_at) antes de persistir.
    """
    r = await get_redis()
    dead_data = {
        **data,
        "_dead_reason": reason,
        "_dead_at": datetime.now(timezone.utc).isoformat(),
    }
    await r.lpush(f"queue:dead:{phone}", json.dumps(dead_data))
    logger.warning(
        "Mensagem movida para dead letter: phone=%s reason=%s", phone, reason
    )
