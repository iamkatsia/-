#!/bin/bash
# ============================================================
#  Обновление бота на Amvera в один клик.
#  Просто дважды кликни по этому файлу.
#  Первый раз он попросит ссылку из Amvera — потом не будет.
# ============================================================

cd "$(dirname "$0")" || exit 1
clear
echo "============================================"
echo "   Обновление бота на Amvera"
echo "============================================"
echo

# --- проверим, что git установлен ---
if ! command -v git >/dev/null 2>&1; then
  echo "❌ На этом Маке не найден Git."
  echo "Открой программу «Терминал», вставь команду  xcode-select --install"
  echo "нажми Enter, установи, и запусти этот файл снова."
  echo
  read -r -p "Нажми Enter, чтобы закрыть." _
  exit 1
fi

# --- .gitignore: что НИКОГДА не уходит на Amvera ---
cat > .gitignore <<'GI'
.env
*.db
*.db-journal
__pycache__/
*.pyc
.DS_Store
GI

# --- убрать застрявшую блокировку, если есть ---
rm -f .git/index.lock 2>/dev/null

# --- если репозитория нет или он битый — создать заново ---
if ! git rev-parse HEAD >/dev/null 2>&1; then
  rm -rf .git
  git init -b master . >/dev/null 2>&1 || { git init . >/dev/null 2>&1; git checkout -b master >/dev/null 2>&1; }
fi

# --- имя и почта для коммитов (если не заданы) ---
git config user.email >/dev/null 2>&1 || git config user.email "e.tikhomirova.eng@gmail.com"
git config user.name  >/dev/null 2>&1 || git config user.name  "Kate"

# --- адрес Amvera (спросим один раз, дальше запомнится) ---
if ! git remote get-url amvera >/dev/null 2>&1; then
  echo "Похоже, это первый запуск. Нужна ссылка из Amvera."
  echo
  echo "Где её взять:"
  echo "  1. Зайди на сайт Amvera, открой свой проект с ботом."
  echo "  2. Найди вкладку/раздел с Git (там есть команды git remote add ...)."
  echo "  3. Скопируй ссылку вида:"
  echo "       https://git.amvera.ru/ТВОЙ_ЛОГИН/имя-проекта"
  echo
  read -r -p "Вставь сюда эту ссылку и нажми Enter: " AMVERA_URL
  AMVERA_URL="$(echo "$AMVERA_URL" | tr -d '[:space:]')"
  if [ -z "$AMVERA_URL" ]; then
    echo "Ссылку не ввели. Запусти файл ещё раз."
    read -r -p "Нажми Enter, чтобы закрыть." _
    exit 1
  fi
  git remote add amvera "$AMVERA_URL"
fi

# --- сохранить изменения и отправить ---
git add -A
git commit -m "Обновление $(date '+%Y-%m-%d %H:%M')" >/dev/null 2>&1

echo
echo "Отправляю изменения на Amvera..."
echo "👉 В ПЕРВЫЙ раз спросит логин и пароль от Amvera — введи их."
echo "   (пароль при вводе не виден — это нормально, печатай и жми Enter)"
echo
echo "--------------------------------------------"
git push -f amvera master
PUSH_OK=$?
echo "--------------------------------------------"
echo

if [ $PUSH_OK -eq 0 ]; then
  echo "✅ Готово! Изменения улетели на Amvera."
  echo "Бот пересоберётся сам за пару минут."
  echo "Можешь зайти на Amvera и глянуть вкладку «Логи»."
else
  echo "⚠️ Что-то пошло не так при отправке."
  echo "Чаще всего это неверный логин/пароль или ссылка."
  echo "Запусти файл ещё раз и проверь данные."
fi

echo
read -r -p "Нажми Enter, чтобы закрыть это окно." _
