from __future__ import annotations

import time
from threading import Lock


class CircuitBreaker:
    """Per-key circuit breaker (one instance covers all keys, e.g. one per
    LLM provider name). After `failure_threshold` consecutive failures for a
    key, that key is skipped ("open") for `cooldown_seconds` instead of
    being retried on every request — a degraded provider gets rediscovered
    once per cooldown window, not once per user request. After the cooldown
    elapses the next call is let through as a trial ("half-open"): success
    closes the circuit again, failure re-opens it for another full window.
    """

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}
        self._lock = Lock()

    def is_open(self, key: str) -> bool:
        with self._lock:
            opened_at = self._opened_at.get(key)
            if opened_at is None:
                return False
            return time.monotonic() - opened_at < self.cooldown_seconds

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._opened_at.pop(key, None)

    def record_failure(self, key: str) -> None:
        with self._lock:
            count = self._failures.get(key, 0) + 1
            self._failures[key] = count
            if count >= self.failure_threshold:
                self._opened_at[key] = time.monotonic()
