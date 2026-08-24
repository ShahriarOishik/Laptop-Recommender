import unittest
from unittest.mock import patch

from app.services.circuit_breaker import CircuitBreaker


class CircuitBreakerTests(unittest.TestCase):
    def test_stays_closed_below_the_failure_threshold(self):
        breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
        breaker.record_failure("groq")
        breaker.record_failure("groq")
        self.assertFalse(breaker.is_open("groq"))

    def test_opens_once_the_threshold_is_reached(self):
        breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
        for _ in range(3):
            breaker.record_failure("groq")
        self.assertTrue(breaker.is_open("groq"))

    def test_a_success_resets_the_failure_count(self):
        breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
        breaker.record_failure("groq")
        breaker.record_failure("groq")
        breaker.record_success("groq")
        breaker.record_failure("groq")
        self.assertFalse(breaker.is_open("groq"))

    def test_keys_are_independent(self):
        breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=30.0)
        breaker.record_failure("groq")
        self.assertTrue(breaker.is_open("groq"))
        self.assertFalse(breaker.is_open("gemini"))

    def test_closes_again_after_the_cooldown_elapses(self):
        breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=10.0)
        with patch("app.services.circuit_breaker.time.monotonic", return_value=1000.0):
            breaker.record_failure("groq")
            self.assertTrue(breaker.is_open("groq"))
        with patch("app.services.circuit_breaker.time.monotonic", return_value=1011.0):
            self.assertFalse(breaker.is_open("groq"))

    def test_a_failed_trial_after_cooldown_reopens_for_a_full_new_window(self):
        breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=10.0)
        with patch("app.services.circuit_breaker.time.monotonic", return_value=1000.0):
            breaker.record_failure("groq")
        with patch("app.services.circuit_breaker.time.monotonic", return_value=1011.0):
            self.assertFalse(breaker.is_open("groq"))  # half-open trial allowed
            breaker.record_failure("groq")  # trial failed
            self.assertTrue(breaker.is_open("groq"))
        with patch("app.services.circuit_breaker.time.monotonic", return_value=1015.0):
            self.assertTrue(breaker.is_open("groq"))  # still within the new window


if __name__ == "__main__":
    unittest.main()
