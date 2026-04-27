"""Debounce de mensagens por phone.

Quando um lead manda varias mensagens em sequencia (texto + audio + texto),
juntamos tudo em um buffer e processamos como UMA SO interacao apos N segundos
sem nova mensagem. Evita o bot responder 2-3x para o mesmo "turno" do lead.

Funcionamento:
1. Webhook chama add_message(phone, msg_data) -> entra no buffer
2. Agendamos task asyncio que espera DEBOUNCE_SECONDS
3. Se nova msg chegar antes, cancela a task anterior e agenda nova
4. Quando timer expirar sem nova msg, processa todas msgs combinadas

Limitacao: in-memory, funciona apenas com 1 replica do servico.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 12  # tempo de espera apos ultima msg antes de processar

_buffers: dict[str, list[dict]] = {}
_tasks: dict[str, asyncio.Task] = {}
_locks: dict[str, asyncio.Lock] = {}


def _get_lock(phone: str) -> asyncio.Lock:
    if phone not in _locks:
        _locks[phone] = asyncio.Lock()
    return _locks[phone]


async def add_message(phone: str, msg_data: dict) -> None:
    """Adiciona msg ao buffer e agenda (ou reagenda) processamento."""
    async with _get_lock(phone):
        _buffers.setdefault(phone, []).append(msg_data)
        # cancela task pendente
        old_task = _tasks.get(phone)
        if old_task and not old_task.done():
            old_task.cancel()
        # agenda nova task
        _tasks[phone] = asyncio.create_task(_debounced_process(phone))
        logger.info("[DEBOUNCE] msg adicionada ao buffer: phone=%s pending=%d", phone, len(_buffers[phone]))


async def _debounced_process(phone: str) -> None:
    """Espera DEBOUNCE_SECONDS sem nova msg, depois processa o buffer."""
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        # cancelado por nova msg - sai sem fazer nada
        return

    # extrai msgs do buffer
    async with _get_lock(phone):
        msgs = _buffers.pop(phone, [])
        _tasks.pop(phone, None)

    if not msgs:
        return

    logger.info("[DEBOUNCE] processando %d msg(s) para phone=%s", len(msgs), phone)

    # transcreve audios e combina textos
    parts: list[str] = []
    for m in msgs:
        if m.get("type") == "text":
            text = m.get("text", "").strip()
            if text:
                parts.append(text)
        elif m.get("type") == "audio":
            from audio.pipeline import transcribe_audio
            media_id = m.get("media_id", "")
            if media_id:
                transcript = await transcribe_audio(media_id)
                parts.append(transcript)

    if not parts:
        logger.warning("[DEBOUNCE] sem texto util para phone=%s", phone)
        return

    combined = "\n\n".join(parts)
    # usa msg_data combinado como text
    combined_data = {"type": "text", "text": combined, "msg_id": msgs[-1].get("msg_id", "")}

    # chama o worker existente
    from queue_manager.worker import process_phone
    await process_phone(phone, combined_data)
