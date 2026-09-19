"""Currency rates of the Central Bank of Russia and a simple converter."""

from datetime import datetime

import requests

import config
import keyboards
from loader import bot

RATES_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
CURRENCIES = {"USD": "💵", "EUR": "💶"}
MAX_AMOUNT = 1_000_000_000


def get_rates():
    """Return {'date': '19.09.2026', 'USD': (rate, change), 'EUR': (rate, change)}."""
    response = requests.get(RATES_URL, timeout=config.REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    rates = {"date": datetime.fromisoformat(data["Date"]).strftime("%d.%m.%Y")}
    for code in CURRENCIES:
        item = data["Valute"][code]
        value = item["Value"] / item["Nominal"]
        previous = item["Previous"] / item["Nominal"]
        rates[code] = (value, value - previous)
    return rates


def rates_text(rates):
    """Message with today's rates and the change since the previous day."""
    lines = [f"💱 Курс ЦБ РФ на {rates['date']}", ""]
    for code, emoji in CURRENCIES.items():
        value, change = rates[code]
        if change > 0:
            arrow = "▲"
        elif change < 0:
            arrow = "▼"
        else:
            arrow = "•"
        lines.append(f"{emoji} {code}: {value:.2f} ₽  {arrow} {abs(change):.2f}")
    return "\n".join(lines)


def parse_amount(text):
    """'1 500,50' -> 1500.5. Returns None if the text is not a positive number."""
    try:
        amount = float(text.replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    if amount > MAX_AMOUNT:
        return None
    return amount


def convert(amount, source, target, rates):
    """Convert between roubles and a foreign currency."""
    if source == "RUB":
        return amount / rates[target][0]
    return amount * rates[source][0]


@bot.message_handler(func=lambda message: message.text == keyboards.BTN_CURRENCY)
def send_rates(message):
    try:
        text = rates_text(get_rates())
    except requests.RequestException:
        bot.send_message(message.chat.id, "⚠️ Не удалось получить курсы. Попробуй чуть позже.")
        return
    buttons = keyboards.inline([("USD → ₽", "convert_USD_RUB"), ("EUR → ₽", "convert_EUR_RUB"),
                                ("₽ → USD", "convert_RUB_USD"), ("₽ → EUR", "convert_RUB_EUR")])
    bot.send_message(message.chat.id, text + "\n\nКонвертер 👇", reply_markup=buttons)


@bot.callback_query_handler(func=lambda call: call.data.startswith("convert_"))
def ask_amount(call):
    """callback_data looks like 'convert_USD_RUB'."""
    bot.answer_callback_query(call.id)
    source, target = call.data.split("_")[1:]
    answer = bot.send_message(call.message.chat.id, f"Сколько {source} перевести в {target}?",
                              reply_markup=keyboards.cancel_menu())
    bot.register_next_step_handler(answer, show_converted, source, target)


def show_converted(message, source, target):
    if keyboards.is_cancel(message):
        bot.send_message(message.chat.id, "Отменено.", reply_markup=keyboards.main_menu())
        return
    amount = parse_amount(message.text or "")
    if amount is None:
        answer = bot.send_message(message.chat.id,
                                  "Нужно число больше нуля, например 100 или 99,5. Попробуй ещё раз:")
        bot.register_next_step_handler(answer, show_converted, source, target)
        return
    try:
        result = convert(amount, source, target, get_rates())
    except requests.RequestException:
        bot.send_message(message.chat.id, "⚠️ Не удалось получить курсы. Попробуй чуть позже.",
                         reply_markup=keyboards.main_menu())
        return
    bot.send_message(message.chat.id, f"💱 {amount:,.2f} {source} = {result:,.2f} {target}",
                     reply_markup=keyboards.main_menu())
