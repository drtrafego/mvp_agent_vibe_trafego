import logging
import tempfile
import os
import httpx
import google.generativeai as genai
from config.settings import settings

logger = logging.getLogger(__name__)

META_MEDIA_URL = "https://graph.facebook.com/v21.0/{media_id}"
TRANSCRIPTION_PROMPT = "Transcreva este audio em portugues. Retorne apenas o texto transcrito."


async def transcribe_audio(media_id: str) -> str:
    """Baixa audio da Meta API e transcreve com Gemini Flash. Retorna texto."""
    tmp_path: str | None = None
    try:
        headers = {"Authorization": f"Bearer {settings.META_ACCESS_TOKEN}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Buscar metadados e URL de download
            meta_url = META_MEDIA_URL.format(media_id=media_id)
            meta_resp = await client.get(meta_url, headers=headers)
            meta_resp.raise_for_status()
            meta_data = meta_resp.json()
            download_url = meta_data.get("url")
            mime_type = meta_data.get("mime_type", "audio/ogg")

            if not download_url:
                logger.error("URL de download nao encontrada para media_id=%s", media_id)
                return "[Audio nao pode ser transcrito. O lead enviou um audio.]"

            # 2. Baixar blob de audio
            audio_resp = await client.get(download_url, headers=headers)
            audio_resp.raise_for_status()
            audio_bytes = audio_resp.content

        # 3. Salvar em arquivo temporario
        suffix = ".ogg" if "ogg" in mime_type else ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # 4. Transcrever com Gemini
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")

        with open(tmp_path, "rb") as f:
            audio_data = f.read()

        audio_part = {"mime_type": mime_type, "data": audio_data}
        response = model.generate_content([audio_part, TRANSCRIPTION_PROMPT])
        transcript = response.text.strip()

        logger.info("Audio transcrito: media_id=%s chars=%d", media_id, len(transcript))
        return transcript

    except Exception as exc:
        logger.error("Erro ao transcrever audio media_id=%s: %s", media_id, exc)
        return "[Audio nao pode ser transcrito. O lead enviou um audio.]"

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
