import asyncio
import logging
from aiogram import Bot, Dispatcher, types # type: ignore
from aiogram.client.default import DefaultBotProperties # type: ignore
from aiogram.enums import ParseMode # type: ignore
from aiogram.filters import CommandStart # type: ignore
from aiogram.fsm.context import FSMContext # type: ignore
from aiogram.fsm.state import State, StatesGroup # type: ignore
from apscheduler.schedulers.asyncio import AsyncIOScheduler # type: ignore

from config import BOT_TOKEN
from database import init_db, add_user, get_user

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Asia/Aqtobe")


# Определяем состояния для цепочки диалога (FSM)
class RegistrationState(StatesGroup):
    waiting_for_name = State()             # Ждем ввода имени
    waiting_for_role_and_duties = State()  # Ждем ввода должности и обязанностей


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    existing_user = await get_user(user_id)

    # Если пользователь уже есть в базе
    if existing_user:
        await message.answer(
            f"С возвращением, {existing_user['full_name']}! 👋\n"
            f"Ты уже зарегистрирован в системе как <b>{existing_user['duties']}</b>.\n\n"
            f"Каждое утро я буду спрашивать твои планы на день, а вечером — подводить итоги."
        )
        return

    # Если пользователь новый — начинаем знакомство
    await message.answer(
        "Привет! Я твой ИИ-координатор проектов. 🤖\n\n"
        "Я буду помогать команде фиксировать ежедневные задачи, отслеживать прогресс и формировать отчеты для руководства.\n\n"
        "Давай познакомимся! <b>Как я могу к тебе обращаться?</b> (Напиши свое имя и фамилию)"
    )
    # Переводим бота в состояние ожидания имени
    await state.set_state(RegistrationState.waiting_for_name)


@dp.message(RegistrationState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()

    # Сохраняем имя во временную память FSM
    await state.update_data(full_name=full_name)

    await message.answer(
       f"Приятно познакомиться, {full_name}! 😊\n\n"
        f"Подскажи, <b>какая у тебя должность и чем именно ты занимаешься на работе?</b>\n"
        f"<i>(Например: Frontend-разработчик, верстаю сайты и делаю интеграцию с API)</i>"
    )
    # Переводим бота в состояние ожидания должности и обязанностей
    await state.set_state(RegistrationState.waiting_for_role_and_duties)


@dp.message(RegistrationState.waiting_for_role_and_duties)
async def process_role_and_duties(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    
    # Достаем ранее сохраненное имя из памяти FSM
    user_data = await state.get_data()
    full_name = user_data.get("full_name")
    
    user_id = message.from_user.id

    # Записываем всё в базу данных (SQLite)
    await add_user(
        telegram_id=user_id,
        full_name=full_name,
        role="Сотрудник",        # Общая роль
        duties=user_input        # Должность и чем занимается
    )

    # Сбрасываем состояние FSM, так как регистрация окончена
    await state.clear()

    await message.answer(
        f"Отлично, я все записал и зарегистрировал тебя в системе! 🎉\n\n"
        f"👤 <b>Имя:</b> {full_name}\n"
        f"💼 <b>Обязанности:</b> {user_input}\n\n"
        f"Теперь в 09:00 я буду спрашивать у тебя планы на день, а в 17:30 — отчет!"
    )


# --- Обработчики ответов на Утренний и Вечерний опрос ---
@dp.message(DailySurveyState.waiting_for_morning_plan)
async def process_morning_plan(message: types.Message, state: FSMContext):
    plan_text = message.text.strip()
    await save_plan(message.from_user.id, plan_text)
    await state.clear()
    await message.answer("Спасибо! Утренний план записан. Удачного и продуктивного дня! 🚀")


@dp.message(DailySurveyState.waiting_for_evening_report)
async def process_evening_report(message: types.Message, state: FSMContext):
    report_text = message.text.strip()
    await save_report(message.from_user.id, report_text)
    await state.clear()
    await message.answer("Отчет принят! Отличная работа сегодня, отдыхай! 🌙")


# --- Рассылки по расписанию ---
async def send_morning_survey():
    """Утренний опрос (09:00)"""
    users = await get_all_users()
    for user in users:
        try:
            # Для каждого пользователя устанавливаем состояние ожидания плана
            ctx = dp.fsm.resolve_context(bot, user["telegram_id"], user["telegram_id"])
            await ctx.set_state(DailySurveyState.waiting_for_morning_plan)
            
            await bot.send_message(
                user["telegram_id"],
                f"Доброе утро, {user['full_name']}! ☀️\n\n"
                f"<b>Какие у тебя основные задачи и планы на сегодня?</b>\n"
                f"Напиши ответ простым сообщением."
            )
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение {user['telegram_id']}: {e}")


async def send_evening_survey():
    """Вечерний опрос (17:30)"""
    users = await get_all_users()
    for user in users:
        try:
            ctx = dp.fsm.resolve_context(bot, user["telegram_id"], user["telegram_id"])
            await ctx.set_state(DailySurveyState.waiting_for_evening_report)
            
            await bot.send_message(
                user["telegram_id"],
                f"Добрый вечер, {user['full_name']}! 🌆\n\n"
                f"<b>Что удалось сделать за сегодня? Были ли какие-то блокеры/проблемы?</b>"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение {user['telegram_id']}: {e}")


async def send_daily_digest_to_admin():
    """Формирование и отправка дайджеста руководителю (18:30)"""
    summary = await get_daily_summary()
    date_str = datetime.now().strftime("%d.%m.%Y")

    digest_text = f"📊 <b>Ежедневный дайджест команды за {date_str}</b>\n\n"

    if not summary:
        digest_text += "В базе нет зарегистрированных сотрудников."
    else:
        for idx, item in enumerate(summary, 1):
            digest_text += f"<b>{idx}. {item['full_name']}</b>\n"
            digest_text += f"📌 <b>План:</b> {item['plan']}\n"
            digest_text += f"✅ <b>Отчет:</b> {item['report']}\n"
            digest_text += "───────────────\n"

    try:
        await bot.send_message(ADMIN_ID, digest_text)
    except Exception as e:
        logging.error(f"Ошибка отправки дайджеста админу: {e}")


# --- Команды ручного тестирования для ДЕМО заказчикам ---
@dp.message(Command("test_morning"))
async def cmd_test_morning(message: types.Message):
    """Принудительный запуск утреннего опроса"""
    await send_morning_survey()


@dp.message(Command("test_evening"))
async def cmd_test_evening(message: types.Message):
    """Принудительный запуск вечернего опроса"""
    await send_evening_survey()


@dp.message(Command("test_digest"))
async def cmd_test_digest(message: types.Message):
    """Принудительная генерация дайджеста"""
    await send_daily_digest_to_admin()


async def main():
    await init_db()
    logging.info("База данных успешно инициализирована.")

    # Настройка планировщика расписания
    scheduler.add_job(send_morning_survey, 'cron', hour=9, minute=0)
    scheduler.add_job(send_evening_survey, 'cron', hour=17, minute=30)
    scheduler.add_job(send_daily_digest_to_admin, 'cron', hour=18, minute=30)
    
    scheduler.start()
    logging.info("Планировщик задач запущен.")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())