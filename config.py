"""Конфигурация бота. Значения берутся из файла .env."""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or "0")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow").strip()

# Реквизиты для оплаты — этот текст бот показывает ученику и шлёт в напоминаниях.
# Многострочный текст можно задать в .env через \n.
PAYMENT_DETAILS = os.getenv(
    "PAYMENT_DETAILS",
    "Реквизиты для оплаты пока не заданы. Укажи их в файле .env (PAYMENT_DETAILS).",
).replace("\\n", "\n").strip()

# Цена одного урока — для показа суммы к оплате. Можно поменять в .env.
LESSON_PRICE_RUB = int(os.getenv("LESSON_PRICE_RUB", "1100") or "1100")
LESSON_PRICE_BYN = int(os.getenv("LESSON_PRICE_BYN", "35") or "35")

# Путь к базе данных.
# На хостинге Amvera папка /data сохраняется между перезапусками — используем её,
# чтобы не терять записи и баланс уроков. Локально — файл рядом с проектом.
if os.path.isdir("/data"):
    DB_PATH = "/data/tutor_bot.db"
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "tutor_bot.db")

if not BOT_TOKEN:
    raise RuntimeError(
        "Не задан BOT_TOKEN. Скопируй .env.example в .env и впиши токен от @BotFather."
    )
