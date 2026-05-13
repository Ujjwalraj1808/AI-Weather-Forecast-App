import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
import joblib

# CSV file read
data = pd.read_csv("weather.csv")

# Fake data create
data['Humidity'] = [60 + i % 30 for i in range(len(data))]
data['Wind'] = [5 + i % 20 for i in range(len(data))]

# Rain column create
data['RainTomorrow'] = [
    1 if "rain" in str(x).lower() else 0
    for x in data['Weather']
]

# Input data
X = data[['Humidity', 'Wind']]

# Output data
y = data['RainTomorrow']

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2
)

# ML model
model = DecisionTreeClassifier()

# Train model
model.fit(X_train, y_train)

# Save model
joblib.dump(model, "rain_model.pkl")

print("Model Trained Successfully")