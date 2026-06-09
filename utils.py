"""Вспомогательные функции."""
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message

_RU_MONTHS = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
_RU_WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def fmt_dt(start_at: str) -> str:
    """'2026-06-09 18:00' -> '9 июня (вт), 18:00'. При ошибке вернёт как есть."""
    try:
        dt = datetime.strptime(start_at, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return start_at
    return f"{dt.day} {_RU_MONTHS[dt.month]} ({_RU_WEEKDAYS[dt.weekday()]}), {dt.strftime('%H:%M')}"


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
