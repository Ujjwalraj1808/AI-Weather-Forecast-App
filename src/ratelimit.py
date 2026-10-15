"""Per-client sliding-window rate limit for the API endpoints."""

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

# Pages, assets and probes are never limited; only routes that can reach WeatherAPI are.
LIMITED_PATHS = ("/search", "/resolve", "/weather", "/forecast", "/predict-rain", "/dashboard")


class RateLimiter:
    def __init__(self, limit, window_seconds=60, clock=time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key):
        """Record a hit. Returns 0 if allowed, else seconds until the next slot frees up."""
        now = self.clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, int(hits[0] + self.window - now) + 1)
            hits.append(now)
            # Drop idle clients so memory stays bounded
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return 0

    def reset(self):
        with self._lock:
            self._hits.clear()


limiter = RateLimiter(int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60")))


async def rate_limit(request: Request, call_next):
    if request.url.path in LIMITED_PATHS:
        client = request.client.host if request.client else "unknown"
        retry_after = limiter.check(client)
        if retry_after:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Wait a minute and try again."},
                headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)
