"""
webhook/router.py

FastAPI router para receber eventos da Meta Cloud API (WhatsApp).

GET  /webhook  — verificacao do webhook (hub challenge)
POST /webhook  — recepcao de mensagens e eventos

Nota Vercel/serverless:
  - O processamento de mensagens ocorre via BackgroundTasks do FastAPI,
    sem depender de worker Redis Pub/Sub (incompativel com serverless).
  - O lock Redis dentro de process_phone continua funcionando normalmente
    para evitar processamento duplicado de mensagens concorrentes.
"""

import hashlib
import hmac
import json
import logging
import re

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

_DIGITS_RE = re.compile(r"\D")


async def _process_and_respond(phone: str, data: dict) -> None:
    """
    Processa uma mensagem e envia resposta via worker existente.

    Chamado via BackgroundTasks — o lock Redis dentro de process_phone
    garante que mensagens concorrentes do mesmo phone nao se sobreponham.
    """
    from queue_manager.worker import process_phone
    await process_phone(phone, data)


def _normalize_phone(raw: str) -> str:
    """Remove tudo que nao for digito e strips espacos."""
    return _DIGITS_RE.sub("", raw.strip())


def _extract_messages(payload: dict) -> list[dict]:
    """
    Extrai a lista de mensagens do payload Meta Cloud API.

    Retorna lista vazia se nao houver mensagens (ex: eventos de status).
    """
    try:
        changes = payload["entry"][0]["changes"]
        value = changes[0]["value"]
        return value.get("messages", [])
    except (KeyError, IndexError, TypeError):
        return []


def _verify_signature(secret: str, body: bytes, signature_header: str) -> bool:
    """Valida HMAC-SHA256 do payload. Retorna True se valido."""
    expected_prefix = "sha256="
    if not signature_header.startswith(expected_prefix):
        return False
    received_hex = signature_header[len(expected_prefix):]
    computed = hmac.new(
        secret.encode(),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, received_hex)


@router.get("/webhook", response_class=PlainTextResponse)
async def webhook_verify(
    request: Request,
) -> str:
    """
    Endpoint de verificacao do webhook Meta.

    Meta envia GET com hub.mode=subscribe, hub.verify_token e hub.challenge.
    Se o token bater, retorna hub.challenge como texto puro (200).
    Caso contrario, retorna 403.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    verify_token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    if mode == "subscribe" and verify_token == settings.META_VERIFY_TOKEN:
        logger.info("Verificacao de webhook aceita")
        return challenge

    logger.warning(
        "Verificacao de webhook rejeitada: mode=%s token_match=%s",
        mode,
        verify_token == settings.META_VERIFY_TOKEN,
    )
    raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/webhook")
async def webhook_receive(request: Request, background_tasks: BackgroundTasks) -> PlainTextResponse:
    """
    Endpoint de recepcao de eventos da Meta Cloud API.

    Retorna "ok" imediatamente (critico: Meta reencaminha se nao receber
    200 em 5s). O processamento ocorre em background via BackgroundTasks.

    Valida assinatura HMAC-SHA256 se META_APP_SECRET estiver configurado.
    Ignora eventos de status de entrega (sem campo 'messages').
    Ignora mensagens enviadas pelo proprio bot.
    Processa mensagens de texto e audio; ignora demais tipos.
    """
    body = await request.body()

    # Validacao de assinatura (opcional, apenas se secret estiver configurado)
    if settings.META_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_signature(settings.META_APP_SECRET, body, signature):
            logger.warning("Assinatura HMAC invalida — requisicao rejeitada")
            raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Payload invalido: nao e JSON valido")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    messages = _extract_messages(payload)

    if not messages:
        # Evento de status de entrega ou outro sem mensagens — ignorar silenciosamente
        return PlainTextResponse("ok", status_code=200)

    for msg in messages:
        phone_raw = msg.get("from", "")
        msg_id = msg.get("id", "")
        msg_type = msg.get("type", "")

        if not phone_raw:
            continue

        phone = _normalize_phone(phone_raw)

        # Ignora mensagens enviadas pelo proprio bot
        if phone == _normalize_phone(settings.META_PHONE_NUMBER_ID):
            logger.debug("Mensagem ignorada (enviada pelo bot): msg_id=%s", msg_id)
            continue

        if msg_type == "text":
            body_text = msg.get("text", {}).get("body", "").strip()
            if not body_text:
                continue
            msg_data = {
                "type": "text",
                "text": body_text,
                "msg_id": msg_id,
            }
            background_tasks.add_task(_process_and_respond, phone, msg_data)
            logger.info("Mensagem de texto agendada para processamento: phone=%s msg_id=%s", phone, msg_id)

        elif msg_type == "audio":
            media_id = msg.get("audio", {}).get("id", "")
            if not media_id:
                logger.warning("Audio sem media_id: phone=%s msg_id=%s", phone, msg_id)
                continue
            msg_data = {
                "type": "audio",
                "media_id": media_id,
                "msg_id": msg_id,
            }
            background_tasks.add_task(_process_and_respond, phone, msg_data)
            logger.info("Audio agendado para processamento: phone=%s media_id=%s", phone, media_id)

        else:
            logger.debug(
                "Tipo de mensagem ignorado: type=%s phone=%s msg_id=%s",
                msg_type,
                phone,
                msg_id,
            )

    return PlainTextResponse("ok", status_code=200)
