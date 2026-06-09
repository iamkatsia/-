"""Клавиатуры бота."""
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from utils import fmt_dt

# ---------- Меню ученика ----------

def student_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Записаться на урок")],
            [KeyboardButton(text="🔔 Мои записи"), KeyboardButton(text="📚 Домашнее задание")],
            [KeyboardButton(text="💳 Оплата"), KeyboardButton(text="📅 Моё расписание")],
        ],
        resize_keyboard=True,
    )


# ---------- Меню админа ----------

def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить слоты"), KeyboardButton(text="🗓 Все записи")],
            [KeyboardButton(text="✅ Провести урок"), KeyboardButton(text="📝 Выдать ДЗ")],
            [KeyboardButton(text="💰 Отметить оплату"), KeyboardButton(text="🔔 Напомнить об оплате")],
            [KeyboardButton(text="👥 Ученики"), KeyboardButton(text="📣 Рассылка")],
            [KeyboardButton(text="⬅️ Режим ученика")],
        ],
        resize_keyboard=True,
    )


# ---------- Инлайн-клавиатуры ----------

def slots_kb(slots: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📅 {fmt_dt(s['start_at'])}", callback_data=f"book:{s['id']}")]
        for s in slots
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bookings_kb(bookings: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"❌ Отменить {fmt_dt(b['start_at'])}", callback_data=f"cancel:{b['id']}")]
        for b in bookings
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_kb(slot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтверждаю", callback_data=f"confirm:{slot_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel:{slot_id}"),
        ]]
    )


def students_kb(students: list[dict], action: str) -> InlineKeyboardMarkup:
    """action: 'done' (провести урок), 'hw' (выдать ДЗ), 'pay' (отметить оплату),
    'payremind' (напомнить об оплате)."""
    rows = [
        [InlineKeyboardButton(
            text=f"{s['name']} (осталось: {s['lessons_left']})",
            callback_data=f"{action}:{s['tg_id']}",
        )]
        for s in students
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def hw_submit_kb(hw_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📤 Сдать ДЗ", callback_data=f"hwsubmit:{hw_id}")]]
    )
