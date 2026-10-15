"""Prometheus request metrics: request count and latency per route."""

import time

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests handled",
    ["method", "path", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)


def _route_path(request: Request):
    # Label by route template ("/weather", "/static"), never the raw URL,
    # so query strings and file names can't create unbounded label values.
    route = request.scope.get("route")
    return route.path if route is not None else "unmatched"


async def track_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    path = _route_path(request)
    LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    return response


def metrics_response():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
