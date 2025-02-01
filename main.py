from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv
import os

load_dotenv()  # Загружает переменные из файла .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
dp = Dispatcher(bot)

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    await message.answer("Привет! Я твой бот-напоминалка.")

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
