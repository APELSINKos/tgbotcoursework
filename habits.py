"""Habit tracker: daily marks, statistics and the current streak."""

from datetime import date, timedelta

import config
import database
import keyboards
from loader import bot


def days_word(number):
    """Russian plural: 1 день, 2 дня, 5 дней, 11 дней, 21 день."""
    if number % 10 == 1 and number % 100 != 11:
        return "день"
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return "дня"
    return "дней"


def calc_streak(marks, today):
    """Days in a row with a 'done' mark, counted back from today.
    If today is not marked yet, the count starts from yesterday."""
    day = today
    if marks.get(day.isoformat()) is None:
        day -= timedelta(days=1)
    streak = 0
    while marks.get(day.isoformat()) == 1:
        streak += 1
        day -= timedelta(days=1)
    return streak


def habit_lines(habit, today):
    """Two lines of statistics: 'Спорт — 12/17 дней 🔥' and the streak."""
    habit_id, name, created_at = habit
    marks = database.get_habit_marks(habit_id)
    done_days = sum(marks.values())
    total_days = (today - date.fromisoformat(created_at)).days + 1
    streak = calc_streak(marks, today)
    fire = " 🔥" if streak >= 3 else ""
    return [f"{name} — {done_days}/{total_days} {days_word(total_days)}{fire}",
            f"Текущая серия — {streak} {days_word(streak)}"]


def habits_text(user_id):
    habits = database.get_habits(user_id)
    if not habits:
        return "🎯 Привычек пока нет. Нажми «Добавить», чтобы начать."
    today = database.user_now(user_id).date()
    lines = [f"🎯 Твои привычки ({len(habits)}/{config.MAX_HABITS}):"]
    for number, habit in enumerate(habits, start=1):
        first, second = habit_lines(habit, today)
        lines += ["", f"{number}. {first}", f"    {second}"]
    return "\n".join(lines)


def today_progress(user_id):
    """(how many habits are done today, how many habits there are)."""
    habits = database.get_habits(user_id)
    today = database.user_now(user_id).date().isoformat()
    done = sum(1 for habit in habits if database.get_habit_marks(habit[0]).get(today) == 1)
    return done, len(habits)


def best_streak(user_id):
    """(habit name, streak) for the longest current streak, or None."""
    today = database.user_now(user_id).date()
    best = None
    for habit_id, name, created_at in database.get_habits(user_id):
        streak = calc_streak(database.get_habit_marks(habit_id), today)
        if streak > 0 and (best is None or streak > best[1]):
            best = (name, streak)
    return best


@bot.message_handler(func=lambda message: message.text == keyboards.BTN_HABITS)
def show_habits(message):
    buttons = keyboards.inline([("✅ Отметить сегодня", "habit_mark"), ("➕ Добавить", "habit_add"),
                                ("🗑 Удалить", "habit_delete")])
    bot.send_message(message.chat.id, habits_text(message.from_user.id), reply_markup=buttons)


@bot.callback_query_handler(func=lambda call: call.data == "habit_mark")
def ask_marks(call):
    """Send one message per habit with the Done / Skipped buttons."""
    bot.answer_callback_query(call.id)
    habits = database.get_habits(call.from_user.id)
    if not habits:
        bot.send_message(call.message.chat.id, "Сначала добавь хотя бы одну привычку.")
        return
    for habit_id, name, created_at in habits:
        buttons = keyboards.inline([("✅ Выполнил", f"habit_done_{habit_id}"),
                                    ("❌ Пропустил", f"habit_skip_{habit_id}")])
        bot.send_message(call.message.chat.id, f"{name} — как сегодня?", reply_markup=buttons)


@bot.callback_query_handler(
    func=lambda call: call.data.startswith(("habit_done_", "habit_skip_")))
def save_mark(call):
    """callback_data looks like 'habit_done_12' or 'habit_skip_12'."""
    action, habit_id = call.data.split("_")[1:]
    habit_id = int(habit_id)
    names = {habit[0]: habit[1] for habit in database.get_habits(call.from_user.id)}
    if habit_id not in names:
        bot.answer_callback_query(call.id, "Эта привычка уже удалена.")
        return
    done = 1 if action == "done" else 0
    today = database.user_now(call.from_user.id).date().isoformat()
    database.set_habit_mark(habit_id, today, done)
    result = "✅ выполнено сегодня" if done else "❌ пропущено сегодня"
    bot.edit_message_text(f"{names[habit_id]} — {result}", call.message.chat.id,
                          call.message.message_id)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "habit_add")
def ask_habit_name(call):
    bot.answer_callback_query(call.id)
    if len(database.get_habits(call.from_user.id)) >= config.MAX_HABITS:
        bot.send_message(call.message.chat.id,
                         f"Достигнут лимит — {config.MAX_HABITS} привычек. Удали лишние.")
        return
    answer = bot.send_message(
        call.message.chat.id,
        f"✍️ Как называется привычка? (до {config.MAX_HABIT_LENGTH} символов)",
        reply_markup=keyboards.cancel_menu())
    bot.register_next_step_handler(answer, save_habit)


def save_habit(message):
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    name = (message.text or "").strip()
    if not name or len(name) > config.MAX_HABIT_LENGTH:
        answer = bot.send_message(
            message.chat.id,
            f"Название — текст от 1 до {config.MAX_HABIT_LENGTH} символов. Попробуй ещё раз:")
        bot.register_next_step_handler(answer, save_habit)
        return
    existing = [habit[1].lower() for habit in database.get_habits(message.from_user.id)]
    if name.lower() in existing:
        answer = bot.send_message(message.chat.id,
                                  "Такая привычка уже есть. Придумай другое название:")
        bot.register_next_step_handler(answer, save_habit)
        return
    database.add_habit(message.from_user.id, name)
    bot.send_message(message.chat.id, f"✅ Привычка «{name}» добавлена.",
                     reply_markup=keyboards.main_menu())


@bot.callback_query_handler(func=lambda call: call.data == "habit_delete")
def ask_habit_number(call):
    bot.answer_callback_query(call.id)
    if not database.get_habits(call.from_user.id):
        bot.send_message(call.message.chat.id, "Удалять нечего — привычек нет.")
        return
    answer = bot.send_message(call.message.chat.id, "🗑 Напиши номер привычки, которую удалить:",
                              reply_markup=keyboards.cancel_menu())
    bot.register_next_step_handler(answer, delete_habit)


def delete_habit(message):
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    habits = database.get_habits(message.from_user.id)
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= len(habits)):
        answer = bot.send_message(message.chat.id,
                                  f"Нужен номер от 1 до {len(habits)}. Попробуй ещё раз:")
        bot.register_next_step_handler(answer, delete_habit)
        return
    habit_id, name, created_at = habits[int(text) - 1]
    database.delete_habit(habit_id)
    bot.send_message(message.chat.id, f"🗑 Привычка «{name}» удалена.",
                     reply_markup=keyboards.main_menu())
