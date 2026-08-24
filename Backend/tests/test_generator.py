import asyncio
import unittest
from unittest.mock import AsyncMock

from app.config import Settings
from app.models import (
    IndexType,
    LaptopRecommendation,
    ParsedQuery,
    RetrievalResponse,
    SourceChunk,
)
from app.services.generator import GenerationError, GroundedGenerator


def retrieval_response(outlier=False):
    source = SourceChunk(
        vector_id=1,
        chunk_id="100_spec",
        laptop_id=100,
        chunk_type="spec",
        score=0.8,
        text="A supported laptop specification.",
    )
    recommendation = LaptopRecommendation(
        laptop_id=100,
        brand="Test",
        model="Test Laptop",
        price_usd=999,
        score=0.8,
        sources=[source],
    )
    return RetrievalResponse(
        status="no_relevant_match" if outlier else "ok",
        message="No relevant laptops were found." if outlier else None,
        index_used=IndexType.IVF_FLAT,
        requested_top_k=5,
        matched_count=0 if outlier else 1,
        parsed_query=ParsedQuery(
            original_query="test laptop",
            semantic_query="test laptop",
        ),
        top_similarity=0.2 if outlier else 0.8,
        similarity_threshold=0.6,
        outlier=outlier,
        recommendations=[] if outlier else [recommendation],
        retrieval_latency_ms=1.0,
    )


class GeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_is_used_when_groq_fails(self):
        generator = GroundedGenerator(
            Settings(groq_api_key="groq-key", gemini_api_key="gemini-key")
        )
        self.addAsyncCleanup(generator.aclose)
        generator._groq = AsyncMock(side_effect=GenerationError("temporary failure"))
        generator._gemini = AsyncMock(return_value="Gemini grounded answer")

        answer, provider = await generator.generate("test laptop", retrieval_response())

        self.assertEqual(provider, "gemini")
        self.assertEqual(answer, "Gemini grounded answer")
        generator._groq.assert_awaited_once()
        generator._gemini.assert_awaited_once()

    async def test_retrieval_only_answer_without_provider_keys(self):
        generator = GroundedGenerator(Settings())
        self.addAsyncCleanup(generator.aclose)
        answer, provider = await generator.generate("test laptop", retrieval_response())
        self.assertEqual(provider, "retrieval_only")
        self.assertIn("Test Laptop", answer)
        self.assertIn("100_spec", answer)

    async def test_outlier_never_calls_llm(self):
        generator = GroundedGenerator(
            Settings(groq_api_key="groq-key", gemini_api_key="gemini-key")
        )
        self.addAsyncCleanup(generator.aclose)
        generator._groq = AsyncMock()
        generator._gemini = AsyncMock()
        answer, provider = await generator.generate("cake recipe", retrieval_response(outlier=True))
        self.assertEqual(provider, "retrieval_only")
        self.assertIn("No relevant", answer)
        generator._groq.assert_not_awaited()
        generator._gemini.assert_not_awaited()

    async def test_openrouter_is_used_when_groq_and_gemini_both_fail(self):
        generator = GroundedGenerator(
            Settings(groq_api_key="groq-key", gemini_api_key="gemini-key", openrouter_api_key="or-key")
        )
        self.addAsyncCleanup(generator.aclose)
        generator._groq = AsyncMock(side_effect=GenerationError("down"))
        generator._gemini = AsyncMock(side_effect=GenerationError("down"))
        generator._openrouter = AsyncMock(return_value="OpenRouter grounded answer")

        answer, provider = await generator.generate("test laptop", retrieval_response())

        self.assertEqual(provider, "openrouter")
        self.assertEqual(answer, "OpenRouter grounded answer")
        generator._groq.assert_awaited_once()
        generator._gemini.assert_awaited_once()
        generator._openrouter.assert_awaited_once()

    async def test_a_provider_stuck_past_its_budget_falls_through_instead_of_hanging(self):
        """Regression test: observed live, a degraded provider retrying 3x
        with backoff could burn 30+ seconds before the chain even reached
        the next tier (96s end to end across all three). Each provider now
        gets a bounded budget instead of an unbounded retry loop."""
        generator = GroundedGenerator(
            Settings(
                groq_api_key="groq-key",
                gemini_api_key="gemini-key",
                llm_provider_budget_seconds=0.05,
            )
        )
        self.addAsyncCleanup(generator.aclose)

        async def hangs_forever(_prompt):
            await asyncio.sleep(10)
            return "too late"

        generator._groq = hangs_forever
        generator._gemini = AsyncMock(return_value="Gemini answered instead")

        answer, provider = await generator.generate("test laptop", retrieval_response())

        self.assertEqual(provider, "gemini")
        self.assertEqual(answer, "Gemini answered instead")

    async def test_repeatedly_failing_provider_is_skipped_without_being_called(self):
        """After enough consecutive failures, the circuit breaker should
        skip a provider entirely on the next request — no attempt, no
        retries, no budget spent — instead of rediscovering the outage from
        scratch on every single call."""
        generator = GroundedGenerator(
            Settings(
                groq_api_key="groq-key",
                gemini_api_key="gemini-key",
                llm_circuit_failure_threshold=2,
                llm_circuit_cooldown_seconds=30.0,
            )
        )
        self.addAsyncCleanup(generator.aclose)
        generator._groq = AsyncMock(side_effect=GenerationError("down"))
        generator._gemini = AsyncMock(return_value="Gemini answered")

        # Two failures trips the breaker (threshold=2).
        await generator.generate("q", retrieval_response())
        await generator.generate("q", retrieval_response())
        self.assertEqual(generator._groq.await_count, 2)

        generator._groq.reset_mock()
        answer, provider = await generator.generate("q", retrieval_response())

        self.assertEqual(provider, "gemini")
        self.assertEqual(answer, "Gemini answered")
        generator._groq.assert_not_awaited()  # skipped by the open circuit

    async def test_configured_providers_reflects_all_three_tiers_in_order(self):
        generator = GroundedGenerator(
            Settings(groq_api_key="groq-key", gemini_api_key="gemini-key", openrouter_api_key="or-key")
        )
        self.addAsyncCleanup(generator.aclose)
        self.assertEqual(generator.configured_providers, ["groq", "gemini", "openrouter"])

    async def test_card_insights_fall_back_to_gemini_when_groq_fails(self):
        """Regression test: card insights used to only ever try the first
        configured provider (Groq) and give up on failure instead of
        falling through the same chain the main answer uses."""
        generator = GroundedGenerator(
            Settings(groq_api_key="groq-key", gemini_api_key="gemini-key")
        )
        self.addAsyncCleanup(generator.aclose)
        generator._groq = AsyncMock(side_effect=GenerationError("down"))
        generator._gemini = AsyncMock(
            return_value='[{"laptop_id": 100, "match_reason": "Great fit", "strengths": ["Fast"], "tradeoffs": []}]'
        )

        insights = await generator.generate_card_insights(retrieval_response())

        self.assertEqual(insights[100].match_reason, "Great fit")
        generator._gemini.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
