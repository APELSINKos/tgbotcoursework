"""All work with the SQLite database is collected in this file."""

import sqlite3

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
