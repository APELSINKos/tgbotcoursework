"""All work with the SQLite database is collected in this file."""

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import config


def run(query, params=(), fetch=False):
    """Run one SQL query. A new connection is opened every time,
    so the function is safe to call from different threads."""
    connection = sqlite3.connect(config.DB_PATH)
    cursor = connection.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall() if fetch else None
    connection.commit()
    connection.close()
    return rows


def init_db():
    """Create the tables if they do not exist yet."""
    run("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        city TEXT, lat REAL, lon REAL, timezone TEXT,
        morning_time TEXT, morning_enabled INTEGER,
        last_morning_date TEXT)""")
    run("""CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, text TEXT, created_at TEXT)""")
    run("""CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, text TEXT, remind_at TEXT, sent INTEGER DEFAULT 0)""")
    run("""CREATE TABLE IF NOT EXISTS habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, name TEXT, created_at TEXT)""")
    run("""CREATE TABLE IF NOT EXISTS habit_marks (
        habit_id INTEGER, day TEXT, done INTEGER,
        PRIMARY KEY (habit_id, day))""")


# ---------- users ----------

def add_user(user_id):
    """Save a new user with the default settings (does nothing if he exists)."""
    run("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, ?, 1, '')",
        (user_id, config.DEFAULT_CITY, config.DEFAULT_LAT, config.DEFAULT_LON,
         config.DEFAULT_TIMEZONE, config.DEFAULT_MORNING_TIME))


def get_user(user_id):
    """Return the user's settings as a dictionary."""
    add_user(user_id)
    row = run("SELECT city, lat, lon, timezone, morning_time, morning_enabled, "
              "last_morning_date FROM users WHERE user_id = ?", (user_id,), fetch=True)[0]
    return {"city": row[0], "lat": row[1], "lon": row[2], "timezone": row[3],
            "morning_time": row[4], "morning_enabled": row[5], "last_morning_date": row[6]}


def get_all_user_ids():
    rows = run("SELECT user_id FROM users", fetch=True)
    return [row[0] for row in rows]


def set_city(user_id, city, lat, lon, timezone):
    run("UPDATE users SET city = ?, lat = ?, lon = ?, timezone = ? WHERE user_id = ?",
        (city, lat, lon, timezone, user_id))


def set_morning_time(user_id, morning_time):
    run("UPDATE users SET morning_time = ? WHERE user_id = ?", (morning_time, user_id))


def set_morning_enabled(user_id, enabled):
    run("UPDATE users SET morning_enabled = ? WHERE user_id = ?", (enabled, user_id))


def set_last_morning_date(user_id, day):
    run("UPDATE users SET last_morning_date = ? WHERE user_id = ?", (day, user_id))


def user_now(user_id):
    """Current date and time in the timezone of the user's city."""
    timezone = get_user(user_id)["timezone"]
    return datetime.now(ZoneInfo(timezone)).replace(tzinfo=None)


# ---------- notes ----------

def add_note(user_id, text):
    created_at = user_now(user_id).strftime("%Y-%m-%d %H:%M")
    run("INSERT INTO notes (user_id, text, created_at) VALUES (?, ?, ?)",
        (user_id, text, created_at))


def get_notes(user_id):
    """Return a list of (id, text, created_at), the oldest note first."""
    return run("SELECT id, text, created_at FROM notes WHERE user_id = ? ORDER BY id",
               (user_id,), fetch=True)


def delete_note(note_id):
    run("DELETE FROM notes WHERE id = ?", (note_id,))


# ---------- reminders ----------

def add_reminder(user_id, text, remind_at):
    """remind_at is a string 'YYYY-MM-DD HH:MM' in the user's local time."""
    run("INSERT INTO reminders (user_id, text, remind_at) VALUES (?, ?, ?)",
        (user_id, text, remind_at))


def get_reminders(user_id):
    """Reminders that were not sent yet: (id, text, remind_at), the nearest first."""
    return run("SELECT id, text, remind_at FROM reminders "
               "WHERE user_id = ? AND sent = 0 ORDER BY remind_at", (user_id,), fetch=True)


def delete_reminder(reminder_id):
    run("DELETE FROM reminders WHERE id = ?", (reminder_id,))


def mark_reminder_sent(reminder_id):
    run("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))


# ---------- habits ----------

def add_habit(user_id, name):
    created_at = user_now(user_id).strftime("%Y-%m-%d")
    run("INSERT INTO habits (user_id, name, created_at) VALUES (?, ?, ?)",
        (user_id, name, created_at))


def get_habits(user_id):
    """Return a list of (id, name, created_at)."""
    return run("SELECT id, name, created_at FROM habits WHERE user_id = ? ORDER BY id",
               (user_id,), fetch=True)


def delete_habit(habit_id):
    run("DELETE FROM habit_marks WHERE habit_id = ?", (habit_id,))
    run("DELETE FROM habits WHERE id = ?", (habit_id,))


def set_habit_mark(habit_id, day, done):
    """Save the mark for one day: done is 1 (completed) or 0 (skipped)."""
    run("INSERT OR REPLACE INTO habit_marks (habit_id, day, done) VALUES (?, ?, ?)",
        (habit_id, day, done))


def get_habit_marks(habit_id):
    """Return a dictionary {'2026-09-19': 1, '2026-09-18': 0, ...}."""
    rows = run("SELECT day, done FROM habit_marks WHERE habit_id = ?", (habit_id,), fetch=True)
    return {day: done for day, done in rows}
