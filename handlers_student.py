"""Хендлеры для учеников."""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
from config import ADMIN_ID, PAYMENT_DETAILS, LESSON_PRICE_RUB, LESSON_PRICE_BYN
from states import StudentStates
from utils import extract_file, send_stored_file, fmt_dt

router = Router()

ABOUT_TEXT = (
    "🇬🇧 <b>Школа английского</b>\n\n"
    "Здесь ты можешь записаться на урок, оплатить занятия, "
    "получать домашние задания и напоминания.\n\n"
    "По всем вопросам пиши прямо в этот чат — учитель ответит."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await db.add_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username,
    )
    hello = f"Привет, {message.from_user.first_name}! 👋\nВыбери действие в меню ниже."
    await message.answer(hello, reply_markup=kb.student_menu())
    if message.from_user.id == ADMIN_ID:
        await message.answer("Ты вошла как админ. Команда /admin — панель учителя.")


# ---------- Запись на урок ----------

@router.message(F.text == "📅 Записаться на урок")
async def show_slots(message: Message):
    slots = await db.free_slots()
    if not slots:
        await message.answer("Свободных слотов пока нет. Загляни позже 🙏")
        return
    await message.answer("Выбери удобное время:", reply_markup=kb.slots_kb(slots))


@router.callback_query(F.data.startswith("book:"))
async def book(call: CallbackQuery, bot: Bot):
    slot_id = int(call.data.split(":")[1])
    ok = await db.book_slot(slot_id, call.from_user.id)
    if not ok:
        await call.answer("Увы, этот слот только что заняли.", show_alert=True)
        return
    slot = await db.get_slot(slot_id)
    await call.message.edit_text(f"✅ Ты записана на {fmt_dt(slot['start_at'])}.")
    await call.answer("Записал!")
    # уведомление учителю
    uname = f"@{call.from_user.username}" if call.from_user.username else call.from_user.full_name
    await bot.send_message(
        ADMIN_ID, f"🆕 Новая запись: {uname} — {fmt_dt(slot['start_at'])}"
    )


# ---------- Мои записи ----------

@router.message(F.text == "🔔 Мои записи")
async def my_bookings(message: Message):
    bookings = await db.student_bookings(message.from_user.id)
    if not bookings:
        await message.answer("У тебя нет предстоящих записей.")
        return
    text = "Твои записи:\n" + "\n".join(f"• {fmt_dt(b['start_at'])}" for b in bookings)
    await message.answer(text, reply_markup=kb.bookings_kb(bookings))


@router.message(F.text == "📅 Моё расписание")
async def my_schedule(message: Message):
    bookings = await db.student_bookings(message.from_user.id)
    if not bookings:
        await message.answer("У тебя пока нет запланированных уроков. Запишись на удобное время 📅")
        return
    text = "🗓 Твоё расписание:\n" + "\n".join(f"• {fmt_dt(b['start_at'])}" for b in bookings)
    await message.answer(text)


@router.callback_query(F.data.startswith("cancel:"))
async def cancel(call: CallbackQuery, bot: Bot):
    slot_id = int(call.data.split(":")[1])
    slot = await db.get_slot(slot_id)
    ok = await db.cancel_slot(slot_id, call.from_user.id)
    if not ok:
        await call.answer("Не получилось отменить.", show_alert=True)
        return
    await call.message.edit_text(f"❌ Запись на {fmt_dt(slot['start_at'])} отменена.")
    await call.answer("Отменено")
    uname = f"@{call.from_user.username}" if call.from_user.username else call.from_user.full_name
    await bot.send_message(ADMIN_ID, f"⚠️ Отмена записи: {uname} — {fmt_dt(slot['start_at'])}")


@router.callback_query(F.data.startswith("confirm:"))
async def confirm(call: CallbackQuery):
    await call.answer("Спасибо, ждём на уроке! 👍")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ---------- Оплата (сколько уроков к оплате + реквизиты) ----------

@router.message(F.text == "💳 Оплата")
async def payment_menu(message: Message):
    user = await db.get_user(message.from_user.id)
    owed = user["lessons_left"] if user else 0
    rub = owed * LESSON_PRICE_RUB
    byn = owed * LESSON_PRICE_BYN
    await message.answer(
        f"💳 <b>Оплата</b>\n\n"
        f"Уроков к оплате: <b>{owed}</b>\n"
        f"К оплате: <b>{rub} ₽</b> или <b>{byn} BYN</b>\n\n"
        f"Реквизиты для оплаты:\n{PAYMENT_DETAILS}\n\n"
        "Оплата в конце месяца. После оплаты учитель отметит это в боте."
    )


# ---------- Домашнее задание ----------

@router.message(F.text == "📚 Домашнее задание")
async def show_homework(message: Message, bot: Bot):
    hw = await db.current_homework(message.from_user.id)
    if not hw:
        await message.answer("Пока нет выданных домашних заданий.")
        return
    text = hw["task_text"] or "Домашнее задание:"
    if hw["status"] == "submitted":
        text += "\n\n(Ты уже отправила ответ ✅)"
    await message.answer(text, reply_markup=kb.hw_submit_kb(hw["id"]))
    if hw["task_file"]:
        await send_stored_file(bot, message.from_user.id, hw["task_file"], "Материал к заданию")


@router.callback_query(F.data.startswith("hwsubmit:"))
async def hw_submit_start(call: CallbackQuery, state: FSMContext):
    hw_id = int(call.data.split(":")[1])
    await state.set_state(StudentStates.submitting_hw)
    await state.update_data(hw_id=hw_id)
    await call.message.answer("Пришли ответ: текст или файл/фото 📎")
    await call.answer()


@router.message(StudentStates.submitting_hw)
async def hw_submit_receive(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    hw_id = data["hw_id"]
    answer_file = extract_file(message)
    answer_text = message.text or message.caption
    await db.submit_homework(hw_id, answer_file, answer_text)
    await state.clear()
    await message.answer("✅ Ответ отправлен учителю!")
    # пересылаем учителю
    uname = message.from_user.full_name
    await bot.send_message(ADMIN_ID, f"📥 ДЗ сдал(а): {uname}")
    if answer_text:
        await bot.send_message(ADMIN_ID, f"Ответ: {answer_text}")
    if answer_file:
        await send_stored_file(bot, ADMIN_ID, answer_file, f"Файл от {uname}")


# ---------- О школе ----------

@router.message(F.text == "ℹ️ О школе")
async def about(message: Message):
    await message.answer(ABOUT_TEXT)
