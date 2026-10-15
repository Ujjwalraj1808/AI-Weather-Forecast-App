"""WeatherAPI client, location resolution and response parsing."""

import os
import re

import requests

from src.weather.scenes import scene_for

BASE_URL = "https://api.weatherapi.com/v1"
TIMEOUT_SECONDS = 10

# WeatherAPI error codes: https://www.weatherapi.com/docs/#intro-error-codes
_KEY_ERRORS = {1002, 2006, 2008, 2009}
_QUOTA_EXCEEDED = 2007
_NO_LOCATION = 1006

# Queries WeatherAPI resolves exactly on its own; these skip name search.
_EXACT_QUERY = re.compile(
    r"^(id:\d+|iata:\w+|metar:\w+|auto:ip|-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?)$",
    re.IGNORECASE,
)

_COUNTRY_ALIASES = {
    "uk": "united kingdom",
    "england": "united kingdom",
    "usa": "united states of america",
    "us": "united states of america",
    "uae": "united arab emirates",
}


class CityNotFoundError(Exception):
    pass


class AmbiguousLocationError(Exception):
    def __init__(self, query, candidates):
        super().__init__(f'Several places match "{query}"')
        self.candidates = candidates


class WeatherServiceError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def get_api_key():
    key = os.environ.get("WEATHER_API_KEY")
    if not key:
        raise WeatherServiceError("WEATHER_API_KEY is not set on the server.", 503)
    return key


def get_preferred_country():
    return os.environ.get("PREFERRED_COUNTRY", "India")


def _request(endpoint, params):
    """Call WeatherAPI. Error messages never include the request URL (it holds the key)."""
    try:
        response = requests.get(
            f"{BASE_URL}/{endpoint}",
            params={"key": get_api_key(), **params},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.Timeout:
        raise WeatherServiceError("WeatherAPI did not respond in time. Try again.", 504) from None
    except requests.RequestException:
        raise WeatherServiceError("Could not reach WeatherAPI. Try again shortly.", 502) from None

    try:
        data = response.json()
    except ValueError:
        raise WeatherServiceError("WeatherAPI returned an unreadable response.", 502) from None

    if isinstance(data, dict) and "error" in data:
        code = data["error"].get("code")
        message = data["error"].get("message", "Unknown error")
        if code == _NO_LOCATION:
            raise CityNotFoundError(message)
        if code in _KEY_ERRORS:
            raise WeatherServiceError("WeatherAPI rejected the server's API key.", 503)
        if code == _QUOTA_EXCEEDED:
            raise WeatherServiceError("WeatherAPI usage limit reached. Try again later.", 429)
        raise WeatherServiceError(f"WeatherAPI error: {message}", 502)

    if response.status_code == 429:
        raise WeatherServiceError("WeatherAPI rate limit reached. Try again shortly.", 429)
    if not response.ok:
        raise WeatherServiceError(f"WeatherAPI returned HTTP {response.status_code}.", 502)
    return data


def normalize_city(city):
    city = city.strip()
    # WeatherAPI does not resolve "Gurugram"; the old name works.
    if city.lower() == "gurugram":
        city = "gurgaon"
    return city


def _location_summary(loc):
    return {
        "id": loc["id"],
        "name": loc["name"],
        "region": loc["region"],
        "country": loc["country"],
        "lat": loc["lat"],
        "lon": loc["lon"],
    }


def search_locations(query):
    """Autocomplete matches from WeatherAPI's search endpoint."""
    return [_location_summary(loc) for loc in _request("search.json", {"q": query})]


def _matches_qualifier(qualifier, loc):
    q = _COUNTRY_ALIASES.get(qualifier.lower(), qualifier.lower())
    return q == loc["country"].lower() or q in loc["region"].lower()


def choose_location(candidates, name, qualifier, preferred_country):
    """Pick one location from search results, or raise if the choice is not clear.

    1. A qualifier ("Delhi, India", "London, UK") filters by country or region.
    2. Exact name matches beat partial matches.
    3. With no qualifier, the preferred country breaks a tie between exact matches.
    4. Anything still ambiguous goes back to the user to choose.
    """
    pool = candidates
    if qualifier:
        pool = [c for c in pool if _matches_qualifier(qualifier, c)]
    if not pool:
        where = f" in {qualifier}" if qualifier else ""
        raise CityNotFoundError(f'No place called "{name}" found{where}.')

    exact = [c for c in pool if c["name"].lower() == name.lower()]
    pool = exact or pool
    if len(pool) == 1:
        return pool[0]

    if not qualifier and exact:
        preferred = [c for c in pool if c["country"].lower() == preferred_country.lower()]
        if len(preferred) == 1:
            return preferred[0]

    raise AmbiguousLocationError(f"{name}, {qualifier}" if qualifier else name, pool)


def _dedupe(locations):
    seen = set()
    return [loc for loc in locations if not (loc["id"] in seen or seen.add(loc["id"]))]


def find_candidates(name, qualifier=""):
    """Search results for a place name, widened so the right match is in the list.

    WeatherAPI's search does not always list every place with a name: "Delhi"
    returns only Delhi, Ontario, Canada, while "Delhi, India" returns Delhi, India.
    So we also search "name, qualifier" (or "name, PREFERRED_COUNTRY" when the
    first search has nothing in that country), and list preferred-country matches first.
    """
    name = normalize_city(name)
    if qualifier:
        return _dedupe(search_locations(f"{name}, {qualifier}") + search_locations(name))
    preferred = get_preferred_country()
    results = search_locations(name)
    if not any(r["country"].lower() == preferred.lower() for r in results):
        results = results + search_locations(f"{name}, {preferred}")
    results = _dedupe(results)
    return sorted(results, key=lambda r: r["country"].lower() != preferred.lower())


def resolve_location(query):
    """Turn free text into one exact location; returns its summary dict."""
    name, _, qualifier = (part.strip() for part in query.partition(","))
    name = normalize_city(name)
    return choose_location(find_candidates(name, qualifier), name, qualifier, get_preferred_country())


def resolve_query(query):
    """Return a WeatherAPI `q` value that identifies exactly one place."""
    query = query.strip()
    if _EXACT_QUERY.match(query):
        return query
    return f"id:{resolve_location(query)['id']}"


def fetch_forecast(q, days=10):
    """Raw WeatherAPI forecast payload for an exact `q` (see resolve_query)."""
    return _request("forecast.json", {"q": q, "days": days})


def get_advice(temp, condition):
    if temp > 35:
        return "It is very hot. Drink more water."
    if temp < 10:
        return "Weather is cold. Wear warm clothes."
    if "rain" in condition.lower():
        return "Carry umbrella today."
    return "Weather looks nice today."


def _icon_url(icon):
    return f"https:{icon}" if icon.startswith("//") else icon


def parse_current(data):
    loc = data["location"]
    current = data["current"]
    today = data["forecast"]["forecastday"][0]
    astro = today["astro"]
    condition = current["condition"]
    return {
        "location": loc["name"],
        "region": loc["region"],
        "country": loc["country"],
        "lat": loc["lat"],
        "lon": loc["lon"],
        "tz_id": loc["tz_id"],
        "localtime": loc["localtime"],
        "condition": condition["text"],
        "condition_code": condition["code"],
        "icon": _icon_url(condition["icon"]),
        "is_day": bool(current["is_day"]),
        "temp_c": current["temp_c"],
        "feelslike_c": current["feelslike_c"],
        "humidity": current["humidity"],
        "wind_kph": current["wind_kph"],
        "chance_of_rain_today": today["day"]["daily_chance_of_rain"],
        "sunrise": astro["sunrise"],
        "sunset": astro["sunset"],
        "advice": get_advice(current["temp_c"], condition["text"]),
        "scene": scene_for(
            condition["code"],
            bool(current["is_day"]),
            loc["localtime"],
            astro["sunrise"],
            astro["sunset"],
        ),
    }


def parse_forecast(data):
    days = []
    for day in data["forecast"]["forecastday"]:
        d = day["day"]
        days.append(
            {
                "date": day["date"],
                "condition": d["condition"]["text"],
                "icon": _icon_url(d["condition"]["icon"]),
                "maxtemp_c": d["maxtemp_c"],
                "mintemp_c": d["mintemp_c"],
                "avghumidity": d["avghumidity"],
                "chance_of_rain": d["daily_chance_of_rain"],
                "maxwind_kph": d["maxwind_kph"],
            }
        )
    return days


def parse_hourly(data, hours=24):
    """The next `hours` hourly entries, starting with the current local hour."""
    now = data["location"]["localtime_epoch"]
    current_hour = now - now % 3600
    upcoming = [
        h
        for day in data["forecast"]["forecastday"]
        for h in day["hour"]
        if h["time_epoch"] >= current_hour
    ]
    return [
        {
            "time": h["time"],
            "temp_c": h["temp_c"],
            "condition": h["condition"]["text"],
            "icon": _icon_url(h["condition"]["icon"]),
            "chance_of_rain": h["chance_of_rain"],
            "is_day": bool(h["is_day"]),
        }
        for h in upcoming[:hours]
    ]
