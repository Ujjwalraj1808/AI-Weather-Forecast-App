from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.model.predict import load_model, predict_rain
from src.weather import (
    AmbiguousLocationError,
    CityNotFoundError,
    WeatherServiceError,
    fetch_forecast,
    find_candidates,
    parse_current,
    parse_forecast,
    parse_hourly,
    resolve_location,
    resolve_query,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model = load_model()
    yield


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
SCENE_IMAGE_EXTENSIONS = (".webp", ".jpg")

app = FastAPI(title="Weather Forecast API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(CityNotFoundError)
def city_not_found(request: Request, exc: CityNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(AmbiguousLocationError)
def ambiguous_location(request: Request, exc: AmbiguousLocationError):
    return JSONResponse(
        status_code=409, content={"detail": str(exc), "candidates": exc.candidates}
    )


@app.exception_handler(WeatherServiceError)
def weather_service_error(request: Request, exc: WeatherServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


def scene_image(scene):
    """URL of an optional photo in static/img/ for this scene, or None."""
    for ext in SCENE_IMAGE_EXTENSIONS:
        if (STATIC_DIR / "img" / f"{scene}{ext}").is_file():
            return f"/static/img/{scene}{ext}"
    return None


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/search")
def search(q: str = Query(..., min_length=2)):
    return find_candidates(q)


@app.get("/resolve")
def resolve(q: str = Query(..., min_length=1)):
    return resolve_location(q)


@app.get("/weather")
def weather(city: str = Query(..., min_length=1)):
    current = parse_current(fetch_forecast(resolve_query(city), days=1))
    current["scene_image"] = scene_image(current["scene"])
    return current


@app.get("/forecast")
def forecast(city: str = Query(..., min_length=1), days: int = Query(3, ge=1, le=14)):
    data = fetch_forecast(resolve_query(city), days=days)
    return {
        "location": data["location"]["name"],
        "days": parse_forecast(data),
        "hourly": parse_hourly(data),
    }


@app.get("/predict-rain")
def predict(request: Request, city: str = Query(..., min_length=1)):
    current = parse_current(fetch_forecast(resolve_query(city), days=1))
    return {
        "location": current["location"],
        "humidity": current["humidity"],
        "wind_kph": current["wind_kph"],
        "rain_expected": predict_rain(
            request.app.state.model, current["humidity"], current["wind_kph"]
        ),
    }
