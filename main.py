import asyncio                                   # Для асинхронных операций (ожидания, планирования задач)
import os                                        # Для работы с переменными окружения
import sqlite3                                   # Для работы с базой данных SQLite
from datetime import datetime, timedelta, time   # Для работы с датой, временем и вычислениями
import dateparser                                # Для парсинга естественного языка с датой/временем
from aiogram import Bot, Dispatcher, types       # Основные классы aiogram для создания бота и обработки сообщений
from aiogram.filters import Command             # Фильтр для обработки команд (например, /start, /list)
from dotenv import load_dotenv                   # Для загрузки переменных окружения из файла .env

# ==========================
# Блок 1. Загрузка переменных и настройки
# ==========================
load_dotenv()                                    # Загружаем переменные окружения (например, из .env)
BOT_TOKEN = os.getenv("BOT_TOKEN")               # Получаем токен бота
DB_NAME = "reminders.db"                         # Имя файла базы данных для хранения напоминаний

# ==========================
# Блок 2. Функции работы с базой данных (SQLite)
# ==========================
def init_db():
    """
    Создает таблицу reminders, если она не существует.
    Таблица содержит поля:
      - id: уникальный идентификатор (PRIMARY KEY)
      - chat_id: идентификатор чата Telegram
      - reminder_text: текст напоминания (оригинальное сообщение пользователя)
      - reminder_date: время напоминания (сохраняется в ISO-формате)
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
    Дата сохраняется в формате ISO (строка).
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
    Удаляет напоминание из базы данных после его отправки.
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
    Каждый элемент списка – словарь с ключами:
      - chat_id
      - reminder_text
      - reminder_date (как datetime)
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
    Ждет до наступления reminder_date, затем отправляет напоминание пользователю
    и удаляет его из базы данных.
    """
    delay = (reminder_date - datetime.now()).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    await bot.send_message(
        chat_id,
        f"Напоминание: {reminder_text}\nВремя: {reminder_date.strftime('%d.%m.%Y %H:%M')}"
    )
    remove_reminder_from_db(chat_id, reminder_text, reminder_date)

# ==========================
# Блок 4. Основная функция бота
# ==========================
async def main():
    init_db()  # Инициализируем базу данных (создаем таблицу, если отсутствует)

    bot = Bot(token=BOT_TOKEN)    # Создаем объект бота
    dp = Dispatcher()             # Инициализируем диспетчер для обработки сообщений

    # При запуске планируем отправку всех будущих напоминаний (из базы)
    pending = get_pending_reminders()
    for reminder in pending:
        asyncio.create_task(schedule_reminder(
            bot,
            reminder["chat_id"],
            reminder["reminder_text"],
            reminder["reminder_date"]
        ))

    @dp.message(Command("start"))
    async def start_handler(message: types.Message):
        await message.answer(
            "Привет! Я бот-напоминалка.\n"
            "Добавь напоминание, например, напиши: 'завтра встреча в 20:00' или '12 февраля нужно сходить на встречу'.\n"
            "При добавлении я запланирую два напоминания:\n"
            "• Вечер перед событием (в 20:00 за день до события)\n"
            "• Утро в день события (в 7:00)"
        )

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
                response_lines.append(
                    f"• {reminder_text} в {reminder_date.strftime('%d.%m.%Y %H:%M')}"
                )
            await message.answer("\n".join(response_lines))

    @dp.message()
    async def add_reminder(message: types.Message):
        text = message.text  # Исходный текст напоминания от пользователя
        try:
            # Пытаемся распарсить дату и время из текста, используя dateparser
            parsed_date = dateparser.parse(
                text,
                languages=['ru'],
                settings={'PREFER_DATES_FROM': 'future'}
            )
            # Если не удалось распарсить, сообщаем об ошибке
            if not parsed_date:
                await message.answer(
                    "Не удалось распознать дату и время. Попробуйте указать, например, 'завтра встреча в 20:00'."
                )
                return

            now = datetime.now()
            # Если время не указано (получился 00:00), задаем утреннее время 7:00
            if parsed_date.hour == 0 and parsed_date.minute == 0:
                parsed_date = parsed_date.replace(hour=7, minute=0)

            if parsed_date < now:
                await message.answer("Время для напоминания уже прошло. Попробуйте указать другое время.")
                return

            # Утреннее напоминание: в день события (parsed_date)
            morning_dt = parsed_date

            # Вечернее напоминание: за день до события в 20:00
            event_date = parsed_date.date()
            evening_date = event_date - timedelta(days=1)
            evening_dt = datetime.combine(evening_date, time(20, 0))

            # Сохраняем утреннее напоминание
            add_reminder_to_db(message.chat.id, text, morning_dt)
            # Если вечернее напоминание ещё в будущем, сохраняем и его
            if evening_dt > now:
                add_reminder_to_db(message.chat.id, text, evening_dt)

            response = f"Отлично, я запланировал напоминания для '{text}':\n"
            if evening_dt > now:
                response += f"• Вечер: {evening_dt.strftime('%d.%m.%Y %H:%M')}\n"
            response += f"• Утро: {morning_dt.strftime('%d.%m.%Y %H:%M')}"
            await message.answer(response)

            # Планируем отправку напоминаний
            asyncio.create_task(schedule_reminder(bot, message.chat.id, text, morning_dt))
            if evening_dt > now:
                asyncio.create_task(schedule_reminder(bot, message.chat.id, text, evening_dt))
        except Exception as e:
            await message.answer("Ошибка при обработке напоминания. Проверьте формат сообщения.")
            print("Ошибка при разборе сообщения:", e)

    # Запускаем получение обновлений от Telegram (long polling)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
