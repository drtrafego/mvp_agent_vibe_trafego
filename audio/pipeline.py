"""Transcricao de audio via api.transcrever.casaldotrafego.com (Whisper local).

Fluxo (sincrono, rapido ~5-15s):
1. Baixa audio da Meta API
2. Upload para api.transcrever via /videos/upload (salva em /opt/transcrever/videos/)
3. POST /transcribe com video_path absoluto -> retorna texto direto
"""
import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

META_MEDIA_URL = "https://graph.facebook.com/v21.0/{media_id}"
TRANSCRIBE_BASE = "https://api.transcrever.casaldotrafego.com"
TRANSCRIBE_VIDEOS_PATH = "/opt/transcrever/videos"  # path interno do servidor
TRANSCRIBE_TIMEOUT_S = 180  # max 3 min para audios longos
FALLBACK = "[Audio nao pode ser transcrito. O lead enviou um audio.]"


async def _download_meta_audio(media_id: str) -> tuple[bytes, str] | None:
    headers = {"Authorization": f"Bearer {settings.META_ACCESS_TOKEN}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        meta_url = META_MEDIA_URL.format(media_id=media_id)
        meta_resp = await client.get(meta_url, headers=headers)
        meta_resp.raise_for_status()
        meta_data = meta_resp.json()
        download_url = meta_data.get("url")
        mime_type = meta_data.get("mime_type", "audio/ogg")

        if not download_url:
            logger.error("URL de download nao encontrada para media_id=%s", media_id)
            return None

        audio_resp = await client.get(download_url, headers=headers)
        audio_resp.raise_for_status()
        return audio_resp.content, mime_type


async def transcribe_audio(media_id: str) -> str:
    """Baixa audio da Meta e transcreve via api.transcrever (Whisper local). Sem custo Gemini."""
    try:
        downloaded = await _download_meta_audio(media_id)
        if not downloaded:
            return FALLBACK
        audio_bytes, mime_type = downloaded

        suffix = ".ogg" if "ogg" in mime_type else ".mp4"
        filename = f"meta_{media_id[:30]}{suffix}"

        async with httpx.AsyncClient(timeout=TRANSCRIBE_TIMEOUT_S + 30) as client:
            # 1. Upload
            files = {"file": (filename, audio_bytes, mime_type)}
            up = await client.post(f"{TRANSCRIBE_BASE}/videos/upload", files=files)
            up.raise_for_status()
            uploaded_filename = up.json().get("filename", filename)
            logger.info("Audio uploaded: %s", uploaded_filename)

            # 2. Transcrever direto (sincrono, ~5-15s)
            video_path = f"{TRANSCRIBE_VIDEOS_PATH}/{uploaded_filename}"
            tr = await client.post(
                f"{TRANSCRIBE_BASE}/transcribe",
                json={"video_path": video_path, "language": "pt"},
                timeout=TRANSCRIBE_TIMEOUT_S,
            )
            tr.raise_for_status()
            data = tr.json()
            if data.get("status") != "success":
                logger.error("Transcricao falhou: %s", data)
                return FALLBACK
            transcript = (data.get("text") or "").strip()
            if not transcript:
                logger.warning("Transcricao vazia: media_id=%s", media_id)
                return FALLBACK
            logger.info("Audio transcrito: media_id=%s chars=%d", media_id, len(transcript))
            return transcript

    except Exception as exc:
        logger.error("Erro ao transcrever audio media_id=%s: %s", media_id, exc)
        return FALLBACK
