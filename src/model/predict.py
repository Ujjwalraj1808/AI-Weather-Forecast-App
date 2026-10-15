import json
import math
import os

import joblib
import pandas as pd

from src.model.train import FEATURES

MODEL_PATH = os.environ.get("MODEL_PATH", "rain_model.pkl")
METRICS_PATH = os.environ.get("METRICS_PATH", "model_metrics.json")


def load_model(path=MODEL_PATH):
    return joblib.load(path)


def load_model_info(path=METRICS_PATH):
    with open(path) as f:
        return json.load(f)


def features_from_current(current):
    """Model inputs from parse_current() output (WeatherAPI current conditions)."""
    month = int(current["localtime"][5:7])
    return {
        "humidity": current["humidity"],
        "wind_kph": current["wind_kph"],
        "temp_c": current["temp_c"],
        "pressure_mb": current["pressure_mb"],
        "cloud": current["cloud"],
        "month_sin": math.sin(2 * math.pi * month / 12),
        "month_cos": math.cos(2 * math.pi * month / 12),
    }


def predict_rain(model, features):
    row = pd.DataFrame([[features[name] for name in FEATURES]], columns=FEATURES)
    probability = float(model.predict_proba(row)[0][1])
    return {"rain_expected": probability >= 0.5, "probability": round(probability, 3)}
