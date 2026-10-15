"""Build the training set from Open-Meteo's historical weather archive.

Run with: python -m src.model.data   (needs internet; runs during the Docker build)

Each sample is one hour of observed weather in one city. Its label is whether
the *next* local calendar day had at least RAIN_THRESHOLD_MM of precipitation.
That matches how the app predicts: current conditions in, "rain tomorrow?" out.

Weather data by Open-Meteo.com (CC BY 4.0), based on Copernicus ERA5 reanalysis.
"""

import math
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DATA_PATH = os.environ.get("TRAINING_DATA_PATH", "data/weather_history.csv")

HOURLY_VARS = {
    "relative_humidity_2m": "humidity",
    "wind_speed_10m": "wind_kph",  # Open-Meteo default unit is km/h
    "temperature_2m": "temp_c",
    "pressure_msl": "pressure_mb",  # hPa == mb
    "cloud_cover": "cloud",
    "precipitation": "precip_mm",
}

# Mixed climates (monsoon, temperate, tropical, southern hemisphere) so the model
# is not tied to one place's weather.
CITIES = [
    ("Delhi", 28.61, 77.21),
    ("Mumbai", 19.08, 72.88),
    ("Kolkata", 22.57, 88.36),
    ("Chennai", 13.08, 80.27),
    ("Bengaluru", 12.97, 77.59),
    ("Patna", 25.59, 85.14),
    ("London", 51.51, -0.13),
    ("Paris", 48.86, 2.35),
    ("Stockholm", 59.33, 18.07),
    ("New York", 40.71, -74.01),
    ("Singapore", 1.35, 103.82),
    ("Sydney", -33.87, 151.21),
]

YEARS_OF_HISTORY = 2
ARCHIVE_DELAY_DAYS = 7  # ERA5 data arrives with about 5 days' delay
SAMPLE_EVERY_HOURS = 3  # thin out neighbouring, near-identical hours
RAIN_THRESHOLD_MM = 1.0


def date_range(today=None):
    today = today or date.today()
    end = today - timedelta(days=ARCHIVE_DELAY_DAYS)
    start = end - timedelta(days=365 * YEARS_OF_HISTORY)
    return start, end


def _session():
    retry = Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_city(session, lat, lon, start, end):
    """Raw Open-Meteo archive JSON for one location (times in local time)."""
    response = session.get(
        ARCHIVE_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": ",".join(HOURLY_VARS),
            "timezone": "auto",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def samples_from_payload(payload, city):
    """Turn one archive response into labelled hourly samples."""
    hourly = payload["hourly"]
    df = pd.DataFrame({"time": pd.to_datetime(hourly["time"])})
    for api_name, column in HOURLY_VARS.items():
        df[column] = hourly[api_name]

    df["date"] = df["time"].dt.date
    daily = df.groupby("date").agg(
        precip_mm=("precip_mm", "sum"), hours=("precip_mm", "count")
    )
    complete_days = daily[daily["hours"] == 24]["precip_mm"]
    next_day = df["date"] + timedelta(days=1)
    df["next_day_precip_mm"] = next_day.map(complete_days)

    df = df[df["time"].dt.hour % SAMPLE_EVERY_HOURS == 0]
    df = df.dropna(subset=[*HOURLY_VARS.values(), "next_day_precip_mm"]).copy()

    month = df["time"].dt.month
    df["month_sin"] = (2 * math.pi * month / 12).map(math.sin)
    df["month_cos"] = (2 * math.pi * month / 12).map(math.cos)
    df["rain_tomorrow"] = (df["next_day_precip_mm"] >= RAIN_THRESHOLD_MM).astype(int)
    df["city"] = city
    return df.drop(columns=["precip_mm", "next_day_precip_mm"])


def build_dataset(today=None):
    start, end = date_range(today)
    session = _session()
    frames = []
    for name, lat, lon in CITIES:
        payload = fetch_city(session, lat, lon, start, end)
        frames.append(samples_from_payload(payload, name))
        print(f"  {name}: {len(frames[-1])} samples")
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    dataset = build_dataset()
    Path(DATA_PATH).parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(DATA_PATH, index=False)
    print(f"Saved {len(dataset)} samples to {DATA_PATH}")
