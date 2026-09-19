"""Reminders: the bot writes to the user at the chosen time."""

from datetime import datetime

import config
import database
import keyboards
from loader import bot

TIME_HELP = ("Когда напомнить? Примеры:\n"
             "• 18:30 — сегодня (или завтра, если время уже прошло)\n"
             "• 25.09 18:30 — в этом году\n"
             "• 25.09.2027 18:30 — точная дата")


def parse_remind_time(text, now):
    """Turn the user's text into a datetime. Returns None if the format is wrong."""
    parts = text.strip().split()
    try:
        if len(parts) == 1:  # "18:30" - today
            clock = datetime.strptime(parts[0], "%H:%M")
            return now.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
        if len(parts) == 2:  # "25.09 18:30" or "25.09.2027 18:30"
            day = parts[0]
            if day.count(".") == 1:
                day += f".{now.year}"
            return datetime.strptime(f"{day} {parts[1]}", "%d.%m.%Y %H:%M")
    except ValueError:
        return None
    return None


def format_moment(remind_at):
    """'2026-09-25 18:30' -> '25.09 18:30'."""
    return datetime.strptime(remind_at, "%Y-%m-%d %H:%M").strftime("%d.%m %H:%M")


def reminders_text(user_id):
    reminders = database.get_reminders(user_id)
    if not reminders:
        return "⏰ Активных напоминаний нет. Нажми «Добавить», чтобы создать."
    lines = [f"⏰ Твои напоминания ({len(reminders)}/{config.MAX_REMINDERS}):", ""]
    for number, (reminder_id, text, remind_at) in enumerate(reminders, start=1):
        lines.append(f"{number}. {format_moment(remind_at)} — {text}")
    return "\n".join(lines)


@bot.message_handler(func=lambda message: message.text == keyboards.BTN_REMINDERS)
def show_reminders(message):
    buttons = keyboards.inline([("➕ Добавить", "remind_add"), ("🗑 Удалить", "remind_delete")])
    bot.send_message(message.chat.id, reminders_text(message.from_user.id), reply_markup=buttons)


@bot.callback_query_handler(func=lambda call: call.data == "remind_add")
def ask_reminder_text(call):
    bot.answer_callback_query(call.id)
    if len(database.get_reminders(call.from_user.id)) >= config.MAX_REMINDERS:
        bot.send_message(call.message.chat.id,
                         f"Достигнут лимит — {config.MAX_REMINDERS} напоминаний. Удали лишние.")
        return
    answer = bot.send_message(
        call.message.chat.id,
        f"✍️ О чём напомнить? (до {config.MAX_REMINDER_LENGTH} символов)",
        reply_markup=keyboards.cancel_menu())
    bot.register_next_step_handler(answer, ask_reminder_time)


def ask_reminder_time(message):
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    text = (message.text or "").strip()
    if not text or len(text) > config.MAX_REMINDER_LENGTH:
        answer = bot.send_message(
            message.chat.id,
            f"Нужен текст от 1 до {config.MAX_REMINDER_LENGTH} символов. Попробуй ещё раз:")
        bot.register_next_step_handler(answer, ask_reminder_time)
        return
    answer = bot.send_message(message.chat.id, TIME_HELP)
    bot.register_next_step_handler(answer, save_reminder, text)


def save_reminder(message, text):
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    now = database.user_now(message.from_user.id)
    moment = parse_remind_time(message.text or "", now)
    if moment is None:
        answer = bot.send_message(message.chat.id, "Не понял время. " + TIME_HELP)
        bot.register_next_step_handler(answer, save_reminder, text)
        return
    if moment <= now:
        answer = bot.send_message(message.chat.id,
                                  "Это время уже прошло. Укажи момент в будущем:")
        bot.register_next_step_handler(answer, save_reminder, text)
        return
    database.add_reminder(message.from_user.id, text, moment.strftime("%Y-%m-%d %H:%M"))
    bot.send_message(message.chat.id,
                     f"✅ Напомню {moment.strftime('%d.%m.%Y в %H:%M')}: {text}",
                     reply_markup=keyboards.main_menu())


@bot.callback_query_handler(func=lambda call: call.data == "remind_delete")
def ask_reminder_number(call):
    bot.answer_callback_query(call.id)
    if not database.get_reminders(call.from_user.id):
        bot.send_message(call.message.chat.id, "Удалять нечего — напоминаний нет.")
        return
    answer = bot.send_message(call.message.chat.id,
                              "🗑 Напиши номер напоминания, которое удалить:",
                              reply_markup=keyboards.cancel_menu())
    bot.register_next_step_handler(answer, delete_reminder)


def delete_reminder(message):
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    reminders = sorted(database.get_reminders(message.from_user.id))
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= len(reminders)):
        answer = bot.send_message(message.chat.id,
                                  f"Нужен номер от 1 до {len(reminders)}. Попробуй ещё раз:")
        bot.register_next_step_handler(answer, delete_reminder)
        return
    database.delete_reminder(reminders[int(text) - 1][0])
    bot.send_message(message.chat.id, f"🗑 Напоминание №{text} удалено.",
                     reply_markup=keyboards.main_menu())
