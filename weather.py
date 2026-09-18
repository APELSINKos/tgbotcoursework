"""Smart weather: forecast from Open-Meteo plus useful tips."""

from datetime import datetime

import requests

import config
import database
import keyboards
from loader import bot

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes: (first code, last code, emoji, description)
WEATHER_CODES = [
    (0, 0, "☀️", "ясно"), (1, 2, "🌤", "малооблачно"), (3, 3, "☁️", "пасмурно"),
    (45, 48, "🌫", "туман"), (51, 57, "🌦", "морось"), (61, 67, "🌧", "дождь"),
    (71, 77, "🌨", "снег"), (80, 82, "🌧", "ливень"), (85, 86, "🌨", "снегопад"),
    (95, 99, "⛈", "гроза"),
]


def describe_code(code):
    """Turn a numeric weather code into an emoji and a Russian word."""
    for first, last, emoji, text in WEATHER_CODES:
        if first <= code <= last:
            return emoji, text
    return "🌡", "без осадков"


def format_temp(value):
    """14.2 -> '+14°C', -3.7 -> '-4°C', 0.2 -> '0°C'."""
    number = round(value)
    if number == 0:
        return "0°C"
    return f"{number:+d}°C"


def find_city(name):
    """Look up a city by name. Returns a dictionary or None if nothing is found."""
    response = requests.get(GEOCODING_URL, timeout=config.REQUEST_TIMEOUT,
                            params={"name": name, "count": 1, "language": "ru"})
    results = response.json().get("results")
    if not results:
        return None
    city = results[0]
    return {"name": city["name"], "lat": city["latitude"], "lon": city["longitude"],
            "timezone": city.get("timezone", config.DEFAULT_TIMEZONE)}


def get_forecast(lat, lon):
    """Download the forecast for today and tomorrow."""
    response = requests.get(FORECAST_URL, timeout=config.REQUEST_TIMEOUT, params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
        "wind_speed_unit": "ms",
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation",
        "minutely_15": "precipitation",
        "hourly": "temperature_2m,precipitation_probability",
        "daily": "temperature_2m_max,temperature_2m_min",
    })
    response.raise_for_status()
    return response.json()


def build_tips(data):
    """The 'smart' part: turn raw numbers into short human advice."""
    tips = []
    current = data["current"]
    now = datetime.fromisoformat(current["time"])  # local time of the city
    is_snow = current["temperature_2m"] <= 0
    word = "снег" if is_snow else "дождь"
    emoji = "🌨" if is_snow else "🌧"
    advice = "надень капюшон" if is_snow else "возьми зонт"

    # 1. Precipitation right now or in the next two hours (15-minute steps)
    rain_soon = False
    if current["precipitation"] >= 0.1:
        tips.append(f"{emoji} Сейчас идёт {word} — {advice}")
        rain_soon = True
    else:
        steps = zip(data["minutely_15"]["time"], data["minutely_15"]["precipitation"])
        for time_text, amount in steps:
            minutes = int((datetime.fromisoformat(time_text) - now).total_seconds() / 60)
            if 0 < minutes <= 120 and (amount or 0) >= 0.1:
                tips.append(f"{emoji} Через {minutes} минут {word} — {advice}")
                rain_soon = True
                break

    # Hourly data for the rest of today: {hour: (temperature, rain probability)}
    today = {}
    hourly = data["hourly"]
    for time_text, temp, chance in zip(hourly["time"], hourly["temperature_2m"],
                                       hourly["precipitation_probability"]):
        moment = datetime.fromisoformat(time_text)
        if moment.date() == now.date():
            today[moment.hour] = (temp, chance or 0)

    # 2. Precipitation later today
    rain_later = False
    if not rain_soon:
        for hour in sorted(today):
            if hour > now.hour and today[hour][1] >= 60:
                tips.append(f"☔ {word.capitalize()} ожидается после {hour:02d}:00 — "
                            "зонт сегодня пригодится")
                rain_later = True
                break

    # 3. Morning against evening
    if 8 in today and 18 in today:
        difference = today[18][0] - today[8][0]
        if difference >= 5:
            tips.append("🧥 Утром холодно, вечером потеплеет")
        elif difference <= -5:
            tips.append("🌡 К вечеру похолодает — захвати кофту")

    # 4. Wind, frost and heat
    if current["wind_speed_10m"] >= 10:
        tips.append("💨 Сильный ветер — одевайся плотнее")
    if current["apparent_temperature"] <= -15:
        tips.append("🥶 Очень холодно — одевайся теплее")
    if current["apparent_temperature"] >= 30:
        tips.append("🥵 Жара — пей больше воды")

    # 5. A good day for a bike ride: dry, warm and not windy
    day_max = data["daily"]["temperature_2m_max"][0]
    if (not rain_soon and not rain_later and 12 <= day_max <= 28
            and current["wind_speed_10m"] < 7):
        tips.append("🚲 Сегодня хороший день для велосипеда")

    if not tips:
        tips.append("👌 Погода без сюрпризов")
    return tips


def weather_text(user_id):
    """Full weather message for the user's city."""
    user = database.get_user(user_id)
    data = get_forecast(user["lat"], user["lon"])
    current = data["current"]
    emoji, description = describe_code(current["weather_code"])
    lines = [
        f"{emoji} {user['city']}: {format_temp(current['temperature_2m'])}, {description}",
        f"Ощущается как {format_temp(current['apparent_temperature'])}, "
        f"ветер {round(current['wind_speed_10m'])} м/с",
        f"Сегодня: {format_temp(data['daily']['temperature_2m_min'][0]).replace('°C', '')}…"
        f"{format_temp(data['daily']['temperature_2m_max'][0])}",
        "",
    ]
    return "\n".join(lines + build_tips(data))


@bot.message_handler(func=lambda message: message.text == keyboards.BTN_WEATHER)
def send_weather(message):
    """The user pressed the Weather button."""
    try:
        text = weather_text(message.from_user.id)
    except requests.RequestException:
        text = "⚠️ Не удалось получить погоду. Попробуй чуть позже."
    buttons = keyboards.inline([("🏙 Сменить город", "settings_city")])
    bot.send_message(message.chat.id, text, reply_markup=buttons)
