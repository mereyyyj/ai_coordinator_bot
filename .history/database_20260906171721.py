import aiosqlite # type: ignore
from datetime import datetime

# Название файла базы данных, который создастся в папке
DB_NAME = "coordinator.db"

async def init_db():
    """Создает таблицы в базе данных при первом запуске, если их еще нет"""
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Таблица сотрудников
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                role TEXT DEFAULT 'employee',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Таблица утренних планов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                date TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                structured_tasks TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
            )
        """)

        # 3. Таблица вечерних отчетов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                date TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                done_tasks TEXT,
                blockers TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
            )
        """)

        await db.commit() # Сохраняем изменения


# --- Функции для сохранения и получения данных ---

async def add_user(telegram_id: int, full_name: str, role: str = "employee"):
    """Записывает нового сотрудника в базу данных"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (telegram_id, full_name, role)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name
        """, (telegram_id, full_name, role))
        await db.commit()


async def get_all_users():
    """Возвращает список всех сотрудников из базы"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT telegram_id, full_name, role FROM users") as cursor:
            rows = await cursor.fetchall()
            return [{"telegram_id": r[0], "full_name": r[1], "role": r[2]} for r in rows]