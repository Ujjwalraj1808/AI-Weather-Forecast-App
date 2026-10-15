# ---- Build stage: install dependencies, download training data, train the model ----
FROM python:3.14-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ src/
# Needs internet: pulls ~2 years of hourly history from Open-Meteo, then trains.
# The build fails (and nothing deploys) if the data can't be fetched or the
# model misses the quality bar in src/model/train.py.
RUN python -m src.model.data && python -m src.model.train

# ---- Runtime stage ----
FROM python:3.14-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    FORWARDED_ALLOW_IPS="*"

RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/rain_model.pkl /app/model_metrics.json ./
COPY src/ src/
COPY static/ static/

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)"

CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
