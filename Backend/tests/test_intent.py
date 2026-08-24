import unittest

from app.models import LaptopRecommendation, SearchFilters
from app.models import ChatIntent
from app.services.conversation_store import ConversationState
from app.services.intent import classify, cleared_fields, merge_filters, resolve_references
from app.services.parser import QueryParser


def _recommendation(laptop_id, brand, model, price):
    return LaptopRecommendation(laptop_id=laptop_id, brand=brand, model=model, price_usd=price)


def _state_with_recommendations():
    state = ConversationState(conversation_id="c1")
    state.last_recommendations = [
        _recommendation(1, "Dell", "XPS 13", 1200.0),
        _recommendation(2, "Lenovo", "ThinkPad X1", 1400.0),
        _recommendation(3, "Asus", "ROG Zephyrus", 900.0),
    ]
    state.last_filters = SearchFilters(max_price_usd=1500)
    return state


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.parser = QueryParser()

    def test_no_prior_recommendations_is_new_recommendation(self):
        state = ConversationState(conversation_id="c0")
        result = classify("Recommend a laptop for programming under $1000", state, self.parser)
        self.assertEqual(result.intent, ChatIntent.NEW_RECOMMENDATION)

    def test_ordinal_reference_is_follow_up(self):
        state = _state_with_recommendations()
        result = classify("Why is the first one better than the third?", state, self.parser)
        self.assertEqual(result.intent, ChatIntent.FOLLOW_UP)
        self.assertEqual(result.referenced_laptop_ids, [1, 3])

    def test_brand_reference_is_follow_up(self):
        state = _state_with_recommendations()
        result = classify("Why did you recommend the Lenovo?", state, self.parser)
        self.assertEqual(result.intent, ChatIntent.FOLLOW_UP)
        self.assertIn(2, result.referenced_laptop_ids)

    def test_budget_change_is_updated_requirements(self):
        state = _state_with_recommendations()
        result = classify("My budget is actually $900", state, self.parser)
        self.assertEqual(result.intent, ChatIntent.UPDATED_REQUIREMENTS)

    def test_relaxation_phrase_is_updated_requirements(self):
        state = _state_with_recommendations()
        result = classify("I don't care about the GPU requirement anymore", state, self.parser)
        self.assertEqual(result.intent, ChatIntent.UPDATED_REQUIREMENTS)

    def test_definition_question_is_general(self):
        state = _state_with_recommendations()
        result = classify("What does dedicated GPU mean?", state, self.parser)
        self.assertEqual(result.intent, ChatIntent.GENERAL_QUESTION)

    def test_ambiguous_follow_up_falls_back_to_follow_up(self):
        state = _state_with_recommendations()
        result = classify("Tell me more about that", state, self.parser)
        self.assertEqual(result.intent, ChatIntent.FOLLOW_UP)


class ResolveReferencesTests(unittest.TestCase):
    def test_cheaper_and_pricier(self):
        state = _state_with_recommendations()
        cheaper = resolve_references("which is the cheaper one?", state.last_recommendations)
        pricier = resolve_references("which is the more expensive one?", state.last_recommendations)
        self.assertEqual(cheaper, [3])
        self.assertEqual(pricier, [2])

    def test_option_number(self):
        state = _state_with_recommendations()
        resolved = resolve_references("compare option 1 and option 2", state.last_recommendations)
        self.assertEqual(resolved, [1, 2])

    def test_these_resolves_to_all(self):
        state = _state_with_recommendations()
        resolved = resolve_references("are these good for gaming?", state.last_recommendations)
        self.assertEqual(resolved, [1, 2, 3])

    def test_no_reference_returns_empty(self):
        state = _state_with_recommendations()
        resolved = resolve_references("what about battery life", state.last_recommendations)
        self.assertEqual(resolved, [])


class FilterMergeTests(unittest.TestCase):
    def test_merge_carries_forward_and_overrides(self):
        previous = SearchFilters(max_price_usd=1200, min_ram_gb=16)
        new_explicit = SearchFilters(max_price_usd=900)
        merged = merge_filters(previous, new_explicit, set())
        self.assertEqual(merged.max_price_usd, 900)
        self.assertEqual(merged.min_ram_gb, 16)

    def test_cleared_field_is_dropped(self):
        previous = SearchFilters(max_price_usd=1200, min_ram_gb=16)
        merged = merge_filters(previous, SearchFilters(), {"min_ram_gb"})
        self.assertIsNone(merged.min_ram_gb)
        self.assertEqual(merged.max_price_usd, 1200)

    def test_cleared_fields_detects_no_budget_limit(self):
        self.assertIn("max_price_usd", cleared_fields("There's no budget limit anymore"))


if __name__ == "__main__":
    unittest.main()
