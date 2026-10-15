import src.main
from src.weather import CityNotFoundError, WeatherServiceError
from src.weather import client as weather_client


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_weather(client, fetch_calls):
    r = client.get("/weather", params={"city": "Stockholm"})
    assert r.status_code == 200
    body = r.json()
    assert body["location"] == "Stockholm"
    assert body["country"] == "Sweden"
    assert body["temp_c"] == 12.0
    assert body["sunrise"] == "07:30 AM"
    assert body["advice"] == "Carry umbrella today."
    assert body["scene"] == "rain"
    assert body["icon"].startswith("https://cdn.weatherapi.com/")
    assert fetch_calls == [("id:50", 1)]


def test_weather_with_location_id_skips_search(client, fetch_calls, monkeypatch):
    monkeypatch.setattr(weather_client, "search_locations", None)
    assert client.get("/weather", params={"city": "id:2"}).status_code == 200
    assert fetch_calls == [("id:2", 1)]


def test_weather_with_coordinates_skips_search(client, fetch_calls):
    assert client.get("/weather", params={"city": "28.67,77.22"}).status_code == 200
    assert fetch_calls == [("28.67,77.22", 1)]


def test_weather_requires_city(client):
    assert client.get("/weather").status_code == 422


def test_forecast(client, fetch_calls):
    r = client.get("/forecast", params={"city": "id:50", "days": 3})
    assert r.status_code == 200
    body = r.json()
    assert len(body["days"]) == 3
    assert body["days"][0]["chance_of_rain"] == 70
    assert len(body["hourly"]) == 24
    assert body["hourly"][0]["time"] == "2026-10-15 10:00"
    assert fetch_calls == [("id:50", 3)]


def test_forecast_days_out_of_range(client):
    assert client.get("/forecast", params={"city": "X", "days": 0}).status_code == 422
    assert client.get("/forecast", params={"city": "X", "days": 15}).status_code == 422


def test_predict_rain(client):
    r = client.get("/predict-rain", params={"city": "id:50"})
    assert r.status_code == 200
    assert r.json() == {"location": "Stockholm", "rain_expected": True, "probability": 0.8}


def test_search_delhi_lists_india_first(client):
    """Live WeatherAPI search for "Delhi" returns only Canada; we widen it."""
    r = client.get("/search", params={"q": "Delhi"})
    assert r.status_code == 200
    assert [(c["id"], c["country"]) for c in r.json()] == [(1112321, "India"), (313868, "Canada")]


def test_resolve_delhi_prefers_india(client):
    r = client.get("/resolve", params={"q": "Delhi"})
    assert r.status_code == 200
    assert (r.json()["id"], r.json()["country"]) == (1112321, "India")


def test_ambiguous_city_returns_409_with_candidates(client):
    r = client.get("/weather", params={"city": "Springfield"})
    assert r.status_code == 409
    body = r.json()
    assert body["detail"] == 'Several places match "Springfield"'
    assert len(body["candidates"]) == 4


def test_unknown_city_returns_404(client):
    r = client.get("/weather", params={"city": "Atlantis"})
    assert r.status_code == 404


def test_city_not_found_from_forecast_returns_404(client, monkeypatch):
    def raise_not_found(q, days=10):
        raise CityNotFoundError("No matching location found.")

    monkeypatch.setattr(src.main, "fetch_forecast", raise_not_found)
    assert client.get("/weather", params={"city": "id:1"}).status_code == 404


def test_service_errors_keep_status_and_message(client, monkeypatch):
    def raise_timeout(q, days=10):
        raise WeatherServiceError("WeatherAPI did not respond in time. Try again.", 504)

    monkeypatch.setattr(src.main, "fetch_forecast", raise_timeout)
    r = client.get("/weather", params={"city": "id:1"})
    assert r.status_code == 504
    assert r.json() == {"detail": "WeatherAPI did not respond in time. Try again."}


def test_scene_image_is_null_without_photo(client):
    body = client.get("/weather", params={"city": "id:50"}).json()
    assert body["scene_image"] is None


def test_scene_image_uses_photo_when_present(client, monkeypatch, tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "rain.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(src.main, "STATIC_DIR", tmp_path)
    body = client.get("/weather", params={"city": "id:50"}).json()
    assert body["scene_image"] == "/static/img/rain.jpg"


def test_index_serves_web_ui(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert '<script src="/static/app.js"' in r.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_dashboard_uses_one_weatherapi_call(client, fetch_calls):
    r = client.get("/dashboard", params={"city": "Delhi"})
    assert r.status_code == 200
    body = r.json()
    assert body["current"]["location"] == "Stockholm"
    assert body["current"]["scene"] == "rain"
    assert len(body["days"]) == 10
    assert len(body["hourly"]) == 24
    assert body["prediction"] == {"rain_expected": True, "probability": 0.8}
    assert fetch_calls == [("id:1112321", 10)]


def test_model_info(client):
    assert client.get("/model").json() == {"model": "RandomForestClassifier", "metrics": {"roc_auc": 0.8}}


def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    from src.ratelimit import limiter

    monkeypatch.setattr(limiter, "limit", 3)
    codes = [client.get("/weather", params={"city": "id:50"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = client.get("/weather", params={"city": "id:50"})
    assert int(r.headers["Retry-After"]) >= 1
    # Pages and probes are never limited
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200
