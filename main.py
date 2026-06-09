"""Точка входа. Запуск: python main.py"""
# Тест авто-деплоя через GitHub → Amvera (2026-06-09)
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import db
from config import BOT_TOKEN
import handlers_admin
import handlers_student
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    await db.init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # порядок важен: админ-роутер первым (он с фильтром по ADMIN_ID)
    dp.include_router(handlers_admin.router)
    dp.include_router(handlers_student.router)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    logging.info("Бот запущен. Останов — Ctrl+C.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
