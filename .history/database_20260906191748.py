import aiosqlite # type: ignore
from datetime import date

DB_NAME = "coordinator.db"

async def init_db():
    """Создает таблицы в базе данных при первом запуске, если их еще нет"""
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Таблица сотрудников (добавили поле duties)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                duties TEXT,
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

        await db.commit()


async def add_user(telegram_id: int, full_name: str, role: str, duties: str):
    """Записывает нового сотрудника или обновляет его данные"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (telegram_id, full_name, role, duties)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET 
                full_name=excluded.full_name,
                role=excluded.role,
                duties=excluded.duties
        """, (telegram_id, full_name, role, duties))
        await db.commit()


async def get_user(telegram_id: int):
    """Проверяет, зарегистрирован ли уже пользователь"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT telegram_id, full_name, role, duties FROM users WHERE telegram_id = ?", 
            (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"telegram_id": row[0], "full_name": row[1], "role": row[2], "duties": row[3]}
            return None