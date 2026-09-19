"""Background thread: sends reminders when their time comes."""

import threading
import time

from telebot.apihelper import ApiTelegramException

import database
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


def loop():
    while True:
        try:
            send_due_reminders()
        except Exception as error:  # the thread must survive any error
            print("Scheduler error:", error)
        time.sleep(CHECK_INTERVAL)


def start():
    """Run the loop in a separate thread so it does not block the bot."""
    threading.Thread(target=loop, daemon=True).start()
