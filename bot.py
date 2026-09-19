"""Entry point. Run this file to start the bot:  python bot.py"""

import database
import keyboards
from loader import bot

# Importing a module registers its handlers in the bot
import weather
import settings
import currency
import notes
import reminders
import habits
import scheduler

WELCOME_TEXT = (
    "👋 Привет! Я твой личный помощник.\n\n"
    "🌤 Погода — прогноз с полезными советами\n"
    "📅 Мой день — всё важное одним сообщением\n"
    "⏰ Напоминания — напомню в нужное время\n"
    "📝 Заметки — сохраню, чтобы не забыть\n"
    "🎯 Привычки — отмечай и держи серию\n"
    "💱 Курс валют — доллар и евро по ЦБ РФ\n"
    "⚙️ Настройки — город и утренняя сводка\n\n"
    "Выбери раздел в меню ниже 👇"
)


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    """Greet the user and show the main menu."""
    database.add_user(message.from_user.id)
    bot.send_message(message.chat.id, WELCOME_TEXT, reply_markup=keyboards.main_menu())


@bot.message_handler(content_types=["text", "photo", "sticker", "voice", "document"])
def unknown_message(message):
    """Anything the other handlers did not recognise comes here."""
    bot.send_message(message.chat.id, "🤔 Не понял. Выбери раздел в меню ниже 👇",
                     reply_markup=keyboards.main_menu())


if __name__ == "__main__":
    database.init_db()
    scheduler.start()
    print("Bot is running. Press Ctrl+C to stop.")
    bot.infinity_polling()
