import aiosqlite  # type: ignore
from datetime import date

DB_NAME = "coordinator.db"


async def init_db():
    """Создает таблицы в базе данных при первом запуске, если их еще нет"""
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Таблица сотрудников
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
                telegram_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                structured_tasks TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id),
                UNIQUE(telegram_id, date)
            )
        """)

        # 3. Таблица вечерних отчетов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id),
                UNIQUE(telegram_id, date)
            )
        """)
        
        # 4. Таблица актитвных планерок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                date_str TEXT NOT NULL,
                time_str TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


async def get_all_users():
    """Получает список всех зарегистрированных сотрудников для рассылки"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT telegram_id, full_name FROM users") as cursor:
            rows = await cursor.fetchall()
            return [{"telegram_id": row[0], "full_name": row[1]} for row in rows]


async def save_plan(telegram_id: int, plan_text: str):
    """Сохраняет или обновляет план на сегодня"""
    async with aiosqlite.connect(DB_NAME) as db:
        today = date.today().isoformat()
        await db.execute("""
            INSERT INTO daily_plans (telegram_id, date, raw_text)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id, date) DO UPDATE SET raw_text = excluded.raw_text
        """, (telegram_id, today, plan_text))
        await db.commit()


async def save_report(telegram_id: int, report_text: str):
    """Сохраняет или обновляет отчет за сегодня"""
    async with aiosqlite.connect(DB_NAME) as db:
        today = date.today().isoformat()
        await db.execute("""
            INSERT INTO daily_reports (telegram_id, date, raw_text)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id, date) DO UPDATE SET raw_text = excluded.raw_text
        """, (telegram_id, today, report_text))
        await db.commit()


async def get_daily_summary():
    """Возвращает сгруппированную сводку: 1 сотрудник = 1 карточка в дайджесте"""
    async with aiosqlite.connect(DB_NAME) as db:
        today = date.today().isoformat()
        
        query = """
            SELECT 
                u.full_name,
                u.duties,
                MAX(p.raw_text) AS plan,
                MAX(r.raw_text) AS report
            FROM users u
            LEFT JOIN daily_plans p ON u.telegram_id = p.telegram_id AND p.date = ?
            LEFT JOIN daily_reports r ON u.telegram_id = r.telegram_id AND r.date = ?
            GROUP BY u.telegram_id
        """
        async with db.execute(query, (today, today)) as cursor:
            rows = await cursor.fetchall()
            summary_data = []
            for row in rows:
                plan_val = row[2] if row[2] else "❌ Не заполнял(а)"
                report_val = row[3] if row[3] else "❌ Не заполнял(а)"
                
                summary_data.append({
                    "full_name": row[0],
                    "duties": row[1] if row[1] else "Должность не указана",
                    "plan": plan_val,
                    "report": report_val
                })
            return summary_data
        
        
        
async def add_meeting(topic: str, date_str: str, time_str: str) -> int:
    """Сохраняет новую планерку и возвращает ее ID"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO meetings (topic, date_str, time_str)
            VALUES (?, ?, ?)
        """, (topic, date_str, time_str))
        await db.commit()
        return cursor.lastrowid

async def get_active_meetings():
    """Получает список всех запланированных планерок"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, topic, date_str, time_str FROM meetings ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [{"id": row[0], "topic": row[1], "date_str": row[2], "time_str": row[3]} for row in rows]

async def update_meeting(meeting_id: int, new_date: str, new_time: str):
    """Обновляет дату и время перенесенной планерки"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE meetings 
            SET date_str = ?, time_str = ? 
            WHERE id = ?
        """, (new_date, new_time, meeting_id))
        await db.commit()

async def get_meeting_by_id(meeting_id: int):
    """Находит планерку по ее ID"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, topic, date_str, time_str FROM meetings WHERE id = ?", (meeting_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"id": row[0], "topic": row[1], "date_str": row[2], "time_str": row[3]}
            return None