"""Creates the bot object. Other modules import it from here."""

import sys

import telebot

from config import BOT_TOKEN

if not BOT_TOKEN:
    print("BOT_TOKEN is not set. Copy .env.example to .env and paste the token.")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
