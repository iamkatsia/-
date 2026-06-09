"""Слой работы с базой данных (SQLite через aiosqlite)."""
import aiosqlite
from datetime import datetime
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

async def add_user(tg_id: int, name: str, username: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
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
