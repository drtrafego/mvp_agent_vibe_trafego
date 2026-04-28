"""
output/sender.py

Envia respostas do agente diretamente via Meta Cloud API (WhatsApp).

Comportamento:
- Mensagens <= 1500 chars: enviadas em um unico POST.
- Mensagens > 1500 chars: divididas por paragrafos duplos, cada parte enviada
  com delay de 1s entre si.
- Retry 3x com backoff 2s em caso de status != 200.
- Falha total (todas tentativas esgotadas): loga e retorna False sem lancar excecao.
"""

import asyncio
import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

MAX_LEN = 1500
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 2  # segundos entre tentativas
CHUNK_DELAY = 1.0  # segundos entre chunks de mensagem longa
REQUEST_TIMEOUT = 30.0  # segundos


def split_message(text: str, max_len: int = MAX_LEN) -> list[str]:
    """
    Divide texto em partes de ate max_len caracteres.

    Algoritmo:
    1. Divide por paragrafos duplos (\\n\\n).
    2. Agrupa paragrafos consecutivos enquanto a parte atual nao exceder max_len.
    3. Se um paragrafo individual exceder max_len, divide por sentencas ('. ' ou '\\n').
    4. Se uma sentenca individual ainda exceder max_len, forca corte em max_len
       sem cortar palavras (faz split por espaco e monta ate o limite).

    Retorna lista de strings, cada uma com <= max_len caracteres.
    """
    if len(text) <= max_len:
        return [text]

    paragraphs = text.split("\n\n")
    parts: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Paragrafo cabe inteiro no slot atual
        needed = len(para) + (2 if current else 0)  # +2 para o \n\n separador
        if current_len + needed <= max_len:
            current.append(para)
            current_len += needed
        else:
            # Descarrega current antes de processar o novo paragrafo
            if current:
                parts.append("\n\n".join(current))
                current = []
                current_len = 0

            # Paragrafo cabe sozinho numa parte nova
            if len(para) <= max_len:
                current.append(para)
                current_len = len(para)
            else:
                # Paragrafo e grande: divide por sentencas
                parts.extend(_split_by_sentences(para, max_len))

    if current:
        parts.append("\n\n".join(current))

    return parts


def _split_by_sentences(text: str, max_len: int) -> list[str]:
    """
    Divide um bloco de texto por sentencas ('. ' ou newline simples).
    Se uma sentenca ainda exceder max_len, forca corte por palavras.
    """
    import re

    # Divide preservando o delimitador ao final de cada sentenca
    sentences = re.split(r"(?<=\.)\s+|\n", text)
    parts: list[str] = []
    current_sentences: list[str] = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        needed = len(sentence) + (1 if current_sentences else 0)  # espaco separador

        if current_len + needed <= max_len:
            current_sentences.append(sentence)
            current_len += needed
        else:
            if current_sentences:
                parts.append(" ".join(current_sentences))
                current_sentences = []
                current_len = 0

            if len(sentence) <= max_len:
                current_sentences.append(sentence)
                current_len = len(sentence)
            else:
                # Sentenca enorme: corte forcado por palavras
                parts.extend(_split_by_words(sentence, max_len))

    if current_sentences:
        parts.append(" ".join(current_sentences))

    return parts


def _split_by_words(text: str, max_len: int) -> list[str]:
    """
    Ultimo recurso: divide por palavras sem cortar ao meio.
    """
    words = text.split()
    parts: list[str] = []
    current_words: list[str] = []
    current_len = 0

    for word in words:
        needed = len(word) + (1 if current_words else 0)
        if current_len + needed <= max_len:
            current_words.append(word)
            current_len += needed
        else:
            if current_words:
                parts.append(" ".join(current_words))
            current_words = [word]
            current_len = len(word)

    if current_words:
        parts.append(" ".join(current_words))

    return parts


META_SEND_URL = "https://graph.facebook.com/v21.0/{phone_number_id}/messages"


async def _post_single(client: httpx.AsyncClient, phone: str, text: str) -> bool:
    """
    Envia um unico chunk direto via Meta Cloud API com retry 3x e backoff 2s.
    Retorna True se enviou com sucesso, False se todas as tentativas falharam.
    """
    url = META_SEND_URL.format(phone_number_id=settings.META_PHONE_NUMBER_ID)
    headers = {
        "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {"body": text},
    }

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                logger.info(
                    "meta-send ok: phone=%s tentativa=%d text=%r",
                    phone,
                    attempt,
                    text[:200],
                )
                return True

            logger.warning(
                "meta-send status inesperado: phone=%s tentativa=%d status=%d body=%s",
                phone,
                attempt,
                response.status_code,
                response.text[:200],
            )
        except httpx.TimeoutException:
            logger.warning("meta-send timeout: phone=%s tentativa=%d", phone, attempt)
        except httpx.RequestError as exc:
            logger.warning(
                "meta-send erro de conexao: phone=%s tentativa=%d erro=%s",
                phone,
                attempt,
                exc,
            )

        if attempt < RETRY_ATTEMPTS:
            await asyncio.sleep(RETRY_BACKOFF)

    logger.error(
        "meta-send falhou apos %d tentativas: phone=%s", RETRY_ATTEMPTS, phone
    )
    return False


async def send_message(phone: str, text: str) -> bool:
    """
    Envia mensagem ao lead via bot-send.

    Se o texto exceder MAX_LEN chars, divide em partes e envia sequencialmente
    com delay de 1s entre cada chunk.

    Retorna True se todos os chunks foram enviados com sucesso, False caso contrario.
    """
    chunks = split_message(text, max_len=MAX_LEN)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        all_ok = True
        for idx, chunk in enumerate(chunks):
            if idx > 0:
                await asyncio.sleep(CHUNK_DELAY)

            ok = await _post_single(client, phone, chunk)
            if not ok:
                all_ok = False
                logger.error(
                    "falha ao enviar chunk %d/%d para %s", idx + 1, len(chunks), phone
                )
                # Continua tentando os proximos chunks mesmo apos falha parcial

    return all_ok
