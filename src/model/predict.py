import os

import joblib
import pandas as pd

from src.model.train import FEATURES

MODEL_PATH = os.environ.get("MODEL_PATH", "rain_model.pkl")


def load_model(path=MODEL_PATH):
    return joblib.load(path)


def predict_rain(model, humidity, wind_kph):
    """Return True if the model predicts rain tomorrow.

    Inputs match the training features (Humidity, Wind).
    """
    row = pd.DataFrame([[humidity, wind_kph]], columns=FEATURES)
    return bool(model.predict(row)[0] == 1)
