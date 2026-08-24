from __future__ import annotations

import random
import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    """Sliding-window request limiter, keyed by an arbitrary string (client
    IP in practice). In-memory and per-process — sufficient for a single
    backend instance; a multi-instance deployment would need a shared store
    (e.g. Redis) instead."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """Returns (allowed, retry_after_seconds). Records the hit only if allowed."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False, max(self.window_seconds - (now - hits[0]), 0.0)
            hits.append(now)
            # Opportunistic cleanup so long-idle clients don't accumulate
            # empty entries forever — cheap, and doesn't need a background
            # task/thread for what is a low-traffic, single-process limiter.
            if random.random() < 0.01:
                self._evict_stale(now)
            return True, 0.0

    def _evict_stale(self, now: float) -> None:
        stale = [
            key
            for key, hits in self._hits.items()
            if not hits or now - hits[-1] > self.window_seconds
        ]
        for key in stale:
            del self._hits[key]
