"""'My day' summary and the text of the morning message."""

import requests

import database
import habits
import keyboards
import weather
from loader import bot

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def reminders_word(number):
    """Russian plural: 1 напоминание, 2 напоминания, 5 напоминаний."""
    if number % 10 == 1 and number % 100 != 11:
        return "напоминание"
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return "напоминания"
    return "напоминаний"


def todays_reminders(user_id):
    """Lines like '• 12:30 — встреча' for the reminders planned for today."""
    today = database.user_now(user_id).date().isoformat()
    lines = []
    for reminder_id, text, remind_at in database.get_reminders(user_id):
        if remind_at.startswith(today):
            lines.append(f"• {remind_at[11:]} — {text}")
    return lines


def my_day_text(user_id):
    """Everything important for today in one message."""
    user = database.get_user(user_id)
    now = database.user_now(user_id)
    lines = [f"📅 Сегодня, {now.day} {MONTHS[now.month - 1]}, {WEEKDAYS[now.weekday()]}", ""]

    try:
        data = weather.get_forecast(user["lat"], user["lon"])
        emoji, description = weather.describe_code(data["current"]["weather_code"])
        temperature = weather.format_temp(data["current"]["temperature_2m"])
        lines.append(f"{emoji} {user['city']}: {temperature}, {description}")
        lines.append(weather.build_tips(data)[0])
    except requests.RequestException:
        lines.append("🌤 Погода временно недоступна")

    reminders = todays_reminders(user_id)
    lines.append(f"📌 {len(reminders)} {reminders_word(len(reminders))} на сегодня")
    lines += reminders

    done, total = habits.today_progress(user_id)
    lines.append(f"🎯 Привычки: {done}/{total}")
    lines.append(f"📝 Заметок: {len(database.get_notes(user_id))}")
    return "\n".join(lines)


def morning_text(user_id):
    """The proactive message the bot sends in the morning."""
    user = database.get_user(user_id)
    lines = ["☀️ Доброе утро!", ""]

    try:
        data = weather.get_forecast(user["lat"], user["lon"])
        low = weather.format_temp(data["daily"]["temperature_2m_min"][0]).replace("°C", "")
        high = weather.format_temp(data["daily"]["temperature_2m_max"][0])
        lines.append(f"🌡 {user['city']}: {low}…{high}")
        lines += weather.build_tips(data)
    except requests.RequestException:
        lines.append("🌤 Погода временно недоступна")

    reminders = todays_reminders(user_id)
    lines.append("")
    if reminders:
        lines.append("📌 Сегодня:")
        lines += reminders
    else:
        lines.append("📌 На сегодня напоминаний нет")

    best = habits.best_streak(user_id)
    if best is not None:
        name, streak = best
        lines += ["", f"🔥 Серия привычки «{name}»: {streak} {habits.days_word(streak)}"]
    return "\n".join(lines)


@bot.message_handler(func=lambda message: message.text == keyboards.BTN_MY_DAY)
def show_my_day(message):
    bot.send_message(message.chat.id, my_day_text(message.from_user.id))
