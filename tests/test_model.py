"""ML pipeline tests. No network: Open-Meteo responses are built in the documented shape."""

import json
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.model import data as model_data
from src.model.predict import features_from_current, load_model, load_model_info, predict_rain
from src.model.train import FEATURES, ModelQualityError, time_split, train


def archive_payload(days, rain_on=()):
    """Open-Meteo /v1/archive response: hourly arrays keyed by variable, local ISO times."""
    start = datetime(2025, 7, 1)
    times = [start + timedelta(hours=h) for h in range(24 * days)]
    rain_dates = {start.date() + timedelta(days=d) for d in rain_on}
    return {
        "latitude": 28.6,
        "longitude": 77.2,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "hourly_units": {"precipitation": "mm"},
        "hourly": {
            "time": [t.strftime("%Y-%m-%dT%H:%M") for t in times],
            "relative_humidity_2m": [70] * len(times),
            "wind_speed_10m": [10.0] * len(times),
            "temperature_2m": [30.0] * len(times),
            "pressure_msl": [1005.0] * len(times),
            "cloud_cover": [50] * len(times),
            # 0.5 mm in each of 3 hours = 1.5 mm on rain days
            "precipitation": [0.5 if t.date() in rain_dates and t.hour < 3 else 0.0 for t in times],
        },
    }


def test_labels_use_next_local_day():
    df = model_data.samples_from_payload(archive_payload(days=4, rain_on={2}), "Delhi")
    by_date = df.groupby(df["time"].dt.date)["rain_tomorrow"].unique()
    # Day 1 (index 1) is followed by the rainy day 2; the last day has no "tomorrow" and is dropped
    assert {d.isoformat(): list(v) for d, v in by_date.items()} == {
        "2025-07-01": [0],
        "2025-07-02": [1],
        "2025-07-03": [0],
    }


def test_samples_every_three_hours_with_expected_columns():
    df = model_data.samples_from_payload(archive_payload(days=3), "Delhi")
    assert set(df["time"].dt.hour) == {0, 3, 6, 9, 12, 15, 18, 21}
    assert set(FEATURES) <= set(df.columns)
    assert {"time", "city", "rain_tomorrow"} <= set(df.columns)
    assert "precip_mm" not in df.columns  # no leakage of the day's own rain


def test_incomplete_next_day_is_dropped():
    payload = archive_payload(days=3)
    for values in payload["hourly"].values():
        del values[-5:]  # day 3 now has only 19 hours
    df = model_data.samples_from_payload(payload, "Delhi")
    assert set(df["time"].dt.date.astype(str)) == {"2025-07-01"}


def test_missing_values_are_dropped():
    payload = archive_payload(days=3)
    payload["hourly"]["pressure_msl"][0] = None
    df = model_data.samples_from_payload(payload, "Delhi")
    assert pd.Timestamp("2025-07-01 00:00") not in set(df["time"])


def test_date_range_leaves_archive_delay():
    start, end = model_data.date_range(today=date(2026, 10, 15))
    assert end == date(2026, 10, 8)
    assert (end - start).days == 730


def test_fetch_city_requests_documented_parameters():
    calls = {}

    class Session:
        def get(self, url, params, timeout):
            calls.update(url=url, params=params)

            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"hourly": {}}

            return R()

    model_data.fetch_city(Session(), 28.6, 77.2, date(2024, 1, 1), date(2025, 1, 1))
    assert calls["url"] == "https://archive-api.open-meteo.com/v1/archive"
    assert calls["params"]["hourly"].split(",") == [
        "relative_humidity_2m", "wind_speed_10m", "temperature_2m",
        "pressure_msl", "cloud_cover", "precipitation",
    ]
    assert calls["params"]["timezone"] == "auto"
    assert calls["params"]["start_date"] == "2024-01-01"


def synthetic_dataset(n=4000, signal=True, seed=0):
    rng = np.random.default_rng(seed)
    humidity = rng.uniform(20, 100, n)
    cloud = rng.uniform(0, 100, n)
    if signal:
        rain = ((humidity + cloud) / 2 + rng.normal(0, 10, n) > 65).astype(int)
    else:
        rain = rng.integers(0, 2, n)
    times = pd.date_range("2024-01-01", periods=n, freq="3h")
    return pd.DataFrame({
        "time": times.strftime("%Y-%m-%d %H:%M:%S"),
        "humidity": humidity,
        "wind_kph": rng.uniform(0, 40, n),
        "temp_c": rng.uniform(0, 40, n),
        "pressure_mb": rng.uniform(990, 1030, n),
        "cloud": cloud,
        "month_sin": np.sin(2 * np.pi * times.month / 12),
        "month_cos": np.cos(2 * np.pi * times.month / 12),
        "rain_tomorrow": rain,
        "city": "Test",
    })


def test_time_split_keeps_test_period_after_training():
    df = synthetic_dataset()
    train_df, test_df = time_split(df)
    assert pd.to_datetime(train_df["time"]).max() < pd.to_datetime(test_df["time"]).min()
    assert 0.15 < len(test_df) / len(df) < 0.25


def test_train_saves_model_and_honest_metrics(tmp_path):
    csv = tmp_path / "d.csv"
    synthetic_dataset().to_csv(csv, index=False)
    train(data_path=csv, model_path=tmp_path / "m.pkl", metrics_path=tmp_path / "m.json")

    info = load_model_info(tmp_path / "m.json")
    assert info == json.loads((tmp_path / "m.json").read_text())
    assert info["features"] == FEATURES
    assert info["metrics"]["roc_auc"] > 0.8
    assert info["train_samples"] + info["test_samples"] == 4000
    assert set(info["metrics"]) == {
        "accuracy", "precision", "recall", "f1", "roc_auc", "rain_day_share", "always_no_rain_accuracy",
    }

    model = load_model(tmp_path / "m.pkl")
    wet = {**dict.fromkeys(FEATURES, 0.0), "humidity": 98, "cloud": 98, "pressure_mb": 1000}
    dry = {**wet, "humidity": 25, "cloud": 5}
    assert predict_rain(model, wet)["probability"] > predict_rain(model, dry)["probability"]


def test_quality_gate_rejects_useless_model(tmp_path):
    csv = tmp_path / "d.csv"
    synthetic_dataset(signal=False).to_csv(csv, index=False)
    with pytest.raises(ModelQualityError):
        train(data_path=csv, model_path=tmp_path / "m.pkl", metrics_path=tmp_path / "m.json")
    assert not (tmp_path / "m.pkl").exists()


def test_training_is_reproducible(tmp_path):
    csv = tmp_path / "d.csv"
    synthetic_dataset().to_csv(csv, index=False)
    _, a = train(data_path=csv, model_path=tmp_path / "a.pkl", metrics_path=tmp_path / "a.json")
    _, b = train(data_path=csv, model_path=tmp_path / "b.pkl", metrics_path=tmp_path / "b.json")
    assert a["metrics"] == b["metrics"]


def test_features_from_current_and_column_order():
    current = {"humidity": 81, "wind_kph": 12.0, "temp_c": 25.0, "pressure_mb": 1008.0,
               "cloud": 75, "localtime": "2026-07-15 10:00"}
    features = features_from_current(current)
    assert features["month_sin"] == pytest.approx(np.sin(2 * np.pi * 7 / 12))
    seen = {}

    class Recorder:
        def predict_proba(self, rows):
            seen["columns"] = list(rows.columns)
            seen["row"] = rows.iloc[0].tolist()
            return [[0.3, 0.7]]

    assert predict_rain(Recorder(), features) == {"rain_expected": True, "probability": 0.7}
    assert seen["columns"] == FEATURES
    assert seen["row"][:5] == [81, 12.0, 25.0, 1008.0, 75]
