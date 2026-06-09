"""Вспомогательные функции."""
from __future__ import annotations
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
