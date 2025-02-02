import asyncio                                   # Для асинхронных операций и ожидания (sleep)
import os                                        # Для работы с переменными окружения
import sqlite3                                   # Для работы с базой данных SQLite
from datetime import datetime, timedelta, time   # Для работы с датами, временем, разницей между датами и создания времени
import dateparser                                # Для парсинга естественного языка с датами (например, "завтра встреча в 20:00")
from aiogram import Bot, Dispatcher, types       # Основные классы aiogram для создания бота и обработки сообщений
from aiogram.filters import Command             # Фильтр для обработки команд (например, /start, /list)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup  # Для создания инлайн-клавиатур (если потребуется)
from dotenv import load_dotenv                   # Для загрузки переменных окружения из файла .env

# ==========================
# Блок 1. Загрузка переменных и настройки
# ==========================
load_dotenv()                                    # Загружаем переменные окружения из файла .env (или они заданы на сервере)
BOT_TOKEN = os.getenv("BOT_TOKEN")               # Получаем токен бота из переменной окружения
DB_NAME = "reminders.db"                         # Имя файла базы данных для хранения напоминаний

# ==========================
# Блок 2. Функции работы с базой данных (SQLite)
# ==========================
def init_db():
    """
    Создает таблицу reminders, если она еще не существует.
    Таблица имеет поля: id, chat_id, reminder_text и reminder_date (в ISO-формате).
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
    Дата сохраняется в виде строки в ISO-формате.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reminders (chat_id, reminder_text, reminder_date) VALUES (?, ?, ?)",
        (chat_id, reminder_text, reminder_date.isoformat())
    )
    conn.commit()
    conn.close()

def remove_reminder_from_db(chat_id: int, reminder_text: str, reminder_date: datetime):
    """
    Удаляет напоминание из базы данных после отправки.
    Для точного соответствия удаляем запись с указанными chat_id, текстом и датой.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM reminders WHERE chat_id=? AND reminder_text=? AND reminder_date=?",
        (chat_id, reminder_text, reminder_date.isoformat())
    )
    conn.commit()
    conn.close()

def get_pending_reminders():
    """
    Возвращает список всех напоминаний, время которых наступит в будущем.
    Каждый элемент – словарь с полями: chat_id, reminder_text и reminder_date (как datetime).
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
# Блок 3. Функция отправки напоминания
# ==========================
async def schedule_reminder(bot: Bot, chat_id: int, reminder_text: str, reminder_date: datetime):
    """
    Ожидает до наступления reminder_date, затем отправляет напоминание пользователю
    и удаляет его из базы данных.
    """
    delay = (reminder_date - datetime.now()).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    await bot.send_message(chat_id, f"Напоминание: {reminder_text}\nВремя: {reminder_date.strftime('%d.%m.%Y %H:%M')}")
    remove_reminder_from_db(chat_id, reminder_text, reminder_date)

# ==========================
# Блок 4. Основная функция бота
# ==========================
async def main():
    init_db()  # Инициализируем базу данных (создаем таблицу, если отсутствует)

    bot = Bot(token=BOT_TOKEN)    # Создаем объект бота
    dp = Dispatcher()             # Инициализируем диспетчер для обработки сообщений

    # При запуске, планируем отправку всех будущих напоминаний (из базы)
    pending = get_pending_reminders()
    for reminder in pending:
        asyncio.create_task(schedule_reminder(
            bot,
            reminder["chat_id"],
            reminder["reminder_text"],
            reminder["reminder_date"]
        ))

    # ==========================
    # Обработчик команды /start
    # ==========================
    @dp.message(Command("start"))
    async def start_handler(message: types.Message):
        await message.answer(
            "Привет! Я твой бот-напоминалка.\n"
            "Добавь напоминание, например, написав:\n"
            "«завтра встреча в 20:00» или «12 февраля нужно сходить на встречу».\n"
            "При добавлении я запланирую два напоминания:\n"
            "1. Вечер перед событием (в 20:00).\n"
            "2. Утром в день события (в 7:00)."
        )

    # ==========================
    # Обработчик команды /list – показывает текущие напоминания
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
            await message.answer("\n".join(response_lines))

    # ==========================
    # Обработчик текстовых сообщений – добавление нового напоминания
    # ==========================
    @dp.message()
    async def add_reminder(message: types.Message):
        text = message.text  # Текст сообщения от пользователя
        try:
            # Парсим текст с помощью dateparser:
            # - languages=['ru'] – анализируем русский текст
            # - settings={'PREFER_DATES_FROM': 'future'} – выбираем ближайшую будущую дату при относительных выражениях
            parsed_date = dateparser.parse(text, languages=['ru'], settings={'PREFER_DATES_FROM': 'future'})
            if not parsed_date:
                await message.answer("Не удалось распознать дату и время. Попробуйте указать, например, 'завтра встреча в 20:00'.")
                return

            now = datetime.now()
            # Если время не указано (по умолчанию 00:00), ставим утреннее время 7:00
            if parsed_date.hour == 0 and parsed_date.minute == 0:
                parsed_date = parsed_date.replace(hour=7, minute=0)

            if parsed_date < now:
                await message.answer("Время для напоминания уже прошло. Попробуйте указать другое время.")
                return

            # Вычисляем время для утреннего напоминания – оно равно parsed_date (обычно 7:00 в день события)
            morning_dt = parsed_date

            # Вычисляем время для вечернего напоминания – на день раньше, в 20:00
            evening_date = parsed_date.date() - timedelta(days=1)
            evening_dt = datetime.combine(evening_date, time(20, 0))

            # Сохраняем утреннее напоминание в базе данных
            add_reminder_to_db(message.chat.id, text, morning_dt)
            # Если вечернее напоминание в будущем, сохраняем его тоже
            if evening_dt > now:
                add_reminder_to_db(message.chat.id, text, evening_dt)

            # Отправляем подтверждение пользователю
            response = f"Отлично, я запланировал напоминания для '{text}':\n"
            response += f"• Вечер перед событием: {evening_dt.strftime('%d.%m.%Y %H:%M')}\n" if evening_dt > now else ""
            response += f"• Утром в день события: {morning_dt.strftime('%d.%m.%Y %H:%M')}"
            await message.answer(response)

            # Планируем отправку утреннего напоминания
            delay_morning = (morning_dt - now).total_seconds()
            asyncio.create_task(schedule_reminder(bot, message.chat.id, text, morning_dt))
            # Планируем отправку вечернего напоминания, если время еще не прошло
            if evening_dt > now:
                delay_evening = (evening_dt - now).total_seconds()
                asyncio.create_task(schedule_reminder(bot, message.chat.id, text, evening_dt))
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
