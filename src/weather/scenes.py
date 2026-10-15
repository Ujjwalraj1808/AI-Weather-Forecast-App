"""Map a WeatherAPI condition to a background scene name used by the web UI.

Condition codes: https://www.weatherapi.com/docs/weather_conditions.json
"""

from datetime import datetime

CLEAR = {1000, 1003}
CLOUDY = {1006, 1009}
FOG = {1030, 1135, 1147}
STORM = {1087, 1273, 1276, 1279, 1282}
RAIN = {1063, 1072, 1150, 1153, 1168, 1171, 1240, 1243, 1246} | set(range(1180, 1202, 3))
SNOW = (
    {1066, 1069, 1114, 1117, 1204, 1207, 1237, 1249, 1252, 1255, 1258, 1261, 1264}
    | set(range(1210, 1226, 3))
)

GOLDEN_HOUR_MINUTES = 45

SCENES = (
    "clear-day",
    "clear-night",
    "golden",
    "cloudy-day",
    "cloudy-night",
    "rain",
    "storm",
    "snow",
    "fog",
    "default",
)


def _minutes(clock):
    """'06:12 AM' -> minutes after midnight."""
    t = datetime.strptime(clock.strip(), "%I:%M %p")
    return t.hour * 60 + t.minute


def is_golden_hour(localtime, sunrise, sunset):
    """True within GOLDEN_HOUR_MINUTES of sunrise or sunset (local time)."""
    now = datetime.strptime(localtime, "%Y-%m-%d %H:%M")
    now_min = now.hour * 60 + now.minute
    try:
        edges = [_minutes(sunrise), _minutes(sunset)]
    except ValueError:  # WeatherAPI sends "No sunrise"/"No sunset" in polar regions
        return False
    return any(abs(now_min - edge) <= GOLDEN_HOUR_MINUTES for edge in edges)


def scene_for(code, is_day, localtime, sunrise, sunset):
    if code in STORM:
        return "storm"
    if code in SNOW:
        return "snow"
    if code in RAIN:
        return "rain"
    if code in FOG:
        return "fog"
    if code in CLOUDY:
        return "cloudy-day" if is_day else "cloudy-night"
    if code in CLEAR:
        if is_golden_hour(localtime, sunrise, sunset):
            return "golden"
        return "clear-day" if is_day else "clear-night"
    return "default"
