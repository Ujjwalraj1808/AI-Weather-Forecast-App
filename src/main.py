from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.metrics import metrics_response, track_requests
from src.model.predict import features_from_current, load_model, load_model_info, predict_rain
from src.ratelimit import rate_limit
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
    app.state.model_info = load_model_info()
    yield


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
SCENE_IMAGE_EXTENSIONS = (".webp", ".jpg")

app = FastAPI(title="Weather Forecast API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
# Starlette runs the last-added middleware first: metrics wrap the rate limiter,
# so rejected (429) requests are counted too.
app.middleware("http")(rate_limit)
app.middleware("http")(track_requests)


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


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


@app.get("/search")
def search(q: str = Query(..., min_length=2)):
    return find_candidates(q)


@app.get("/resolve")
def resolve(q: str = Query(..., min_length=1)):
    return resolve_location(q)


def _current(data):
    current = parse_current(data)
    current["scene_image"] = scene_image(current["scene"])
    return current


def _prediction(request, current):
    return predict_rain(request.app.state.model, features_from_current(current))


@app.get("/model")
def model_info(request: Request):
    """How the rain model was trained and how it scored on held-out data."""
    return request.app.state.model_info


@app.get("/dashboard")
def dashboard(
    request: Request,
    city: str = Query(..., min_length=1),
    days: int = Query(10, ge=1, le=14),
):
    """Everything the page needs from one WeatherAPI call."""
    data = fetch_forecast(resolve_query(city), days=days)
    current = _current(data)
    return {
        "current": current,
        "days": parse_forecast(data),
        "hourly": parse_hourly(data),
        "prediction": _prediction(request, current),
    }


@app.get("/weather")
def weather(city: str = Query(..., min_length=1)):
    return _current(fetch_forecast(resolve_query(city), days=1))


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
    return {"location": current["location"], **_prediction(request, current)}
