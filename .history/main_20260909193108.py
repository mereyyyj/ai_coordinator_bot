import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
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


# --- Состояния (FSM) ---
class RegistrationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_role_and_duties = State()


class DailySurveyState(StatesGroup):
    waiting_for_morning_plan = State()
    waiting_for_evening_report = State()
    
    
class MeetingState(StatesGroup):
    # Создание планерки
    waiting_for_topic = State()
    waiting_for_date = State()       #  Отдельно дата
    waiting_for_time = State()       #  Отдельно время
    
    # Перенос / Изменение времени
    waiting_for_reschedule_topic = State()
    waiting_for_new_date = State()   #  Отдельно дата
    waiting_for_new_time = State()   #  Отдельно время
    


# --- Клавиатуры ---
def get_commands_inline_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для быстрых тестов и команд"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="☀️ Утренний опрос", callback_data="test_morning"),
                InlineKeyboardButton(text="🌆 Вечерний отчет", callback_data="test_evening"),
            ]
        ]
    )


async def set_main_menu(bot: Bot):
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="meeting", description="📅 Запланировать планерку (Админ)"),
        BotCommand(command="reschedule", description="🔄 Перенести планерку (Админ)"),
        BotCommand(command="test_morning", description="Тест утреннего опроса"),
        BotCommand(command="test_evening", description="Тест вечернего отчета"),
        BotCommand(command="test_digest", description="Тест отправки дайджеста"),
    ]
    await bot.set_my_commands(commands)


# --- Команда /start ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
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


# --- Регистрация ---
@dp.message(RegistrationState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
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
    if not message.text or message.text.startswith("/"):
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






# --- Команды опросов TEST ---
@dp.message(Command("test_morning"))
async def cmd_test_morning(message: types.Message, state: FSMContext):
    await state.set_state(DailySurveyState.waiting_for_morning_plan)
    user_name = message.from_user.first_name
    
    await message.answer(
        f"Доброе утро, {user_name}! ☀️ (Тестовый опрос)\n\n"
        f"<b>Какие у тебя основные задачи и планы на сегодня?</b>\n"
        f"Напиши ответ простым сообщением."
    )


@dp.message(Command("test_evening"))
async def cmd_test_evening(message: types.Message, state: FSMContext):
    await state.set_state(DailySurveyState.waiting_for_evening_report)
    user_name = message.from_user.first_name
    
    await message.answer(
        f"Добрый вечер, {user_name}! 🌆 (Тестовый опрос)\n\n"
        f"<b>Что удалось сделать за сегодня? Были ли какие-то блокеры/проблемы?</b>\n"
        f"Напиши ответ простым сообщением."
    )


@dp.message(Command("test_digest"))
async def cmd_test_digest(message: types.Message):
    user_id = message.from_user.id
    if not ADMIN_ID or int(ADMIN_ID) == 0:
        await message.answer("⚠️ Ошибка: ADMIN_ID не настроен в config.py!")
        return

    summary = await get_daily_summary()
    date_str = datetime.now().strftime("%d.%m.%Y")
    digest_text = f"📊 <b>Ежедневный дайджест команды за {date_str}</b>\n\n"

    if not summary:
        digest_text += "В базе пока нет записей за сегодня."
    else:
        for idx, item in enumerate(summary, 1):
            digest_text += f"<b>{idx}. {item['full_name']}</b> (<i>{item.get('duties', 'Нет')}</i>)\n"
            digest_text += f"📌 <b>План:</b> {item.get('plan', 'Не заполнен')}\n"
            digest_text += f"✅ <b>Отчет:</b> {item.get('report', 'Не заполнен')}\n"
            digest_text += "───────────────\n"

    try:
        await bot.send_message(ADMIN_ID, digest_text)
        if user_id != int(ADMIN_ID):
            await message.answer("✅ Дайджест отправлен администратору!")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {e}")
        
        
        
        
        
# --- Команда для админа: создать планерку ---
@dp.message(Command("meeting"))
async def cmd_meeting(message: types.Message, state: FSMContext):
    # Проверка: только админ может запускать
    if str(message.from_user.id) != str(ADMIN_ID):
        await message.answer("⚠️ Эта команда доступна только администратору!")
        return

    await state.set_state(MeetingState.waiting_for_topic)
    await message.answer("📝 <b>Создание планерки</b>\n\nВведите <b>тему</b> встречи:")


# Шаг 1: Получаем тему и спрашиваем время
@dp.message(MeetingState.waiting_for_topic)
async def process_meeting_topic(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        await message.answer("⚠️ Пожалуйста, введите тему текстом.")
        return

    await state.update_data(topic=message.text.strip())
    await state.set_state(MeetingState.waiting_for_datetime)
    await message.answer("📅 Отлично! Теперь укажите <b>дату и время</b> (например: <i>Завтра в 11:00</i>):")


# Шаг 2: Получаем время и рассылаем оповещение всем!
@dp.message(MeetingState.waiting_for_datetime)
async def process_meeting_datetime(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        await message.answer("⚠️ Пожалуйста, укажите дата/время текстом.")
        return

    date_time_text = message.text.strip()
    user_data = await state.get_data()
    topic_text = user_data.get("topic")

    await state.clear()
    
    # 1. Отвечаем админу
    await message.answer("✅ Планерка создана! Рассылаю уведомления сотрудникам...")

    # 2. Мгновенно рассылаем всем сотрудникам из базы
    await notify_meeting_scheduled(topic=topic_text, date_time=date_time_text)        
        
        
# --- Команда для админа: перенести планерку ---
@dp.message(Command("reschedule"))
async def cmd_reschedule(message: types.Message, state: FSMContext):
    # Проверка прав администратора
    if str(message.from_user.id) != str(ADMIN_ID):
        await message.answer("⚠️ Эта команда доступна только администратору!")
        return

    await state.set_state(MeetingState.waiting_for_reschedule_topic)
    await message.answer(
        "🔄 <b>Перенос времени планерки</b>\n\n"
        "Введите <b>тему</b> планерки, время которой нужно изменить:"
    )


# Шаг 1: Получаем тему планерки и спрашиваем новое время
@dp.message(MeetingState.waiting_for_reschedule_topic)
async def process_reschedule_topic(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        await message.answer("⚠️ Пожалуйста, укажите тему текстом.")
        return

    await state.update_data(topic=message.text.strip())
    await state.set_state(MeetingState.waiting_for_new_datetime)
    await message.answer("🕒 Укажите <b>новое дата и время</b> (например: <i>Сегодня в 16:30</i>):")


# Шаг 2: Получаем новое время и рассылаем оповещение об изменении
@dp.message(MeetingState.waiting_for_new_datetime)
async def process_new_datetime(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        await message.answer("⚠️ Пожалуйста, укажите новое время текстом.")
        return

    new_date_time = message.text.strip()
    user_data = await state.get_data()
    topic = user_data.get("topic")

    await state.clear()

    # 1. Отвечаем админу
    await message.answer("✅ Время планерки успешно изменено! Рассылаю обновленные данные сотрудникам...")

    # 2. Рассылаем сотрудникам уведомление с предупреждением об изменении
    await notify_meeting_changed(topic=topic, new_date_time=new_date_time)
    
    
        



# --- Обработчики ответов на опросы ---
@dp.message(DailySurveyState.waiting_for_morning_plan)
async def process_morning_plan(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        await message.answer("⚠️ Пожалуйста, напиши текст плана простым сообщением.")
        return

    await save_plan(message.from_user.id, message.text)
    await state.clear()
    await message.answer("Спасибо! Утренний план записан. Удачного дня! 🚀")


@dp.message(DailySurveyState.waiting_for_evening_report)
async def process_evening_report(message: types.Message, state: FSMContext):
    if not message.text or message.text.startswith("/"):
        await message.answer("⚠️ Пожалуйста, напиши текст отчета простым сообщением.")
        return

    await save_report(message.from_user.id, message.text)
    await state.clear()
    await message.answer("Отчет принят! Отличная работа, отдыхай! 🌙")


# --- Обработка кликов по Inline-кнопкам ---
@dp.callback_query(F.data == "test_morning")
async def process_test_morning_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_test_morning(callback.message, state)


@dp.callback_query(F.data == "test_evening")
async def process_test_evening_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_test_evening(callback.message, state)







# --- Оповещения и рассылка планерок ---
async def send_broadcast(text: str):
    """Отправка уведомления всем зарегистрированным пользователям"""
    users = await get_all_users()
    for user in users:
        try:
            await bot.send_message(chat_id=user["telegram_id"], text=text)
            await asyncio.sleep(0.05)
        except (TelegramForbiddenError, Exception) as e:
            logging.error(f"Не удалось отправить пользователю {user['telegram_id']}: {e}")


async def notify_meeting_scheduled(topic: str, date_time: str):
    text = (
        "📢 <b>ВНИМАНИЕ! ЗАПЛАНИРОВАНА ПЛАНЕРКА</b>\n\n"
        f"📌 <b>Тема:</b> {topic}\n"
        f"📅 <b>Дата и время:</b> {date_time}\n\n"
        "Пожалуйста, запланируйте время!"
    )
    await send_broadcast(text)


async def notify_meeting_changed(topic: str, new_date_time: str):
    text = (
        "⚠️ <b>ИЗМЕНЕНИЕ ВРЕМЕНИ ПЛАНЕРКИ!</b>\n\n"
        f"📌 <b>Тема:</b> {topic}\n"
        f"🕒 <b>Новое время:</b> {new_date_time}\n\n"
        "Обратите внимание на изменения в графике!"
    )
    await send_broadcast(text)






# --- Автоматические рассылки по расписанию ---
async def set_user_state(user_id: int, state: State):
    storage_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    ctx = FSMContext(storage=dp.storage, key=storage_key)
    await ctx.set_state(state)


async def send_morning_survey():
    users = await get_all_users()
    for user in users:
        try:
            await set_user_state(user["telegram_id"], DailySurveyState.waiting_for_morning_plan)
            await bot.send_message(
                user["telegram_id"],
                f"Доброе утро, {user['full_name']}! ☀️\n\n"
                f"<b>Какие у тебя основные задачи и планы на сегодня?</b>"
            )
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"Ошибка отправки утреннего опроса {user['telegram_id']}: {e}")


async def send_evening_survey():
    users = await get_all_users()
    for user in users:
        try:
            await set_user_state(user["telegram_id"], DailySurveyState.waiting_for_evening_report)
            await bot.send_message(
                user["telegram_id"],
                f"Добрый вечер, {user['full_name']}! 🌆\n\n"
                f"<b>Что удалось сделать за сегодня? Были ли какие-то блокеры/проблемы?</b>"
            )
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"Ошибка отправки вечернего опроса {user['telegram_id']}: {e}")

# 1. Функция отправки дайджеста (для APScheduler и для команды)
async def send_daily_digest():
    if not ADMIN_ID or int(ADMIN_ID) == 0:
        logging.error("⚠️ Ошибка: ADMIN_ID не настроен в config.py!")
        return

    summary = await get_daily_summary()
    date_str = datetime.now().strftime("%d.%m.%Y")
    digest_text = f"📊 <b>Ежедневный дайджест команды за {date_str}</b>\n\n"

    if not summary:
        digest_text += "В базе пока нет записей за сегодня."
    else:
        for idx, item in enumerate(summary, 1):
            digest_text += f"<b>{idx}. {item['full_name']}</b> (<i>{item.get('duties', 'Нет')}</i>)\n"
            digest_text += f"📌 <b>План:</b> {item.get('plan', 'Не заполнен')}\n"
            digest_text += f"✅ <b>Отчет:</b> {item.get('report', 'Не заполнен')}\n"
            digest_text += "───────────────\n"

    try:
        await bot.send_message(ADMIN_ID, digest_text)
    except Exception as e:
        logging.error(f"❌ Ошибка отправки дайджеста: {e}")




# --- Хэндлер неизвестных сообщений (В самом конце файла) ---
@dp.message(F.text)
async def unknown_message_handler(message: types.Message):
    await message.answer(
        "Я вас не совсем понял 😅\nВыберите нужное действие из меню ниже:",
        reply_markup=get_commands_inline_keyboard()
    )




# --- Запуск приложения ---
async def main():
    await init_db()
    logging.info("База данных инициализирована.")

    scheduler.add_job(send_morning_survey, 'cron', hour=9, minute=0)
    scheduler.add_job(send_evening_survey, 'cron', hour=17, minute=30)
    scheduler.add_job(send_daily_digest, 'cron', hour=18, minute=30)
    scheduler.start()

    await set_main_menu(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())