from unittest import mock

from src.cache import TTLCache
from src.ratelimit import RateLimiter
from src.weather import client as weather_client
from tests.conftest import make_payload


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_ttl_cache_expires_and_copies():
    clock = Clock()
    cache = TTLCache(ttl_seconds=10, max_entries=10, clock=clock)
    cache.set("a", {"x": [1]})
    got = cache.get("a")
    got["x"].append(2)  # callers can't mutate the cached copy
    assert cache.get("a") == {"x": [1]}
    clock.now = 10
    assert cache.get("a") is None


def test_ttl_cache_evicts_oldest():
    cache = TTLCache(ttl_seconds=100, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # a is now most recently used
    cache.set("c", 3)
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (1, None, 3)


def test_forecast_is_cached(monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "k")
    response = mock.Mock(status_code=200, ok=True)
    response.json.return_value = make_payload(1)
    with mock.patch.object(weather_client.requests, "get", return_value=response) as get:
        weather_client.fetch_forecast("id:1", days=1)
        weather_client.fetch_forecast("ID:1 ", days=1)
        weather_client.fetch_forecast("id:1", days=3)
    assert get.call_count == 2  # same place+days served from cache


def test_search_is_cached(monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "k")
    response = mock.Mock(status_code=200, ok=True)
    response.json.return_value = [
        {"id": 1, "name": "Delhi", "region": "Delhi", "country": "India", "lat": 1, "lon": 2, "url": "x"}
    ]
    with mock.patch.object(weather_client.requests, "get", return_value=response) as get:
        assert weather_client.search_locations("Delhi") == weather_client.search_locations("delhi")
    assert get.call_count == 1


def test_errors_are_not_cached(monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "k")
    bad = mock.Mock(status_code=400, ok=False)
    bad.json.return_value = {"error": {"code": 9999, "message": "boom"}}
    good = mock.Mock(status_code=200, ok=True)
    good.json.return_value = make_payload(1)
    with mock.patch.object(weather_client.requests, "get", side_effect=[bad, good]):
        try:
            weather_client.fetch_forecast("id:1", days=1)
        except weather_client.WeatherServiceError:
            pass
        assert weather_client.fetch_forecast("id:1", days=1)["location"]["name"] == "Stockholm"


def test_rate_limiter_window():
    clock = Clock()
    limiter = RateLimiter(limit=2, window_seconds=60, clock=clock)
    assert limiter.check("ip") == 0
    assert limiter.check("ip") == 0
    assert limiter.check("ip") > 0
    assert limiter.check("other") == 0  # separate budget per client
    clock.now = 60.1
    assert limiter.check("ip") == 0
