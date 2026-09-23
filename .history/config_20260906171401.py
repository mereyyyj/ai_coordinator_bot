import os
from dotenv import load_dotenv

# load_dotenv() читает файл .env и загружает данные в систему
load_dotenv()

# Достаем значение переменных по их именам из .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", 0))