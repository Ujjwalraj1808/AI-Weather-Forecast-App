"""Train and evaluate the rain-tomorrow model. Run with: python -m src.model.train

Reads the dataset written by src.model.data, holds out the most recent 20% of
dates for testing (no shuffling across time), and refuses to save a model that
does not beat MIN_ROC_AUC on that held-out period.
"""

import json
import os
from datetime import UTC, datetime

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

from src.model.data import DATA_PATH, RAIN_THRESHOLD_MM

MODEL_PATH = os.environ.get("MODEL_PATH", "rain_model.pkl")
METRICS_PATH = os.environ.get("METRICS_PATH", "model_metrics.json")
MIN_ROC_AUC = float(os.environ.get("MIN_ROC_AUC", "0.65"))

FEATURES = ["humidity", "wind_kph", "temp_c", "pressure_mb", "cloud", "month_sin", "month_cos"]
LABEL = "rain_tomorrow"
TEST_FRACTION = 0.2
RANDOM_STATE = 42


class ModelQualityError(Exception):
    pass


def time_split(df):
    """Earlier dates train, the latest TEST_FRACTION of dates test."""
    dates = pd.to_datetime(df["time"]).dt.normalize()
    cutoff = dates.quantile(1 - TEST_FRACTION)
    return df[dates < cutoff], df[dates >= cutoff]


def evaluate(model, test):
    proba = model.predict_proba(test[FEATURES])[:, 1]
    pred = (proba >= 0.5).astype(int)
    y = test[LABEL]
    base_rate = float(y.mean())
    return {
        "accuracy": round(accuracy_score(y, pred), 4),
        "precision": round(precision_score(y, pred, zero_division=0), 4),
        "recall": round(recall_score(y, pred, zero_division=0), 4),
        "f1": round(f1_score(y, pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y, proba), 4),
        "rain_day_share": round(base_rate, 4),
        "always_no_rain_accuracy": round(1 - base_rate, 4),
    }


def train(data_path=DATA_PATH, model_path=MODEL_PATH, metrics_path=METRICS_PATH):
    df = pd.read_csv(data_path)
    train_df, test_df = time_split(df)

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=20,
        class_weight="balanced",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    model.fit(train_df[FEATURES], train_df[LABEL])
    metrics = evaluate(model, test_df)

    if metrics["roc_auc"] < MIN_ROC_AUC:
        raise ModelQualityError(
            f"ROC AUC {metrics['roc_auc']} is below the minimum {MIN_ROC_AUC}; model not saved."
        )

    info = {
        "model": "RandomForestClassifier",
        "features": FEATURES,
        "label": f"next local day precipitation >= {RAIN_THRESHOLD_MM} mm",
        "cities": sorted(df["city"].unique().tolist()),
        "data_from": str(pd.to_datetime(df["time"]).min().date()),
        "data_to": str(pd.to_datetime(df["time"]).max().date()),
        "train_samples": len(train_df),
        "test_samples": len(test_df),
        "test_period_from": str(pd.to_datetime(test_df["time"]).min().date()),
        "metrics": metrics,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_source": "Open-Meteo Historical Weather API (ERA5), CC BY 4.0",
    }
    joblib.dump(model, model_path)
    with open(metrics_path, "w") as f:
        json.dump(info, f, indent=2)
    return model, info


if __name__ == "__main__":
    _, info = train()
    print(json.dumps(info["metrics"], indent=2))
    print(f"Model saved to {MODEL_PATH}, metrics to {METRICS_PATH}")
