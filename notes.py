"""Notes: add, show and delete short text notes."""

import config
import database
import keyboards
from loader import bot


def notes_text(user_id):
    """Numbered list of the user's notes."""
    notes = database.get_notes(user_id)
    if not notes:
        return "📝 Заметок пока нет. Нажми «Добавить», чтобы создать первую."
    lines = [f"📝 Твои заметки ({len(notes)}/{config.MAX_NOTES}):", ""]
    for number, (note_id, text, created_at) in enumerate(notes, start=1):
        lines.append(f"{number}. {text}")
    return "\n".join(lines)


@bot.message_handler(func=lambda message: message.text == keyboards.BTN_NOTES)
def show_notes(message):
    buttons = keyboards.inline([("➕ Добавить", "note_add"), ("🗑 Удалить", "note_delete")])
    bot.send_message(message.chat.id, notes_text(message.from_user.id), reply_markup=buttons)


@bot.callback_query_handler(func=lambda call: call.data == "note_add")
def ask_note_text(call):
    bot.answer_callback_query(call.id)
    if len(database.get_notes(call.from_user.id)) >= config.MAX_NOTES:
        bot.send_message(call.message.chat.id,
                         f"Достигнут лимит — {config.MAX_NOTES} заметок. Удали лишние.")
        return
    answer = bot.send_message(call.message.chat.id,
                              f"✍️ Напиши текст заметки (до {config.MAX_NOTE_LENGTH} символов):",
                              reply_markup=keyboards.cancel_menu())
    bot.register_next_step_handler(answer, save_note)


def save_note(message):
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    text = (message.text or "").strip()
    if not text or len(text) >= config.MAX_NOTE_LENGTH:
        answer = bot.send_message(
            message.chat.id,
            f"Заметка — это текст от 1 до {config.MAX_NOTE_LENGTH} символов. Попробуй ещё раз:")
        bot.register_next_step_handler(answer, save_note)
        return
    database.add_note(message.from_user.id, text)
    bot.send_message(message.chat.id, "✅ Заметка сохранена.", reply_markup=keyboards.main_menu())


@bot.callback_query_handler(func=lambda call: call.data == "note_delete")
def ask_note_number(call):
    bot.answer_callback_query(call.id)
    if not database.get_notes(call.from_user.id):
        bot.send_message(call.message.chat.id, "Удалять нечего — заметок нет.")
        return
    answer = bot.send_message(call.message.chat.id, "🗑 Напиши номер заметки, которую удалить:",
                              reply_markup=keyboards.cancel_menu())
    bot.register_next_step_handler(answer, delete_note)


def delete_note(message):
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    notes = database.get_notes(message.from_user.id)
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= len(notes)):
        answer = bot.send_message(message.chat.id,
                                  f"Нужен номер от 1 до {len(notes)}. Попробуй ещё раз:")
        bot.register_next_step_handler(answer, delete_note)
        return
    note_id = notes[int(text) - 1][0]
    database.delete_note(note_id)
    bot.send_message(message.chat.id, f"🗑 Заметка №{text} удалена.",
                     reply_markup=keyboards.main_menu())
