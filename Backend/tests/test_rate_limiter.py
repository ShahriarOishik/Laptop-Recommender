import unittest
from unittest.mock import patch

from app.services.rate_limiter import RateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_allows_up_to_the_limit_then_blocks(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60.0)
        for _ in range(3):
            allowed, _ = limiter.check("1.2.3.4")
            self.assertTrue(allowed)
        allowed, retry_after = limiter.check("1.2.3.4")
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_different_keys_are_independent(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60.0)
        self.assertTrue(limiter.check("1.2.3.4")[0])
        self.assertTrue(limiter.check("5.6.7.8")[0])
        self.assertFalse(limiter.check("1.2.3.4")[0])

    def test_window_expiry_allows_requests_again(self):
        limiter = RateLimiter(max_requests=1, window_seconds=10.0)
        with patch("app.services.rate_limiter.time.monotonic", return_value=1000.0):
            self.assertTrue(limiter.check("1.2.3.4")[0])
            self.assertFalse(limiter.check("1.2.3.4")[0])
        with patch("app.services.rate_limiter.time.monotonic", return_value=1011.0):
            self.assertTrue(limiter.check("1.2.3.4")[0])


if __name__ == "__main__":
    unittest.main()
