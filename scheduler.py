"""Напоминания об уроках через APScheduler."""
from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db
import keyboards as kb
from config import TIMEZONE, ADMIN_ID


async def check_reminders(bot: Bot) -> None:
    """Шлёт напоминания за 24 часа и за 2 часа до урока."""
    now = datetime.now()
    for b in await db.all_upcoming_bookings():
        try:
            start = datetime.strptime(b["start_at"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        hours = (start - now).total_seconds() / 3600
        if hours <= 0:
            continue

        if hours <= 24 and not b["reminded_24"]:
            try:
                await bot.send_message(
                    b["student_id"],
                    f"🔔 Напоминание: завтра в {start.strftime('%H:%M')} у нас урок английского 🇬🇧",
                    reply_markup=kb.reminder_kb(b["id"]),
                )
            except Exception:
                pass
            await db.mark_reminded(b["id"], "reminded_24")

        if hours <= 2 and not b["reminded_2"]:
            try:
                await bot.send_message(
                    b["student_id"],
                    f"⏰ Через пару часов ({start.strftime('%H:%M')}) начинаем урок. До встречи!",
                )
            except Exception:
                pass
            await db.mark_reminded(b["id"], "reminded_2")


async def daily_summary(bot: Bot) -> None:
    """Утренняя сводка учителю: уроки на сегодня."""
    today = datetime.now().strftime("%Y-%m-%d")
    bookings = [b for b in await db.all_upcoming_bookings() if b["start_at"].startswith(today)]
    if not bookings:
        return
    lines = []
    for b in bookings:
        uname = f"@{b['student_username']}" if b["student_username"] else b["student_name"]
        lines.append(f"• {b['start_at'][-5:]} — {uname}")
    await bot.send_message(ADMIN_ID, "☀️ Уроки на сегодня:\n" + "\n".join(lines))


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    # проверяем напоминания каждые 10 минут
    scheduler.add_job(check_reminders, "interval", minutes=10, args=[bot])
    # утренняя сводка в 08:00
    scheduler.add_job(daily_summary, "cron", hour=8, minute=0, args=[bot])
    return scheduler
