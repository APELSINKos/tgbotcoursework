"""Keyboards (buttons) of the bot."""

from telebot import types

# Texts of the main menu buttons
BTN_WEATHER = "🌤 Погода"
BTN_MY_DAY = "📅 Мой день"
BTN_REMINDERS = "⏰ Напоминания"
BTN_NOTES = "📝 Заметки"
BTN_HABITS = "🎯 Привычки"
BTN_CURRENCY = "💱 Курс валют"
BTN_SETTINGS = "⚙️ Настройки"
BTN_CANCEL = "❌ Отмена"


def main_menu():
    """Big buttons under the input field."""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(BTN_WEATHER, BTN_MY_DAY)
    keyboard.add(BTN_REMINDERS, BTN_NOTES)
    keyboard.add(BTN_HABITS, BTN_CURRENCY)
    keyboard.add(BTN_SETTINGS)
    return keyboard


def cancel_menu():
    """Shown while the bot waits for the user's input."""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(BTN_CANCEL)
    return keyboard


def inline(buttons):
    """Build buttons under a message from a list of (text, callback_data)."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(*[types.InlineKeyboardButton(text, callback_data=data)
                   for text, data in buttons])
    return keyboard


def is_cancel(message):
    """True if the user pressed Cancel or sent a command instead of an answer."""
    text = message.text or ""
    return text == BTN_CANCEL or text.startswith("/")
