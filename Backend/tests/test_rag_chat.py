import asyncio
import unittest

import numpy as np

from app.config import Settings
from app.models import (
    ChatIntent,
    ChatRequest,
    IndexType,
    LaptopRecommendation,
    ParsedQuery,
    RetrievalResponse,
    SearchFilters,
)
from app.services.conversation_store import ConversationStore
from app.services.parser import QueryParser
from app.services.rag import RagService


class FakeEmbeddings:
    def encode(self, _text):
        return np.ones(768, dtype=np.float32) / np.sqrt(768)


class FakeRetrieval:
    def __init__(self):
        self.calls = 0
        self.requests = []
        self.restored_ids = []

    def recommendations_for_ids(self, laptop_ids):
        self.restored_ids.append(list(laptop_ids))
        laptops = {
            1: LaptopRecommendation(laptop_id=1, brand="Dell", model="XPS 13", price_usd=1200.0),
            2: LaptopRecommendation(laptop_id=2, brand="Lenovo", model="ThinkPad X1", price_usd=1400.0),
        }
        return [laptops[laptop_id] for laptop_id in laptop_ids if laptop_id in laptops]

    async def retrieve(self, request, parsed=None, query_vector=None):
        self.calls += 1
        self.requests.append(request)
        parsed = parsed or QueryParser().parse(request.message, request.filters)
        recommendations = [
            LaptopRecommendation(laptop_id=1, brand="Dell", model="XPS 13", price_usd=1200.0, score=0.9),
            LaptopRecommendation(laptop_id=2, brand="Lenovo", model="ThinkPad X1", price_usd=1400.0, score=0.8),
            LaptopRecommendation(laptop_id=3, brand="Asus", model="ROG Zephyrus", price_usd=900.0, score=0.7),
        ]
        response = RetrievalResponse(
            status="ok",
            index_used=IndexType.IVF_FLAT,
            requested_top_k=5,
            matched_count=len(recommendations),
            parsed_query=parsed,
            top_similarity=0.9,
            similarity_threshold=0.6,
            outlier=False,
            recommendations=recommendations,
            retrieval_latency_ms=1.0,
        )
        return response, None


class FakeGenerator:
    def __init__(self):
        self.configured_providers = []
        self.follow_up_calls = []
        self.general_calls = []

    async def generate(self, _query, _retrieval):
        return "Here are your top laptops.", "retrieval_only"

    async def generate_card_insights(self, _retrieval):
        return {}

    async def generate_follow_up(self, query, recommendations, referenced_ids, recent_turns):
        self.follow_up_calls.append(
            (query, [r.laptop_id for r in recommendations], referenced_ids, recent_turns)
        )
        return "The Lenovo has more RAM.", "retrieval_only"

    async def generate_general(self, query):
        self.general_calls.append(query)
        return "A dedicated GPU is a separate graphics chip.", "retrieval_only"


def _label_for(text: str, delay_for: dict[str, float]) -> str:
    """Resolve which concurrent test call a query belongs to."""
    best_key, best_index = None, -1
    for key in delay_for:
        index = text.rfind(key)
        if index > best_index:
            best_key, best_index = key, index
    return best_key if best_key is not None else text


class LoggingFakeRetrieval:
    """Like FakeRetrieval, but appends timestamped start/end markers to a
    shared log and returns query-distinguishable recommendation sets, so a
    test can prove two concurrent chat() calls on the same conversation
    either interleaved (bug) or fully serialized (fixed)."""

    def __init__(self, log: list[str], delay_for: dict[str, float]):
        self.log = log
        self.delay_for = delay_for

    async def retrieve(self, request, parsed=None, query_vector=None):
        label = _label_for(request.message, self.delay_for)
        self.log.append(f"retrieve_start:{label}")
        await asyncio.sleep(self.delay_for.get(label, 0.0))
        parsed = parsed or QueryParser().parse(request.message, request.filters)
        laptop_id = 100 if "gaming" in label else 200
        recommendations = [
            LaptopRecommendation(laptop_id=laptop_id, brand="Dell", model=label, price_usd=1200.0, score=0.9)
        ]
        response = RetrievalResponse(
            status="ok",
            index_used=IndexType.IVF_FLAT,
            requested_top_k=5,
            matched_count=len(recommendations),
            parsed_query=parsed,
            top_similarity=0.9,
            similarity_threshold=0.6,
            outlier=False,
            recommendations=recommendations,
            retrieval_latency_ms=1.0,
        )
        self.log.append(f"retrieve_end:{label}")
        return response, None


class LoggingFakeGenerator:
    def __init__(self, log: list[str], delay_for: dict[str, float]):
        self.log = log
        self.delay_for = delay_for
        self.configured_providers = []

    async def generate(self, query, _retrieval):
        label = _label_for(query, self.delay_for)
        self.log.append(f"generate_start:{label}")
        await asyncio.sleep(self.delay_for.get(label, 0.0))
        self.log.append(f"generate_end:{label}")
        return f"Answer for {label}.", "retrieval_only"

    async def generate_card_insights(self, _retrieval):
        return {}

    async def generate_follow_up(self, query, recommendations, referenced_ids, recent_turns):
        return "n/a", "retrieval_only"

    async def generate_general(self, query):
        return "n/a", "retrieval_only"


class RagServiceChatTests(unittest.IsolatedAsyncioTestCase):
    def _service(self):
        settings = Settings(cache_enabled=False)
        retrieval = FakeRetrieval()
        generator = FakeGenerator()
        service = RagService(
            settings,
            FakeEmbeddings(),
            QueryParser(),
            retrieval,
            generator,
            cache=None,  # unused while cache_enabled is False
            conversations=ConversationStore(),
        )
        return service, retrieval, generator

    async def test_new_recommendation_runs_retrieval_and_assigns_conversation_id(self):
        service, retrieval, _ = self._service()
        request = ChatRequest(
            message="Recommend a laptop for programming under $1300", force_retrieval=True
        )
        response = await service.chat(request)
        self.assertEqual(response.intent, ChatIntent.NEW_RECOMMENDATION)
        self.assertEqual(retrieval.calls, 1)
        self.assertTrue(response.conversation_id)
        self.assertEqual(len(response.recommendations), 3)

    async def test_follow_up_does_not_call_retrieval_and_resolves_reference(self):
        service, retrieval, generator = self._service()
        first = await service.chat(
            ChatRequest(
                message="Recommend a laptop for programming under $1300", force_retrieval=True
            )
        )
        follow_up = await service.chat(
            ChatRequest(
                message="Why is the first one better than the second?",
                conversation_id=first.conversation_id,
            )
        )
        self.assertEqual(retrieval.calls, 1)  # unchanged since the first call
        self.assertEqual(follow_up.intent, ChatIntent.FOLLOW_UP)
        self.assertEqual(follow_up.referenced_laptop_ids, [1, 2])
        self.assertEqual(follow_up.conversation_id, first.conversation_id)
        self.assertEqual(len(generator.follow_up_calls), 1)
        _, recommendation_ids, referenced_ids, recent_turns = generator.follow_up_calls[0]
        self.assertEqual(recommendation_ids, [1, 2, 3])
        self.assertEqual(referenced_ids, [1, 2])
        self.assertEqual([turn["role"] for turn in recent_turns], ["user", "assistant"])

    async def test_follow_up_restores_exact_grounding_after_conversation_expiry(self):
        service, retrieval, generator = self._service()
        response = await service.chat(
            ChatRequest(
                message="Why is the first one better?",
                conversation_id="expired-conversation",
                grounding_laptop_ids=[1, 2],
            )
        )

        self.assertEqual(response.intent, ChatIntent.FOLLOW_UP)
        self.assertEqual(retrieval.calls, 0)
        self.assertEqual(retrieval.restored_ids, [[1, 2]])
        self.assertEqual(generator.follow_up_calls[-1][1], [1, 2])

    async def test_explicit_retrieval_uses_only_current_message_and_filters(self):
        service, retrieval, _ = self._service()
        first = await service.chat(
            ChatRequest(
                message="Recommend a laptop for programming",
                filters=SearchFilters(min_ram_gb=16),
                force_retrieval=True,
            )
        )
        second = await service.chat(
            ChatRequest(
                message="My budget is actually $900",
                conversation_id=first.conversation_id,
                force_retrieval=True,
            )
        )
        self.assertEqual(retrieval.calls, 2)
        self.assertEqual(second.intent, ChatIntent.UPDATED_REQUIREMENTS)
        self.assertIsNone(second.parsed_query.filters.min_ram_gb)
        self.assertEqual(second.parsed_query.filters.max_price_usd, 900)
        self.assertEqual(retrieval.requests[1].message, "My budget is actually $900")

    async def test_false_with_prior_recommendations_always_uses_grounded_follow_up(self):
        service, retrieval, generator = self._service()
        first = await service.chat(
            ChatRequest(message="Recommend a laptop for programming", force_retrieval=True)
        )
        answer = await service.chat(
            ChatRequest(message="What does dedicated GPU mean?", conversation_id=first.conversation_id)
        )
        self.assertEqual(answer.intent, ChatIntent.FOLLOW_UP)
        self.assertEqual(len(answer.recommendations), 3)
        self.assertEqual(retrieval.calls, 1)
        self.assertEqual(len(generator.follow_up_calls), 1)
        self.assertEqual(len(generator.general_calls), 0)

    async def test_false_without_prior_recommendations_returns_instruction(self):
        service, retrieval, generator = self._service()
        response = await service.chat(ChatRequest(message="Recommend a laptop for programming"))
        self.assertEqual(retrieval.calls, 0)
        self.assertEqual(response.search_mode, "retrieval_required")
        self.assertIn("/suggest", response.answer)
        self.assertIn("filters", response.answer)
        self.assertEqual(response.recommendations, [])
        self.assertEqual(len(generator.general_calls), 0)

    async def test_false_general_question_without_prior_set_returns_instruction(self):
        service, retrieval, generator = self._service()
        response = await service.chat(ChatRequest(message="What does dedicated GPU mean?"))
        self.assertEqual(retrieval.calls, 0)
        self.assertEqual(response.intent, ChatIntent.GENERAL_QUESTION)
        self.assertEqual(response.recommendations, [])
        self.assertIn("/suggest", response.answer)
        self.assertEqual(len(generator.general_calls), 0)

    async def test_explicit_filter_only_request_retrieves(self):
        service, retrieval, _ = self._service()
        response = await service.chat(
            ChatRequest(
                filters=SearchFilters(max_price_usd=1000),
                force_retrieval=True,
            )
        )
        self.assertEqual(retrieval.calls, 1)
        self.assertIsNone(retrieval.requests[0].message)
        self.assertEqual(response.parsed_query.filters.max_price_usd, 1000)

    async def test_recommendation_looking_message_without_force_flag_grounds_in_prior_set(self):
        """Same gate, but once a /suggest has already produced a top-5, a
        later plain message — even one that reads like a new request — is
        answered as a follow-up grounded in that existing set, not a fresh
        search."""
        service, retrieval, generator = self._service()
        first = await service.chat(
            ChatRequest(message="Recommend a laptop for programming", force_retrieval=True)
        )
        second = await service.chat(
            ChatRequest(
                message="Recommend something for gaming too",
                conversation_id=first.conversation_id,
            )
        )
        self.assertEqual(retrieval.calls, 1)
        self.assertEqual(second.intent, ChatIntent.FOLLOW_UP)
        self.assertEqual(len(second.recommendations), 3)
        self.assertEqual(len(generator.follow_up_calls), 1)

    async def test_force_retrieval_overrides_a_follow_up_looking_message(self):
        """The other direction: /suggest always forces a fresh search, even
        if the wording would otherwise read as a follow-up (e.g. mentions a
        brand from the current set)."""
        service, retrieval, _ = self._service()
        first = await service.chat(
            ChatRequest(message="Recommend a laptop for programming", force_retrieval=True)
        )
        second = await service.chat(
            ChatRequest(
                message="Why is the Dell good?",
                conversation_id=first.conversation_id,
                force_retrieval=True,
            )
        )
        self.assertEqual(retrieval.calls, 2)
        self.assertEqual(second.intent, ChatIntent.UPDATED_REQUIREMENTS)

    async def test_explicit_retrieval_bypasses_semantic_cache_reads(self):
        class FailingReadCache:
            def __init__(self):
                self.puts = 0

            def get(self, namespace, query_vector):
                raise AssertionError("explicit retrieval must not read the semantic cache")

            def put(self, namespace, query_vector, value):
                self.puts += 1

        settings = Settings(cache_enabled=True)
        retrieval = FakeRetrieval()
        cache = FailingReadCache()
        service = RagService(
            settings,
            FakeEmbeddings(),
            QueryParser(),
            retrieval,
            FakeGenerator(),
            cache,
            conversations=ConversationStore(),
        )
        response = await service.chat(
            ChatRequest(message="Recommend a programming laptop", force_retrieval=True)
        )
        self.assertEqual(retrieval.calls, 1)
        self.assertFalse(response.cache_hit)
        self.assertEqual(cache.puts, 1)

    async def test_stream_recommendation_emits_recommendations_before_answer_before_done(self):
        service, retrieval, generator = self._service()
        generator.generate_card_insights = self._card_insights_stub
        request = ChatRequest(message="Recommend a laptop for programming", force_retrieval=True)

        events = [(event, payload) async for event, payload in service.chat_stream(request)]
        by_event = dict(events)
        names = [name for name, _ in events]

        # "recommendations" always leads and "done" always trails, but
        # "answer" and "card_insights" are two independent tasks raced with
        # FIRST_COMPLETED — their relative order is intentionally not fixed.
        self.assertEqual(names[0], "recommendations")
        self.assertEqual(names[-1], "done")
        self.assertEqual(set(names), {"recommendations", "answer", "card_insights", "done"})
        self.assertEqual(retrieval.calls, 1)

        recs_payload = by_event["recommendations"]
        self.assertEqual(len(recs_payload["recommendations"]), 3)
        self.assertEqual(recs_payload["status"], "ok")
        self.assertEqual(recs_payload["intent"], "new_recommendation")

        answer_payload = by_event["answer"]
        self.assertEqual(answer_payload["answer"], "Here are your top laptops.")
        self.assertEqual(answer_payload["provider"], "retrieval_only")

        insights_payload = by_event["card_insights"]
        self.assertEqual(insights_payload["card_insights"]["1"]["match_reason"], "Great pick.")

        done_payload = by_event["done"]
        self.assertEqual(done_payload["answer"], "Here are your top laptops.")
        self.assertEqual(len(done_payload["recommendations"]), 3)
        self.assertEqual(done_payload["intent"], "new_recommendation")

    async def test_stream_follow_up_emits_recommendations_then_answer_then_done(self):
        service, retrieval, _ = self._service()
        first = await service.chat(
            ChatRequest(message="Recommend a laptop for programming", force_retrieval=True)
        )
        events = [
            (event, payload)
            async for event, payload in service.chat_stream(
                ChatRequest(
                    message="Why is the first one better?",
                    conversation_id=first.conversation_id,
                )
            )
        ]
        names = [name for name, _ in events]
        self.assertEqual(names, ["recommendations", "answer", "done"])
        self.assertEqual(retrieval.calls, 1)  # unchanged — follow-up never re-searches
        self.assertEqual(events[0][1]["intent"], "follow_up")
        self.assertEqual(events[-1][1]["intent"], "follow_up")

    async def test_concurrent_chat_on_same_conversation_is_fully_serialized(self):
        """Regression test for the conversation-state race: two chat() calls
        on the *same* conversation_id used to share one mutable
        ConversationState with no lock held across the request, so whichever
        call's LLM work finished last silently overwrote the other's
        last_recommendations/last_filters — even if it started first. This
        proves the per-conversation lock now makes concurrent same-
        conversation requests fully serialized: one call's entire
        retrieve+generate+save sequence completes before the other's begins,
        so there is no window where they could interleave."""
        settings = Settings(cache_enabled=False)
        log: list[str] = []
        # "gaming laptop" is the slow call despite starting first — this is
        # exactly the "started first, finished last" scenario the audit
        # describes. Without the lock, "student laptop" (fast) would start
        # and finish its own retrieve+generate *while* "gaming laptop" is
        # still awaiting its generate() call.
        delay_for = {"gaming laptop": 0.05, "student laptop": 0.0}
        retrieval = LoggingFakeRetrieval(log, delay_for)
        generator = LoggingFakeGenerator(log, delay_for)
        service = RagService(
            settings,
            FakeEmbeddings(),
            QueryParser(),
            retrieval,
            generator,
            cache=None,
            conversations=ConversationStore(),
        )

        # Reserve a conversation_id without adding a setup retrieval to the log.
        conversation_id = service.conversations.get_or_create(None).conversation_id

        await asyncio.gather(
            service.chat(
                ChatRequest(
                    message="gaming laptop",
                    conversation_id=conversation_id,
                    force_retrieval=True,
                )
            ),
            service.chat(
                ChatRequest(
                    message="student laptop",
                    conversation_id=conversation_id,
                    force_retrieval=True,
                )
            ),
        )

        # Fully serialized: every event of whichever call ran first must
        # precede every event of the other — no interleaving of retrieve/
        # generate start/end markers between the two labels.
        gaming_positions = [i for i, event in enumerate(log) if event.endswith(":gaming laptop")]
        student_positions = [i for i, event in enumerate(log) if event.endswith(":student laptop")]
        self.assertEqual(len(gaming_positions), 4)
        self.assertEqual(len(student_positions), 4)
        serialized = max(gaming_positions) < min(student_positions) or max(student_positions) < min(
            gaming_positions
        )
        self.assertTrue(
            serialized,
            f"expected fully serialized event log, got interleaving: {log}",
        )

        # The final state reflects exactly one call's result, never a mix of
        # one call's recommendations with the other's filters/index.
        final_state = service.conversations.get(conversation_id)
        final_laptop_id = final_state.last_recommendations[0].laptop_id
        self.assertIn(final_laptop_id, (100, 200))

    async def test_stream_general_question_emits_only_answer_then_done(self):
        service, retrieval, _ = self._service()
        events = [
            (event, payload)
            async for event, payload in service.chat_stream(
                ChatRequest(message="What does dedicated GPU mean?")
            )
        ]
        names = [name for name, _ in events]
        self.assertEqual(names, ["answer", "done"])
        self.assertEqual(retrieval.calls, 0)
        self.assertEqual(events[-1][1]["recommendations"], [])

    @staticmethod
    async def _card_insights_stub(retrieval):
        from app.models import CardInsight

        return {
            item.laptop_id: CardInsight(match_reason="Great pick.", strengths=["Fast"], tradeoffs=[])
            for item in retrieval.recommendations[:1]
        }


if __name__ == "__main__":
    unittest.main()
