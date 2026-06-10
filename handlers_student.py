"""Хендлеры для учеников."""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
from config import ADMIN_ID, PAYMENT_DETAILS, LESSON_PRICE_RUB, LESSON_PRICE_BYN
from states import StudentStates
from utils import extract_file, send_stored_file, fmt_dt, week_bounds, week_title

router = Router()

ABOUT_TEXT = (
    "🇬🇧 <b>Школа английского</b>\n\n"
    "Здесь ты можешь записаться на урок, оплатить занятия, "
    "получать домашние задания и напоминания.\n\n"
    "По всем вопросам пиши прямо в этот чат — учитель ответит."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    is_new = await db.add_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username,
    )
    hello = f"Привет, {message.from_user.first_name}! 👋\nВыбери действие в меню ниже."
    await message.answer(hello, reply_markup=kb.student_menu())
    if message.from_user.id == ADMIN_ID:
        await message.answer("Ты вошла как админ. Команда /admin — панель учителя.")
        return
    if is_new:
        uname = f" (@{message.from_user.username})" if message.from_user.username else ""
        await bot.send_message(
            ADMIN_ID,
            f"🆕 Новый ученик: <b>{message.from_user.full_name}</b>{uname}\n"
            f"Назначь ему расписание 👇",
            reply_markup=kb.new_student_notify_kb(message.from_user.id),
        )


# ---------- Мои материалы ----------

@router.message(F.text == "📎 Мои материалы")
async def show_materials(message: Message):
    user = await db.get_user(message.from_user.id)
    url = user.get("materials_url") if user else None
    if url:
        await message.answer(
            f"📎 <b>Твои учебные материалы:</b>\n\n{url}",
            disable_web_page_preview=False,
        )
    else:
        await message.answer(
            "📎 Учитель ещё не добавил ссылку на твои материалы.\n"
            "Она появится здесь, как только будет готова."
        )


# ---------- Мой профиль ----------

@router.message(F.text == "👤 Мой профиль")
async def my_profile(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Нажми /start, чтобы зарегистрироваться.")
        return

    schedule = await db.get_student_schedule(message.from_user.id)
    if schedule:
        sched_text = "\n".join(
            f"  • {kb.DAYS_NAMES[i['day_of_week']]} {i['time_str']}"
            for i in schedule
        )
    else:
        sched_text = "  пока не назначено"

    level = user.get("level") or "—"
    progress = user.get("progress") or "—"
    materials = user.get("materials_url") or "—"
    owed = user["lessons_left"]
    rub = owed * LESSON_PRICE_RUB
    byn = owed * LESSON_PRICE_BYN

    await message.answer(
        f"👤 <b>{user['name']}</b>\n\n"
        f"📊 <b>Уровень:</b> {level}\n"
        f"📝 <b>Прогресс:</b> {progress}\n"
        f"🔗 <b>Материалы:</b> {materials}\n\n"
        f"📋 <b>Постоянное расписание:</b>\n{sched_text}\n\n"
        f"💳 <b>Уроков к оплате:</b> {owed}"
        + (f" ({rub} ₽ / {byn} BYN)" if owed else ""),
        disable_web_page_preview=True,
    )


# ---------- Перенос / отмена занятия ----------

@router.message(F.text == "🔄 Перенести/Отменить занятие")
async def my_bookings(message: Message):
    bookings = await db.student_bookings(message.from_user.id)
    if not bookings:
        await message.answer(
            "У тебя нет предстоящих уроков.\n"
            "Записаться можно через «📆 Моё расписание»."
        )
        return
    await message.answer(
        "Твои ближайшие уроки:\n"
        "❌ — отменить урок, 🔄 — перенести на другое время",
        reply_markup=kb.bookings_kb(bookings),
    )


# ---------- Запись на урок ----------

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
    uname = f"@{call.from_user.username}" if call.from_user.username else call.from_user.full_name
    await bot.send_message(
        ADMIN_ID, f"🆕 Новая запись: {uname} — {fmt_dt(slot['start_at'])}"
    )


# ---------- Моё расписание — недельный вид ----------

async def _send_student_week(target, student_id: int, offset: int) -> None:
    """Отправляет или редактирует сообщение с расписанием на неделю.
    target — Message (send) или CallbackQuery (edit).
    """
    date_from, date_to = week_bounds(offset)
    slots = await db.slots_in_range(date_from, date_to)

    title = week_title(offset)
    visible = [s for s in slots if s["student_id"] is None or s["student_id"] == student_id]

    if visible:
        text = (
            f"📆 <b>Расписание: {title}</b>\n\n"
            "📅 — свободно, нажми чтобы записаться\n"
            "✅ — твой урок (нажми → отменить)  🔄 — перенести"
        )
    else:
        text = (
            f"📆 <b>Расписание: {title}</b>\n\n"
            "На эту неделю слотов нет.\n"
            "Листай вперёд ▶ — там могут быть свободные слоты."
        )

    markup = kb.student_week_kb(slots, student_id, offset)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text.in_({"📆 Моё расписание", "🔔 Мои записи", "📅 Моё расписание"}))
async def my_schedule(message: Message):
    await _send_student_week(message, message.from_user.id, offset=0)


@router.callback_query(F.data.startswith("sweek:"))
async def student_week_nav(call: CallbackQuery):
    offset = int(call.data.split(":")[1])
    await _send_student_week(call, call.from_user.id, offset)


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


# ---------- Перенос урока ----------

@router.callback_query(F.data.startswith("reschedule:"))
async def reschedule_start(call: CallbackQuery, state: FSMContext):
    slot_id = int(call.data.split(":")[1])
    slot = await db.get_slot(slot_id)
    if not slot or slot["student_id"] != call.from_user.id:
        await call.answer("Слот не найден.", show_alert=True)
        return
    free = await db.free_slots()
    # Убираем текущий слот из списка свободных (его ещё нет там, но на всякий случай)
    free = [s for s in free if s["id"] != slot_id]
    if not free:
        await call.answer("Свободных слотов для переноса пока нет.", show_alert=True)
        return
    await state.set_state(StudentStates.rescheduling)
    await state.update_data(old_slot_id=slot_id)
    await call.message.answer(
        f"🔄 Перенос урока <b>{fmt_dt(slot['start_at'])}</b>.\n\nВыбери новое время:",
        reply_markup=kb.reschedule_slots_kb(free),
    )
    await call.answer()


@router.callback_query(StudentStates.rescheduling, F.data.startswith("rebook:"))
async def reschedule_pick(call: CallbackQuery, state: FSMContext, bot: Bot):
    new_slot_id = int(call.data.split(":")[1])
    data = await state.get_data()
    old_slot_id = data["old_slot_id"]

    old_slot = await db.get_slot(old_slot_id)
    ok = await db.cancel_slot(old_slot_id, call.from_user.id)
    if not ok:
        await call.answer("Не удалось освободить старый слот.", show_alert=True)
        await state.clear()
        return

    booked = await db.book_slot(new_slot_id, call.from_user.id)
    if not booked:
        await call.message.answer(
            "⚠️ Выбранный слот только что заняли.\n"
            "Старый урок отменён — запишись на другое время через «📆 Моё расписание»."
        )
        await state.clear()
        await call.answer()
        return

    new_slot = await db.get_slot(new_slot_id)
    await state.clear()
    await call.message.edit_text(
        f"✅ Урок перенесён!\n"
        f"Было: {fmt_dt(old_slot['start_at'])}\n"
        f"Стало: {fmt_dt(new_slot['start_at'])}"
    )
    await call.answer("Перенесено!")
    uname = f"@{call.from_user.username}" if call.from_user.username else call.from_user.full_name
    await bot.send_message(
        ADMIN_ID,
        f"🔄 Перенос урока: {uname}\n"
        f"Было: {fmt_dt(old_slot['start_at'])}\n"
        f"Стало: {fmt_dt(new_slot['start_at'])}",
    )


@router.callback_query(StudentStates.rescheduling, F.data == "reschedule_cancel")
async def reschedule_abort(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Перенос отменён. Урок остался на прежнем времени.")
    await call.answer()


# ---------- Оплата ----------

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
