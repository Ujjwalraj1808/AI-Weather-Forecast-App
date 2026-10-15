"""Shared fixtures. All WeatherAPI traffic is faked; tests never touch the network.

LOCATIONS maps a search.json query (lowercase) to its results. Entries for
"delhi", "delhi, india", "new delhi", "muzaffarpur, india", "london, uk",
"paris, france" and "springfield" copy live WeatherAPI responses observed on
2026-10-15. The others are hand-written in the same shape.
"""

import pytest
from fastapi.testclient import TestClient

import src.main
from src.weather import client as weather_client

DELHI_CA = {"id": 313868, "name": "Delhi", "region": "Ontario", "country": "Canada", "lat": 42.85, "lon": -80.5}
DELHI_IN = {"id": 1112321, "name": "Delhi", "region": "Delhi", "country": "India", "lat": 28.67, "lon": 77.22}
NEW_DELHI = {"id": 1126581, "name": "New Delhi", "region": "Delhi", "country": "India", "lat": 28.6, "lon": 77.2}
MUZAFFARPUR = {"id": 1125492, "name": "Muzaffarpur", "region": "Bihar", "country": "India", "lat": 26.12, "lon": 85.4}
LONDON_UK = {"id": 2801268, "name": "London", "region": "City of London, Greater London", "country": "United Kingdom", "lat": 51.52, "lon": -0.11}
LONDON_CA = {"id": 315398, "name": "London", "region": "Ontario", "country": "Canada", "lat": 42.98, "lon": -81.25}
PARIS = {"id": 803267, "name": "Paris", "region": "Ile-de-France", "country": "France", "lat": 48.87, "lon": 2.33}
SPRINGFIELDS = [
    {"id": 2594863, "name": "Springfield", "region": "Massachusetts", "country": "United States of America", "lat": 42.1, "lon": -72.59},
    {"id": 2606548, "name": "Springfield", "region": "Missouri", "country": "United States of America", "lat": 37.22, "lon": -93.3},
    {"id": 2630518, "name": "Springfield", "region": "Ohio", "country": "United States of America", "lat": 39.92, "lon": -83.81},
    {"id": 2668021, "name": "Springfield", "region": "Virginia", "country": "United States of America", "lat": 38.79, "lon": -77.19},
]
STOCKHOLM = {"id": 50, "name": "Stockholm", "region": "Stockholms Lan", "country": "Sweden", "lat": 59.33, "lon": 18.05}

LOCATIONS = {
    "delhi": [DELHI_CA],
    "delhi, india": [DELHI_IN],
    "delhi india": [DELHI_IN],
    "new delhi": [NEW_DELHI],
    "muzaffarpur": [MUZAFFARPUR],
    "muzaffarpur, india": [MUZAFFARPUR],
    "london": [LONDON_UK, LONDON_CA],
    "london, uk": [LONDON_UK],
    "paris": [PARIS],
    "paris, france": [PARIS],
    "springfield": SPRINGFIELDS,
    "stockholm": [STOCKHOLM],
}

BASE_EPOCH = 1792054800  # 2026-10-15 10:00 local in these fixtures


def make_payload(days=3, code=1183, is_day=1, localtime="2026-10-15 10:00"):
    def hours(day_index):
        return [
            {
                "time_epoch": BASE_EPOCH - 10 * 3600 + (day_index * 24 + h) * 3600,
                "time": f"2026-10-{15 + day_index} {h:02d}:00",
                "temp_c": 8.0 + h / 2,
                "is_day": 1 if 7 <= h < 18 else 0,
                "chance_of_rain": 60,
                "condition": {"text": "Light rain", "code": 1183, "icon": "//cdn.weatherapi.com/weather/64x64/day/296.png"},
            }
            for h in range(24)
        ]

    return {
        "location": {
            "name": "Stockholm",
            "region": "Stockholms Lan",
            "country": "Sweden",
            "lat": 59.33,
            "lon": 18.05,
            "tz_id": "Europe/Stockholm",
            "localtime_epoch": BASE_EPOCH,
            "localtime": localtime,
        },
        "current": {
            "temp_c": 12.0,
            "feelslike_c": 10.5,
            "humidity": 82,
            "wind_kph": 14.4,
            "is_day": is_day,
            "condition": {"text": "Light rain", "code": code, "icon": "//cdn.weatherapi.com/weather/64x64/day/296.png"},
        },
        "forecast": {
            "forecastday": [
                {
                    "date": f"2026-10-{15 + i}",
                    "astro": {"sunrise": "07:30 AM", "sunset": "05:45 PM"},
                    "day": {
                        "maxtemp_c": 13.0 + i,
                        "mintemp_c": 6.0 + i,
                        "avghumidity": 80,
                        "daily_chance_of_rain": 70,
                        "maxwind_kph": 20.0,
                        "condition": {"text": "Patchy rain", "code": 1063, "icon": "//cdn.weatherapi.com/weather/64x64/day/176.png"},
                    },
                    "hour": hours(i),
                }
                for i in range(days)
            ]
        },
    }


def fake_search(query):
    return [dict(loc) for loc in LOCATIONS.get(query.strip().lower(), [])]


class FakeModel:
    """Predicts rain when humidity > 75."""

    def predict(self, rows):
        return [1 if h > 75 else 0 for h in rows["Humidity"]]


@pytest.fixture
def fetch_calls(monkeypatch):
    """Replace WeatherAPI forecast and search calls."""
    calls = []

    def fake_fetch(q, days=10):
        calls.append((q, days))
        return make_payload(days)

    monkeypatch.setattr(src.main, "fetch_forecast", fake_fetch)
    monkeypatch.setattr(weather_client, "search_locations", fake_search)
    monkeypatch.delenv("PREFERRED_COUNTRY", raising=False)
    return calls


@pytest.fixture
def client(monkeypatch, fetch_calls):
    monkeypatch.setattr(src.main, "load_model", lambda: FakeModel())
    with TestClient(src.main.app) as c:
        yield c
