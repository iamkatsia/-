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

# --- адрес Amvera зашит прямо здесь, вводить ничего не нужно ---
AMVERA_URL="https://iamkatsia@git.msk0.amvera.ru/iamkatsia/bot-anglijskij"
git remote remove amvera >/dev/null 2>&1
git remote add amvera "$AMVERA_URL"

# --- сохранить изменения и отправить ---
git add -A
git commit -m "Обновление $(date '+%Y-%m-%d %H:%M')" >/dev/null 2>&1

echo
echo "Отправляю изменения на Amvera..."
echo "👉 Спросит ТОЛЬКО пароль от Amvera (Password) — введи его."
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
