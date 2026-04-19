import logging
import httpx
from config.settings import settings

logger = logging.getLogger(__name__)

META_MESSAGES_URL = "https://graph.facebook.com/v21.0/{phone_number_id}/messages"


async def notify_appointment(event: dict) -> None:
    """Envia mensagem WhatsApp para settings.NOTIFY_PHONE com dados do evento."""
    try:
        summary = event.get("summary", "Sem titulo")
        start = event.get("start", "")
        email = event.get("email", "")
        html_link = event.get("htmlLink", "")

        body_text = (
            f"Novo agendamento!\n"
            f"{summary}\n"
            f"{start}\n"
            f"Lead: {email}\n"
            f"{html_link}"
        )

        url = META_MESSAGES_URL.format(phone_number_id=settings.META_PHONE_NUMBER_ID)
        headers = {
            "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": settings.NOTIFY_PHONE,
            "type": "text",
            "text": {"body": body_text},
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info("Notificacao de agendamento enviada para %s", settings.NOTIFY_PHONE)

    except Exception as exc:
        logger.error("Falha ao enviar notificacao de agendamento: %s", exc)
