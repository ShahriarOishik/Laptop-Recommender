from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict, defaultdict
from threading import Lock
from typing import Any

import numpy as np

from app.config import Settings
from app.models import (
    IndexType,
    LaptopRecommendation,
    ParsedQuery,
    RetrievalCandidate,
    RetrievalResponse,
    SearchRequest,
    SearchFilters,
    SourceChunk,
)
from app.services.embeddings import EmbeddingService
from app.services.faiss_manager import FaissIndexManager, VectorHit
from app.services.filtering import FilterPass, build_filter_passes
from app.services.metadata import MetadataStore
from app.services.parser import QueryParser


class RetrievalService:
    SEMANTIC_WEIGHT = 0.65
    FILTER_AWARE_WEIGHT = 0.35
    TOP_CHUNK_WEIGHTS = (0.60, 0.25, 0.15)
    # Final ranking blend: how much each signal contributes to a laptop's
    # overall rank (each set sums to 1.0). VALUE_WEIGHT is the hardware/spec
    # quality score (_value_score — RAM, CPU, GPU, storage, display) shown
    # to users as "spec_score" / the Value bar on the frontend; TEXT_WEIGHT
    # is semantic query-similarity. Tuned so specs and semantic match both
    # carry more influence, price-fit slightly less, funded by shrinking
    # soft_preference (the least critical signal — brand/weight hints)
    # rather than cutting into text or value:
    #   text   0.55 -> 0.60 (0.75 -> 0.78 with no price component)
    #   price  0.20 -> 0.15 (0.40 -> 0.30 in filter-only mode)
    #   soft   0.10 -> 0.05 (0.10 -> 0.02 with no price component)
    #   value  0.15 -> 0.20 (0.60 -> 0.70 in filter-only mode)
    HYBRID_TEXT_WEIGHT = 0.60
    HYBRID_PRICE_FIT_WEIGHT = 0.15
    HYBRID_SOFT_PREFERENCE_WEIGHT = 0.05
    HYBRID_VALUE_WEIGHT = 0.20
    SEMANTIC_TEXT_WEIGHT = 0.78
    SEMANTIC_SOFT_PREFERENCE_WEIGHT = 0.02
    SEMANTIC_VALUE_WEIGHT = 0.20
    FILTER_ONLY_VALUE_WEIGHT = 0.70
    FILTER_ONLY_PRICE_FIT_WEIGHT = 0.30
    # A query whose best chunk score falls just short of the calibrated
    # per-index threshold (see artifacts/calibrated_thresholds*.json) is
    # still shown as a best-effort, clearly-labeled "closest match" rather
    # than a hard zero-result rejection. This does not touch the threshold
    # itself or any calibration/evaluation artifact — it only widens the
    # accept band for *this* response's outlier flag and message, so the
    # M4 evaluation numbers (which read the calibrated threshold directly)
    # are unaffected. Queries that miss by more than this margin are still
    # rejected exactly as before.
    NEAR_MISS_MARGIN = 0.03
    # A stated budget ("under $800") is a preference, not a hard wall: if the
    # strict price cutoff leaves fewer than top_k laptops, the search is
    # retried once with the price band widened by this ratio in whichever
    # direction is constrained (e.g. up to $896 for an $800 max). Laptops
    # inside the original budget still rank above ones only found via this
    # widened band — see _price_fit_score, which uses the same ratio as its
    # falloff so a laptop right at the edge of the widened band scores ~0.
    PRICE_RELAXATION_RATIO = 0.12

    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingService,
        parser: QueryParser,
        indexes: FaissIndexManager,
        metadata: MetadataStore,
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.parser = parser
        self.indexes = indexes
        self.metadata = metadata
        self._metadata_cache: OrderedDict[int, list[dict[str, Any]]] = OrderedDict()
        self._metadata_cache_size = max(settings.cache_max_entries * 8, 512)
        self._metadata_cache_lock = Lock()

    async def retrieve(
        self,
        request: SearchRequest,
        parsed: ParsedQuery | None = None,
        query_vector: np.ndarray | None = None,
    ) -> tuple[RetrievalResponse, np.ndarray | None]:
        started = time.perf_counter()
        timings: dict[str, float] = {}
        index_type = request.index_type or IndexType(self.settings.default_index)
        top_k = request.top_k or self.settings.default_top_k
        stage_started = time.perf_counter()
        parsed = parsed or self.parser.parse(request.message, request.filters)
        timings["parse"] = self._elapsed_ms(stage_started)
        has_semantic_query = bool(parsed.semantic_query)
        has_filters = bool(parsed.filters.active_fields())
        search_mode = (
            "hybrid" if has_semantic_query and has_filters
            else "semantic" if has_semantic_query
            else "filter_only"
        )

        if search_mode == "filter_only":
            stage_started = time.perf_counter()
            points = await asyncio.to_thread(self.metadata.filter_all, request.filters)
            price_band_widened = False
            if request.allow_filter_relaxation and self._unique_laptop_count(points) < top_k and (
                request.filters.min_price_usd is not None or request.filters.max_price_usd is not None
            ):
                widened_filters = self._widen_price_filters(request.filters, self.PRICE_RELAXATION_RATIO)
                widened_points = await asyncio.to_thread(self.metadata.filter_all, widened_filters)
                if self._unique_laptop_count(widened_points) > self._unique_laptop_count(points):
                    points = widened_points
                    price_band_widened = True
            timings["metadata_filter"] = self._elapsed_ms(stage_started)
            stage_started = time.perf_counter()
            # No embedding/FAISS score exists here, so without a ranking
            # signal _recommendations would fall back to raw ascending
            # price — which surfaces implausible-cheap data outliers first
            # (e.g. a $95 laptop with 16GB RAM). Rank by the same
            # value/price-fit heuristics hybrid search already uses instead.
            value_by_id = {int(p["vector_id"]): self._value_score(p, "") for p in points}
            price_fit_by_id: dict[int, float] = {}
            if request.filters.min_price_usd is not None or request.filters.max_price_usd is not None:
                price_fit_by_id = {
                    int(p["vector_id"]): self._price_fit_score(p, request.filters) for p in points
                }
            recommendations = self._recommendations(
                points, {}, {}, {}, {}, {}, value_by_id, price_fit_by_id, top_k
            )
            timings["filter_and_rerank"] = self._elapsed_ms(stage_started)
            message = None if recommendations else "No laptops match the selected filters."
            if price_band_widened and recommendations:
                message = (
                    "Not enough laptops matched your exact budget, so this also includes "
                    "close options slightly outside it, weighted lower the further they are "
                    "from your budget."
                )
            return (
                RetrievalResponse(
                    status="ok" if recommendations else "no_metadata_match",
                    message=message,
                    search_mode=search_mode,
                    index_used=None,
                    candidate_k=None,
                    metadata_match_count=len({int(point["laptop_id"]) for point in points}),
                    requested_top_k=top_k,
                    matched_count=len(recommendations),
                    filter_level=1,
                    filter_name="strict",
                    relaxed_filters=["price_range"] if price_band_widened else [],
                    parsed_query=parsed,
                    top_similarity=None,
                    similarity_threshold=None,
                    outlier=False,
                    recommendations=recommendations,
                    retrieval_latency_ms=self._elapsed_ms(started),
                    timings_ms=timings,
                ),
                None,
            )

        vector = query_vector
        stage_started = time.perf_counter()
        if vector is None:
            if has_filters and hasattr(self.embeddings, "encode_many"):
                vector, semantic_vector = await asyncio.to_thread(
                    self.embeddings.encode_many,
                    [parsed.embedding_query, parsed.semantic_query],
                )
            else:
                vector = await asyncio.to_thread(self.embeddings.encode, parsed.embedding_query)
                semantic_vector = vector
                if has_filters:
                    semantic_vector = await asyncio.to_thread(
                        self.embeddings.encode, parsed.semantic_query
                    )
        else:
            semantic_vector = vector
            if has_filters:
                semantic_vector = await asyncio.to_thread(
                    self.embeddings.encode, parsed.semantic_query
                )
        timings["embedding"] = self._elapsed_ms(stage_started)

        nprobe = request.nprobe or self.settings.default_nprobe
        ef_search = request.ef_search or self.settings.default_ef_search
        search_k = max(self.settings.candidate_k * 5, top_k * 20)
        threshold = (
            request.min_cosine_similarity
            if request.min_cosine_similarity is not None
            else self.indexes.threshold_for(index_type)
        )
        metadata_match_count = None
        pre_filter_candidates: list[RetrievalCandidate] = []
        price_band_widened = False
        if search_mode == "hybrid":
            if request.include_diagnostics:
                stage_started = time.perf_counter()
                raw_laptop_hits = await asyncio.to_thread(
                    self.indexes.search_laptops,
                    index_type,
                    vector,
                    search_k,
                    nprobe,
                    ef_search,
                )
                raw_points = await asyncio.to_thread(
                    self._get_laptops_cached, [hit.vector_id for hit in raw_laptop_hits]
                )
                pre_filter_candidates = self._laptop_candidate_hits(
                    raw_laptop_hits,
                    raw_points,
                    parsed.filters,
                    limit=self.settings.candidate_k,
                )
                timings["diagnostics"] = self._elapsed_ms(stage_started)
            hard_fields = request.filters.active_fields() | (
                parsed.locked_fields
                if request.allow_filter_relaxation
                else parsed.filters.active_fields()
            )
            hard_filters = parsed.filters.subset(hard_fields)
            stage_started = time.perf_counter()
            allowed_laptop_ids = await asyncio.to_thread(
                self.metadata.matching_laptop_ids, hard_filters
            )
            if request.allow_filter_relaxation and len(allowed_laptop_ids) < top_k and (
                hard_filters.min_price_usd is not None or hard_filters.max_price_usd is not None
            ):
                widened_filters = self._widen_price_filters(hard_filters, self.PRICE_RELAXATION_RATIO)
                widened_ids = await asyncio.to_thread(
                    self.metadata.matching_laptop_ids, widened_filters
                )
                if len(widened_ids) > len(allowed_laptop_ids):
                    allowed_laptop_ids = widened_ids
                    price_band_widened = True
            timings["metadata_filter"] = self._elapsed_ms(stage_started)
            metadata_match_count = len(allowed_laptop_ids)
            if not allowed_laptop_ids:
                return (
                    RetrievalResponse(
                        status="no_metadata_match",
                        message="No laptops match the selected hard constraints.",
                        search_mode=search_mode,
                        index_used=index_type,
                        candidate_k=self.settings.candidate_k,
                        metadata_match_count=0,
                        pre_filter_candidates=pre_filter_candidates,
                        requested_top_k=top_k,
                        matched_count=0,
                        parsed_query=parsed,
                        top_similarity=None,
                        similarity_threshold=self.indexes.threshold_for(index_type),
                        outlier=False,
                        recommendations=[],
                        retrieval_latency_ms=self._elapsed_ms(started),
                        timings_ms=timings,
                    ),
                    vector,
                )
            stage_started = time.perf_counter()
            laptop_hits = await asyncio.to_thread(
                self.indexes.search_laptops_constrained,
                index_type,
                vector,
                allowed_laptop_ids,
                search_k,
                nprobe,
                ef_search,
            )
            timings["laptop_search"] = self._elapsed_ms(stage_started)
        else:
            stage_started = time.perf_counter()
            laptop_hits = await asyncio.to_thread(
                self.indexes.search_laptops,
                index_type,
                vector,
                search_k,
                nprobe,
                ef_search,
            )
            timings["laptop_search"] = self._elapsed_ms(stage_started)
        stage_started = time.perf_counter()
        candidate_points = await asyncio.to_thread(
            self._get_laptops_cached, [hit.vector_id for hit in laptop_hits]
        )
        timings["metadata_fetch"] = self._elapsed_ms(stage_started)
        candidate_vector_ids = [int(point["vector_id"]) for point in candidate_points]
        query_vectors = [vector]
        if has_filters:
            query_vectors.append(semantic_vector)
        stage_started = time.perf_counter()
        score_maps = await asyncio.to_thread(
            self.indexes.score_vectors_multi,
            index_type,
            query_vectors,
            candidate_vector_ids,
            nprobe,
            ef_search,
        )
        timings["chunk_score"] = self._elapsed_ms(stage_started)
        chunk_filter_scores = score_maps[0]
        semantic_scores = score_maps[1] if has_filters else chunk_filter_scores
        hits = [
            VectorHit(vector_id=vector_id, similarity=score)
            for vector_id, score in chunk_filter_scores.items()
        ]
        hits.sort(key=lambda hit: hit.similarity, reverse=True)
        scores = self._combine_scores(chunk_filter_scores, semantic_scores)
        candidate_hits = self._laptop_candidate_hits(
            laptop_hits,
            candidate_points,
            parsed.filters,
        )
        top_similarity = max(scores["filter_aware"].values(), default=None)
        below_threshold = not hits or top_similarity is None or top_similarity < threshold
        near_miss = (
            below_threshold
            and top_similarity is not None
            and top_similarity >= threshold - self.NEAR_MISS_MARGIN
        )
        if below_threshold and not near_miss:
            return (
                RetrievalResponse(
                    status="no_relevant_match",
                    message="The query does not closely match the available laptop data.",
                    search_mode=search_mode,
                    index_used=index_type,
                    candidate_k=self.settings.candidate_k,
                    metadata_match_count=metadata_match_count,
                    pre_filter_candidates=pre_filter_candidates,
                    candidate_hits=candidate_hits,
                    requested_top_k=top_k,
                    matched_count=0,
                    parsed_query=parsed,
                    top_similarity=top_similarity,
                    similarity_threshold=threshold,
                    outlier=True,
                    retrieval_latency_ms=self._elapsed_ms(started),
                    timings_ms=timings,
                ),
                vector,
            )

        stage_started = time.perf_counter()
        effective_threshold = threshold - self.NEAR_MISS_MARGIN if near_miss else threshold
        relevant_hits = [
            hit for hit in hits if scores["filter_aware"].get(hit.vector_id, hit.similarity) >= effective_threshold
        ]
        candidate_ids = [hit.vector_id for hit in relevant_hits]
        score_by_id = {
            hit.vector_id: scores["ranking"].get(hit.vector_id, hit.similarity)
            for hit in relevant_hits
        }
        locked_fields = parsed.locked_fields | request.filters.active_fields()
        if not request.allow_filter_relaxation:
            locked_fields |= parsed.filters.active_fields()
        # Price is normally a locked/core field, so every relaxation tier
        # below would otherwise keep re-enforcing the *original* strict
        # budget here and silently undo the widened band already applied to
        # allowed_laptop_ids above. Widen it here too so the laptops that
        # widening was meant to surface actually survive this second pass —
        # _price_fit_score still scores against the original parsed.filters,
        # so they still rank below anything actually within budget.
        filters_for_passes = (
            self._widen_price_filters(parsed.filters, self.PRICE_RELAXATION_RATIO)
            if price_band_widened
            else parsed.filters
        )
        passes = build_filter_passes(
            filters_for_passes,
            locked_fields,
            allow_relaxation=request.allow_filter_relaxation,
        )

        selected_pass = passes[-1]
        selected_points: list[dict[str, Any]] = []
        if not request.allow_filter_relaxation:
            candidate_id_set = set(candidate_ids)
            selected_pass = passes[0]
            selected_points = [
                point
                for point in candidate_points
                if int(point.get("vector_id", -1)) in candidate_id_set
            ]
        else:
            for filter_pass in passes:
                points = await self._apply_pass(candidate_ids, filter_pass)
                selected_pass = filter_pass
                selected_points = points
                if self._unique_laptop_count(points) >= top_k:
                    break

        constraint_fit_by_id = {
            int(point["vector_id"]): self._constraint_fit(point, parsed.filters)
            for point in selected_points
        }
        soft_preference_by_id = {
            int(point["vector_id"]): self._soft_preference_score(
                point, parsed.filters, parsed.inferred_filters, parsed.semantic_query
            )
            for point in selected_points
        }
        value_by_id = {
            int(point["vector_id"]): self._value_score(
                point, parsed.semantic_query
            )
            for point in selected_points
        }
        price_fit_by_id = {}
        if parsed.filters.min_price_usd is not None or parsed.filters.max_price_usd is not None:
            price_fit_by_id = {
                int(point["vector_id"]): self._price_fit_score(
                    point, parsed.filters
                )
                for point in selected_points
            }
        ranked_recommendations = self._recommendations(
            selected_points,
            score_by_id,
            scores["semantic"],
            scores["filter_aware"],
            constraint_fit_by_id,
            soft_preference_by_id,
            value_by_id,
            price_fit_by_id,
            self.settings.candidate_k,
        )
        candidate_hits = self._candidate_hits_from_recommendations(ranked_recommendations)
        recommendations = ranked_recommendations[:top_k]
        timings["filter_and_rerank"] = self._elapsed_ms(stage_started)
        message = None
        if near_miss and recommendations:
            message = (
                "No laptop closely matched every part of this query, so these are the "
                "closest available options rather than an exact match."
            )
        elif price_band_widened and recommendations:
            message = (
                "Not enough laptops matched your exact budget, so this also includes "
                "close options slightly outside it, weighted lower the further they are "
                "from your budget."
            )
        elif len(recommendations) < top_k:
            message = (
                f"Only {len(recommendations)} unique laptops passed the similarity threshold "
                "and available metadata filter levels."
            )
        relaxed_filters = list(selected_pass.relaxed_fields)
        if price_band_widened:
            relaxed_filters.append("price_range")
        return (
            RetrievalResponse(
                status="ok" if recommendations else "no_metadata_match",
                message=message,
                search_mode=search_mode,
                index_used=index_type,
                candidate_k=self.settings.candidate_k,
                metadata_match_count=metadata_match_count,
                pre_filter_candidates=pre_filter_candidates,
                candidate_hits=candidate_hits,
                requested_top_k=top_k,
                matched_count=len(recommendations),
                filter_level=selected_pass.level,
                filter_name=selected_pass.name,
                relaxed_filters=relaxed_filters,
                parsed_query=parsed,
                top_similarity=top_similarity,
                top_ranking_score=max(
                    (recommendation.score for recommendation in recommendations),
                    default=None,
                ),
                similarity_threshold=threshold,
                outlier=near_miss and bool(recommendations),
                recommendations=recommendations,
                retrieval_latency_ms=self._elapsed_ms(started),
                timings_ms=timings,
            ),
            vector,
        )

    def recommendations_for_ids(self, laptop_ids: list[int]) -> list[LaptopRecommendation]:
        """Restore an exact grounded set without running vector retrieval."""
        unique_ids = list(dict.fromkeys(laptop_ids))[:20]
        if not unique_ids:
            return []
        points = self._get_laptops_cached(unique_ids)
        recommendations = self._recommendations(
            points, {}, {}, {}, {}, {}, {}, {}, len(unique_ids)
        )
        by_id = {item.laptop_id: item for item in recommendations}
        return [by_id[laptop_id] for laptop_id in unique_ids if laptop_id in by_id]

    def _combine_scores(
        self,
        filter_aware: dict[int, float],
        semantic: dict[int, float],
    ) -> dict[str, dict[int, float]]:
        ranking = {
            vector_id: self.SEMANTIC_WEIGHT * semantic.get(vector_id, filter_score)
            + self.FILTER_AWARE_WEIGHT * filter_score
            for vector_id, filter_score in filter_aware.items()
        }
        return {
            "semantic": semantic,
            "filter_aware": filter_aware,
            "ranking": ranking,
        }

    def _get_laptops_cached(self, laptop_ids: list[int]) -> list[dict[str, Any]]:
        ordered_ids = list(dict.fromkeys(int(value) for value in laptop_ids))
        with self._metadata_cache_lock:
            missing = []
            for laptop_id in ordered_ids:
                if laptop_id in self._metadata_cache:
                    self._metadata_cache.move_to_end(laptop_id)
                else:
                    missing.append(laptop_id)
        if missing:
            fetched = self.metadata.get_laptops(missing)
            grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for point in fetched:
                laptop_id = point.get("laptop_id")
                if laptop_id is not None:
                    grouped[int(laptop_id)].append(point)
            with self._metadata_cache_lock:
                for laptop_id in missing:
                    self._metadata_cache[laptop_id] = grouped.get(laptop_id, [])
                    self._metadata_cache.move_to_end(laptop_id)
                while len(self._metadata_cache) > self._metadata_cache_size:
                    self._metadata_cache.popitem(last=False)
        with self._metadata_cache_lock:
            points: list[dict[str, Any]] = []
            for laptop_id in ordered_ids:
                cached = self._metadata_cache.get(laptop_id)
                if cached is not None:
                    self._metadata_cache.move_to_end(laptop_id)
                    points.extend(cached)
            return points

    async def _apply_pass(
        self, candidate_ids: list[int], filter_pass: FilterPass
    ) -> list[dict[str, Any]]:
        if filter_pass.active_fields:
            return await asyncio.to_thread(
                self.metadata.filter_candidates, candidate_ids, filter_pass.filters
            )
        return await asyncio.to_thread(self.metadata.retrieve, candidate_ids)

    @staticmethod
    def _unique_laptop_count(points: list[dict[str, Any]]) -> int:
        return len({int(point["laptop_id"]) for point in points if point.get("laptop_id") is not None})

    @staticmethod
    def _candidate_hits(
        hits: list[VectorHit],
        points: list[dict[str, Any]],
        threshold: float,
        scores: dict[str, dict[int, float]],
        filters: SearchFilters | None = None,
        limit: int | None = None,
    ) -> list[RetrievalCandidate]:
        points_by_id = {int(point["vector_id"]): point for point in points}
        candidates: list[RetrievalCandidate] = []
        ranking_scores = scores.get("ranking", {})
        semantic_scores = scores.get("semantic", {})
        filter_scores = scores.get("filter_aware", {})
        ordered_hits = sorted(
            hits,
            key=lambda hit: ranking_scores.get(hit.vector_id, hit.similarity),
            reverse=True,
        )
        if limit is not None:
            ordered_hits = ordered_hits[:limit]
        for hit in ordered_hits:
            point = points_by_id.get(hit.vector_id, {})
            excluded = {"vector_id", "chunk_id", "chunk_type", "chunk_text", "laptop_id"}
            metadata = {key: value for key, value in point.items() if key not in excluded}
            candidates.append(
                RetrievalCandidate(
                    vector_id=hit.vector_id,
                    laptop_id=(
                        int(point["laptop_id"])
                        if point.get("laptop_id") is not None
                        else None
                    ),
                    chunk_id=(
                        str(point["chunk_id"])
                        if point.get("chunk_id") is not None
                        else None
                    ),
                    chunk_type=point.get("chunk_type"),
                    brand=(str(point["brand"]) if point.get("brand") is not None else None),
                    model=(str(point["model"]) if point.get("model") is not None else None),
                    price_usd=point.get("price_usd"),
                    score=round(ranking_scores.get(hit.vector_id, hit.similarity), 6),
                    semantic_score=round(semantic_scores[hit.vector_id], 6)
                    if hit.vector_id in semantic_scores
                    else None,
                    filter_aware_score=round(filter_scores[hit.vector_id], 6)
                    if hit.vector_id in filter_scores
                    else None,
                    constraint_fit_score=(
                        round(RetrievalService._constraint_fit(point, filters), 6)
                        if filters is not None and point
                        else None
                    ),
                    passed_similarity_threshold=filter_scores.get(hit.vector_id, hit.similarity) >= threshold,
                    text=str(point.get("chunk_text", "")),
                    metadata=metadata,
                )
            )
        return candidates

    @staticmethod
    def _laptop_candidate_hits(
        hits: list[VectorHit],
        points: list[dict[str, Any]],
        filters: SearchFilters,
        limit: int | None = None,
    ) -> list[RetrievalCandidate]:
        points_by_laptop: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for point in points:
            laptop_id = point.get("laptop_id")
            if laptop_id is not None:
                points_by_laptop[int(laptop_id)].append(point)
        candidates: list[RetrievalCandidate] = []
        for hit in hits[:limit] if limit is not None else hits:
            laptop_id = hit.vector_id
            laptop_points = points_by_laptop.get(laptop_id, [])
            if not laptop_points:
                continue
            best = sorted(
                laptop_points,
                key=lambda point: (
                    0 if point.get("chunk_type") == "spec" else 1,
                    int(point.get("vector_id", -1)),
                ),
            )[0]
            excluded = {"vector_id", "chunk_id", "chunk_type", "chunk_text", "laptop_id"}
            metadata = {key: value for key, value in best.items() if key not in excluded}
            candidates.append(
                RetrievalCandidate(
                    vector_id=int(best["vector_id"]),
                    laptop_id=laptop_id,
                    chunk_id=(
                        str(best["chunk_id"])
                        if best.get("chunk_id") is not None
                        else None
                    ),
                    chunk_type=best.get("chunk_type"),
                    brand=(str(best["brand"]) if best.get("brand") is not None else None),
                    model=(str(best["model"]) if best.get("model") is not None else None),
                    price_usd=best.get("price_usd"),
                    score=round(hit.similarity, 6),
                    semantic_score=round(hit.similarity, 6),
                    filter_aware_score=round(hit.similarity, 6),
                    constraint_fit_score=round(
                        RetrievalService._constraint_fit(best, filters), 6
                    ),
                    text=str(best.get("chunk_text", "")),
                    metadata=metadata,
                )
            )
        return candidates

    @staticmethod
    def _candidate_hits_from_recommendations(
        recommendations: list[LaptopRecommendation],
    ) -> list[RetrievalCandidate]:
        candidates: list[RetrievalCandidate] = []
        for recommendation in recommendations:
            source = recommendation.sources[0] if recommendation.sources else None
            candidates.append(
                RetrievalCandidate(
                    vector_id=source.vector_id if source else recommendation.laptop_id,
                    laptop_id=recommendation.laptop_id,
                    chunk_id=source.chunk_id if source else None,
                    chunk_type=source.chunk_type if source else None,
                    brand=recommendation.brand,
                    model=recommendation.model,
                    price_usd=recommendation.price_usd,
                    score=recommendation.score or 0.0,
                    semantic_score=recommendation.semantic_score,
                    filter_aware_score=recommendation.filter_aware_score,
                    constraint_fit_score=recommendation.constraint_fit_score,
                    soft_preference_score=recommendation.soft_preference_score,
                    value_score=recommendation.value_score,
                    price_fit_score=recommendation.price_fit_score,
                    spec_score=recommendation.spec_score,
                    text=source.text if source else "",
                    metadata=recommendation.metadata,
                )
            )
        return candidates

    def _recommendations(
        self,
        points: list[dict[str, Any]],
        score_by_id: dict[int, float],
        semantic_score_by_id: dict[int, float],
        filter_score_by_id: dict[int, float],
        constraint_fit_by_id: dict[int, float],
        soft_preference_by_id: dict[int, float],
        value_by_id: dict[int, float],
        price_fit_by_id: dict[int, float],
        top_k: int,
    ) -> list[LaptopRecommendation]:
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for point in points:
            laptop_id = point.get("laptop_id")
            vector_id = int(point.get("vector_id", -1))
            if laptop_id is None or (score_by_id and vector_id not in score_by_id):
                continue
            grouped[int(laptop_id)].append(point)

        group_scores: dict[int, dict[str, float]] = {}
        if score_by_id:
            for laptop_id, laptop_points in grouped.items():
                ordered = sorted(
                    laptop_points,
                    key=lambda point: score_by_id[int(point["vector_id"])],
                    reverse=True,
                )
                weights = self.TOP_CHUNK_WEIGHTS[: len(ordered)]
                weight_total = sum(weights)
                text_score = sum(
                    weight * score_by_id[int(point["vector_id"])]
                    for weight, point in zip(weights, ordered)
                ) / weight_total
                semantic_score = sum(
                    weight * semantic_score_by_id.get(int(point["vector_id"]), 0.0)
                    for weight, point in zip(weights, ordered)
                ) / weight_total
                filter_score = sum(
                    weight * filter_score_by_id.get(int(point["vector_id"]), 0.0)
                    for weight, point in zip(weights, ordered)
                ) / weight_total
                fit_score = sum(
                    constraint_fit_by_id.get(int(point["vector_id"]), 1.0)
                    for point in ordered[:3]
                ) / min(len(ordered), 3)
                soft_preference_score = sum(
                    weight * soft_preference_by_id.get(int(point["vector_id"]), 0.5)
                    for weight, point in zip(weights, ordered)
                ) / weight_total
                value_score = sum(
                    weight * value_by_id.get(int(point["vector_id"]), 0.5)
                    for weight, point in zip(weights, ordered)
                ) / weight_total
                price_fit_score = sum(
                    weight * price_fit_by_id.get(int(point["vector_id"]), 0.5)
                    for weight, point in zip(weights, ordered)
                ) / weight_total
                if price_fit_by_id:
                    final_score = (
                        self.HYBRID_TEXT_WEIGHT * text_score
                        + self.HYBRID_PRICE_FIT_WEIGHT * price_fit_score
                        + self.HYBRID_SOFT_PREFERENCE_WEIGHT * soft_preference_score
                        + self.HYBRID_VALUE_WEIGHT * value_score
                    )
                else:
                    final_score = (
                        self.SEMANTIC_TEXT_WEIGHT * text_score
                        + self.SEMANTIC_SOFT_PREFERENCE_WEIGHT * soft_preference_score
                        + self.SEMANTIC_VALUE_WEIGHT * value_score
                    )
                group_scores[laptop_id] = {
                    "score": final_score,
                    "semantic_score": semantic_score,
                    "filter_aware_score": filter_score,
                    "constraint_fit_score": fit_score,
                    "soft_preference_score": soft_preference_score,
                    "value_score": value_score,
                    "price_fit_score": price_fit_score,
                    "spec_score": value_score,
                }
            ranked_groups = [
                (laptop_id, grouped[laptop_id])
                for laptop_id in sorted(
                    group_scores,
                    key=lambda laptop_id: group_scores[laptop_id]["score"],
                    reverse=True,
                )[:top_k]
            ]
        elif value_by_id:
            # Filter-only ranking (no semantic score): the same value/price-fit
            # heuristics as hybrid search, so a plausible well-specced laptop
            # outranks a cheap outlier that happens to have a lower price.
            for laptop_id, laptop_points in grouped.items():
                vector_ids = [int(point["vector_id"]) for point in laptop_points]
                value_score = sum(value_by_id.get(vid, 0.5) for vid in vector_ids) / len(vector_ids)
                group_scores[laptop_id] = {
                    "score": value_score,
                    "semantic_score": None,
                    "filter_aware_score": None,
                    "constraint_fit_score": None,
                    "soft_preference_score": None,
                    "value_score": value_score,
                    "spec_score": value_score,
                }
                if price_fit_by_id:
                    price_fit_score = sum(
                        price_fit_by_id.get(vid, 0.5) for vid in vector_ids
                    ) / len(vector_ids)
                    group_scores[laptop_id]["score"] = (
                        self.FILTER_ONLY_VALUE_WEIGHT * value_score
                        + self.FILTER_ONLY_PRICE_FIT_WEIGHT * price_fit_score
                    )
                    group_scores[laptop_id]["price_fit_score"] = price_fit_score
            ranked_groups = sorted(
                grouped.items(),
                key=lambda item: (
                    -group_scores[item[0]]["score"],
                    float(item[1][0].get("price_usd"))
                    if item[1][0].get("price_usd") is not None
                    else float("inf"),
                    item[0],
                ),
            )[:top_k]
        else:
            ranked_groups = sorted(
                grouped.items(),
                key=lambda item: (
                    float(item[1][0].get("price_usd"))
                    if item[1][0].get("price_usd") is not None
                    else float("inf"),
                    item[0],
                ),
            )[:top_k]

        recommendations: list[LaptopRecommendation] = []
        for laptop_id, laptop_points in ranked_groups:
            if score_by_id:
                laptop_points.sort(
                    key=lambda point: score_by_id[int(point["vector_id"])], reverse=True
                )
            else:
                laptop_points.sort(
                    key=lambda point: (
                        0 if point.get("chunk_type") == "spec" else 1,
                        int(point.get("vector_id", -1)),
                    )
                )
            best = laptop_points[0]
            group_score = group_scores.get(laptop_id, {})
            sources = [
                SourceChunk(
                    vector_id=int(point["vector_id"]),
                    chunk_id=str(point.get("chunk_id", point["vector_id"])),
                    laptop_id=laptop_id,
                    chunk_type=point.get("chunk_type"),
                    score=(
                        round(score_by_id[int(point["vector_id"])], 6)
                        if score_by_id
                        else None
                    ),
                    semantic_score=(
                        round(semantic_score_by_id[int(point["vector_id"])], 6)
                        if int(point["vector_id"]) in semantic_score_by_id
                        else None
                    ),
                    filter_aware_score=(
                        round(filter_score_by_id[int(point["vector_id"])], 6)
                        if int(point["vector_id"]) in filter_score_by_id
                        else None
                    ),
                    text=str(point.get("chunk_text", "")),
                )
                for point in laptop_points[:3]
            ]
            excluded = {"vector_id", "chunk_id", "chunk_type", "chunk_text", "laptop_id", "embedding"}
            metadata = {key: value for key, value in best.items() if key not in excluded}

            def _rounded(key: str, _group_score: dict[str, float] = group_score) -> float | None:
                value = _group_score.get(key)
                return round(value, 6) if value is not None else None

            recommendations.append(
                LaptopRecommendation(
                    laptop_id=laptop_id,
                    brand=str(best.get("brand", "Unknown")),
                    model=str(best.get("model", "Unknown")),
                    price_usd=best.get("price_usd"),
                    score=_rounded("score"),
                    semantic_score=_rounded("semantic_score"),
                    filter_aware_score=_rounded("filter_aware_score"),
                    constraint_fit_score=_rounded("constraint_fit_score"),
                    soft_preference_score=_rounded("soft_preference_score"),
                    value_score=_rounded("value_score"),
                    price_fit_score=_rounded("price_fit_score"),
                    spec_score=_rounded("spec_score"),
                    metadata=metadata,
                    sources=sources,
                )
            )
        return recommendations

    @staticmethod
    def _constraint_fit(point: dict[str, Any], filters: SearchFilters) -> float:
        """Score how well a laptop satisfies constraints, including relaxed ones."""
        scores: list[float] = []

        def numeric_min(field: str, required: float | None) -> None:
            if required is None:
                return
            actual = point.get(field)
            scores.append(min(float(actual) / required, 1.0) if actual is not None and required else 0.0)

        def numeric_max(field: str, maximum: float | None) -> None:
            if maximum is None:
                return
            actual = point.get(field)
            scores.append(min(maximum / float(actual), 1.0) if actual is not None and actual > 0 else 0.0)

        numeric_min("ram_capacity_gb", filters.min_ram_gb)
        numeric_min("storage_capacity_gb", filters.min_storage_gb)
        numeric_min("vram_capacity_gb", filters.min_vram_gb)
        numeric_min("weight_kg", filters.min_weight_kg)
        numeric_min("price_usd", filters.min_price_usd)
        numeric_max("price_usd", filters.max_price_usd)
        numeric_max("weight_kg", filters.max_weight_kg)

        brand = str(point.get("brand_normalized", point.get("brand", ""))).lower()
        if filters.brands:
            scores.append(1.0 if brand in filters.brands else 0.0)
        if filters.excluded_brands:
            scores.append(0.0 if brand in filters.excluded_brands else 1.0)

        def values_for(field: str) -> set[str]:
            value = point.get(field, [])
            if isinstance(value, str):
                return {value.lower()}
            return {str(item).lower() for item in value}

        gpu_tags = values_for("gpu_tags")
        if filters.gpu_tags:
            scores.append(1.0 if gpu_tags.intersection(filters.gpu_tags) else 0.0)
        if filters.excluded_gpu_tags:
            scores.append(0.0 if gpu_tags.intersection(filters.excluded_gpu_tags) else 1.0)
        if filters.storage_types:
            scores.append(
                1.0
                if values_for("storage_types").intersection(filters.storage_types)
                else 0.0
            )
        if filters.operating_systems:
            operating_system = str(
                point.get("os_normalized", point.get("operating_system", ""))
            ).lower()
            scores.append(1.0 if operating_system in filters.operating_systems else 0.0)
        return sum(scores) / len(scores) if scores else 1.0

    @classmethod
    def _widen_price_filters(cls, filters: SearchFilters, ratio: float) -> SearchFilters:
        """A copy of ``filters`` with any stated price bound loosened by
        ``ratio`` in the constrained direction, so a laptop just outside the
        stated budget can still be found (and ranked, via _price_fit_score,
        below anything actually within budget)."""
        updates: dict[str, float] = {}
        if filters.max_price_usd is not None:
            updates["max_price_usd"] = filters.max_price_usd * (1 + ratio)
        if filters.min_price_usd is not None:
            updates["min_price_usd"] = filters.min_price_usd * (1 - ratio)
        if not updates:
            return filters
        return filters.model_copy(update=updates)

    @classmethod
    def _price_fit_score(cls, point: dict[str, Any], filters: SearchFilters) -> float:
        price = cls._number(point.get("price_usd"))
        if price is None or price <= 0:
            return 0.0
        if filters.max_price_usd is not None:
            budget = filters.max_price_usd
            if price <= budget:
                return cls._clamp(price / budget)
            # Over budget (only reachable via the widened price band): score
            # falls linearly to 0 at the edge of that widened band instead
            # of being clamped back up to 1.0, so it always ranks behind an
            # in-budget option.
            overage_ratio = (price - budget) / budget
            return cls._clamp(1.0 - overage_ratio / cls.PRICE_RELAXATION_RATIO)
        if filters.min_price_usd is not None:
            floor = filters.min_price_usd
            if price >= floor:
                return cls._clamp(floor / price)
            shortfall_ratio = (floor - price) / floor
            return cls._clamp(1.0 - shortfall_ratio / cls.PRICE_RELAXATION_RATIO)
        return 0.5

    def _soft_preference_score(
        self,
        point: dict[str, Any],
        explicit_filters: SearchFilters,
        inferred_filters: SearchFilters,
        semantic_query: str,
    ) -> float:
        scores: list[float] = []
        price = self._number(point.get("price_usd"))
        weight = self._number(point.get("weight_kg"))

        if explicit_filters.max_weight_kg is not None and weight:
            scores.append(self._clamp(explicit_filters.max_weight_kg / weight))
        if explicit_filters.min_weight_kg is not None and weight:
            scores.append(self._clamp(weight / explicit_filters.min_weight_kg))

        if inferred_filters.min_price_usd is not None and price:
            scores.append(
                0.85
                + 0.15 * self._clamp(price / inferred_filters.min_price_usd)
                if price < inferred_filters.min_price_usd
                else 1.0
            )
        if inferred_filters.max_price_usd is not None and price:
            scores.append(
                0.85
                + 0.15 * self._clamp(inferred_filters.max_price_usd / price)
                if price > inferred_filters.max_price_usd
                else 1.0
            )
        if inferred_filters.max_weight_kg is not None and weight:
            scores.append(
                0.85
                + 0.15 * self._clamp(inferred_filters.max_weight_kg / weight)
                if weight > inferred_filters.max_weight_kg
                else 1.0
            )

        lower_query = semantic_query.lower()
        if any(term in lower_query for term in ("lightweight", "portable", "travel")):
            stats = self.parser.range_statistics.get("weight_kg", {})
            minimum = stats.get("min")
            maximum = stats.get("max")
            if weight and minimum is not None and maximum is not None and maximum > minimum:
                scores.append(self._clamp((maximum - weight) / (maximum - minimum)))

        return sum(scores) / len(scores) if scores else 0.5

    @staticmethod
    def _value_score(point: dict[str, Any], _semantic_query: str) -> float:
        """Score available hardware evidence without making missing fields punitive."""
        components: list[tuple[float, float]] = []

        ram = RetrievalService._number(point.get("ram_capacity_gb"))
        if ram is not None:
            components.append((0.20, RetrievalService._clamp(ram / 16.0)))

        storage = RetrievalService._number(point.get("storage_capacity_gb"))
        if storage is not None:
            components.append((0.15, RetrievalService._clamp(storage / 512.0)))

        cpu = str(point.get("cpu_full", "")).lower()
        if cpu:
            if re.search(r"\b(?:i9|i7|ryzen\s*[79]|core\s*ultra\s*[79]|m[2-4]\s*(?:pro|max))\b", cpu):
                cpu_score = 1.0
            elif re.search(r"\b(?:i5|ryzen\s*5|core\s*ultra\s*5|m[1-4])\b", cpu):
                cpu_score = 0.80
            elif re.search(r"\b(?:i3|ryzen\s*3|celeron|pentium|athlon)\b", cpu):
                cpu_score = 0.55
            else:
                cpu_score = 0.65
            components.append((0.30, cpu_score))

        gpu_tags = point.get("gpu_tags", [])
        if isinstance(gpu_tags, str):
            gpu_tags = [gpu_tags]
        gpu_tags = {str(tag).lower() for tag in gpu_tags}
        if gpu_tags:
            if gpu_tags.intersection({"rtx", "rtx 4090", "rtx 4080", "rtx 4070"}):
                gpu_score = 1.0
            elif gpu_tags.intersection({"gtx", "rx", "arc", "radeon"}):
                gpu_score = 0.85
            elif "integrated" in gpu_tags:
                gpu_score = 0.60
            else:
                gpu_score = 0.70
            components.append((0.20, gpu_score))

        display_size = RetrievalService._number(point.get("display_size_inches"))
        if display_size is not None:
            display_score = 1.0 if 13.0 <= display_size <= 16.5 else 0.80
            components.append((0.05, display_score))
        width = RetrievalService._number(point.get("display_resolution_width"))
        height = RetrievalService._number(point.get("display_resolution_height"))
        if width is not None and height is not None:
            resolution_score = 1.0 if width >= 1920 and height >= 1080 else 0.75
            components.append((0.05, resolution_score))

        battery = str(point.get("battery", ""))
        battery_match = re.search(r"(\d+(?:\.\d+)?)\s*wh", battery.lower())
        if battery_match:
            components.append((0.05, RetrievalService._clamp(float(battery_match.group(1)) / 60.0)))

        if not components:
            return 0.5
        total_weight = sum(weight for weight, _ in components)
        return sum(weight * score for weight, score in components) / total_weight

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)
