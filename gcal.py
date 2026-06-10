"""Интеграция с Google Календарём через сервисный аккаунт.

Работает, только если задан GOOGLE_CALENDAR_ID и есть учётные данные сервисного
аккаунта (файл или JSON в переменной окружения). Если что-то не настроено —
все функции тихо ничего не делают, бот продолжает работать как обычно.

Главный принцип: ошибка календаря НИКОГДА не должна ломать бота. Поэтому каждая
функция ловит исключения, пишет их в лог и возвращает безопасное значение.

Что умеет:
- create_event   — создать событие урока в твоём календаре, вернуть его id
- delete_event   — удалить событие по id (при отмене/переносе урока)
- busy_intervals — узнать, когда ты занята (твои события в календаре),
                   чтобы бот не предлагал ученикам занятое время
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import (
    TIMEZONE,
    GOOGLE_CALENDAR_ID,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_CREDENTIALS_JSON,
    LESSON_DURATION_MIN,
)

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_TZ = ZoneInfo(TIMEZONE)

# Сервис строим один раз и кешируем (build не потокобезопасен — защищаем замком).
_service = None
_service_lock = threading.Lock()

# Небольшой кеш занятости, чтобы не дёргать Google на каждый показ слотов.
_busy_cache: tuple[str, str, list[tuple[datetime, datetime]], float] | None = None
_BUSY_TTL = 60  # секунд


def enabled() -> bool:
    """Календарь подключён? (Задан ID календаря и есть откуда взять учётные данные.)"""
    if not GOOGLE_CALENDAR_ID:
        return False
    return bool(GOOGLE_CREDENTIALS_JSON) or os.path.isfile(GOOGLE_CREDENTIALS_FILE)


def _parse_creds_json(raw: str) -> dict:
    """Разбирает ключ сервисного аккаунта.

    Принимает либо обычный JSON, либо его base64-версию. base64 удобен для
    хостингов вроде Amvera, где в значении переменной нельзя ставить кавычки.
    """
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import base64

        decoded = base64.b64decode(raw).decode("utf-8")
        return json.loads(decoded)


def _load_credentials():
    """Грузит учётные данные сервисного аккаунта из JSON-переменной или файла."""
    from google.oauth2 import service_account

    if GOOGLE_CREDENTIALS_JSON:
        info = _parse_creds_json(GOOGLE_CREDENTIALS_JSON)
        return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    return service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=_SCOPES
    )


def _get_service():
    """Возвращает (и кеширует) клиент Google Calendar API. None — если не вышло."""
    global _service
    if _service is not None:
        return _service
    with _service_lock:
        if _service is not None:
            return _service
        try:
            from googleapiclient.discovery import build

            creds = _load_credentials()
            _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            log.info("Google Calendar: подключение готово (%s).", GOOGLE_CALENDAR_ID)
        except Exception as e:  # noqa: BLE001
            import traceback
            log.warning("Google Calendar: не удалось подключиться — %s\n%s", e, traceback.format_exc())
            _service = None
    return _service


def _parse_local(start_at: str) -> datetime:
    """'YYYY-MM-DD HH:MM' (локальное время) -> datetime с часовым поясом."""
    return datetime.strptime(start_at, "%Y-%m-%d %H:%M").replace(tzinfo=_TZ)


# ---------- Синхронные операции (выполняются в отдельном потоке) ----------

def _create_event_sync(start_at: str, summary: str, description: str) -> str | None:
    service = _get_service()
    if service is None:
        return None
    try:
        start = _parse_local(start_at)
        end = start + timedelta(minutes=LESSON_DURATION_MIN)
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        }
        event = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=body).execute()
        return event.get("id")
    except Exception as e:  # noqa: BLE001
        log.warning("Google Calendar: не удалось создать событие — %s", e)
        return None


def _delete_event_sync(event_id: str) -> None:
    service = _get_service()
    if service is None:
        return
    try:
        service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
    except Exception as e:  # noqa: BLE001
        # 404/410 — событие уже удалено вручную, это норма.
        log.info("Google Calendar: удаление события %s — %s", event_id, e)


def _busy_intervals_sync(date_from: str, date_to: str) -> list[tuple[datetime, datetime]]:
    """Список занятых интервалов (локальные naive datetime) за [date_from..date_to].
    date_from/date_to — 'YYYY-MM-DD'."""
    service = _get_service()
    if service is None:
        return []
    try:
        time_min = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=_TZ)
        time_max = (
            datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=_TZ) + timedelta(days=1)
        )
        body = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "timeZone": TIMEZONE,
            "items": [{"id": GOOGLE_CALENDAR_ID}],
        }
        resp = service.freebusy().query(body=body).execute()
        cal = resp.get("calendars", {}).get(GOOGLE_CALENDAR_ID, {})
        out: list[tuple[datetime, datetime]] = []
        for b in cal.get("busy", []):
            s = datetime.fromisoformat(b["start"]).astimezone(_TZ).replace(tzinfo=None)
            e = datetime.fromisoformat(b["end"]).astimezone(_TZ).replace(tzinfo=None)
            out.append((s, e))
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("Google Calendar: не удалось прочитать занятость — %s", e)
        return []


# ---------- Асинхронные обёртки (чтобы не блокировать бота) ----------

async def create_event(start_at: str, summary: str, description: str = "") -> str | None:
    if not enabled():
        return None
    return await asyncio.to_thread(_create_event_sync, start_at, summary, description)


async def delete_event(event_id: str | None) -> None:
    if not event_id or not enabled():
        return
    await asyncio.to_thread(_delete_event_sync, event_id)


async def busy_intervals(date_from: str, date_to: str) -> list[tuple[datetime, datetime]]:
    if not enabled():
        return []
    global _busy_cache
    now = asyncio.get_event_loop().time()
    if _busy_cache is not None:
        cf, ct, data, ts = _busy_cache
        if cf == date_from and ct == date_to and (now - ts) < _BUSY_TTL:
            return data
    data = await asyncio.to_thread(_busy_intervals_sync, date_from, date_to)
    _busy_cache = (date_from, date_to, data, now)
    return data


def slot_is_busy(start_at: str, busy: list[tuple[datetime, datetime]]) -> bool:
    """Пересекается ли слот [start, start+урок] с каким-нибудь занятым интервалом."""
    try:
        s = datetime.strptime(start_at, "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    e = s + timedelta(minutes=LESSON_DURATION_MIN)
    for bs, be in busy:
        if s < be and bs < e:  # есть пересечение
            return True
    return False
