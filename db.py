"""Слой работы с базой данных (SQLite через aiosqlite)."""
from __future__ import annotations
import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH


async def init_db() -> None:
    """Создаёт таблицы при первом запуске."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                tg_id       INTEGER PRIMARY KEY,
                name        TEXT,
                username    TEXT,
                lessons_left INTEGER DEFAULT 0,
                created_at  TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS slots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                start_at    TEXT NOT NULL,            -- 'YYYY-MM-DD HH:MM'
                student_id  INTEGER,                  -- NULL = свободен
                reminded_24 INTEGER DEFAULT 0,
                reminded_2  INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS homework (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  INTEGER NOT NULL,
                task_text   TEXT,
                task_file   TEXT,                     -- file_id материала от учителя
                answer_file TEXT,                     -- file_id ответа ученика
                answer_text TEXT,
                status      TEXT DEFAULT 'assigned',  -- assigned / submitted
                created_at  TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_templates (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                day_of_week INTEGER NOT NULL,   -- 0=Пн, 6=Вс
                time_str    TEXT NOT NULL,       -- 'ЧЧ:ММ'
                UNIQUE(day_of_week, time_str)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS student_schedules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,   -- 0=Пн … 6=Вс
                time_str    TEXT NOT NULL,       -- 'ЧЧ:ММ'
                UNIQUE(student_id, day_of_week, time_str)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  INTEGER NOT NULL,
                package     TEXT,
                lessons     INTEGER,
                amount      INTEGER,
                created_at  TEXT
            )
            """
        )
        await db.commit()


# ---------- Пользователи ----------

async def add_user(tg_id: int, name: str, username: str | None) -> bool:
    """Добавляет пользователя. Возвращает True если ученик новый."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT tg_id FROM users WHERE tg_id = ?", (tg_id,))
        is_new = (await cur.fetchone()) is None
        await db.execute(
            "INSERT OR IGNORE INTO users (tg_id, name, username, created_at) VALUES (?, ?, ?, ?)",
            (tg_id, name, username, datetime.now().isoformat(timespec="seconds")),
        )
        # имя/username обновляем на случай изменений
        await db.execute(
            "UPDATE users SET name = ?, username = ? WHERE tg_id = ?",
            (name, username, tg_id),
        )
        await db.commit()
    return is_new


async def get_user(tg_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users ORDER BY name")
        return [dict(r) for r in await cur.fetchall()]


async def change_lessons(tg_id: int, delta: int) -> int:
    """Меняет счётчик уроков «к оплате» на delta. Возвращает новое значение.
    Поле lessons_left здесь = сколько уроков ученик уже взял и пока не оплатил."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET lessons_left = MAX(0, lessons_left + ?) WHERE tg_id = ?",
            (delta, tg_id),
        )
        await db.commit()
        cur = await db.execute("SELECT lessons_left FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
        return row[0] if row else 0


async def reset_lessons(tg_id: int) -> int:
    """Обнуляет счётчик уроков к оплате (после оплаты). Возвращает сколько было до обнуления."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT lessons_left FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
        was = row[0] if row else 0
        await db.execute("UPDATE users SET lessons_left = 0 WHERE tg_id = ?", (tg_id,))
        await db.commit()
        return was


# ---------- Слоты / запись ----------

async def add_slot(start_at: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO slots (start_at) VALUES (?)", (start_at,))
        await db.commit()


async def free_slots() -> list[dict]:
    """Свободные слоты в будущем."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM slots WHERE student_id IS NULL AND start_at >= ? ORDER BY start_at",
            (now,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_slot(slot_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def book_slot(slot_id: int, student_id: int) -> bool:
    """Бронирует слот, если он ещё свободен. True при успехе."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE slots SET student_id = ? WHERE id = ? AND student_id IS NULL",
            (student_id, slot_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def cancel_slot(slot_id: int, student_id: int) -> bool:
    """Освобождает слот, если он принадлежит этому ученику."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE slots SET student_id = NULL, reminded_24 = 0, reminded_2 = 0 "
            "WHERE id = ? AND student_id = ?",
            (slot_id, student_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def student_bookings(student_id: int) -> list[dict]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM slots WHERE student_id = ? AND start_at >= ? ORDER BY start_at",
            (student_id, now),
        )
        return [dict(r) for r in await cur.fetchall()]


async def all_upcoming_bookings() -> list[dict]:
    """Все будущие записи с именем ученика — для админа и напоминаний."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT s.*, u.name AS student_name, u.username AS student_username
            FROM slots s JOIN users u ON u.tg_id = s.student_id
            WHERE s.student_id IS NOT NULL AND s.start_at >= ?
            ORDER BY s.start_at
            """,
            (now,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def mark_reminded(slot_id: int, field: str) -> None:
    assert field in ("reminded_24", "reminded_2")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE slots SET {field} = 1 WHERE id = ?", (slot_id,))
        await db.commit()


# ---------- Домашние задания ----------

async def add_homework(student_id: int, task_text: str, task_file: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO homework (student_id, task_text, task_file, created_at) "
            "VALUES (?, ?, ?, ?)",
            (student_id, task_text, task_file, datetime.now().isoformat(timespec="seconds")),
        )
        await db.commit()


async def current_homework(student_id: int) -> dict | None:
    """Последнее выданное ДЗ ученика."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM homework WHERE student_id = ? ORDER BY id DESC LIMIT 1",
            (student_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def submit_homework(hw_id: int, answer_file: str | None, answer_text: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE homework SET answer_file = ?, answer_text = ?, status = 'submitted' WHERE id = ?",
            (answer_file, answer_text, hw_id),
        )
        await db.commit()


# ---------- Платежи ----------

async def add_payment(student_id: int, package: str, lessons: int, amount: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO payments (student_id, package, lessons, amount, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (student_id, package, lessons, amount, datetime.now().isoformat(timespec="seconds")),
        )
        await db.commit()


# ---------- Слоты по диапазону дат ----------

async def slots_in_range(date_from: str, date_to: str) -> list[dict]:
    """Все слоты за период [date_from..date_to] (формат 'YYYY-MM-DD').
    LEFT JOIN users — чтобы получить имя ученика если слот занят."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT s.*, u.name AS student_name, u.username AS student_username
            FROM slots s
            LEFT JOIN users u ON u.tg_id = s.student_id
            WHERE s.start_at >= ? AND s.start_at <= ?
            ORDER BY s.start_at
            """,
            (date_from + " 00:00", date_to + " 23:59"),
        )
        return [dict(r) for r in await cur.fetchall()]


# ---------- Шаблон расписания ----------

async def add_template(day_of_week: int, time_str: str) -> None:
    """Добавляет регулярный слот в шаблон (0=Пн … 6=Вс). Дубликаты игнорируются."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO schedule_templates (day_of_week, time_str) VALUES (?, ?)",
            (day_of_week, time_str),
        )
        await db.commit()


async def remove_template(template_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM schedule_templates WHERE id = ?", (template_id,))
        await db.commit()


async def get_templates() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM schedule_templates ORDER BY day_of_week, time_str"
        )
        return [dict(r) for r in await cur.fetchall()]


# ---------- Личное расписание ученика ----------

async def get_student_schedule(student_id: int) -> list[dict]:
    """Возвращает личное расписание ученика (дни/время)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM student_schedules WHERE student_id = ? ORDER BY day_of_week, time_str",
            (student_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def add_student_schedule_item(student_id: int, day_of_week: int, time_str: str) -> None:
    """Добавляет один слот в личное расписание ученика."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO student_schedules (student_id, day_of_week, time_str) VALUES (?, ?, ?)",
            (student_id, day_of_week, time_str),
        )
        await db.commit()


async def remove_student_schedule_item(item_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM student_schedules WHERE id = ?", (item_id,))
        await db.commit()


async def generate_student_slots(student_id: int, weeks: int = 4) -> int:
    """Генерирует предзабронированные слоты для ученика на N недель вперёд.
    Если на это время уже есть свободный общий слот — бронирует его.
    Если нет — создаёт персональный слот.
    Возвращает количество созданных/забронированных слотов."""
    schedule = await get_student_schedule(student_id)
    if not schedule:
        return 0

    today = datetime.now().date()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    by_day: dict[int, list[str]] = {}
    for item in schedule:
        by_day.setdefault(item["day_of_week"], []).append(item["time_str"])

    added = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for delta in range(weeks * 7):
            day = today + timedelta(days=delta)
            dow = day.weekday()
            if dow not in by_day:
                continue
            for time_str in by_day[dow]:
                start_at = f"{day.strftime('%Y-%m-%d')} {time_str}"
                if start_at <= now_str:
                    continue
                # Уже есть слот для этого ученика в это время?
                cur = await db.execute(
                    "SELECT id FROM slots WHERE start_at = ? AND student_id = ?",
                    (start_at, student_id),
                )
                if await cur.fetchone():
                    continue  # уже есть
                # Есть свободный общий слот в это время — занимаем его
                cur = await db.execute(
                    "SELECT id FROM slots WHERE start_at = ? AND student_id IS NULL",
                    (start_at,),
                )
                free = await cur.fetchone()
                if free:
                    await db.execute(
                        "UPDATE slots SET student_id = ? WHERE id = ?",
                        (student_id, free[0]),
                    )
                else:
                    # Создаём персональный слот
                    await db.execute(
                        "INSERT INTO slots (start_at, student_id) VALUES (?, ?)",
                        (start_at, student_id),
                    )
                added += 1
        await db.commit()
    return added


async def generate_slots_from_templates(weeks: int = 4) -> int:
    """Создаёт слоты на ближайшие N недель по шаблону. Возвращает кол-во новых слотов."""
    templates = await get_templates()
    if not templates:
        return 0

    today = datetime.now().date()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    by_day: dict[int, list[str]] = {}
    for tpl in templates:
        by_day.setdefault(tpl["day_of_week"], []).append(tpl["time_str"])

    added = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for delta in range(weeks * 7):
            day = today + timedelta(days=delta)
            dow = day.weekday()          # 0=Пн
            if dow not in by_day:
                continue
            for time_str in by_day[dow]:
                start_at = f"{day.strftime('%Y-%m-%d')} {time_str}"
                if start_at <= now_str:
                    continue
                cur = await db.execute(
                    "SELECT id FROM slots WHERE start_at = ?", (start_at,)
                )
                if await cur.fetchone():
                    continue            # слот уже есть
                await db.execute("INSERT INTO slots (start_at) VALUES (?)", (start_at,))
                added += 1
        await db.commit()
    return added
