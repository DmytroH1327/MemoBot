import asyncio
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command  # Импортируем только Command, так как Text не нужен
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()
# Получаем токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Глобальный список для хранения напоминаний
reminders = []

async def main():
    # Создаем объект бота
    bot = Bot(token=BOT_TOKEN)
    # Инициализируем диспетчер для обработки входящих сообщений и callback'ов
    dp = Dispatcher()

    # Обработчик команды /start
    @dp.message(Command("start"))
    async def start_handler(message: types.Message):
        await message.answer(
            "Привет! Я твой бот-напоминалка.\n"
            "Отправь сообщение вида '12 февраля нужно сходить на встречу', и я напомню тебе в 7:00 в этот день.\n"
            "Чтобы посмотреть текущие напоминания, используй команду /list."
        )

    # Обработчик команды /list для показа кнопки "Показать напоминания"
    @dp.message(Command("list"))
    async def list_handler(message: types.Message):
        # Создаем инлайн-клавиатуру с одной кнопкой
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Показать напоминания", callback_data="show_reminders")]
        ])
        await message.answer("Нажми кнопку, чтобы увидеть текущие напоминания:", reply_markup=keyboard)

    # Обработчик callback-запроса для кнопки "Показать напоминания"
    # Вместо Text("show_reminders") используем лямбда-функцию для проверки callback_data
    @dp.callback_query(lambda callback: callback.data == "show_reminders")
    async def show_reminders_handler(callback: types.CallbackQuery):
        # Отбираем напоминания для текущего чата
        chat_reminders = [r for r in reminders if r["chat_id"] == callback.message.chat.id]
        if not chat_reminders:
            response = "У тебя нет активных напоминаний."
        else:
            response_lines = []
            for r in chat_reminders:
                dt = r["reminder_date"].strftime("%d.%m.%Y %H:%M")
                response_lines.append(f"• {r['reminder_text']} в {dt}")
            response = "\n".join(response_lines)
        await callback.message.answer(response)
        # Отвечаем на callback, чтобы убрать индикатор ожидания в Telegram
        await callback.answer()

    # Обработчик текстовых сообщений для создания напоминания
    @dp.message()
    async def add_reminder(message: types.Message):
        text = message.text
        try:
            # Разбиваем сообщение на 3 части: день, месяц и описание напоминания
            parts = text.split(' ', 2)
            day = int(parts[0])
            month_str = parts[1].lower()
            # Словарь для сопоставления названий месяцев с числовыми значениями
            months = {
                "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
                "мая": 5, "июня": 6, "июля": 7, "августа": 8,
                "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
            }
            if month_str not in months:
                await message.answer("Не могу распознать месяц. Используй, например, 'февраля'.")
                return
            month = months[month_str]
            reminder_text = parts[2] if len(parts) > 2 else "Напоминание!"

            now = datetime.now()
            # Формируем дату напоминания с фиксированным временем 7:00
            reminder_date = datetime(year=now.year, month=month, day=day, hour=7, minute=0)
            if reminder_date < now:
                await message.answer("Эта дата уже прошла. Попробуй указать другую дату.")
                return

            # Добавляем напоминание в глобальный список
            reminders.append({
                "chat_id": message.chat.id,
                "reminder_text": reminder_text,
                "reminder_date": reminder_date
            })

            await message.answer(f"Отлично, я напомню тебе: '{reminder_text}' в {reminder_date.strftime('%d.%m.%Y %H:%M')}.")
            # Вычисляем задержку до момента напоминания в секундах
            delay = (reminder_date - now).total_seconds()
            # Создаем асинхронную задачу для отправки напоминания
            asyncio.create_task(schedule_reminder(bot, message.chat.id, reminder_text, delay))
        except Exception as e:
            await message.answer("Ошибка при обработке сообщения. Убедись, что формат: '12 февраля нужно сходить на встречу'.")
            print("Ошибка парсинга:", e)

    # Функция, которая ждет указанное время и отправляет напоминание
    async def schedule_reminder(bot: Bot, chat_id: int, text: str, delay: float):
        await asyncio.sleep(delay)
        await bot.send_message(chat_id, f"Напоминание: {text}")
        # Удаляем отправленное напоминание из списка
        global reminders
        reminders = [r for r in reminders if not (r["chat_id"] == chat_id and r["reminder_text"] == text)]

    # Запускаем long polling для получения обновлений от Telegram
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
