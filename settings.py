"""Settings: the user's city and the morning message."""

from datetime import datetime

import requests

import database
import keyboards
import weather
from loader import bot


def parse_time(text):
    """'7:30' -> '07:30'. Returns None if the text is not a correct time."""
    try:
        return datetime.strptime(text.strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def settings_view(user_id):
    """Text of the settings screen and the buttons under it."""
    user = database.get_user(user_id)
    state = "включена ✅" if user["morning_enabled"] else "выключена ❌"
    text = ("⚙️ Настройки\n\n"
            f"🏙 Город: {user['city']}\n"
            f"🌅 Утренняя сводка: {state}\n"
            f"🕗 Время сводки: {user['morning_time']}")
    toggle = "🔕 Выключить сводку" if user["morning_enabled"] else "🔔 Включить сводку"
    buttons = keyboards.inline([("🏙 Сменить город", "settings_city"),
                                ("🕗 Время сводки", "settings_time"),
                                (toggle, "settings_toggle")])
    return text, buttons


@bot.message_handler(func=lambda message: message.text == keyboards.BTN_SETTINGS)
def show_settings(message):
    text, buttons = settings_view(message.from_user.id)
    bot.send_message(message.chat.id, text, reply_markup=buttons)


@bot.callback_query_handler(func=lambda call: call.data == "settings_toggle")
def toggle_morning(call):
    """Switch the morning message on or off."""
    user = database.get_user(call.from_user.id)
    database.set_morning_enabled(call.from_user.id, 0 if user["morning_enabled"] else 1)
    text, buttons = settings_view(call.from_user.id)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=buttons)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "settings_city")
def ask_city(call):
    bot.answer_callback_query(call.id)
    answer = bot.send_message(call.message.chat.id, "🏙 Напиши название города:",
                              reply_markup=keyboards.cancel_menu())
    bot.register_next_step_handler(answer, save_city)


def save_city(message):
    """The next message after ask_city comes here."""
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    name = (message.text or "").strip()
    if not name or len(name) > 50:
        answer = bot.send_message(message.chat.id,
                                  "Название города — текст до 50 символов. Попробуй ещё раз:")
        bot.register_next_step_handler(answer, save_city)
        return
    try:
        city = weather.find_city(name)
    except requests.RequestException:
        bot.send_message(message.chat.id, "⚠️ Сервис поиска городов недоступен. Попробуй позже.",
                         reply_markup=keyboards.main_menu())
        return
    if city is None:
        answer = bot.send_message(message.chat.id,
                                  f"Не нашёл город «{name}». Проверь название и напиши ещё раз:")
        bot.register_next_step_handler(answer, save_city)
        return
    database.set_city(message.from_user.id, city["name"], city["lat"], city["lon"],
                      city["timezone"])
    bot.send_message(message.chat.id, f"✅ Город сохранён: {city['name']}",
                     reply_markup=keyboards.main_menu())


@bot.callback_query_handler(func=lambda call: call.data == "settings_time")
def ask_time(call):
    bot.answer_callback_query(call.id)
    answer = bot.send_message(call.message.chat.id,
                              "🕗 Во сколько присылать утреннюю сводку? Формат ЧЧ:ММ, например 07:30",
                              reply_markup=keyboards.cancel_menu())
    bot.register_next_step_handler(answer, save_time)


def save_time(message):
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    morning_time = parse_time(message.text or "")
    if morning_time is None:
        answer = bot.send_message(message.chat.id,
                                  "Не похоже на время. Нужен формат ЧЧ:ММ, например 07:30:")
        bot.register_next_step_handler(answer, save_time)
        return
    database.set_morning_time(message.from_user.id, morning_time)
    bot.send_message(message.chat.id, f"✅ Сводка будет приходить в {morning_time}",
                     reply_markup=keyboards.main_menu())
