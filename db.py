# db.py
import asyncpg
from datetime import date, datetime, timedelta
from typing import List, Optional, Any
from config import DATABASE_URL

_pool: Optional[asyncpg.pool.Pool] = None

async def init_db_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    async with _pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            id SERIAL PRIMARY KEY,
            habit_id INT REFERENCES habits(id) ON DELETE CASCADE,
            done_date DATE NOT NULL
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id SERIAL PRIMARY KEY,
            day_of_week INT NOT NULL, -- 0 = Monday ... 6 = Sunday
            text TEXT NOT NULL
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """)

# ---------------- Habit functions ----------------
async def add_habit(name: str) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("INSERT INTO habits (name) VALUES ($1) RETURNING id", name)
        return row["id"]

async def list_habits() -> List[asyncpg.Record]:
    async with _pool.acquire() as conn:
        return await conn.fetch("SELECT id, name FROM habits ORDER BY id")

async def mark_done(habit_id: int, when: Optional[date] = None) -> bool:
    if when is None:
        when = date.today()
    async with _pool.acquire() as conn:
        exists = await conn.fetchrow("SELECT 1 FROM progress WHERE habit_id=$1 AND done_date=$2", habit_id, when)
        if exists:
            return False
        await conn.execute("INSERT INTO progress (habit_id, done_date) VALUES ($1, $2)", habit_id, when)
        return True

async def habit_stats(habit_id: int) -> dict:
    async with _pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM progress WHERE habit_id=$1", habit_id)
        last_row = await conn.fetchrow("SELECT done_date FROM progress WHERE habit_id=$1 ORDER BY done_date DESC LIMIT 1", habit_id)
        last_done = last_row["done_date"].isoformat() if last_row else None

        # compute streak (consecutive days up to today)
        streak = 0
        cur_date = date.today()
        while True:
            exists = await conn.fetchval("SELECT 1 FROM progress WHERE habit_id=$1 AND done_date=$2", habit_id, cur_date)
            if exists:
                streak += 1
                cur_date = cur_date.fromordinal(cur_date.toordinal() - 1)
            else:
                break

        return {"total": total or 0, "last_done": last_done, "streak": streak}

async def delete_habit(habit_id: int) -> bool:
    """Удаляет привычку (и связанные прогрессы по ON DELETE CASCADE). Возвращает True если удалено."""
    async with _pool.acquire() as conn:
        res = await conn.execute("DELETE FROM habits WHERE id=$1", habit_id)
        # res like "DELETE <n>"
        return res.endswith("DELETE 1") or res.endswith("DELETE 1\r\n")

# ---------------- Schedule functions ----------------
async def set_schedule_for_day(day_of_week: int, text: str):
    async with _pool.acquire() as conn:
        exists = await conn.fetchrow("SELECT id FROM schedules WHERE day_of_week=$1", day_of_week)
        if exists:
            await conn.execute("UPDATE schedules SET text=$1 WHERE day_of_week=$2", text, day_of_week)
        else:
            await conn.execute("INSERT INTO schedules (day_of_week, text) VALUES ($1, $2)", day_of_week, text)

async def get_schedule_for_day(day_of_week: int) -> Optional[str]:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT text FROM schedules WHERE day_of_week=$1", day_of_week)
        return row["text"] if row else None

async def list_all_schedules() -> List[asyncpg.Record]:
    async with _pool.acquire() as conn:
        return await conn.fetch("SELECT day_of_week, text FROM schedules ORDER BY day_of_week")

async def delete_schedule_for_day(day_of_week: int) -> bool:
    async with _pool.acquire() as conn:
        res = await conn.execute("DELETE FROM schedules WHERE day_of_week=$1", day_of_week)
        return res.endswith("DELETE 1") or res.endswith("DELETE 1\r\n")

# ---------------- Notes ----------------
async def add_note(content: str) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("INSERT INTO notes (content) VALUES ($1) RETURNING id", content)
        return row["id"]

async def list_notes() -> List[asyncpg.Record]:
    async with _pool.acquire() as conn:
        return await conn.fetch("SELECT id, content, created_at FROM notes ORDER BY id")

async def delete_note(note_id: int) -> bool:
    async with _pool.acquire() as conn:
        res = await conn.execute("DELETE FROM notes WHERE id=$1", note_id)
        return res.endswith("DELETE 1") or res.endswith("DELETE 1\r\n")

async def get_all_notes_texts() -> List[asyncpg.Record]:
    async with _pool.acquire() as conn:
        return await conn.fetch("SELECT id, content FROM notes ORDER BY id")

async def cleanup_old_notes(days: int = 3) -> int:
    """Удаляет заметки старше `days` дней. Возвращает количество удалённых записей."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with _pool.acquire() as conn:
        # Возвращаем количество удалённых строк. PostgreSQL: DELETE ... RETURNING id
        rows = await conn.fetch("DELETE FROM notes WHERE created_at < $1 RETURNING id", cutoff)
        return len(rows)
