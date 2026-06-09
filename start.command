#!/bin/bash
# Запускалка бота репетитора для macOS.
# Запуск: в Терминале напиши  bash  (с пробелом) и перетащи сюда этот файл, затем Enter.
# Либо двойной клик (если разрешён запуск).

cd "$(dirname "$0")"
clear
echo "============================================"
echo "   Настройка и запуск бота репетитора"
echo "============================================"
echo

# 1. Проверяем, установлен ли Python
if ! command -v python3 &>/dev/null; then
  echo "❌ На компьютере не установлен Python."
  echo
  echo "Что делать:"
  echo "  1. Открой страницу: https://www.python.org/downloads/"
  echo "  2. Нажми жёлтую кнопку «Download Python»."
  echo "  3. Открой скачанный файл и установи (просто жми «Продолжить»)."
  echo "  4. Потом запусти этот файл start.command снова."
  echo
  read -p "Нажми Enter, чтобы закрыть это окно."
  exit 1
fi

# 2. Если бот ещё не настроен — спрашиваем данные и сохраняем
if [ ! -f .env ]; then
  echo "Настроим бота. Понадобятся 2 вещи из Телеграма."
  echo "(если их ещё нет — напиши в чат Claude, подскажу где взять)"
  echo
  read -p "1) Вставь ТОКЕН бота (от @BotFather): " TOKEN
  read -p "2) Вставь свой ID, число (от @userinfobot): " AID
  echo
  echo "3) Реквизиты для оплаты — что увидят ученики."
  read -p "   Напиши одной строкой (например: Сбер 1234 5678, Катя): " PAY
  {
    echo "BOT_TOKEN=$TOKEN"
    echo "ADMIN_ID=$AID"
    echo "PAYMENT_DETAILS=$PAY"
    echo "TIMEZONE=Europe/Moscow"
  } > .env
  echo
  echo "✅ Настройки сохранены."
  echo
fi

# 3. Устанавливаем нужные компоненты (только при первом запуске это займёт минуту)
echo "Проверяю компоненты бота..."
python3 -m pip install --quiet --user -r requirements.txt 2>/dev/null \
  || python3 -m pip install --quiet --break-system-packages -r requirements.txt

echo
echo "🚀 Запускаю бота!"
echo "   ─ НЕ закрывай это окно, пока бот должен работать."
echo "   ─ Чтобы остановить бота — закрой окно или нажми Ctrl+C."
echo
python3 main.py

echo
read -p "Бот остановлен. Нажми Enter, чтобы закрыть окно."
