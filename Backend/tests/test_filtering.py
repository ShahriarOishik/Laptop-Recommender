import unittest

from app.models import SearchFilters
from app.services.filtering import build_filter_passes


class FilterPassTests(unittest.TestCase):
    def test_relaxes_preferences_but_preserves_locked_fields(self):
        filters = SearchFilters(
            max_price_usd=1500,
            min_ram_gb=16,
            brands=["dell"],
            storage_types=["ssd"],
        )
        passes = build_filter_passes(filters, {"max_price_usd"})
        self.assertEqual(passes[0].name, "strict")
        self.assertEqual(passes[0].active_fields, frozenset(filters.active_fields()))
        self.assertNotIn("brands", passes[1].active_fields)
        self.assertTrue(all("max_price_usd" in item.active_fields for item in passes))

    def test_empty_filters_produce_single_pass(self):
        passes = build_filter_passes(SearchFilters(), set())
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0].name, "no_metadata_constraints")


if __name__ == "__main__":
    unittest.main()
