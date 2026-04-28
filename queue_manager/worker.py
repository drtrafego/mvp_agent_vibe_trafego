"""
queue_manager/worker.py

Worker assincrono que consome mensagens da fila Redis e aciona o agente.

Fluxo por mensagem:
  1. Tenta adquirir lock para o phone (ate 3 tentativas com backoff exponencial).
  2. Com lock: resolve texto (direto para texto, transcricao para audio).
  3. Chama agent.core.process_message e envia resposta via output.sender.
  4. Libera lock em bloco finally.
  5. Se todas as tentativas de lock falharem: envia para dead letter.

Loop principal:
  - Assina canal Redis 'new_messages' via Pub/Sub.
  - Ao receber phone: verifica fila e processa.
  - Polling a cada 5s como fallback (cobre reconexoes e mensagens perdidas).
"""

import asyncio
import logging

from queue_manager.redis_queue import (
    acquire_lock,
    dequeue_message,
    get_redis,
    move_to_dead_letter,
    release_lock,
)

logger = logging.getLogger(__name__)

_LOCK_RETRY_MAX = 3
_LOCK_RETRY_BACKOFF = [2, 4, 8]  # segundos por tentativa
_POLL_INTERVAL = 5  # segundos entre polls de fallback
_ACTIVE_QUEUES_KEY = "active_phones"  # set Redis com phones que tem fila pendente


async def _resolve_text(data: dict) -> str | None:
    """
    Extrai ou transcreve o texto da mensagem.

    Para audio: importa audio.pipeline lazily e transcreve.
    Para texto: retorna o campo 'text' diretamente.
    Retorna None se nao conseguir obter texto util.
    """
    msg_type = data.get("type", "text")

    if msg_type == "text":
        text = data.get("text", "").strip()
        return text if text else None

    if msg_type == "audio":
        media_id = data.get("media_id", "")
        if not media_id:
            logger.warning("Audio sem media_id — descartando")
            return None
        try:
            # Import lazy para evitar circular import e carregamento desnecessario
            from audio.pipeline import transcribe_audio  # type: ignore[import]

            text = await transcribe_audio(media_id)
            return text.strip() if text else None
        except ImportError:
            logger.error("audio.pipeline nao disponivel — audio descartado")
            return None
        except Exception as exc:
            logger.error("Erro ao transcrever audio %s: %s", media_id, exc)
            return None

    logger.debug("Tipo desconhecido em _resolve_text: %s", msg_type)
    return None


async def process_phone(phone: str, data: dict) -> None:
    """
    Processa uma mensagem de um phone com lock Redis.

    Tenta adquirir lock ate _LOCK_RETRY_MAX vezes com backoff exponencial.
    Em caso de falha total, move a mensagem para dead letter.
    """
    lock_acquired = False

    for attempt in range(_LOCK_RETRY_MAX):
        lock_acquired = await acquire_lock(phone)
        if lock_acquired:
            break

        wait = _LOCK_RETRY_BACKOFF[attempt]
        logger.debug(
            "Lock nao obtido para %s (tentativa %d/%d) — aguardando %ds",
            phone,
            attempt + 1,
            _LOCK_RETRY_MAX,
            wait,
        )
        await asyncio.sleep(wait)

    if not lock_acquired:
        reason = f"lock nao obtido apos {_LOCK_RETRY_MAX} tentativas"
        logger.error("Falha ao processar %s: %s", phone, reason)
        await move_to_dead_letter(phone, data, reason)
        return

    try:
        text = await _resolve_text(data)
        if text is None:
            logger.warning(
                "Mensagem sem texto utilizavel: phone=%s type=%s",
                phone,
                data.get("type"),
            )
            return

        # Import lazy para evitar circular import com agent.core
        from agent import core as agent_core  # type: ignore[import]
        from tools.crm import get_contact, update_contact, mark_bot_message
        from datetime import datetime, timezone

        # Garante contato existe e atualiza last_lead_msg_at
        contact = None
        try:
            contact = await get_contact(phone)
            await update_contact(phone, last_lead_msg_at=datetime.now(timezone.utc))
        except Exception as exc:
            logger.error("Falha ao atualizar last_lead_msg_at para %s: %s", phone, exc)

        # Se bot estiver desativado manualmente, salva a mensagem mas nao responde
        if contact and not contact.get("bot_active", True):
            logger.info("Bot inativo para %s — salvando mensagem sem responder", phone)
            try:
                from memory.chat import save_inbound_message
                await save_inbound_message(
                    phone, text,
                    message_type=data.get("type", "text"),
                    media_id=data.get("media_id") if data.get("type") == "audio" else None,
                )
            except Exception as exc:
                logger.error("Falha ao salvar inbound para %s: %s", phone, exc)
            return

        logger.info("Processando mensagem: phone=%s type=%s", phone, data.get("type"))
        response = await agent_core.process_message(phone, text)

        if response:
            from output.sender import send_message
            from memory.chat import save_messages

            logger.info("Resposta gerada: phone=%s text=%r", phone, response[:300])
            sent = await send_message(phone, response)
            if sent:
                await save_messages(
                    phone, text, response,
                    user_message_type=data.get("type", "text"),
                    user_media_id=data.get("media_id") if data.get("type") == "audio" else None,
                )
                try:
                    await mark_bot_message(phone)
                except Exception:
                    pass
            else:
                logger.error("Falha ao enviar resposta para %s", phone)
                try:
                    await save_messages(phone, text, response)
                except Exception:
                    pass
        else:
            logger.warning("Agente retornou resposta vazia para %s", phone)

    except Exception as exc:
        logger.exception("Erro inesperado ao processar mensagem de %s: %s", phone, exc)
        await move_to_dead_letter(phone, data, str(exc))
    finally:
        await release_lock(phone)


async def _process_queue(phone: str) -> None:
    """
    Drena a fila de um phone: processa mensagens ate a fila esvaziar.

    Cada mensagem e processada sequencialmente (respeita ordem FIFO).
    """
    while True:
        data = await dequeue_message(phone)
        if data is None:
            break
        await process_phone(phone, data)


async def _poll_all_queues() -> None:
    """
    Verifica todos os phones com filas pendentes via scan de chaves Redis.

    Usado como fallback quando notificacoes Pub/Sub sao perdidas.
    """
    r = await get_redis()
    cursor = 0
    phones_found: list[str] = []

    while True:
        cursor, keys = await r.scan(cursor, match="queue:*", count=100)
        for key in keys:
            # Exclui dead letter queues
            if key.startswith("queue:dead:"):
                continue
            phone = key.removeprefix("queue:")
            phones_found.append(phone)
        if cursor == 0:
            break

    for phone in phones_found:
        asyncio.create_task(_process_queue(phone))


async def run_worker() -> None:
    """
    Loop principal do worker.

    Assina o canal Redis 'new_messages' para ser notificado imediatamente
    quando uma mensagem e enfileirada. Tambem faz polling a cada 5s como
    fallback para cobrir reconexoes e mensagens que possam ter sido perdidas.
    """
    logger.info("Worker iniciado — aguardando mensagens")

    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("new_messages")

    # Executa poll inicial para processar mensagens que chegaram antes do worker subir
    await _poll_all_queues()

    last_poll = asyncio.get_event_loop().time()

    async for raw_message in pubsub.listen():
        if raw_message["type"] == "message":
            phone = raw_message.get("data", "")
            if phone:
                logger.debug("Notificacao recebida: phone=%s", phone)
                asyncio.create_task(_process_queue(phone))

        # Fallback: polling a cada _POLL_INTERVAL segundos
        now = asyncio.get_event_loop().time()
        if now - last_poll >= _POLL_INTERVAL:
            last_poll = now
            asyncio.create_task(_poll_all_queues())
