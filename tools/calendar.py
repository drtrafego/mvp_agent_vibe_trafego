import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config.settings import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TZ_SP = ZoneInfo("America/Sao_Paulo")
WEEKDAYS_PT = {0: "Segunda", 1: "Terca", 2: "Quarta", 3: "Quinta", 4: "Sexta"}
SLOT_HOURS = [10, 11, 12, 13, 14, 15]


def _build_service():
    creds = Credentials(
        token=None,
        refresh_token=settings.GOOGLE_OAUTH_REFRESH_TOKEN,
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _find_slots(days_ahead: int = 3) -> list[datetime]:
    """Retorna lista de candidatos de slot nos proximos dias_ahead dias uteis."""
    slots = []
    now = datetime.now(TZ_SP)
    day_cursor = now.date()
    checked_days = 0

    while len(slots) < days_ahead * len(SLOT_HOURS) and checked_days < 30:
        checked_days += 1
        day_cursor += timedelta(days=1)
        if day_cursor.weekday() >= 5:  # sabado ou domingo
            continue
        for hour in SLOT_HOURS:
            candidate = datetime(day_cursor.year, day_cursor.month, day_cursor.day, hour, 0, 0, tzinfo=TZ_SP)
            if candidate > now:
                slots.append(candidate)

    return slots


def _get_available_slots_sync(days_ahead: int = 3) -> str:
    service = _build_service()
    candidates = _find_slots(days_ahead)

    if not candidates:
        return "Nenhum horario disponivel nos proximos dias."

    # Construir query freebusy para todos os candidatos de uma vez
    time_min = candidates[0].isoformat()
    time_max = (candidates[-1] + timedelta(hours=1)).isoformat()

    body = {
        "timeMin": time_min,
        "timeMax": time_max,
        "timeZone": "America/Sao_Paulo",
        "items": [{"id": settings.GOOGLE_CALENDAR_ID}],
    }
    fb_result = service.freebusy().query(body=body).execute()
    busy_periods = fb_result.get("calendars", {}).get(settings.GOOGLE_CALENDAR_ID, {}).get("busy", [])

    def is_busy(slot: datetime) -> bool:
        slot_end = slot + timedelta(minutes=30)
        for period in busy_periods:
            p_start = datetime.fromisoformat(period["start"]).astimezone(TZ_SP)
            p_end = datetime.fromisoformat(period["end"]).astimezone(TZ_SP)
            if slot < p_end and slot_end > p_start:
                return True
        return False

    available = [s for s in candidates if not is_busy(s)]
    selected = available[:3]

    if not selected:
        return "Nenhum horario disponivel nos proximos dias."

    lines = []
    for i, slot in enumerate(selected, start=1):
        weekday_name = WEEKDAYS_PT.get(slot.weekday(), "")
        day_str = slot.strftime("%d/%m")
        hour_str = slot.strftime("%Hh")
        lines.append(f"{i}. {weekday_name} {day_str} as {hour_str}")

    return "\n".join(lines)


def _create_event_sync(name: str, email: str, iso_datetime: str, title: str) -> dict:
    service = _build_service()

    start = datetime.fromisoformat(iso_datetime)
    if start.tzinfo is None:
        start = start.replace(tzinfo=TZ_SP)
    end = start + timedelta(minutes=30)

    event_body = {
        "summary": title,
        "description": f"Lead: {name}\nEmail: {email}",
        "start": {"dateTime": start.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": end.isoformat(), "timeZone": "America/Sao_Paulo"},
        "attendees": [{"email": email, "displayName": name}],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ],
        },
    }

    created = (
        service.events()
        .insert(
            calendarId=settings.GOOGLE_CALENDAR_ID,
            body=event_body,
            sendUpdates="all",
        )
        .execute()
    )

    return {
        "htmlLink": created.get("htmlLink", ""),
        "id": created.get("id", ""),
        "summary": created.get("summary", title),
        "start": created.get("start", {}).get("dateTime", iso_datetime),
        "email": email,
        "name": name,
    }


async def get_available_slots(days_ahead: int = 3) -> str:
    """Retorna string com 3 horarios disponiveis formatados em pt-BR."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_available_slots_sync, days_ahead)


async def create_event(name: str, email: str, iso_datetime: str, title: str) -> dict:
    """Cria evento no Google Calendar. Retorna dict com htmlLink e eventId."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _create_event_sync, name, email, iso_datetime, title)
