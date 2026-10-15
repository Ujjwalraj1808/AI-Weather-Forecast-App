"""Small in-memory cache with per-entry expiry (one process, no extra dependency)."""

import copy
import threading
import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, ttl_seconds, max_entries, clock=time.monotonic):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._data = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        """Return a copy of the cached value, or None if missing or expired."""
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if self.clock() >= expires:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return copy.deepcopy(value)

    def set(self, key, value):
        with self._lock:
            self._data[key] = (self.clock() + self.ttl, copy.deepcopy(value))
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def clear(self):
        with self._lock:
            self._data.clear()
