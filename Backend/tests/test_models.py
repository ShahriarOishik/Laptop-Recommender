import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.config import Settings
from app.models import SearchFilters, SearchRequest


class SearchRequestTests(unittest.TestCase):
    def test_message_only_request_is_valid(self):
        request = SearchRequest(message="gaming laptop")
        self.assertEqual(request.message, "gaming laptop")

    def test_filter_only_request_is_valid(self):
        request = SearchRequest(filters=SearchFilters(max_price_usd=1000))
        self.assertIsNone(request.message)

    def test_empty_request_is_rejected(self):
        with self.assertRaises(ValidationError):
            SearchRequest()

    def test_reversed_price_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            SearchRequest(
                filters=SearchFilters(min_price_usd=1500, max_price_usd=1000)
            )

    def test_reversed_weight_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            SearchRequest(
                filters=SearchFilters(min_weight_kg=2.0, max_weight_kg=1.0)
            )

    def test_top_k_accepts_twenty_and_rejects_twenty_one(self):
        self.assertEqual(SearchRequest(message="gaming", top_k=20).top_k, 20)
        with self.assertRaises(ValidationError):
            SearchRequest(message="gaming", top_k=21)

    def test_settings_defaults_match_runtime_fallbacks(self):
        self.assertEqual(Settings().default_index, "ivf_flat")
        self.assertEqual(Settings().index_cache_size, 10)
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.default_index, "ivf_flat")
        self.assertEqual(settings.index_cache_size, 10)


if __name__ == "__main__":
    unittest.main()
