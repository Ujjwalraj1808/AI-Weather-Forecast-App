"""Train the rain classifier. Run with: python -m src.model.train"""

import os

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier

DATA_PATH = os.environ.get("WEATHER_DATA_PATH", "weather.csv")
MODEL_PATH = os.environ.get("MODEL_PATH", "rain_model.pkl")
FEATURES = ["Humidity", "Wind"]
# Fixed seed so every build produces the same model.
RANDOM_STATE = 42


def train(data_path=DATA_PATH, model_path=MODEL_PATH):
    data = pd.read_csv(data_path)

    # Synthetic features (unchanged from the original script)
    data["Humidity"] = [60 + i % 30 for i in range(len(data))]
    data["Wind"] = [5 + i % 20 for i in range(len(data))]

    data["RainTomorrow"] = [
        1 if "rain" in str(x).lower() else 0 for x in data["Weather"]
    ]

    X = data[FEATURES]
    y = data["RainTomorrow"]

    X_train, _X_test, y_train, _y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE
    )

    model = DecisionTreeClassifier(random_state=RANDOM_STATE)
    model.fit(X_train, y_train)

    joblib.dump(model, model_path)
    return model


if __name__ == "__main__":
    train()
    print(f"Model trained and saved to {MODEL_PATH}")
