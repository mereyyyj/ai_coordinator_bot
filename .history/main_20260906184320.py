import asyncio
import logging
from aiogram import Bot, Dispatcher, types # type: ignore
from aiogram.client.default import DefaultBotProperties # type: ignore
from aiogram.enums import ParseMode # type: ignore
from aiogram.filters import CommandStart # type: ignore
from aiogram.fsm.context import FSMContext # type: ignore
from aiogram.fsm.state import State, StatesGroup # type: ignore

from config import BOT_TOKEN
from database import init_db, add_user, get_user

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


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
        f"Теперь я готов к работе. Каждое утро я буду спрашивать твои планы, а вечером — результаты."
    )


async def main():
    await init_db()
    logging.info("База данных успешно инициализирована.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())