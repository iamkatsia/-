"""Хендлеры для учителя-админа. Доступны только пользователю с ADMIN_ID."""
from __future__ import annotations
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
from config import ADMIN_ID, PAYMENT_DETAILS, LESSON_PRICE_RUB, LESSON_PRICE_BYN
from states import AdminStates
from utils import extract_file, send_stored_file, fmt_dt, week_bounds, week_title, week_monday
from utils import _RU_WEEKDAYS_SHORT, _RU_MONTHS_SHORT
from keyboards import DAYS_NAMES
from datetime import timedelta

router = Router()
# Весь роутер доступен только админу
router.message.filter(F.from_user.id == ADMIN_ID)
router.callback_query.filter(F.from_user.id == ADMIN_ID)


@router.message(Command("admin"))
async def open_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Панель учителя 👩‍🏫", reply_markup=kb.admin_menu())


@router.message(F.text == "⬅️ Режим ученика")
async def back_to_student(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вернулась в режим ученика.", reply_markup=kb.student_menu())


# ---------- Добавление слотов ----------

@router.message(F.text == "➕ Добавить слоты")
async def add_slots_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.adding_slots)
    await message.answer(
        "Пришли слоты по одному в строке в формате <b>ГГГГ-ММ-ДД ЧЧ:ММ</b>.\n\n"
        "Пример:\n2026-06-10 18:00\n2026-06-10 19:00\n2026-06-11 17:00"
    )


@router.message(AdminStates.adding_slots)
async def add_slots_receive(message: Message, state: FSMContext):
    added, errors = 0, []
    for line in message.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            dt = datetime.strptime(line, "%Y-%m-%d %H:%M")
            await db.add_slot(dt.strftime("%Y-%m-%d %H:%M"))
            added += 1
        except ValueError:
            errors.append(line)
    await state.clear()
    text = f"✅ Добавлено слотов: {added}."
    if errors:
        text += "\n⚠️ Не распознаны строки:\n" + "\n".join(errors)
    await message.answer(text, reply_markup=kb.admin_menu())


# ---------- Все записи — недельный вид ----------

def _format_admin_week(slots: list[dict], offset: int) -> str:
    """Форматирует сводку недели для учителя."""
    monday = week_monday(offset)
    lines = [f"🗓 <b>Расписание: {week_title(offset)}</b>\n"]
    has_slots = False
    for delta in range(7):
        day = monday + timedelta(days=delta)
        d_str = day.strftime("%Y-%m-%d")
        day_slots = [s for s in slots if s["start_at"].startswith(d_str)]
        if not day_slots:
            continue
        has_slots = True
        day_label = f"<b>{_RU_WEEKDAYS_SHORT[delta]}, {day.day} {_RU_MONTHS_SHORT[day.month]}</b>"
        lines.append(day_label)
        for s in day_slots:
            time = s["start_at"][11:16]
            if s["student_id"]:
                name = s.get("student_name") or "?"
                uname = f" (@{s['student_username']})" if s.get("student_username") else ""
                lines.append(f"  ✅ {time} — {name}{uname}")
            else:
                lines.append(f"  ◻️ {time} — <i>свободно</i>")
        lines.append("")
    if not has_slots:
        lines.append("На эту неделю слотов нет.\nДобавь через «📆 Расписание» или «➕ Добавить слоты».")
    return "\n".join(lines)


async def _send_admin_week(target, offset: int) -> None:
    date_from, date_to = week_bounds(offset)
    slots = await db.slots_in_range(date_from, date_to)
    text = _format_admin_week(slots, offset)
    markup = kb.admin_week_kb(offset)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text == "🗓 Все записи")
async def all_bookings(message: Message):
    await _send_admin_week(message, offset=0)


@router.callback_query(F.data.startswith("aweek:"))
async def admin_week_nav(call: CallbackQuery):
    offset = int(call.data.split(":")[1])
    await _send_admin_week(call, offset)


# ---------- Провести урок (списать занятие) ----------

@router.message(F.text == "✅ Провести урок")
async def lesson_done_menu(message: Message):
    students = await db.all_users()
    students = [s for s in students if s["tg_id"] != ADMIN_ID]
    if not students:
        await message.answer("Пока нет учеников.")
        return
    await message.answer(
        "Выбери ученика — отмечу проведённый урок (+1 к оплате):",
        reply_markup=kb.students_kb(students, "done"),
    )


@router.callback_query(F.data.startswith("done:"))
async def lesson_done(call: CallbackQuery, bot: Bot):
    student_id = int(call.data.split(":")[1])
    owed = await db.change_lessons(student_id, 1)
    student = await db.get_user(student_id)
    await call.message.edit_text(
        f"✅ Урок отмечен у {student['name']}. Уроков к оплате: {owed}."
    )
    await call.answer()
    try:
        await bot.send_message(
            student_id,
            f"Урок проведён ✅\nУроков к оплате накопилось: {owed}.",
        )
    except Exception:
        pass


# ---------- Выдать ДЗ ----------

@router.message(F.text == "📝 Выдать ДЗ")
async def hw_give_menu(message: Message):
    students = await db.all_users()
    students = [s for s in students if s["tg_id"] != ADMIN_ID]
    if not students:
        await message.answer("Пока нет учеников.")
        return
    await message.answer(
        "Кому выдать домашнее задание?",
        reply_markup=kb.students_kb(students, "hw"),
    )


@router.callback_query(F.data.startswith("hw:"))
async def hw_give_pick(call: CallbackQuery, state: FSMContext):
    student_id = int(call.data.split(":")[1])
    await state.set_state(AdminStates.writing_hw)
    await state.update_data(student_id=student_id)
    await call.message.answer("Пришли текст задания (можно с файлом/фото).")
    await call.answer()


@router.message(AdminStates.writing_hw)
async def hw_give_receive(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    student_id = data["student_id"]
    task_text = message.text or message.caption or "Домашнее задание"
    task_file = extract_file(message)
    await db.add_homework(student_id, task_text, task_file)
    await state.clear()
    await message.answer("✅ ДЗ выдано.", reply_markup=kb.admin_menu())
    try:
        await bot.send_message(student_id, f"📚 Новое домашнее задание:\n\n{task_text}")
        if task_file:
            await send_stored_file(bot, student_id, task_file, "Материал к заданию")
    except Exception:
        await message.answer("⚠️ Не удалось доставить ДЗ ученику (он не запускал бота).")


# ---------- Отметить оплату (обнулить счётчик к оплате) ----------

@router.message(F.text == "💰 Отметить оплату")
async def payment_mark_menu(message: Message):
    students = await db.all_users()
    students = [s for s in students if s["tg_id"] != ADMIN_ID]
    if not students:
        await message.answer("Пока нет учеников.")
        return
    await message.answer(
        "Кто оплатил? Выбери ученика — обнулю его счётчик «к оплате»:",
        reply_markup=kb.students_kb(students, "pay"),
    )


@router.callback_query(F.data.startswith("pay:"))
async def payment_mark_pick(call: CallbackQuery, bot: Bot):
    student_id = int(call.data.split(":")[1])
    student = await db.get_user(student_id)
    was = await db.reset_lessons(student_id)
    await db.add_payment(student_id, "manual", was, was * LESSON_PRICE_RUB)
    await call.message.edit_text(
        f"✅ Оплата отмечена: {student['name']}. Счётчик обнулён (было {was} ур.)."
    )
    await call.answer()
    try:
        await bot.send_message(
            student_id,
            "💳 Оплата получена, спасибо! Счёт за уроки обнулён ✅",
        )
    except Exception:
        pass


# ---------- Напомнить об оплате ----------

@router.message(F.text == "🔔 Напомнить об оплате")
async def payment_remind_menu(message: Message):
    students = await db.all_users()
    students = [s for s in students if s["tg_id"] != ADMIN_ID]
    if not students:
        await message.answer("Пока нет учеников.")
        return
    await message.answer(
        "Кому напомнить об оплате?",
        reply_markup=kb.students_kb(students, "payremind"),
    )


@router.callback_query(F.data.startswith("payremind:"))
async def payment_remind_send(call: CallbackQuery, bot: Bot):
    student_id = int(call.data.split(":")[1])
    student = await db.get_user(student_id)
    owed = student["lessons_left"] if student else 0
    rub = owed * LESSON_PRICE_RUB
    byn = owed * LESSON_PRICE_BYN
    try:
        await bot.send_message(
            student_id,
            f"🔔 Напоминание об оплате.\n\n"
            f"Уроков к оплате: {owed}\n"
            f"Сумма: {rub} ₽ или {byn} BYN\n\n"
            f"Реквизиты:\n{PAYMENT_DETAILS}",
        )
        await call.message.edit_text(f"✅ Напоминание отправлено: {student['name']}.")
    except Exception:
        await call.message.edit_text("⚠️ Не удалось отправить (ученик не запускал бота).")
    await call.answer()


# ---------- Ученики ----------

@router.message(F.text == "👥 Ученики")
async def list_students(message: Message):
    try:
        students = await db.all_users()
        students = [s for s in students if s["tg_id"] != ADMIN_ID]
        if not students:
            await message.answer("Пока нет учеников.")
            return
        lines = [f"• {s['name']} — уроков к оплате: {s['lessons_left']}" for s in students]
        text = "👥 <b>Ученики:</b>\n" + "\n".join(lines) + "\n\nВыбери ученика для управления расписанием:"
        await message.answer(text, reply_markup=kb.students_list_kb(students))
    except Exception as e:
        await message.answer(f"⚠️ Ошибка при загрузке учеников: {e}")


@router.callback_query(F.data == "students_list")
async def students_list_cb(call: CallbackQuery):
    try:
        students = await db.all_users()
        students = [s for s in students if s["tg_id"] != ADMIN_ID]
        if not students:
            await call.message.edit_text("Пока нет учеников.")
        else:
            lines = [f"• {s['name']} — уроков к оплате: {s['lessons_left']}" for s in students]
            text = "👥 <b>Ученики:</b>\n" + "\n".join(lines) + "\n\nВыбери ученика:"
            await call.message.edit_text(text, reply_markup=kb.students_list_kb(students))
    except Exception as e:
        await call.message.edit_text(f"⚠️ Ошибка: {e}")
    await call.answer()


async def _show_student_profile(target, student_id: int) -> None:
    """Показывает полный профиль ученика."""
    student = await db.get_user(student_id)
    if not student:
        text = "Ученик не найден."
        markup = None
    else:
        schedule = await db.get_student_schedule(student_id)
        uname = f" (@{student['username']})" if student.get("username") else ""

        # Расписание
        if schedule:
            sched_lines = "\n".join(
                f"  • {DAYS_NAMES[i['day_of_week']]} {i['time_str']}"
                for i in schedule
            )
            sched_text = f"\n\n📋 <b>Расписание:</b>\n{sched_lines}\n<i>Нажми 🗑 напротив дня — удалить.</i>"
        else:
            sched_text = "\n\n📋 <b>Расписание:</b> не назначено"

        # Поля профиля
        materials = student.get("materials_url") or "—"
        level     = student.get("level")    or "—"
        progress  = student.get("progress") or "—"
        notes     = student.get("notes")    or "—"

        text = (
            f"👤 <b>{student['name']}</b>{uname}\n"
            f"Уроков к оплате: <b>{student['lessons_left']}</b>"
            f"{sched_text}\n\n"
            f"🔗 <b>Материалы:</b> {materials}\n"
            f"📊 <b>Уровень:</b> {level}\n"
            f"📝 <b>Прогресс:</b> {progress}\n"
            f"🗒 <b>Заметки:</b> {notes}"
        )
        markup = kb.student_profile_kb(student_id, schedule)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("student_profile:"))
async def student_profile(call: CallbackQuery, state: FSMContext):
    await state.clear()
    student_id = int(call.data.split(":")[1])
    await _show_student_profile(call, student_id)


# ---------- Личное расписание ученика ----------

@router.callback_query(F.data.startswith("add_ssched:"))
async def student_sched_add_start(call: CallbackQuery, state: FSMContext):
    student_id = int(call.data.split(":")[1])
    await state.set_state(AdminStates.student_sched_pick_day)
    await state.update_data(target_student_id=student_id)
    await call.message.answer("Выбери день недели:", reply_markup=kb.days_kb())
    await call.answer()


@router.callback_query(AdminStates.student_sched_pick_day, F.data.startswith("tplday:"))
async def student_sched_pick_day(call: CallbackQuery, state: FSMContext):
    day = int(call.data.split(":")[1])
    await state.set_state(AdminStates.student_sched_pick_time)
    await state.update_data(day_of_week=day)
    await call.message.answer(
        f"День: <b>{DAYS_NAMES[day]}</b>\n"
        "Введи время в формате <b>ЧЧ:ММ</b>, например <code>17:00</code>:"
    )
    await call.answer()


@router.message(AdminStates.student_sched_pick_time)
async def student_sched_pick_time(message: Message, state: FSMContext):
    time_input = (message.text or "").strip()
    try:
        datetime.strptime(time_input, "%H:%M")
    except ValueError:
        await message.answer("Неверный формат. Введи время как <code>17:00</code>:")
        return
    data = await state.get_data()
    student_id = data["target_student_id"]
    day = data["day_of_week"]
    await db.add_student_schedule_item(student_id, day, time_input)
    await state.clear()
    await message.answer(f"✅ Добавлено: {DAYS_NAMES[day]} {time_input}")
    await _show_student_profile(message, student_id)


@router.callback_query(F.data.startswith("del_ssched:"))
async def student_sched_delete(call: CallbackQuery):
    _, item_id_str, student_id_str = call.data.split(":")
    await db.remove_student_schedule_item(int(item_id_str))
    await call.answer("Удалено")
    await _show_student_profile(call, int(student_id_str))


@router.callback_query(F.data.startswith("gen_ssched:"))
async def student_sched_generate(call: CallbackQuery):
    student_id = int(call.data.split(":")[1])
    count = await db.generate_student_slots(student_id, weeks=4)
    if count:
        await call.answer(f"✅ Создано уроков: {count}", show_alert=True)
    else:
        await call.answer(
            "Новых уроков не создано — либо расписание пустое, либо все уже созданы.",
            show_alert=True,
        )


# ---------- Рассылка ----------

@router.message(F.text == "📣 Рассылка")
async def broadcast_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.broadcasting)
    await message.answer("Пришли текст рассылки — отправлю всем ученикам.")


@router.message(AdminStates.broadcasting)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    students = await db.all_users()
    sent, failed = 0, 0
    for s in students:
        if s["tg_id"] == ADMIN_ID:
            continue
        try:
            await bot.send_message(s["tg_id"], message.text)
            sent += 1
        except Exception:
            failed += 1
    await message.answer(
        f"📣 Рассылка завершена. Доставлено: {sent}, не доставлено: {failed}.",
        reply_markup=kb.admin_menu(),
    )


# ---------- Расписание (шаблон + генерация слотов) ----------

async def _schedule_text(templates: list[dict]) -> str:
    if templates:
        lines = [f"• {DAYS_NAMES[t['day_of_week']]} {t['time_str']}" for t in templates]
        return (
            "📆 <b>Шаблон расписания</b>\n\n"
            "Регулярные слоты занятий:\n" + "\n".join(lines) + "\n\n"
            "Нажми 🗑 напротив времени, чтобы убрать его из шаблона.\n"
            "Кнопка «📅 Создать слоты» добавляет свободные слоты на ближайшие 4 недели."
        )
    return (
        "📆 <b>Шаблон расписания</b>\n\n"
        "Шаблон пуст. Нажми «➕ Добавить время», чтобы задать регулярные слоты.\n\n"
        "После настройки шаблона нажми «📅 Создать слоты» — бот добавит все слоты "
        "на ближайшие 4 недели автоматически."
    )


@router.message(F.text == "📆 Расписание")
async def schedule_menu(message: Message, state: FSMContext):
    await state.clear()
    templates = await db.get_templates()
    await message.answer(
        await _schedule_text(templates),
        reply_markup=kb.schedule_template_kb(templates),
    )


@router.callback_query(F.data == "addtpl")
async def template_add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.template_pick_day)
    await call.message.answer("Выбери день недели:", reply_markup=kb.days_kb())
    await call.answer()


@router.callback_query(AdminStates.template_pick_day, F.data.startswith("tplday:"))
async def template_add_day(call: CallbackQuery, state: FSMContext):
    day = int(call.data.split(":")[1])
    await state.set_state(AdminStates.template_pick_time)
    await state.update_data(day_of_week=day)
    await call.message.answer(
        f"День: <b>{DAYS_NAMES[day]}</b>\n"
        "Введи время в формате <b>ЧЧ:ММ</b>, например <code>17:00</code>:"
    )
    await call.answer()


@router.message(AdminStates.template_pick_time)
async def template_add_time(message: Message, state: FSMContext):
    time_input = message.text.strip() if message.text else ""
    try:
        datetime.strptime(time_input, "%H:%M")
    except ValueError:
        await message.answer("Неверный формат. Введи время как <code>17:00</code>:")
        return
    data = await state.get_data()
    day = data["day_of_week"]
    await db.add_template(day, time_input)
    await state.clear()
    templates = await db.get_templates()
    await message.answer(
        f"✅ Добавлено: {DAYS_NAMES[day]} {time_input}\n\n"
        + await _schedule_text(templates),
        reply_markup=kb.schedule_template_kb(templates),
    )


@router.callback_query(F.data.startswith("deltpl:"))
async def template_delete(call: CallbackQuery):
    tpl_id = int(call.data.split(":")[1])
    await db.remove_template(tpl_id)
    templates = await db.get_templates()
    await call.message.edit_text(
        await _schedule_text(templates),
        reply_markup=kb.schedule_template_kb(templates),
    )
    await call.answer("Удалено")


@router.callback_query(F.data == "genslots")
async def generate_slots(call: CallbackQuery):
    count = await db.generate_slots_from_templates(weeks=4)
    if count:
        await call.answer(f"✅ Создано новых слотов: {count}", show_alert=True)
    else:
        await call.answer(
            "Новых слотов не добавлено — либо шаблон пуст, либо все слоты уже существуют.",
            show_alert=True,
        )


# ---------- Редактирование профиля ученика ----------

_FIELD_META = {
    "materials_url": ("🔗 Ссылка на материалы", AdminStates.editing_materials),
    "level":         ("📊 Уровень",              AdminStates.editing_level),
    "progress":      ("📝 Прогресс",             AdminStates.editing_progress),
    "notes":         ("🗒 Заметки",              AdminStates.editing_notes),
}


async def _start_edit(call: CallbackQuery, state: FSMContext, field: str) -> None:
    student_id = int(call.data.split(":")[1])
    label, fsm_state = _FIELD_META[field]
    await state.set_state(fsm_state)
    await state.update_data(student_id=student_id, field=field)
    student = await db.get_user(student_id)
    name = student["name"] if student else str(student_id)
    current = (student or {}).get(field) or "не задано"
    await call.message.answer(
        f"Редактирую <b>{label}</b> для {name}.\n"
        f"Сейчас: <i>{current}</i>\n\n"
        f"Пришли новое значение (или <code>—</code> чтобы очистить поле):"
    )
    await call.answer()


async def _save_edit(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    student_id = data["student_id"]
    field = data["field"]
    value = (message.text or "").strip()
    if value in ("—", "-", ""):
        value = None
    await db.update_student_field(student_id, field, value)
    await state.clear()
    label = _FIELD_META[field][0]
    shown = value or "очищено"
    await message.answer(f"✅ {label} обновлено: <i>{shown}</i>")
    await _show_student_profile(message, student_id)


@router.callback_query(F.data.startswith("edit_materials:"))
async def edit_materials_start(call: CallbackQuery, state: FSMContext):
    await _start_edit(call, state, "materials_url")

@router.callback_query(F.data.startswith("edit_level:"))
async def edit_level_start(call: CallbackQuery, state: FSMContext):
    await _start_edit(call, state, "level")

@router.callback_query(F.data.startswith("edit_progress:"))
async def edit_progress_start(call: CallbackQuery, state: FSMContext):
    await _start_edit(call, state, "progress")

@router.callback_query(F.data.startswith("edit_notes:"))
async def edit_notes_start(call: CallbackQuery, state: FSMContext):
    await _start_edit(call, state, "notes")


@router.message(AdminStates.editing_materials)
async def edit_materials_save(message: Message, state: FSMContext):
    await _save_edit(message, state)

@router.message(AdminStates.editing_level)
async def edit_level_save(message: Message, state: FSMContext):
    await _save_edit(message, state)

@router.message(AdminStates.editing_progress)
async def edit_progress_save(message: Message, state: FSMContext):
    await _save_edit(message, state)

@router.message(AdminStates.editing_notes)
async def edit_notes_save(message: Message, state: FSMContext):
    await _save_edit(message, state)
