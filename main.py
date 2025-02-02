import asyncio                           # Для асинхронного программирования (ожидания, планирования задач)
import os                                # Для работы с переменными окружения
import sqlite3                           # Для постоянного хранения напоминаний в базе данных SQLite
from datetime import datetime           # Для работы с датой и временем
import dateparser                        # Для разбора естественных строк с датой/временем (например, "завтра", "сегодня вечером")
from aiogram import Bot, Dispatcher, types  # Основные классы aiogram для создания бота и обработки сообщений
from aiogram.filters import Command      # Фильтр для обработки команд (например, /start, /list)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup  # Для создания кнопок, если понадобятся
from dotenv import load_dotenv           # Для загрузки переменных окружения из файла .env

# ==========================
# Блок 1. Загрузка переменных и настройки
# ==========================
load_dotenv()                            # Загружаем переменные окружения из файла .env
BOT_TOKEN = os.getenv("BOT_TOKEN")       # Получаем токен бота из переменной окружения
DB_NAME = "reminders.db"                 # Имя файла базы данных для хранения напоминаний

# ==========================
# Блок 2. Функции работы с базой данных (SQLite)
# ==========================

def init_db():
    """
    Создает таблицу reminders, если её нет.
    Таблица имеет следующие поля:
      - id: уникальный идентификатор (PRIMARY KEY)
      - chat_id: идентификатор чата Telegram
      - reminder_text: текст напоминания (оригинальное сообщение пользователя)
      - reminder_date: время напоминания (в ISO-формате)
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            reminder_text TEXT NOT NULL,
            reminder_date TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def add_reminder_to_db(chat_id: int, reminder_text: str, reminder_date: datetime):
    """
    Добавляет напоминание в базу данных.
    Преобразует дату в строку (ISO-формат) для хранения.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO reminders (chat_id, reminder_text, reminder_date) VALUES (?, ?, ?)",
                   (chat_id, reminder_text, reminder_date.isoformat()))
    conn.commit()
    conn.close()

def remove_reminder_from_db(chat_id: int, reminder_text: str):
    """
    Удаляет напоминание из базы данных после отправки.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE chat_id=? AND reminder_text=?", (chat_id, reminder_text))
    conn.commit()
    conn.close()

def get_pending_reminders():
    """
    Возвращает список всех напоминаний, время которых наступит в будущем.
    Каждый элемент списка – словарь с полями: chat_id, reminder_text и reminder_date (как datetime).
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, reminder_text, reminder_date FROM reminders")
    rows = cursor.fetchall()
    conn.close()
    pending = []
    now = datetime.now()
    for chat_id, reminder_text, reminder_date_str in rows:
        reminder_date = datetime.fromisoformat(reminder_date_str)
        if reminder_date > now:
            pending.append({
                "chat_id": chat_id,
                "reminder_text": reminder_text,
                "reminder_date": reminder_date
            })
    return pending

# ==========================
# Блок 3. Функция планирования напоминания
# ==========================
async def schedule_reminder(bot: Bot, chat_id: int, reminder_text: str, delay: float):
    """
    Ожидает указанное время (delay в секундах), затем отправляет напоминание пользователю
    и удаляет запись из базы данных.
    """
    await asyncio.sleep(delay)
    await bot.send_message(chat_id, f"Напоминание: {reminder_text}")
    remove_reminder_from_db(chat_id, reminder_text)

# ==========================
# Блок 4. Основная функция бота
# ==========================
async def main():
    # Инициализируем базу данных (если таблица отсутствует, она создастся)
    init_db()

    # Создаем объект бота и диспетчер для обработки сообщений
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # При старте загружаем все напоминания, дата которых еще не наступила, и планируем их отправку
    pending = get_pending_reminders()
    for reminder in pending:
        delay = (reminder["reminder_date"] - datetime.now()).total_seconds()
        if delay > 0:
            asyncio.create_task(schedule_reminder(bot, reminder["chat_id"],
                                                    reminder["reminder_text"], delay))

    # ==========================
    # Обработчик команды /start
    # ==========================
    @dp.message(Command("start"))
    async def start_handler(message: types.Message):
        await message.answer(
            "Привет! Я твой бот-напоминалка.\n"
            "Ты можешь добавить напоминание, например, написав:\n"
            "«завтра встреча в 20:00» или «12 февраля нужно сходить на встречу».\n"
            "Я запомню напоминание и пришлю его в нужное время."
        )

    # ==========================
    # Обработчик команды /list – выводит текущие напоминания
    # ==========================
    @dp.message(Command("list"))
    async def list_handler(message: types.Message):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT reminder_text, reminder_date FROM reminders WHERE chat_id=?", (message.chat.id,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            await message.answer("У тебя нет активных напоминаний.")
        else:
            response_lines = []
            for reminder_text, reminder_date_str in rows:
                reminder_date = datetime.fromisoformat(reminder_date_str)
                response_lines.append(f"• {reminder_text} в {reminder_date.strftime('%d.%m.%Y %H:%M')}")
            response = "\n".join(response_lines)
            await message.answer(response)

    # ==========================
    # Обработчик текстовых сообщений – добавление нового напоминания
    # ==========================
    @dp.message()
    async def add_reminder(message: types.Message):
        text = message.text  # Получаем текст сообщения от пользователя
        try:
            # Используем dateparser для разбора естественного языка с датой/временем.
            # Параметры:
            # - languages=['ru'] – парсим русский текст;
            # - settings={'PREFER_DATES_FROM': 'future'} – если указана относительная дата (например, "завтра"), выбираем ближайшую будущую.
            parsed_date = dateparser.parse(text, languages=['ru'], settings={'PREFER_DATES_FROM': 'future'})
            if not parsed_date:
                await message.answer("Не удалось распознать дату и время. Попробуйте указать, например, 'завтра встреча в 20:00'.")
                return

            # Если время не указано (например, dateparser вернул 00:00), можно установить время по умолчанию, например, 7:00.
            if parsed_date.hour == 0 and parsed_date.minute == 0:
                parsed_date = parsed_date.replace(hour=7, minute=0)

            now = datetime.now()
            if parsed_date < now:
                await message.answer("Время для напоминания уже прошло. Попробуйте указать другое время.")
                return

            # Сохраняем напоминание в базе данных
            add_reminder_to_db(message.chat.id, text, parsed_date)

            # Отправляем подтверждение пользователю
            await message.answer(f"Отлично, я напомню: '{text}' в {parsed_date.strftime('%d.%m.%Y %H:%M')}.")
            delay = (parsed_date - now).total_seconds()
            # Планируем отправку напоминания
            asyncio.create_task(schedule_reminder(bot, message.chat.id, text, delay))
        except Exception as e:
            await message.answer("Ошибка при обработке напоминания. Убедитесь, что формат сообщения корректен.")
            print("Ошибка при разборе сообщения:", e)

    # Запускаем получение обновлений от Telegram (long polling)
    await dp.start_polling(bot)

# ==========================
# Блок 5. Точка входа в программу
# ==========================
if __name__ == "__main__":
    asyncio.run(main())
