# AI Weather Forecast App

A containerised FastAPI web app that shows live weather from [WeatherAPI.com](https://www.weatherapi.com/):
current conditions, the next 24 hours, a multi-day forecast and an experimental ML rain estimate.
It started as a Tkinter desktop app and was rebuilt as a web service for a DevOps portfolio.

## Features

- **City search with suggestions.** Suggestions show city, region and country. Picking one locks in that exact place.
- **Correct place for ambiguous names.**
  - Typing "Delhi" gives Delhi, India, not Delhi, Canada (see [How a city is chosen](#how-a-city-is-chosen)).
  - When a name stays ambiguous, the app asks you to choose.
- **Use my location** (browser geolocation) and **Open in Google Maps** (exact coordinates).
- **Current weather:** temperature, feels-like, condition and icon, humidity, wind, sunrise, sunset, chance of rain and local time.
- **Forecasts:** a 24-hour hourly strip and a multi-day forecast with temperature-range bars.
- **Backgrounds that follow the real sky:** clear day, clear night, golden hour, cloudy, rain, storm, snow and fog.
- **Experimental ML estimate:** a "rain tomorrow" estimate, shown apart from WeatherAPI's forecast.
- **Clear error messages:** unknown places, invalid API keys, quota limits, timeouts and network errors.
- **Responsive and accessible:** works from 320px phones to desktops, and supports the keyboard, visible focus rings and reduced motion.

## Tech stack

Python 3.12, FastAPI, scikit-learn, pytest, ruff, Docker. The front end is plain HTML, CSS and JS with no frameworks.

## Run it

### With Docker (recommended)

```powershell
Copy-Item .env.example .env      # then put your WeatherAPI key in .env
docker compose up --build -d
docker compose ps                 # wait for STATUS "healthy"
```

Open http://localhost:8000. The model is trained inside the image during the build; no `.pkl` is committed.

### Locally

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m src.model.train         # creates rain_model.pkl
$env:WEATHER_API_KEY = "your_key"
uvicorn src.main:app --reload
```

## Configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `WEATHER_API_KEY` | yes | none | WeatherAPI key. Read only from the environment and never logged or returned. |
| `PREFERRED_COUNTRY` | no | `India` | Tie-breaker when a bare city name matches places in several countries |
| `PORT` | no | `8000` | Port the container listens on |
| `MODEL_PATH` | no | `rain_model.pkl` | Where the model is saved and loaded |

Never commit `.env`. It is listed in `.gitignore` and `.dockerignore`.

## API

| Endpoint | Description |
|---|---|
| `GET /health` | Health check used by Docker's `HEALTHCHECK` |
| `GET /search?q=` | Place suggestions (id, name, region, country, lat, lon) |
| `GET /resolve?q=` | Turns free text into one exact place (`409` with candidates if ambiguous) |
| `GET /weather?city=` | Current conditions plus the background scene |
| `GET /forecast?city=&days=` | Daily forecast (1–14 days) and the next 24 hours |
| `GET /predict-rain?city=` | Experimental ML estimate for tomorrow |

`city` accepts free text ("Delhi, India"), a place id from `/search` (`id:123`) or coordinates (`28.61,77.21`).

Error status codes:

| Status | Meaning |
|---|---|
| 404 | Place not found |
| 409 | Several places match; the response lists them |
| 429 | WeatherAPI quota or rate limit reached |
| 502 | WeatherAPI error |
| 503 | API key missing or rejected |
| 504 | WeatherAPI timed out |

## How a city is chosen

Sending a bare name such as `q=Delhi` lets WeatherAPI pick a match on its own, which returned Delhi, Ontario, Canada.
WeatherAPI's search has the same gap: on 2026-10-15, searching "Delhi" listed only the Canadian Delhi,
while searching "Delhi, India" listed Delhi, India.

So the app:

1. Searches the name. If nothing in `PREFERRED_COUNTRY` comes back, it also searches "name, PREFERRED_COUNTRY" and merges the results.
2. With a qualifier after a comma ("Delhi, India", "London, UK", "Springfield, Missouri"), searches the full text plus the name and keeps matches for that country or region.
3. Prefers exact name matches, and lets `PREFERRED_COUNTRY` break a tie between them.
4. Asks you to choose if it is still ambiguous ("London", "Springfield").

All requests for one search then use that place's id, so current weather, forecast and ML estimate always describe the same place.

## Dynamic backgrounds

The server maps WeatherAPI's condition code and day/night flag to a scene (`src/weather/scenes.py`).
Clear skies within 45 minutes of local sunrise or sunset become "golden".

- **Gradients:** each scene is a CSS gradient. Rain, storm, snow, fog and stars are drawn in CSS, and the animation stops when the system asks for reduced motion.
- **Photos (optional):** to use photos, add licensed files as `static/img/<scene>.webp` (see `static/img/README.md`). The server only offers photos that exist, and the page keeps the gradient if a photo fails to load.
- **Fonts:** Bricolage Grotesque and Figtree are served from `static/fonts/` under the SIL Open Font License.

## The ML estimate

`src/model/train.py` trains a decision tree on `weather.csv` using two features, humidity and wind.
`/predict-rain` feeds it the current humidity and wind.

Training is seeded (`random_state=42`), so every build produces the same model.

Limitations:
- The training rows only contain a weather label. Humidity and wind are generated from the row number.
- The label is the day's own weather, not the next day's.
- The model has not been evaluated, so no accuracy is claimed.

The UI labels it "experimental" and points to WeatherAPI's chance of rain for planning.

## Tests

```powershell
pytest            # 80 tests: API, city choice, scenes, error handling, ML regression
ruff check .
docker compose config --quiet   # validates compose without printing your key
```

All WeatherAPI calls are mocked in tests; no network or API key is needed.

## Project layout

```
src/main.py            FastAPI app and endpoints
src/weather/client.py  WeatherAPI client, city choice, parsing, error mapping
src/weather/scenes.py  Condition -> background scene
src/model/             Training and prediction
static/                index.html, app.js, style.css, fonts/, img/
tests/                 pytest suite
```
