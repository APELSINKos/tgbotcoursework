"""Bot settings. The secret token is read from the .env file."""

import os

from dotenv import load_dotenv

# Read variables from the .env file into the environment
load_dotenv()

# Token from @BotFather. It is stored only in .env and never in the code
BOT_TOKEN = os.getenv("BOT_TOKEN")

# File with the SQLite database
DB_PATH = "bot.db"

# City used until the user picks another one in the settings
DEFAULT_CITY = "Москва"
DEFAULT_LAT = 55.75204
DEFAULT_LON = 37.61781
DEFAULT_TIMEZONE = "Europe/Moscow"

# Time of the morning message (HH:MM)
DEFAULT_MORNING_TIME = "08:00"

# Limits for user data
MAX_NOTE_LENGTH = 500
MAX_NOTES = 50
MAX_REMINDER_LENGTH = 200
MAX_REMINDERS = 20
MAX_HABIT_LENGTH = 50
MAX_HABITS = 10

# How long we wait for an answer from external sites (seconds)
REQUEST_TIMEOUT = 10
