"""Entry point. Run this file to start the bot:  python bot.py"""

import database
import keyboards
from loader import bot

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


if __name__ == "__main__":
    database.init_db()
    print("Bot is running. Press Ctrl+C to stop.")
    bot.infinity_polling()
