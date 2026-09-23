import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Импортируем секреты и функции базы данных из наших соседних файлов
from config import BOT_TOKEN
from database import init_db, add_user

# Настраиваем логирование, чтобы видеть в терминале, что происходит с ботом
logging.basicConfig(level=logging.INFO)

# Инициализируем бота и диспетчер событий
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# Обработчик команды /start
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name

    # Сохраняем человека в базу данных SQLite
    await add_user(telegram_id=user_id, full_name=full_name)

    # Отправляем приветственное сообщение обратно в чат
    await message.answer(
        f"Привет, {full_name}! 👋\n"
        f"Я твой ИИ-координатор проектов. Я зарегистрировал тебя в системе.\n\n"
        f"Каждое утро я буду спрашивать твои планы на день, а вечером — подводить итоги."
    )


async def main():
    # 1. Сначала запускаем создание базы данных
    await init_db()
    logging.info("База данных успешно инициализирована.")

    # 2. Запускаем бесконечный опрос серверов Telegram (Listen Mode)
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Запуск асинхронной функции main()
    asyncio.run(main())