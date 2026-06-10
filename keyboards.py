"""Клавиатуры бота."""
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from utils import fmt_dt, fmt_slot_btn, week_monday, week_title
from datetime import timedelta

DAYS_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# ---------- Меню ученика ----------

def student_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Записаться на урок")],
            [KeyboardButton(text="📆 Моё расписание"), KeyboardButton(text="📚 Домашнее задание")],
            [KeyboardButton(text="💳 Оплата"), KeyboardButton(text="📎 Мои материалы")],
        ],
        resize_keyboard=True,
    )


# ---------- Меню админа ----------

def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📆 Расписание"), KeyboardButton(text="➕ Добавить слоты")],
            [KeyboardButton(text="🗓 Все записи"), KeyboardButton(text="✅ Провести урок")],
            [KeyboardButton(text="📝 Выдать ДЗ"), KeyboardButton(text="💰 Отметить оплату")],
            [KeyboardButton(text="🔔 Напомнить об оплате"), KeyboardButton(text="👥 Ученики")],
            [KeyboardButton(text="📣 Рассылка"), KeyboardButton(text="⬅️ Режим ученика")],
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
    """Для каждого урока — кнопки «Отменить» и «Перенести» в одной строке."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"❌ {fmt_dt(b['start_at'])}",
                callback_data=f"cancel:{b['id']}",
            ),
            InlineKeyboardButton(
                text="🔄 Перенести",
                callback_data=f"reschedule:{b['id']}",
            ),
        ]
        for b in bookings
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reschedule_slots_kb(slots: list[dict]) -> InlineKeyboardMarkup:
    """Слоты для выбора нового времени при переносе."""
    rows = [
        [InlineKeyboardButton(text=f"📅 {fmt_dt(s['start_at'])}", callback_data=f"rebook:{s['id']}")]
        for s in slots
    ]
    rows.append([InlineKeyboardButton(text="↩️ Не переносить", callback_data="reschedule_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_kb(slot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтверждаю", callback_data=f"confirm:{slot_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel:{slot_id}"),
        ]]
    )


def students_kb(students: list[dict], action: str) -> InlineKeyboardMarkup:
    """action: 'done' | 'hw' | 'pay' | 'payremind'."""
    rows = [
        [InlineKeyboardButton(
            text=f"{s['name']} (к оплате: {s['lessons_left']})",
            callback_data=f"{action}:{s['tg_id']}",
        )]
        for s in students
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def students_list_kb(students: list[dict]) -> InlineKeyboardMarkup:
    """Список учеников — каждый ведёт в профиль с расписанием."""
    rows = [
        [InlineKeyboardButton(
            text=f"👤 {s['name']}",
            callback_data=f"student_profile:{s['tg_id']}",
        )]
        for s in students
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def student_profile_kb(student_id: int, schedule: list[dict]) -> InlineKeyboardMarkup:
    """Профиль ученика: личное расписание + редактирование полей профиля."""
    rows = []
    # Текущие слоты расписания — нажать → удалить
    for item in schedule:
        day_name = DAYS_NAMES[item["day_of_week"]]
        rows.append([InlineKeyboardButton(
            text=f"🗑 {day_name} {item['time_str']}",
            callback_data=f"del_ssched:{item['id']}:{student_id}",
        )])
    # Управление расписанием
    rows.append([InlineKeyboardButton(text="➕ Добавить день/время", callback_data=f"add_ssched:{student_id}")])
    rows.append([InlineKeyboardButton(text="📅 Создать уроки на 4 нед.", callback_data=f"gen_ssched:{student_id}")])
    # Редактирование профиля
    rows.append([
        InlineKeyboardButton(text="🔗 Материалы", callback_data=f"edit_materials:{student_id}"),
        InlineKeyboardButton(text="📊 Уровень", callback_data=f"edit_level:{student_id}"),
    ])
    rows.append([
        InlineKeyboardButton(text="📝 Прогресс", callback_data=f"edit_progress:{student_id}"),
        InlineKeyboardButton(text="🗒 Заметки", callback_data=f"edit_notes:{student_id}"),
    ])
    rows.append([InlineKeyboardButton(text="⬅️ К списку учеников", callback_data="students_list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_student_notify_kb(student_id: int) -> InlineKeyboardMarkup:
    """Кнопка в уведомлении о новом ученике."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📋 Назначить расписание", callback_data=f"student_profile:{student_id}"),
    ]])


def student_week_kb(slots: list[dict], student_id: int, offset: int) -> InlineKeyboardMarkup:
    """Недельное расписание для ученика.
    Свободные слоты — кнопка «Записаться».
    Свои уроки — кнопка «✅ дата» (отменить) + «🔄» (перенести).
    Чужие занятые слоты — не показываются.
    Внизу — навигация по неделям.
    """
    rows = []
    for slot in slots:
        label = fmt_slot_btn(slot["start_at"])
        if slot["student_id"] is None:
            # свободный слот
            rows.append([
                InlineKeyboardButton(
                    text=f"📅 {label}",
                    callback_data=f"book:{slot['id']}",
                )
            ])
        elif slot["student_id"] == student_id:
            # урок этого ученика
            rows.append([
                InlineKeyboardButton(
                    text=f"✅ {label}",
                    callback_data=f"cancel:{slot['id']}",
                ),
                InlineKeyboardButton(
                    text="🔄",
                    callback_data=f"reschedule:{slot['id']}",
                ),
            ])
        # чужие занятые — пропускаем

    # навигация
    nav = []
    if offset > 0:
        prev_title = week_title(offset - 1)
        nav.append(InlineKeyboardButton(
            text=f"◀ {prev_title}",
            callback_data=f"sweek:{offset - 1}",
        ))
    next_title = week_title(offset + 1)
    nav.append(InlineKeyboardButton(
        text=f"{next_title} ▶",
        callback_data=f"sweek:{offset + 1}",
    ))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_week_kb(offset: int) -> InlineKeyboardMarkup:
    """Навигация по неделям для учителя."""
    nav = []
    if offset > -4:          # не уходим дальше 4 недель назад
        prev_title = week_title(offset - 1)
        nav.append(InlineKeyboardButton(
            text=f"◀ {prev_title}",
            callback_data=f"aweek:{offset - 1}",
        ))
    next_title = week_title(offset + 1)
    nav.append(InlineKeyboardButton(
        text=f"{next_title} ▶",
        callback_data=f"aweek:{offset + 1}",
    ))
    return InlineKeyboardMarkup(inline_keyboard=[nav])


def hw_submit_kb(hw_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📤 Сдать ДЗ", callback_data=f"hwsubmit:{hw_id}")]]
    )


# ---------- Шаблон расписания (для админа) ----------

def schedule_template_kb(templates: list[dict]) -> InlineKeyboardMarkup:
    """Каждый шаблонный слот — строка с кнопкой удаления.
    Внизу кнопки «Добавить» и «Сгенерировать слоты»."""
    rows = [
        [InlineKeyboardButton(
            text=f"🗑 {DAYS_NAMES[t['day_of_week']]} {t['time_str']}",
            callback_data=f"deltpl:{t['id']}",
        )]
        for t in templates
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить время", callback_data="addtpl")])
    rows.append([InlineKeyboardButton(text="📅 Создать слоты на 4 нед.", callback_data="genslots")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора дня недели."""
    row1 = [
        InlineKeyboardButton(text=DAYS_NAMES[i], callback_data=f"tplday:{i}")
        for i in range(4)
    ]
    row2 = [
        InlineKeyboardButton(text=DAYS_NAMES[i], callback_data=f"tplday:{i}")
        for i in range(4, 7)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])
