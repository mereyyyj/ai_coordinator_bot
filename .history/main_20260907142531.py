import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID
from database import (
    init_db, add_user, get_user, get_all_users, 
    save_plan, save_report, get_daily_summary
)

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Asia/Aqtobe")



# --- Установка меню команд ---
async def set_main_menu(bot: Bot):
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="test_morning", description="Тест утреннего опроса"),
        BotCommand(command="test_evening", description="Тест вечернего отчета"),
        BotCommand(command="test_digest", description="Тест отправки дайджеста"),
    ]
    await bot.set_my_commands(commands)


# --- Состояния (FSM) ---
class RegistrationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_role_and_duties = State()


class DailySurveyState(StatesGroup):
    waiting_for_morning_plan = State()
    waiting_for_evening_report = State()


# --- Команда /start ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    existing_user = await get_user(user_id)

    if existing_user:
        await message.answer(
            f"С возвращением, {existing_user['full_name']}! 👋\n"
            f"Ты зарегистрирован как <b>{existing_user['duties']}</b>.\n\n"
            f"Ожидай автоматических уведомлений в 09:00 и 17:30!"
        )
        return

    await message.answer(
        "Привет! Я твой ИИ-координатор проектов. 🤖\n\n"
        "Давай познакомимся! <b>Как я могу к тебе обращаться?</b> (Напиши имя и фамилию)"
    )
    await state.set_state(RegistrationState.waiting_for_name)


# --- Процесс регистрации ---
@dp.message(RegistrationState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Пожалуйста, отправь имя текстом.")
        return

    full_name = message.text.strip()
    await state.update_data(full_name=full_name)

    await message.answer(
        f"Приятно познакомиться, {full_name}! 😊\n\n"
        f"Подскажи, <b>какая у тебя должность и основные обязанности?</b>"
    )
    await state.set_state(RegistrationState.waiting_for_role_and_duties)


@dp.message(RegistrationState.waiting_for_role_and_duties)
async def process_role_and_duties(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Пожалуйста, отправь свои обязанности текстом.")
        return

    user_input = message.text.strip()
    user_data = await state.get_data()
    full_name = user_data.get("full_name")
    user_id = message.from_user.id

    await add_user(
        telegram_id=user_id,
        full_name=full_name,
        role="Сотрудник",
        duties=user_input
    )
    await state.clear()

    await message.answer(
        f"Регистрация завершена! 🎉\n\n"
        f"👤 <b>Имя:</b> {full_name}\n"
        f"💼 <b>Обязанности:</b> {user_input}\n\n"
        f"Теперь в 09:00 я буду спрашивать у тебя планы на день, а в 17:30 — отчет!"
    )


# --- Обработчики ответов на Утренний и Вечерний опрос ---
@dp.message(DailySurveyState.waiting_for_morning_plan)
async def process_morning_plan(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        await message.answer("⚠️ Пожалуйста, напиши текст плана простым сообщением, а не командой или медиафайлом.")
        return

    # Используем правильное имя функции из database.py
    await save_plan(message.from_user.id, message.text)
    await state.clear()
    await message.answer("Спасибо! Утренний план записан. Удачного и продуктивного дня! 🚀")


@dp.message(DailySurveyState.waiting_for_evening_report)
async def process_evening_report(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        await message.answer("⚠️ Пожалуйста, напиши текст отчета простым сообщением, а не командой или медиафайлом.")
        return

    # Используем правильное имя функции из database.py
    await save_report(message.from_user.id, message.text)
    await state.clear()
    await message.answer("Отчет принят! Отличная работа сегодня, отдыхай! 🌙")


# --- Рассылки по расписанию ---
async def set_user_state(user_id: int, state: State):
    """Вспомогательная функция для установки состояния FSM пользователю вне хэндлеров"""
    storage_key = StorageKey(
        bot_id=bot.id,
        chat_id=user_id,
        user_id=user_id
    )
    ctx = FSMContext(storage=dp.storage, key=storage_key)
    await ctx.set_state(state)


async def send_morning_survey():
    """Утренний опрос (09:00)"""
    users = await get_all_users()
    for user in users:
        try:
            telegram_id = user["telegram_id"]
            await set_user_state(telegram_id, DailySurveyState.waiting_for_morning_plan)
            
            await bot.send_message(
                telegram_id,
                f"Доброе утро, {user['full_name']}! ☀️\n\n"
                f"<b>Какие у тебя основные задачи и планы на сегодня?</b>\n"
                f"Напиши ответ простым сообщением."
            )
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"Не удалось отправить утренний опрос {user.get('telegram_id')}: {e}")


async def send_evening_survey():
    """Вечерний опрос (17:30)"""
    users = await get_all_users()
    for user in users:
        try:
            telegram_id = user["telegram_id"]
            await set_user_state(telegram_id, DailySurveyState.waiting_for_evening_report)
            
            await bot.send_message(
                telegram_id,
                f"Добрый вечер, {user['full_name']}! 🌆\n\n"
                f"<b>Что удалось сделать за сегодня? Были ли какие-то блокеры/проблемы?</b>"
            )
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"Не удалось отправить вечерний опрос {user.get('telegram_id')}: {e}")


async def send_daily_digest_to_admin():
    """Формирование и отправка дайджеста руководителю (18:30)"""
    summary = await get_daily_summary()
    date_str = datetime.now().strftime("%d.%m.%Y")

    digest_text = f"📊 <b>Ежедневный дайджест команды за {date_str}</b>\n\n"

    if not summary:
        digest_text += "В базе нет зарегистрированных сотрудников."
    else:
        for idx, item in enumerate(summary, 1):
            digest_text += f"<b>{idx}. {item['full_name']}</b> (<i>{item.get('duties', 'Нет должности')}</i>)\n"
            digest_text += f"📌 <b>План:</b> {item.get('plan', 'Не заполнен')}\n"
            digest_text += f"✅ <b>Отчет:</b> {item.get('report', 'Не заполнен')}\n"
            digest_text += "───────────────\n"

    try:
        await bot.send_message(ADMIN_ID, digest_text)
    except Exception as e:
        logging.error(f"Ошибка отправки дайджеста админу: {e}")


# --- Тестовые команды ---
@dp.message(Command("test_morning"))
async def cmd_test_morning(message: types.Message, state: FSMContext):
    """Тест утреннего опроса СТРОГО для отправителя команды"""
    await state.set_state(DailySurveyState.waiting_for_morning_plan)
    user_name = message.from_user.first_name
    
    await message.answer(
        f"Доброе утро, {user_name}! ☀️ (Тестовый опрос)\n\n"
        f"<b>Какие у тебя основные задачи и планы на сегодня?</b>\n"
        f"Напиши ответ простым сообщением."
    )


@dp.message(Command("test_evening"))
async def cmd_test_evening(message: types.Message, state: FSMContext):
    """Тест вечернего отчета СТРОГО для отправителя команды"""
    await state.set_state(DailySurveyState.waiting_for_evening_report)
    user_name = message.from_user.first_name
    
    await message.answer(
        f"Добрый вечер, {user_name}! 🌆 (Тестовый опрос)\n\n"
        f"<b>Что удалось сделать за сегодня? Были ли какие-то блокеры/проблемы?</b>\n"
        f"Напиши ответ простым сообщением."
    )


@dp.message(Command("test_digest"))
async def cmd_test_digest(message: types.Message):
    """Тестовая отправка дайджеста"""
    user_id = message.from_user.id
    
    if not ADMIN_ID or int(ADMIN_ID) == 0:
        await message.answer("⚠️ Ошибка: ADMIN_ID не настроен в config.py / .env файле!")
        return

    summary = await get_daily_summary()
    date_str = datetime.now().strftime("%d.%m.%Y")

    digest_text = f"📊 <b>Ежедневный дайджест команды за {date_str}</b>\n\n"

    if not summary:
        digest_text += "В базе пока нет записей за сегодня."
    else:
        for idx, item in enumerate(summary, 1):
            digest_text += f"<b>{idx}. {item['full_name']}</b> (<i>{item.get('duties', 'Нет должности')}</i>)\n"
            digest_text += f"📌 <b>План:</b> {item.get('plan', 'Не заполнен')}\n"
            digest_text += f"✅ <b>Отчет:</b> {item.get('report', 'Не заполнен')}\n"
            digest_text += "───────────────\n"

    try:
        await bot.send_message(ADMIN_ID, digest_text)
        if user_id != int(ADMIN_ID):
            await message.answer("✅ Дайджест сформирован и отправлен администратору!")
    except Exception as e:
        logging.error(f"Ошибка отправки дайджеста: {e}")
        await message.answer(f"❌ Не удалось отправить дайджест. Ошибка: {e}")


# --- Обработчик неизвестных сообщений ---

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

# 1. Определение состояний (FSM)
class SurveyState(StatesGroup):
    waiting_for_test_answer = State()
    waiting_for_evening_answer = State()


# 2. Функция создания Inline-клавиатуры
def get_commands_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="☀️ Дневной тестовый опрос", callback_data="test"),
                InlineKeyboardButton(text="🌆 Вечерний тестовый опрос", callback_data="evening"),
            ]
        ]
    )


bot = Bot(token="ВАШ_ТОКЕН_БОТА")
dp = Dispatcher()


# --- 3. ФУНКЦИИ КОМАНД И ОПРОСОВ ---

# Команда /test (или вызов функции при клике на кнопку Test)
@dp.message(Command("test"))
async def cmd_test(message: Message, state: FSMContext):
    await state.clear()
    # Устанавливаем состояние опроса
    await state.set_state(SurveyState.waiting_for_test_answer)
    await message.answer("☀️ Запущен дневной опрос! Напишите ваш главный приоритет на сегодня:")


# Команда /evening (или вызов функции при клике на кнопку Evening)
@dp.message(Command("evening"))
async def cmd_evening(message: Message, state: FSMContext):
    await state.clear()
    # Устанавливаем состояние опроса
    await state.set_state(SurveyState.waiting_for_evening_answer)
    await message.answer("🌆 Запущен вечерний опрос! Как прошел ваш день? Напишите краткий отчет:")


# --- 4. ОБРАБОТЧИКИ НАЖАТИЙ НА INLINE-КНОПКИ ---

@dp.callback_query(F.data == "test")
async def process_test_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # Убираем индикатор загрузки с кнопки
    # Вызываем готовую функцию cmd_test, передавая ей сообщение из callback
    await cmd_test(callback.message, state)


@dp.callback_query(F.data == "evening")
async def process_evening_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # Убираем индикатор загрузки с кнопки
    # Вызываем готовую функцию cmd_evening, передавая ей сообщение из callback
    await cmd_evening(callback.message, state)


# --- 5. ОБРАБОТКА ОТВЕТОВ НА ВОПРОСЫ (FSM) ---

@dp.message(SurveyState.waiting_for_test_answer)
async def process_test_response(message: Message, state: FSMContext):
    # Принимаем текст ответа на дневной опрос
    await message.answer(f"Спасибо! Твой дневной план принят: {message.text}")
    await state.clear()  # Завершаем опрос


@dp.message(SurveyState.waiting_for_evening_answer)
async def process_evening_response(message: Message, state: FSMContext):
    # Принимаем текст ответа на вечерний опрос
    await message.answer(f"Спасибо! Твой вечерний отчет сохранен: {message.text}")
    await state.clear()  # Завершаем опрос


# --- 6. ХЭНДЛЕР НЕИЗВЕСТНЫХ СООБЩЕНИЙ ---
# Важно: должен располагаться в самом конце!
@dp.message(F.text)
async def unknown_message_handler(message: Message):
    await message.answer(
        "Я вас не совсем понял 😅\nВыберите нужное действие из меню ниже:",
        reply_markup=get_commands_inline_keyboard()
    )


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())


# --- Главная функция запуска ---
async def main():
    await init_db()
    logging.info("База данных успешно инициализирована.")

    # Настройка планировщика расписания
    scheduler.add_job(send_morning_survey, 'cron', hour=9, minute=0)
    scheduler.add_job(send_evening_survey, 'cron', hour=17, minute=30)
    scheduler.add_job(send_daily_digest_to_admin, 'cron', hour=18, minute=30)
    
    scheduler.start()
    logging.info("Планировщик задач запущен.")
    
    await set_main_menu(bot)
    
    # Запуск бота с удалением накопленных обновлений
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
