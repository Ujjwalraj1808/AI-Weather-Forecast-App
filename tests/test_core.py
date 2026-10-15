import itertools
from unittest import mock

import pytest
import requests

from src.model.predict import load_model, predict_rain
from src.model.train import train
from src.weather import client as weather_client
from tests.conftest import make_payload


def _response(payload, status=200):
    response = mock.Mock()
    response.json.return_value = payload
    response.status_code = status
    response.ok = status < 400
    return response


def test_get_advice():
    assert weather_client.get_advice(40, "Sunny") == "It is very hot. Drink more water."
    assert weather_client.get_advice(5, "Sunny") == "Weather is cold. Wear warm clothes."
    assert weather_client.get_advice(20, "Light rain") == "Carry umbrella today."
    assert weather_client.get_advice(20, "Sunny") == "Weather looks nice today."


def test_normalize_city():
    assert weather_client.normalize_city(" Gurugram ") == "gurgaon"
    assert weather_client.normalize_city("Delhi") == "Delhi"


def test_fetch_forecast_uses_env_key(monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "test-key")
    with mock.patch.object(
        weather_client.requests, "get", return_value=_response(make_payload(1))
    ) as get:
        data = weather_client.fetch_forecast("id:2", days=1)
    assert data["location"]["name"] == "Stockholm"
    assert get.call_args.args[0] == "https://api.weatherapi.com/v1/forecast.json"
    assert get.call_args.kwargs["params"] == {"key": "test-key", "q": "id:2", "days": 1}


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("WEATHER_API_KEY", raising=False)
    with pytest.raises(weather_client.WeatherServiceError) as exc:
        weather_client.get_api_key()
    assert exc.value.status_code == 503


@pytest.mark.parametrize(
    ("payload", "status", "expected_status"),
    [
        ({"error": {"code": 2006, "message": "API key is invalid."}}, 401, 503),
        ({"error": {"code": 2008, "message": "API key has been disabled."}}, 403, 503),
        ({"error": {"code": 2007, "message": "API key has exceeded calls per month quota."}}, 403, 429),
        ({"error": {"code": 9999, "message": "Internal application error."}}, 400, 502),
        ({"unexpected": True}, 429, 429),
        ({"unexpected": True}, 500, 502),
    ],
)
def test_api_errors_map_to_status(monkeypatch, payload, status, expected_status):
    monkeypatch.setenv("WEATHER_API_KEY", "test-key")
    with (
        mock.patch.object(weather_client.requests, "get", return_value=_response(payload, status)),
        pytest.raises(weather_client.WeatherServiceError) as exc,
    ):
        weather_client.fetch_forecast("id:1")
    assert exc.value.status_code == expected_status


def test_no_location_error_is_city_not_found(monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "test-key")
    payload = {"error": {"code": 1006, "message": "No matching location found."}}
    with (
        mock.patch.object(weather_client.requests, "get", return_value=_response(payload, 400)),
        pytest.raises(weather_client.CityNotFoundError),
    ):
        weather_client.fetch_forecast("id:1")


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [(requests.Timeout("t"), 504), (requests.ConnectionError("c"), 502)],
)
def test_network_errors_never_leak_key(monkeypatch, exc, expected_status):
    monkeypatch.setenv("WEATHER_API_KEY", "super-secret-key")
    exc.args = ("GET https://api.weatherapi.com/v1/forecast.json?key=super-secret-key failed",)
    with (
        mock.patch.object(weather_client.requests, "get", side_effect=exc),
        pytest.raises(weather_client.WeatherServiceError) as raised,
    ):
        weather_client.fetch_forecast("id:1")
    assert raised.value.status_code == expected_status
    assert "super-secret-key" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_unreadable_response(monkeypatch):
    monkeypatch.setenv("WEATHER_API_KEY", "test-key")
    response = _response(None)
    response.json.side_effect = ValueError("not json")
    with (
        mock.patch.object(weather_client.requests, "get", return_value=response),
        pytest.raises(weather_client.WeatherServiceError),
    ):
        weather_client.fetch_forecast("id:1")


def test_parse_hourly_starts_at_current_hour():
    hourly = weather_client.parse_hourly(make_payload(2))
    assert len(hourly) == 24
    assert hourly[0]["time"] == "2026-10-15 10:00"
    assert hourly[-1]["time"] == "2026-10-16 09:00"


def test_train_and_predict(tmp_path):
    model_path = tmp_path / "rain_model.pkl"
    train(model_path=model_path)
    model = load_model(model_path)
    assert isinstance(predict_rain(model, 80, 10), bool)


def test_training_is_reproducible(tmp_path):
    """Regression: two trainings give identical predictions over the input range."""
    grid = list(itertools.product(range(40, 101, 5), range(0, 41, 5)))
    tables = []
    for i in range(2):
        model = train(model_path=tmp_path / f"m{i}.pkl")
        tables.append([predict_rain(model, h, w) for h, w in grid])
    assert tables[0] == tables[1]


def test_predict_rain_uses_humidity_then_wind():
    seen = {}

    class Recorder:
        def predict(self, rows):
            seen.update(rows.iloc[0].to_dict())
            return [0]

    predict_rain(Recorder(), 81, 12)
    assert seen == {"Humidity": 81, "Wind": 12}
