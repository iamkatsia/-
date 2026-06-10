"""Вспомогательные функции."""
from __future__ import annotations
import re
from datetime import datetime, date, timedelta

from aiogram import Bot
from aiogram.types import Message

_RU_MONTHS_GEN = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
# Короткие названия месяцев для заголовков недели
_RU_MONTHS_SHORT = [
    "", "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]
_RU_WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_RU_WEEKDAYS_LONG  = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

# Оставляем старые алиасы чтобы не ломать существующий код
_RU_MONTHS   = _RU_MONTHS_GEN
_RU_WEEKDAYS = [d.lower()[:2] for d in _RU_WEEKDAYS_SHORT]


def fmt_dt(start_at: str) -> str:
    """'2026-06-09 18:00' → '9 июня (вт), 18:00'."""
    try:
        dt = datetime.strptime(start_at, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return start_at
    return f"{dt.day} {_RU_MONTHS_GEN[dt.month]} ({_RU_WEEKDAYS[dt.weekday()]}), {dt.strftime('%H:%M')}"


def fmt_slot_btn(start_at: str) -> str:
    """Краткий формат для кнопки: 'Пн 9 июн, 17:00'."""
    try:
        dt = datetime.strptime(start_at, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return start_at
    return f"{_RU_WEEKDAYS_SHORT[dt.weekday()]} {dt.day} {_RU_MONTHS_SHORT[dt.month]}, {dt.strftime('%H:%M')}"


def week_monday(offset: int = 0) -> date:
    """Понедельник текущей недели + offset недель."""
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset)


def week_bounds(offset: int = 0) -> tuple[str, str]:
    """Возвращает ('YYYY-MM-DD понедельник', 'YYYY-MM-DD воскресенье') для недели offset."""
    monday = week_monday(offset)
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def week_title(offset: int = 0) -> str:
    """'10 — 16 июн' или '30 июн — 6 июл' для заголовка."""
    monday = week_monday(offset)
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.day} — {sunday.day} {_RU_MONTHS_SHORT[sunday.month]}"
    return f"{monday.day} {_RU_MONTHS_SHORT[monday.month]} — {sunday.day} {_RU_MONTHS_SHORT[sunday.month]}"


# ---------- Разбор слотов из текста учителя ----------

_MONTHS_PREFIX = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5,
    "июн": 6, "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _nearest_future_date(day: int, month: int, today: date) -> date | None:
    """Ближайшая будущая дата с таким днём и месяцем (сегодня тоже подходит)."""
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d >= today:
            return d
    return None


def parse_slots_text(text: str) -> tuple[list[str], list[str]]:
    """Разбирает слоты из свободного текста.

    Каждая строка: дата + одно или несколько времён, например:
      «11 июня 13:00, 15:00»
      «11.06 17:00»
      «2026-06-11 13:00» (старый формат тоже работает)
    Год подставляется автоматически — берётся ближайшая будущая дата.
    Возвращает (список 'YYYY-MM-DD HH:MM', список нераспознанных строк).
    """
    today = date.today()
    parsed: list[str] = []
    errors: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Старый формат: 2026-06-11 13:00
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})", line)
        if m:
            try:
                dt = datetime.strptime(f"{m[1]} {m[2]}", "%Y-%m-%d %H:%M")
                parsed.append(dt.strftime("%Y-%m-%d %H:%M"))
            except ValueError:
                errors.append(raw_line)
            continue
        # «11 июня 13:00, 15:00» или «11.06 13:00 15:00»
        m = re.match(r"^(\d{1,2})(?:\s+([а-яё]+)\.?|[./](\d{1,2}))\s+(.+)$", line, re.IGNORECASE)
        if not m:
            errors.append(raw_line)
            continue
        day = int(m[1])
        month = _MONTHS_PREFIX.get(m[2].lower()[:3]) if m[2] else int(m[3])
        times = _TIME_RE.findall(m[4])
        if not month or not 1 <= month <= 12 or not times:
            errors.append(raw_line)
            continue
        d = _nearest_future_date(day, month, today)
        if d is None:
            errors.append(raw_line)
            continue
        line_slots = []
        for hh, mm in times:
            h, mi = int(hh), int(mm)
            if not (0 <= h <= 23 and 0 <= mi <= 59):
                line_slots = []
                break
            line_slots.append(f"{d.strftime('%Y-%m-%d')} {h:02d}:{mi:02d}")
        if line_slots:
            parsed.extend(line_slots)
        else:
            errors.append(raw_line)
    return parsed, errors


def extract_file(message: Message) -> str | None:
    """Возвращает сохраняемую строку 'тип:file_id' для документа или фото из сообщения."""
    if message.document:
        return f"doc:{message.document.file_id}"
    if message.photo:
        return f"photo:{message.photo[-1].file_id}"
    return None


async def send_stored_file(bot: Bot, chat_id: int, stored: str, caption: str | None = None) -> None:
    """Отправляет ранее сохранённый файл по строке 'тип:file_id'."""
    if not stored or ":" not in stored:
        return
    kind, file_id = stored.split(":", 1)
    if kind == "doc":
        await bot.send_document(chat_id, file_id, caption=caption)
    elif kind == "photo":
        await bot.send_photo(chat_id, file_id, caption=caption)
