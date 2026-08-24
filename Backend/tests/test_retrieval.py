import unittest

import numpy as np

from app.config import Settings
from app.models import IndexType, SearchFilters, SearchRequest
from app.services.faiss_manager import VectorHit
from app.services.parser import QueryParser
from app.services.retrieval import RetrievalService


class FakeEmbeddings:
    def __init__(self):
        self.calls = 0
        self.texts = []

    def encode(self, text):
        self.calls += 1
        self.texts.append(text)
        return np.ones(768, dtype=np.float32) / np.sqrt(768)


class FakeIndexes:
    def __init__(self, top_score=0.8):
        self.top_score = top_score
        self.constrained_calls = 0

    def search(self, *_):
        return [VectorHit(i, self.top_score - i * 0.005) for i in range(20)]

    def threshold_for(self, _):
        return 0.6

    def search_constrained(self, _, __, allowed_ids, k, ___, ____):
        self.constrained_calls += 1
        return [
            VectorHit(i, self.top_score - position * 0.005)
            for position, i in enumerate(allowed_ids[:k])
        ]

    def search_laptops(self, *_):
        return [VectorHit(1000 + i, self.top_score - i * 0.005) for i in range(20)]

    def search_laptops_constrained(self, _, __, allowed_ids, k, ___, ____):
        self.constrained_calls += 1
        return [
            VectorHit(int(laptop_id), self.top_score - position * 0.005)
            for position, laptop_id in enumerate(allowed_ids[:k])
        ]

    def score_vectors(self, _, __, vector_ids, ___, ____):
        return {int(vector_id): self.top_score - index * 0.005 for index, vector_id in enumerate(vector_ids)}

    def score_vectors_multi(self, _, query_vectors, vector_ids, ___, ____):
        scores = self.score_vectors(None, None, vector_ids, None, None)
        return [dict(scores) for _ in query_vectors]


class FakeMetadata:
    def __init__(self):
        self.calls = 0
        self.points = [
            {
                "vector_id": i,
                "chunk_id": f"{1000 + i}_spec",
                "chunk_type": "spec",
                "chunk_text": f"Laptop evidence {i}",
                "laptop_id": 1000 + i,
                "brand": "Dell" if i == 0 else "Lenovo",
                "brand_normalized": "dell" if i == 0 else "lenovo",
                "model": f"Model {i}",
                "price_usd": 1200,
                "ram_capacity_gb": 16,
                "gpu_tags": ["rtx"],
            }
            for i in range(20)
        ]

    def retrieve(self, ids):
        self.calls += 1
        return [point for point in self.points if point["vector_id"] in ids]

    def filter_candidates(self, ids, filters):
        self.calls += 1
        points = self.retrieve(ids)
        if filters.brands:
            points = [point for point in points if point["brand_normalized"] in filters.brands]
        if filters.max_price_usd is not None:
            points = [point for point in points if point["price_usd"] <= filters.max_price_usd]
        if filters.min_ram_gb is not None:
            points = [point for point in points if point["ram_capacity_gb"] >= filters.min_ram_gb]
        return points

    def matching_vector_ids(self, _):
        return [point["vector_id"] for point in self.points]

    def matching_laptop_ids(self, _):
        return list(dict.fromkeys(point["laptop_id"] for point in self.points))

    def get_laptops(self, laptop_ids):
        self.calls += 1
        return [point for point in self.points if point["laptop_id"] in laptop_ids]

    def filter_all(self, filters):
        return self.filter_candidates([point["vector_id"] for point in self.points], filters)


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeats_metadata_filtering_until_five_laptops(self):
        metadata = FakeMetadata()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(),
            metadata,
        )
        response, _ = await service.retrieve(
            SearchRequest(
                message="Dell laptop under $1500 with 16 GB RAM",
                index_type=IndexType.IVF_FLAT,
                allow_filter_relaxation=True,
            )
        )
        self.assertEqual(response.matched_count, 5)
        self.assertGreater(response.filter_level, 1)
        self.assertIn("brands", response.relaxed_filters)

    async def test_hybrid_search_with_zero_metadata_matches_does_not_crash(self):
        """Regression test: a hybrid query (real text + filters) whose hard
        filters match no laptops at all used to raise a Pydantic
        ValidationError (matched_count was missing from the early-return
        RetrievalResponse) instead of gracefully reporting zero matches."""

        class EmptyMatchMetadata(FakeMetadata):
            def matching_laptop_ids(self, _filters):
                return []

        metadata = EmptyMatchMetadata()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(),
            metadata,
        )
        response, _ = await service.retrieve(
            SearchRequest(
                message="laptop under $1500",
                filters=SearchFilters(max_price_usd=1500),
                index_type=IndexType.IVF_FLAT,
            )
        )
        self.assertEqual(response.status, "no_metadata_match")
        self.assertEqual(response.matched_count, 0)
        self.assertEqual(response.recommendations, [])

    async def test_outlier_stops_before_metadata_lookup(self):
        metadata = FakeMetadata()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(top_score=0.3),
            metadata,
        )
        response, _ = await service.retrieve(SearchRequest(message="How do I bake a cake?"))
        self.assertTrue(response.outlier)
        self.assertEqual(len(response.candidate_hits), 20)
        self.assertIn("embedding", response.timings_ms)
        self.assertIn("chunk_score", response.timings_ms)
        self.assertGreater(metadata.calls, 0)

    async def test_near_miss_below_threshold_still_returns_closest_matches(self):
        """A chunk-level top score just under the calibrated threshold
        (within NEAR_MISS_MARGIN) should not hard-reject to zero results —
        it should return the closest laptops, flagged as an outlier/near
        miss so the frontend can label them as not an exact match."""
        metadata = FakeMetadata()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(top_score=0.585),  # threshold_for(...) == 0.6, margin == 0.03
            metadata,
        )
        response, _ = await service.retrieve(SearchRequest(message="laptop for machine learning"))
        self.assertTrue(response.outlier)
        self.assertEqual(response.status, "ok")
        self.assertGreater(response.matched_count, 0)
        self.assertIn("closest", (response.message or "").lower())

    async def test_far_miss_below_threshold_still_returns_zero_results(self):
        """A query that misses by more than NEAR_MISS_MARGIN keeps the
        original hard-rejection behavior — no laptops, no fabricated
        closeness."""
        metadata = FakeMetadata()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(top_score=0.3),
            metadata,
        )
        response, _ = await service.retrieve(SearchRequest(message="How do I bake a cake?"))
        self.assertTrue(response.outlier)
        self.assertEqual(response.status, "no_relevant_match")
        self.assertEqual(response.matched_count, 0)

    async def test_hybrid_prefilters_before_semantic_search(self):
        metadata = FakeMetadata()
        embeddings = FakeEmbeddings()
        indexes = FakeIndexes()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            embeddings,
            QueryParser(),
            indexes,
            metadata,
        )
        response, _ = await service.retrieve(
            SearchRequest(
                message="portable laptop",
                filters=SearchFilters(max_price_usd=1200),
                index_type=IndexType.IVF_FLAT,
                include_diagnostics=True,
            )
        )
        self.assertEqual(response.search_mode, "hybrid")
        self.assertEqual(response.metadata_match_count, 20)
        self.assertEqual(indexes.constrained_calls, 1)
        self.assertEqual(embeddings.calls, 2)
        self.assertIn("portable laptop", embeddings.texts[0])
        self.assertIn("maximum price 1200 USD", embeddings.texts[0])
        self.assertEqual(embeddings.texts[1], "portable laptop")
        self.assertEqual(len(response.pre_filter_candidates), 20)
        self.assertEqual(len(response.candidate_hits), 20)
        self.assertEqual(
            len({candidate.laptop_id for candidate in response.candidate_hits}),
            20,
        )
        self.assertTrue(
            {recommendation.laptop_id for recommendation in response.recommendations}.issubset(
                {candidate.laptop_id for candidate in response.candidate_hits}
            )
        )

    async def test_filter_only_skips_embeddings_and_faiss(self):
        metadata = FakeMetadata()
        embeddings = FakeEmbeddings()
        indexes = FakeIndexes()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            embeddings,
            QueryParser(),
            indexes,
            metadata,
        )
        response, vector = await service.retrieve(
            SearchRequest(filters=SearchFilters(max_price_usd=1200))
        )
        self.assertEqual(response.search_mode, "filter_only")
        self.assertIsNone(response.index_used)
        self.assertIsNone(response.top_similarity)
        self.assertIsNone(vector)
        self.assertEqual(embeddings.calls, 0)
        self.assertEqual(indexes.constrained_calls, 0)
        self.assertEqual(response.matched_count, 5)

    async def test_laptop_score_pools_top_chunks_instead_of_maximum(self):
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(),
            FakeMetadata(),
        )
        points = [
            {
                "vector_id": index,
                "chunk_id": f"3000_{index}",
                "chunk_type": "spec",
                "chunk_text": f"Evidence {index}",
                "laptop_id": 3000,
                "brand": "Dell",
                "model": "Pooled model",
                "price_usd": 1000,
            }
            for index in range(3)
        ]
        recommendations = service._recommendations(
            points,
            {0: 0.90, 1: 0.80, 2: 0.10},
            {0: 0.90, 1: 0.80, 2: 0.10},
            {0: 0.90, 1: 0.80, 2: 0.10},
            {0: 1.0, 1: 1.0, 2: 1.0},
            {0: 1.0, 1: 1.0, 2: 1.0},
            {0: 0.5, 1: 0.5, 2: 0.5},
            {},
            1,
        )
        self.assertEqual(len(recommendations), 1)
        # 0.78*text(0.755) + 0.02*soft_pref(1.0) + 0.20*value(0.5) — see
        # RetrievalService.SEMANTIC_*_WEIGHT for the current ranking blend.
        self.assertAlmostEqual(recommendations[0].score, 0.7089, places=5)
        self.assertLess(recommendations[0].score, 0.90)

    async def test_filter_only_ranking_prefers_value_over_cheapest_outlier(self):
        """Filter-only mode (no query text, hard filters only) must not
        default to raw ascending price — that surfaces implausible-cheap
        data outliers first (e.g. a real $95/16GB-RAM row in the dataset).
        It should rank by the same value/price-fit heuristics hybrid search
        already uses."""
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(),
            FakeMetadata(),
        )
        cheap_outlier = {
            "vector_id": 0,
            "chunk_id": "cheap_spec",
            "chunk_type": "spec",
            "chunk_text": "evidence",
            "laptop_id": 9001,
            "brand": "Dell",
            "model": "Suspiciously Cheap",
            "price_usd": 95.0,
        }
        well_specced = {
            "vector_id": 1,
            "chunk_id": "good_spec",
            "chunk_type": "spec",
            "chunk_text": "evidence",
            "laptop_id": 9002,
            "brand": "Dell",
            "model": "Well Specced",
            "price_usd": 850.0,
        }
        points = [cheap_outlier, well_specced]
        value_by_id = {0: 0.1, 1: 0.9}  # cheap_outlier has poor specs despite low price
        price_fit_by_id = {0: 0.1, 1: 0.7}  # far under budget vs. close-to-budget value
        recommendations = service._recommendations(
            points, {}, {}, {}, {}, {}, value_by_id, price_fit_by_id, 5
        )
        self.assertEqual(recommendations[0].laptop_id, 9002)
        self.assertEqual(recommendations[1].laptop_id, 9001)
        self.assertIsNotNone(recommendations[0].score)
        self.assertGreater(recommendations[0].score, recommendations[1].score)

    async def test_max_budget_prefers_price_closer_to_budget(self):
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(),
            FakeMetadata(),
        )
        self.assertAlmostEqual(
            service._price_fit_score({"price_usd": 1100}, SearchFilters(max_price_usd=1200)),
            1100 / 1200,
        )
        self.assertAlmostEqual(
            service._price_fit_score({"price_usd": 600}, SearchFilters(max_price_usd=1200)),
            0.5,
        )

    async def test_price_fit_score_penalizes_going_over_budget_instead_of_capping_at_one(self):
        """Regression test: previously price/max_price_usd was clamped up to
        1.0 for any price above the budget too (a ratio > 1 clamped down),
        so an over-budget laptop scored identically to one right at budget.
        That was masked only because over-budget laptops could never reach
        this scoring step at all (hard-filtered out earlier). Now that the
        price band can widen (see PRICE_RELAXATION_RATIO), going over budget
        must fall off toward 0 at the edge of that widened band instead."""
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(),
            FakeMetadata(),
        )
        filters = SearchFilters(max_price_usd=1000)
        at_budget = service._price_fit_score({"price_usd": 1000}, filters)
        just_over = service._price_fit_score({"price_usd": 1050}, filters)
        at_widened_edge = service._price_fit_score(
            {"price_usd": 1000 * (1 + RetrievalService.PRICE_RELAXATION_RATIO)}, filters
        )
        self.assertAlmostEqual(at_budget, 1.0)
        self.assertLess(just_over, at_budget)
        self.assertGreater(just_over, 0.0)
        self.assertAlmostEqual(at_widened_edge, 0.0, places=6)

    async def test_hybrid_widens_price_band_when_strict_budget_is_too_thin(self):
        """If the exact budget only turns up a couple of laptops, the search
        should retry with the price band widened by PRICE_RELAXATION_RATIO
        rather than stopping short of top_k — a slightly-over-budget option
        is better than an artificially small result set."""

        class SparseBudgetMetadata(FakeMetadata):
            def __init__(self):
                super().__init__()
                # Only 2 laptops at/under $1000; 3 more just over it.
                for index, point in enumerate(self.points[:5]):
                    point["price_usd"] = 950 if index < 2 else 1080

            def matching_laptop_ids(self, filters):
                ids = []
                for point in self.points:
                    price = point["price_usd"]
                    if filters.max_price_usd is not None and price > filters.max_price_usd:
                        continue
                    if filters.min_price_usd is not None and price < filters.min_price_usd:
                        continue
                    ids.append(point["laptop_id"])
                return list(dict.fromkeys(ids))

        metadata = SparseBudgetMetadata()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(),
            metadata,
        )
        response, _ = await service.retrieve(
            SearchRequest(
                message="laptop under $1000",
                filters=SearchFilters(max_price_usd=1000),
                index_type=IndexType.IVF_FLAT,
                allow_filter_relaxation=True,
            )
        )
        self.assertIn("price_range", response.relaxed_filters)
        self.assertIn("budget", (response.message or "").lower())
        prices = {rec.laptop_id: rec.price_usd for rec in response.recommendations}
        self.assertTrue(any(price > 1000 for price in prices.values()))
        # All 5 laptops here are otherwise identical (same specs, same text
        # match), so price_fit is the only thing that can differ their
        # scores — this isolates that it actually penalizes going over
        # budget, not just that some over-budget result showed up at all.
        in_budget_scores = [rec.score for rec in response.recommendations if rec.price_usd <= 1000]
        over_budget_scores = [rec.score for rec in response.recommendations if rec.price_usd > 1000]
        self.assertTrue(in_budget_scores and over_budget_scores)
        self.assertGreater(min(in_budget_scores), max(over_budget_scores))

    async def test_hybrid_does_not_widen_price_band_when_relaxation_is_disabled(self):
        """Regression test: allow_filter_relaxation defaults to False (and
        the frontend only sends True for a non-strict search), so a locked
        budget must return fewer/zero results rather than silently including
        over-budget alternates — the opposite of the widening test above,
        same sparse-budget setup, relaxation left at its default (off)."""

        class SparseBudgetMetadata(FakeMetadata):
            def __init__(self):
                super().__init__()
                for index, point in enumerate(self.points[:5]):
                    point["price_usd"] = 950 if index < 2 else 1080

            def matching_laptop_ids(self, filters):
                ids = []
                for point in self.points:
                    price = point["price_usd"]
                    if filters.max_price_usd is not None and price > filters.max_price_usd:
                        continue
                    if filters.min_price_usd is not None and price < filters.min_price_usd:
                        continue
                    ids.append(point["laptop_id"])
                return list(dict.fromkeys(ids))

        metadata = SparseBudgetMetadata()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(),
            metadata,
        )
        response, _ = await service.retrieve(
            SearchRequest(
                message="laptop under $1000",
                filters=SearchFilters(max_price_usd=1000),
                index_type=IndexType.IVF_FLAT,
                # allow_filter_relaxation left at its default (False).
            )
        )
        self.assertNotIn("price_range", response.relaxed_filters)
        prices = [rec.price_usd for rec in response.recommendations]
        self.assertTrue(all(price <= 1000 for price in prices))

    async def test_filter_only_widens_price_band_when_strict_budget_is_too_thin(self):
        class SparseBudgetMetadata(FakeMetadata):
            def __init__(self):
                super().__init__()
                for index, point in enumerate(self.points[:5]):
                    point["price_usd"] = 950 if index < 2 else 1080

            def filter_candidates(self, ids, filters):
                points = self.retrieve(ids)
                if filters.max_price_usd is not None:
                    points = [p for p in points if p["price_usd"] <= filters.max_price_usd]
                if filters.min_price_usd is not None:
                    points = [p for p in points if p["price_usd"] >= filters.min_price_usd]
                return points

        metadata = SparseBudgetMetadata()
        service = RetrievalService(
            Settings(load_resources_on_startup=False),
            FakeEmbeddings(),
            QueryParser(),
            FakeIndexes(),
            metadata,
        )
        response, _ = await service.retrieve(
            SearchRequest(filters=SearchFilters(max_price_usd=1000), allow_filter_relaxation=True)
        )
        self.assertEqual(response.search_mode, "filter_only")
        self.assertIn("price_range", response.relaxed_filters)
        prices = [rec.price_usd for rec in response.recommendations]
        self.assertTrue(any(price > 1000 for price in prices))

    async def test_spec_score_uses_hardware_metadata(self):
        strong = {
            "cpu_full": "Intel Core i7-13700H",
            "ram_capacity_gb": 32,
            "storage_capacity_gb": 1024,
            "gpu_tags": ["rtx"],
            "display_size_inches": 15.6,
            "display_resolution_width": 1920,
            "display_resolution_height": 1080,
            "battery": "80 Wh",
        }
        basic = {
            "cpu_full": "Intel Celeron N4020",
            "ram_capacity_gb": 8,
            "storage_capacity_gb": 128,
            "gpu_tags": ["integrated"],
            "display_size_inches": 11.6,
            "display_resolution_width": 1366,
            "display_resolution_height": 768,
            "battery": "30 Wh",
        }
        self.assertGreater(
            RetrievalService._value_score(strong, "programming"),
            RetrievalService._value_score(basic, "programming"),
        )


if __name__ == "__main__":
    unittest.main()
