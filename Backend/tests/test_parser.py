import unittest

from app.models import SearchFilters
from app.services.parser import QueryParser


class QueryParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = QueryParser()

    def test_extracts_numeric_and_gpu_constraints(self):
        parsed = self.parser.parse(
            "Gaming laptop under $1500 with at least 16 GB RAM and RTX graphics"
        )
        self.assertEqual(parsed.filters.max_price_usd, 1500)
        self.assertEqual(parsed.filters.min_ram_gb, 16)
        self.assertIn("rtx", parsed.filters.gpu_tags)
        self.assertIn("gaming", parsed.semantic_constraints)

    def test_trailing_sentence_period_after_price_does_not_crash(self):
        """Regression test: a price immediately followed by a sentence-
        ending period (no space) used to be captured whole — "1000.." —
        by a regex that allowed unlimited digits/commas/dots, which then
        crashed float() in _number() and 500'd the entire request. A
        well-formed price should still be extracted despite the stray dot."""
        parsed = self.parser.parse("I need a gaming laptop under $1000. Thanks!")
        self.assertEqual(parsed.filters.max_price_usd, 1000)

    def test_double_period_after_price_does_not_crash(self):
        parsed = self.parser.parse("laptop under $1000..")
        self.assertEqual(parsed.filters.max_price_usd, 1000)

    def test_between_prices_with_trailing_punctuation_does_not_crash(self):
        parsed = self.parser.parse("laptop between $800 and $1200.")
        self.assertEqual(parsed.filters.min_price_usd, 800)
        self.assertEqual(parsed.filters.max_price_usd, 1200)

    def test_stated_budget_with_trailing_punctuation_does_not_crash(self):
        parsed = self.parser.parse("my budget is $900..")
        self.assertEqual(parsed.filters.max_price_usd, 900)

    def test_infers_soft_opposite_ranges_without_making_them_hard(self):
        parser = QueryParser(
            {
                "price_usd": {"min": 95.0, "max": 11000.0, "robust_std": 563.388},
                "weight_kg": {"min": 0.523, "max": 4.8, "robust_std": 0.51891},
            }
        )
        parsed = parser.parse(
            "Lightweight programming laptop under $1200",
            SearchFilters(max_weight_kg=1.6),
        )
        self.assertEqual(parsed.filters.max_price_usd, 1200)
        self.assertEqual(parsed.filters.max_weight_kg, 1.6)
        self.assertIsNone(parsed.filters.min_price_usd)
        self.assertIsNone(parsed.filters.min_weight_kg)
        self.assertAlmostEqual(parsed.inferred_filters.min_price_usd, 636.612, places=3)
        self.assertAlmostEqual(parsed.inferred_filters.min_weight_kg, 1.08109, places=5)
        self.assertTrue(any("soft minimum price" in warning for warning in parsed.warnings))
        self.assertIn("maximum price 1200 USD", parsed.embedding_query)
        self.assertNotIn("soft preference minimum price", parsed.embedding_query)

    def test_parses_minimum_weight(self):
        parsed = self.parser.parse("Laptop at least 1.2 kg and above 800 USD")
        self.assertEqual(parsed.filters.min_weight_kg, 1.2)
        self.assertEqual(parsed.filters.min_price_usd, 800)

    def test_removes_structured_constraints_from_semantic_query(self):
        parsed = self.parser.parse(
            "Recommend a laptop for programming under 1200 USD with 16 GB RAM and RTX graphics"
        )
        self.assertEqual(parsed.semantic_query, "Recommend a laptop for programming")
        self.assertEqual(
            parsed.embedding_query,
            "Recommend a laptop for programming. Structured constraints: maximum price 1200 USD; at least 16 GB RAM; GPU rtx.",
        )
        self.assertEqual(parsed.filters.max_price_usd, 1200)
        self.assertEqual(parsed.filters.min_ram_gb, 16)
        self.assertEqual(parsed.filters.gpu_tags, ["rtx"])

    def test_ui_filters_override_and_lock_parsed_values(self):
        parsed = self.parser.parse(
            "Dell laptop under $1500",
            SearchFilters(max_price_usd=1200, brands=["Lenovo"]),
        )
        self.assertEqual(parsed.filters.max_price_usd, 1200)
        self.assertEqual(parsed.filters.brands, ["lenovo"])
        self.assertEqual(parsed.locked_fields, {"max_price_usd", "brands"})

    def test_approximate_budget_is_not_hard_filter(self):
        parsed = self.parser.parse("A student laptop around $1000")
        self.assertIsNone(parsed.filters.max_price_usd)
        self.assertTrue(parsed.warnings)

    def test_ram_amount_does_not_leak_into_price_filter(self):
        parsed = self.parser.parse("Laptop for programming with at least 16GB RAM under $1300")
        self.assertEqual(parsed.filters.min_ram_gb, 16)
        self.assertIsNone(parsed.filters.min_price_usd)
        self.assertEqual(parsed.filters.max_price_usd, 1300)

    def test_stated_budget_phrasing_sets_max_price(self):
        parsed = self.parser.parse("My budget is actually $900")
        self.assertEqual(parsed.filters.max_price_usd, 900)

    def test_must_constraint_is_locked(self):
        parsed = self.parser.parse("Gaming laptop that must have RTX")
        self.assertIn("gpu_tags", parsed.locked_fields)

    def test_exact_gpu_does_not_broaden_to_family(self):
        parsed = self.parser.parse("Laptop with RTX 4090")
        self.assertEqual(parsed.filters.gpu_tags, ["rtx 4090"])

    def test_parses_minimum_vram(self):
        parsed = self.parser.parse("Gaming laptop with at least 8 GB VRAM")
        self.assertEqual(parsed.filters.min_vram_gb, 8)
        self.assertIn("at least 8 GB VRAM", parsed.embedding_query)

    def test_negated_gpu_and_brand_become_exclusions(self):
        parsed = self.parser.parse("Laptop without RTX and must not be Dell")
        self.assertEqual(parsed.filters.gpu_tags, [])
        self.assertEqual(parsed.filters.brands, [])
        self.assertEqual(parsed.filters.excluded_gpu_tags, ["rtx"])
        self.assertEqual(parsed.filters.excluded_brands, ["dell"])
        self.assertIn("excluded_gpu_tags", parsed.locked_fields)
        self.assertIn("excluded_brands", parsed.locked_fields)


if __name__ == "__main__":
    unittest.main()
