"""Background thread: sends reminders and the morning message."""

import threading
import time

from telebot.apihelper import ApiTelegramException

import database
import my_day
from loader import bot

CHECK_INTERVAL = 30  # seconds between checks


def send_due_reminders():
    """Send every reminder whose time has come."""
    for user_id in database.get_all_user_ids():
        now_text = database.user_now(user_id).strftime("%Y-%m-%d %H:%M")
        for reminder_id, text, remind_at in database.get_reminders(user_id):
            if remind_at > now_text:
                continue
            try:
                bot.send_message(user_id, f"⏰ Напоминание: {text}")
            except ApiTelegramException as error:
                # For example the user blocked the bot - do not retry forever
                print("Could not deliver a reminder:", error)
            database.mark_reminder_sent(reminder_id)


def send_morning_digests():
    """Send the morning message once a day, within an hour after the chosen time."""
    for user_id in database.get_all_user_ids():
        user = database.get_user(user_id)
        now = database.user_now(user_id)
        today = now.date().isoformat()
        if not user["morning_enabled"] or user["last_morning_date"] == today:
            continue
        hour, minute = user["morning_time"].split(":")
        planned = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
        if not (0 <= (now - planned).total_seconds() < 3600):
            continue
        try:
            bot.send_message(user_id, my_day.morning_text(user_id))
        except ApiTelegramException as error:
            print("Could not deliver the morning message:", error)
        database.set_last_morning_date(user_id, today)


def loop():
    while True:
        try:
            send_due_reminders()
            send_morning_digests()
        except Exception as error:  # the thread must survive any error
            print("Scheduler error:", error)
        time.sleep(CHECK_INTERVAL)


def start():
    """Run the loop in a separate thread so it does not block the bot."""
    threading.Thread(target=loop, daemon=True).start()
