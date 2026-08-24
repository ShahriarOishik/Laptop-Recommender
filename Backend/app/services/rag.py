from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.config import Settings
from app.models import (
    ChatIntent,
    ChatRequest,
    ChatResponse,
    ParsedQuery,
    SearchFilters,
    SearchRequest,
)
from app.services.cache import SemanticCache
from app.services.conversation_store import ConversationState, ConversationStore
from app.services.embeddings import EmbeddingService
from app.services.generator import GroundedGenerator
from app.services.intent import IntentResult, classify, resolve_references
from app.services.parser import QueryParser
from app.services.retrieval import RetrievalService


class RagService:
    FOLLOW_UP_HISTORY_TURNS = 6

    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingService,
        parser: QueryParser,
        retrieval: RetrievalService,
        generator: GroundedGenerator,
        cache: SemanticCache,
        conversations: ConversationStore | None = None,
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.parser = parser
        self.retrieval = retrieval
        self.generator = generator
        self.cache = cache
        self.conversations = conversations or ConversationStore()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        state = self.conversations.get_or_create(request.conversation_id)
        async with self.conversations.lock_for(state.conversation_id):
            message = (request.message or "").strip()
            await self._restore_grounding(request, state)
            result = self._route_intent(request.force_retrieval, state, message)
            intent = result.intent

            if request.force_retrieval:
                response = await self._handle_recommendation(request, state, message, intent)
            elif state.last_recommendations:
                response = await self._handle_follow_up(state, message, result.referenced_laptop_ids)
            else:
                response = self._retrieval_instruction(state, message, request.filters)

            state.add_turn("user", message, intent)
            state.add_turn("assistant", response.answer, intent)
            self.conversations.save(state)
            return response

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Same routing/logic as ``chat()``, but yields (event, payload)
        pairs as results become available instead of waiting for the full
        response. An SSE endpoint forwards each pair to the client as its
        own event. The final "done" event always carries the complete
        ChatResponse (JSON-encoded) — everything before it is a progressive
        preview for the UI, not a different source of truth."""
        state = self.conversations.get_or_create(request.conversation_id)
        async with self.conversations.lock_for(state.conversation_id):
            message = (request.message or "").strip()
            await self._restore_grounding(request, state)
            result = self._route_intent(request.force_retrieval, state, message)
            intent = result.intent

            if request.force_retrieval:
                response = None
                async for event, payload in self._handle_recommendation_stream(request, state, message, intent):
                    if event == "_response":
                        response = payload  # internal handoff only, never sent as an SSE event
                    else:
                        yield event, payload
                assert response is not None
            elif state.last_recommendations:
                response = await self._handle_follow_up(state, message, result.referenced_laptop_ids)
                yield "recommendations", self._recommendations_payload(response, intent)
                yield "answer", {"answer": response.answer, "provider": response.provider}
            else:
                response = self._retrieval_instruction(state, message, request.filters)
                yield "answer", {"answer": response.answer, "provider": response.provider}

            state.add_turn("user", message, intent)
            state.add_turn("assistant", response.answer, intent)
            self.conversations.save(state)
            yield "done", response.model_dump(mode="json")

    async def _handle_recommendation_stream(
        self,
        request: ChatRequest,
        state: ConversationState,
        message: str,
        intent: ChatIntent,
    ) -> AsyncIterator[tuple[str, Any]]:
        search_request = SearchRequest(
            message=request.message,
            index_type=request.index_type,
            top_k=request.top_k,
            nprobe=request.nprobe,
            ef_search=request.ef_search,
            min_cosine_similarity=request.min_cosine_similarity,
            filters=request.filters,
            allow_filter_relaxation=request.allow_filter_relaxation,
            include_diagnostics=request.include_diagnostics,
        )
        parsed = self.parser.parse(search_request.message, search_request.filters)
        query_vector = None
        if parsed.semantic_query:
            query_vector = await asyncio.to_thread(self.embeddings.encode, parsed.embedding_query)
        namespace = self._cache_namespace(
            search_request,
            parsed.filters.model_dump(),
            parsed.locked_fields,
        )
        retrieval, _ = await self.retrieval.retrieve(search_request, parsed, query_vector)
        # This is the actual streaming win: recommendation cards render as
        # soon as retrieval finishes (~100-200ms) instead of waiting for the
        # LLM round trip that follows.
        yield "recommendations", self._recommendations_payload(retrieval, intent)

        answer_task = asyncio.ensure_future(
            self.generator.generate(request.message or "", retrieval)
        )
        insights_task = asyncio.ensure_future(self.generator.generate_card_insights(retrieval))
        answer, provider, card_insights = "", "retrieval_only", {}
        pending = {answer_task, insights_task}
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is answer_task:
                    answer, provider = task.result()
                    yield "answer", {"answer": answer, "provider": provider}
                else:
                    card_insights = task.result()
                    if card_insights:
                        yield "card_insights", self._card_insights_payload(card_insights)

        response = ChatResponse(
            **retrieval.model_dump(),
            answer=answer,
            provider=provider,
            conversation_id=state.conversation_id,
            intent=intent,
            card_insights=card_insights,
        )
        provider_failed = bool(self.generator.configured_providers) and provider == "retrieval_only"
        if (
            self.settings.cache_enabled
            and query_vector is not None
            and not retrieval.outlier
            and not provider_failed
        ):
            self.cache.put(namespace, query_vector, response.model_dump())
        self._update_state_after_recommendation(state, request.message or "", response)
        yield "_response", response

    @staticmethod
    def _recommendations_payload(source: ChatResponse | Any, intent: ChatIntent) -> dict[str, Any]:
        return {
            "recommendations": [r.model_dump(mode="json") for r in source.recommendations],
            "status": source.status,
            "outlier": source.outlier,
            "message": source.message,
            "matched_count": source.matched_count,
            # So the frontend can decide immediately whether this is a full
            # card grid (new/updated recommendation) or a compact reference
            # list (follow-up) instead of waiting for "done" and re-rendering.
            "intent": intent.value,
        }

    @staticmethod
    def _card_insights_payload(card_insights: dict[int, Any]) -> dict[str, Any]:
        return {
            "card_insights": {
                str(laptop_id): insight.model_dump(mode="json")
                for laptop_id, insight in card_insights.items()
            }
        }

    def _route_intent(
        self,
        force_retrieval: bool,
        state: ConversationState,
        message: str,
    ) -> IntentResult:
        """Make retrieval an explicit command, independent of inferred intent."""
        if force_retrieval:
            result = classify(message, state, self.parser)
            if result.intent not in (
                ChatIntent.NEW_RECOMMENDATION,
                ChatIntent.UPDATED_REQUIREMENTS,
            ):
                intent = (
                    ChatIntent.UPDATED_REQUIREMENTS
                    if state.last_recommendations
                    else ChatIntent.NEW_RECOMMENDATION
                )
                return IntentResult(intent=intent)
            return result
        if state.last_recommendations:
            return IntentResult(
                intent=ChatIntent.FOLLOW_UP,
                referenced_laptop_ids=resolve_references(message, state.last_recommendations),
            )
        return IntentResult(intent=ChatIntent.GENERAL_QUESTION)

    async def _handle_recommendation(
        self,
        request: ChatRequest,
        state: ConversationState,
        message: str,
        intent: ChatIntent,
    ) -> ChatResponse:
        search_request = SearchRequest(
            message=request.message,
            index_type=request.index_type,
            top_k=request.top_k,
            nprobe=request.nprobe,
            ef_search=request.ef_search,
            min_cosine_similarity=request.min_cosine_similarity,
            filters=request.filters,
            allow_filter_relaxation=request.allow_filter_relaxation,
            include_diagnostics=request.include_diagnostics,
        )
        parsed = self.parser.parse(search_request.message, search_request.filters)
        query_vector = None
        if parsed.semantic_query:
            query_vector = await asyncio.to_thread(self.embeddings.encode, parsed.embedding_query)
        namespace = self._cache_namespace(
            search_request,
            parsed.filters.model_dump(),
            parsed.locked_fields,
        )
        retrieval, _ = await self.retrieval.retrieve(search_request, parsed, query_vector)
        # These are two independent LLM calls (the narrative answer and the
        # per-card insights) — neither depends on the other's output, so
        # run them concurrently instead of back-to-back to roughly halve
        # the LLM-bound portion of request latency.
        (answer, provider), card_insights = await asyncio.gather(
            self.generator.generate(request.message or "", retrieval),
            self.generator.generate_card_insights(retrieval),
        )
        response = ChatResponse(
            **retrieval.model_dump(),
            answer=answer,
            provider=provider,
            conversation_id=state.conversation_id,
            intent=intent,
            card_insights=card_insights,
        )
        provider_failed = bool(self.generator.configured_providers) and provider == "retrieval_only"
        if (
            self.settings.cache_enabled
            and query_vector is not None
            and not retrieval.outlier
            and not provider_failed
        ):
            self.cache.put(namespace, query_vector, response.model_dump())
        self._update_state_after_recommendation(state, request.message or "", response)
        return response

    async def _handle_follow_up(
        self,
        state: ConversationState,
        message: str,
        referenced_ids: list[int],
    ) -> ChatResponse:
        recent_turns = [
            {"role": turn.role, "text": turn.text[-1000:]}
            for turn in state.turns[-self.FOLLOW_UP_HISTORY_TURNS :]
        ]
        answer, provider = await self.generator.generate_follow_up(
            message,
            state.last_recommendations,
            referenced_ids,
            recent_turns,
        )
        recommendations = (
            [item for item in state.last_recommendations if item.laptop_id in referenced_ids]
            or list(state.last_recommendations)
        )
        return ChatResponse(
            status="ok",
            search_mode="follow_up",
            index_used=state.last_index_type,
            requested_top_k=len(recommendations),
            matched_count=len(recommendations),
            parsed_query=ParsedQuery(
                original_query=message, semantic_query=message, filters=state.last_filters
            ),
            outlier=False,
            recommendations=recommendations,
            retrieval_latency_ms=0.0,
            answer=answer,
            provider=provider,
            conversation_id=state.conversation_id,
            intent=ChatIntent.FOLLOW_UP,
            referenced_laptop_ids=referenced_ids,
        )

    async def _restore_grounding(self, request: ChatRequest, state: ConversationState) -> None:
        if request.force_retrieval or state.last_recommendations or not request.grounding_laptop_ids:
            return
        state.last_recommendations = await asyncio.to_thread(
            self.retrieval.recommendations_for_ids,
            request.grounding_laptop_ids,
        )

    @staticmethod
    def _retrieval_instruction(
        state: ConversationState,
        message: str,
        filters: SearchFilters,
    ) -> ChatResponse:
        answer = (
            "I don't have a retrieved recommendation set yet. Use /suggest, or apply filters "
            "and explicitly request retrieval, before asking follow-up questions."
        )
        return ChatResponse(
            status="ok",
            search_mode="retrieval_required",
            index_used=None,
            requested_top_k=0,
            matched_count=0,
            parsed_query=ParsedQuery(
                original_query=message, semantic_query=message, filters=filters
            ),
            outlier=False,
            recommendations=[],
            retrieval_latency_ms=0.0,
            answer=answer,
            provider="retrieval_only",
            conversation_id=state.conversation_id,
            intent=ChatIntent.GENERAL_QUESTION,
        )

    @staticmethod
    def _update_state_after_recommendation(
        state: ConversationState, effective_message: str, response: ChatResponse
    ) -> None:
        state.last_recommendations = list(response.recommendations)
        state.last_filters = response.parsed_query.filters
        state.last_index_type = response.index_used
        state.last_effective_message = effective_message

    def _cache_namespace(
        self,
        request: SearchRequest,
        filters: dict,
        locked_fields: set[str],
    ) -> str:
        return json.dumps(
            {
                "filters": filters,
                "locked_fields": sorted(locked_fields),
                "index": (request.index_type.value if request.index_type else self.settings.default_index),
                "top_k": request.top_k or self.settings.default_top_k,
                "nprobe": request.nprobe or self.settings.default_nprobe,
                "ef_search": request.ef_search or self.settings.default_ef_search,
                "threshold": request.min_cosine_similarity,
                "allow_filter_relaxation": request.allow_filter_relaxation,
                "include_diagnostics": request.include_diagnostics,
                "dataset": self.settings.dataset_version,
                "prompt": self.settings.prompt_version,
                "embedding_model": self.settings.embedding_model,
                "parser_policy": "v6_soft_range_preferences",
                "groq_model": self.settings.groq_model,
                "gemini_model": self.settings.gemini_model,
            },
            sort_keys=True,
        )
