"""Хендлеры для учителя-админа. Доступны только пользователю с ADMIN_ID."""
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
from config import ADMIN_ID, PAYMENT_DETAILS
from states import AdminStates
from utils import extract_file, send_stored_file, fmt_dt

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


# ---------- Все записи ----------

@router.message(F.text == "🗓 Все записи")
async def all_bookings(message: Message):
    bookings = await db.all_upcoming_bookings()
    if not bookings:
        await message.answer("Предстоящих записей нет.")
        return
    lines = []
    for b in bookings:
        uname = f"@{b['student_username']}" if b["student_username"] else b["student_name"]
        lines.append(f"• {fmt_dt(b['start_at'])} — {uname}")
    await message.answer("🗓 Предстоящие уроки:\n" + "\n".join(lines))


# ---------- Провести урок (списать занятие) ----------

@router.message(F.text == "✅ Провести урок")
async def lesson_done_menu(message: Message):
    students = await db.all_users()
    students = [s for s in students if s["tg_id"] != ADMIN_ID]
    if not students:
        await message.answer("Пока нет учеников.")
        return
    await message.answer(
        "Выбери ученика, чтобы списать 1 урок:",
        reply_markup=kb.students_kb(students, "done"),
    )


@router.callback_query(F.data.startswith("done:"))
async def lesson_done(call: CallbackQuery, bot: Bot):
    student_id = int(call.data.split(":")[1])
    left = await db.change_lessons(student_id, -1)
    student = await db.get_user(student_id)
    await call.message.edit_text(f"✅ Урок списан у {student['name']}. Осталось: {left}.")
    await call.answer()
    try:
        msg = f"Урок проведён ✅ Осталось оплаченных уроков: {left}."
        if left == 1:
            msg += f"\n\n🔔 Остался последний урок — пора оплатить занятия.\n\nРеквизиты:\n{PAYMENT_DETAILS}"
        elif left == 0:
            msg += f"\n\n🔔 Оплаченные уроки закончились. Реквизиты для оплаты:\n{PAYMENT_DETAILS}"
        await bot.send_message(student_id, msg)
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


# ---------- Отметить оплату (начислить уроки) ----------

@router.message(F.text == "💰 Отметить оплату")
async def payment_mark_menu(message: Message):
    students = await db.all_users()
    students = [s for s in students if s["tg_id"] != ADMIN_ID]
    if not students:
        await message.answer("Пока нет учеников.")
        return
    await message.answer(
        "Кто оплатил? Выбери ученика, потом укажешь число уроков:",
        reply_markup=kb.students_kb(students, "pay"),
    )


@router.callback_query(F.data.startswith("pay:"))
async def payment_mark_pick(call: CallbackQuery, state: FSMContext):
    student_id = int(call.data.split(":")[1])
    await state.set_state(AdminStates.adding_payment)
    await state.update_data(student_id=student_id)
    await call.message.answer("Сколько уроков начислить? Пришли число (например, 8).")
    await call.answer()


@router.message(AdminStates.adding_payment)
async def payment_mark_receive(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("Нужно положительное число. Попробуй ещё раз.")
        return
    lessons = int(text)
    data = await state.get_data()
    student_id = data["student_id"]
    new_total = await db.change_lessons(student_id, lessons)
    await db.add_payment(student_id, "manual", lessons, 0)
    await state.clear()
    student = await db.get_user(student_id)
    await message.answer(
        f"✅ {student['name']}: начислено {lessons} ур. На балансе: {new_total}.",
        reply_markup=kb.admin_menu(),
    )
    try:
        await bot.send_message(
            student_id,
            f"💳 Оплата получена, спасибо! Начислено уроков: {lessons}. На балансе: {new_total}.",
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
    left = student["lessons_left"] if student else 0
    try:
        await bot.send_message(
            student_id,
            f"🔔 Напоминание об оплате.\n\nОсталось оплаченных уроков: {left}.\n\n"
            f"Реквизиты:\n{PAYMENT_DETAILS}",
        )
        await call.message.edit_text(f"✅ Напоминание отправлено: {student['name']}.")
    except Exception:
        await call.message.edit_text("⚠️ Не удалось отправить (ученик не запускал бота).")
    await call.answer()


# ---------- Ученики ----------

@router.message(F.text == "👥 Ученики")
async def list_students(message: Message):
    students = await db.all_users()
    students = [s for s in students if s["tg_id"] != ADMIN_ID]
    if not students:
        await message.answer("Пока нет учеников.")
        return
    lines = [f"• {s['name']} — оплачено уроков: {s['lessons_left']}" for s in students]
    await message.answer("👥 Ученики:\n" + "\n".join(lines))


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
