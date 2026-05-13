import tkinter as tk
from tkinter import messagebox
import requests
from datetime import datetime
from PIL import Image, ImageTk
import webbrowser
import geocoder
import joblib

# =========================
# API KEY
# =========================
API_KEY = "1e2af43db7ed4513abc100521261305"

# =========================
# LOAD ML MODEL
# =========================
model = joblib.load("rain_model.pkl")

# =========================
# AUTO LOCATION
# =========================
def detect_location():

    try:
        g = geocoder.ip('me')

        city = g.city

        city_entry.delete(0, tk.END)

        city_entry.insert(0, city)

    except:
        messagebox.showerror(
            "Error",
            "Location detection failed"
        )

# =========================
# OPEN MAP
# =========================
def open_map():

    city = city_entry.get()

    if city != "":
        url = f"https://www.google.com/maps/search/{city}"

        webbrowser.open(url)

# =========================
# GET WEATHER
# =========================
def get_weather(event=None):

    city = city_entry.get()

    if city == "":
        messagebox.showerror(
            "Error",
            "Please enter city name"
        )
        return

    result_text.delete(1.0, tk.END)

    result_text.insert(
        tk.END,
        "⏳ Loading weather data..."
    )

    url = f"http://api.weatherapi.com/v1/forecast.json?key={API_KEY}&q={city}&days=10"

    try:

        response = requests.get(url)

        data = response.json()

        if "error" in data:
            messagebox.showerror(
                "Error",
                data["error"]["message"]
            )
            return

        # =========================
        # CURRENT WEATHER
        # =========================
        location = data["location"]["name"]

        country = data["location"]["country"]

        localtime = data["location"]["localtime"]

        temp = data["current"]["temp_c"]

        feels = data["current"]["feelslike_c"]

        humidity = data["current"]["humidity"]

        wind = data["current"]["wind_kph"]

        weather = data["current"]["condition"]["text"]

        sunrise = data["forecast"]["forecastday"][0]["astro"]["sunrise"]

        sunset = data["forecast"]["forecastday"][0]["astro"]["sunset"]

        # =========================
        # CURRENT ML PREDICTION
        # =========================
        prediction = model.predict([[humidity, wind]])

        if prediction[0] == 1:
            rain_prediction = "🌧 Rain Expected Tomorrow"

        else:
            rain_prediction = "☀ No Rain Expected Tomorrow"

        # =========================
        # AI WEATHER ADVICE
        # =========================
        advice = ""

        if temp > 35:
            advice = "🔥 It's very hot. Drink more water."

        elif "rain" in weather.lower():
            advice = "☔ Carry an umbrella."

        elif temp < 15:
            advice = "🧥 Wear warm clothes."

        elif wind > 30:
            advice = "🌪 Strong winds outside."

        elif humidity > 80:
            advice = "💧 Very humid weather today."

        else:
            advice = "😎 Weather looks nice today."

        # =========================
        # WEATHER ICON
        # =========================
        icon = "☀"

        if "cloud" in weather.lower():
            icon = "☁"

        elif "rain" in weather.lower():
            icon = "🌧"

        elif "storm" in weather.lower():
            icon = "⛈"

        elif "snow" in weather.lower():
            icon = "❄"

        # =========================
        # CLEAR OLD TEXT
        # =========================
        result_text.delete(1.0, tk.END)

        # =========================
        # SHOW CURRENT WEATHER
        # =========================
        result_text.insert(
            tk.END,
            f"""
📍 {location}, {country}

🕒 {localtime}

{icon} {weather}

🌡 Temperature: {temp}°C
🤒 Feels Like: {feels}°C

💧 Humidity: {humidity}%
🌬 Wind Speed: {wind} kph

🤖 AI Advice:
{advice}

🔮 ML Prediction:
{rain_prediction}

🌅 Sunrise: {sunrise}
🌇 Sunset: {sunset}

══════════════════════════
        10 DAY FORECAST
══════════════════════════
"""
        )

        # =========================
        # FORECAST LOOP
        # =========================
        for day in data["forecast"]["forecastday"]:

            date = day["date"]

            day_name = datetime.strptime(
                date,
                "%Y-%m-%d"
            ).strftime("%A")

            condition = day["day"]["condition"]["text"]

            max_temp = day["day"]["maxtemp_c"]

            min_temp = day["day"]["mintemp_c"]

            avg_humidity = day["day"]["avghumidity"]

            max_wind = day["day"]["maxwind_kph"]

            chance_rain = day["day"]["daily_chance_of_rain"]

            sunrise_day = day["astro"]["sunrise"]

            sunset_day = day["astro"]["sunset"]

            # =========================
            # FORECAST ML PREDICTION
            # =========================
            prediction = model.predict(
                [[avg_humidity, max_wind]]
            )

            if prediction[0] == 1:
                future_prediction = "🌧 Rain Expected"

            else:
                future_prediction = "☀ No Rain Expected"

            # =========================
            # FORECAST ICONS
            # =========================
            day_icon = "☀"

            if "cloud" in condition.lower():
                day_icon = "☁"

            elif "rain" in condition.lower():
                day_icon = "🌧"

            elif "storm" in condition.lower():
                day_icon = "⛈"

            elif "snow" in condition.lower():
                day_icon = "❄"

            # =========================
            # SHOW FORECAST
            # =========================
            result_text.insert(
                tk.END,
                f"""

📅 {day_name} ({date})

{day_icon} {condition}

⬆ Max Temp: {max_temp}°C
⬇ Min Temp: {min_temp}°C

💧 Humidity: {avg_humidity}%
🌬 Wind: {max_wind} kph
🌧 Chance of Rain: {chance_rain}%

🌅 Sunrise: {sunrise_day}
🌇 Sunset: {sunset_day}

🔮 ML Prediction:
{future_prediction}

────────────────────────
"""
            )

    except:
        messagebox.showerror(
            "Error",
            "Failed to fetch weather data"
        )

# =========================
# MAIN WINDOW
# =========================
root = tk.Tk()

root.title("Weather Forecast")

root.geometry("1000x700")

root.config(bg="#081b33")

root.resizable(True, True)

# =========================
# WINDOW ICON
# =========================
try:
    root.iconbitmap("weather.ico")

except:
    pass

# =========================
# BACKGROUND IMAGE
# =========================
try:

    bg_image = Image.open("bg.png")

    bg_image = bg_image.resize((1000, 700))

    bg_photo = ImageTk.PhotoImage(bg_image)

    bg_label = tk.Label(root, image=bg_photo)

    bg_label.place(
        x=0,
        y=0,
        relwidth=1,
        relheight=1
    )

except:
    pass

# =========================
# TOP FRAME
# =========================
top_frame = tk.Frame(
    root,
    bg="#000000"
)

top_frame.pack(fill="x")

# =========================
# TITLE
# =========================
title = tk.Label(
    top_frame,
    text="☁ Weather Forecast",
    font=("Arial", 30, "bold"),
    bg="#000000",
    fg="white"
)

title.pack(pady=20)

# =========================
# CITY ENTRY
# =========================
city_entry = tk.Entry(
    top_frame,
    font=("Arial", 18),
    width=25,
    justify="center"
)

city_entry.pack(pady=10)

city_entry.bind("<Return>", get_weather)

# =========================
# BUTTON FRAME
# =========================
btn_frame = tk.Frame(
    top_frame,
    bg="#000000"
)

btn_frame.pack(pady=10)

# =========================
# GET WEATHER BUTTON
# =========================
search_btn = tk.Button(
    btn_frame,
    text="Get Weather",
    font=("Arial", 14, "bold"),
    bg="#1e90ff",
    fg="white",
    padx=15,
    pady=8,
    command=get_weather,
    cursor="hand2"
)

search_btn.grid(
    row=0,
    column=0,
    padx=5
)

# =========================
# AUTO LOCATION BUTTON
# =========================
location_btn = tk.Button(
    btn_frame,
    text="📍 Auto Detect Location",
    font=("Arial", 12, "bold"),
    bg="#28a745",
    fg="white",
    padx=10,
    pady=8,
    command=detect_location,
    cursor="hand2"
)

location_btn.grid(
    row=0,
    column=1,
    padx=5
)

# =========================
# OPEN MAP BUTTON
# =========================
map_btn = tk.Button(
    btn_frame,
    text="🗺 Open Map",
    font=("Arial", 12, "bold"),
    bg="#ff9800",
    fg="white",
    padx=10,
    pady=8,
    command=open_map,
    cursor="hand2"
)

map_btn.grid(
    row=0,
    column=2,
    padx=5
)

# =========================
# BUTTON HOVER EFFECT
# =========================
def on_enter(e):
    search_btn['bg'] = "#00bfff"

def on_leave(e):
    search_btn['bg'] = "#1e90ff"

search_btn.bind("<Enter>", on_enter)

search_btn.bind("<Leave>", on_leave)

# =========================
# RESULT FRAME
# =========================
frame = tk.Frame(
    root,
    bg="#081b33"
)

frame.pack(
    fill="both",
    expand=True,
    padx=20,
    pady=20
)

# =========================
# SCROLLBAR
# =========================
scrollbar = tk.Scrollbar(frame)

scrollbar.pack(
    side="right",
    fill="y"
)

# =========================
# RESULT TEXT
# =========================
result_text = tk.Text(
    frame,
    font=("Arial", 14),
    bg="#102542",
    fg="white",
    wrap="word",
    yscrollcommand=scrollbar.set
)

result_text.pack(
    fill="both",
    expand=True
)

scrollbar.config(
    command=result_text.yview
)

# =========================
# RUN APP
# =========================
root.mainloop()