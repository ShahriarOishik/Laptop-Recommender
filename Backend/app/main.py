from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.container import ServiceContainer
from app.logging_config import configure_logging, request_id_var
from app.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IndexOption,
    IndexSettingsResponse,
    IndexType,
    RetrievalResponse,
    SearchFilters,
    SearchRequest,
)


# flat/pq/ivf_pq are still the pre-tie-tolerant-fix numbers from
# Notebook/benchmark_results.csv (duplicate-chunk ties depressed recall
# across the board — see EVALUATION_REPORT.md Finding 2). hnsw's numbers
# below are the corrected, live-verified ones from the post-fix rerun
# (99.38% recall@10, 0.95ms p50) — refresh the other four once a corrected
# CSV is regenerated; do not treat them as current.
BENCHMARKS = {
    "flat": {"recall_at_10": 1.0, "p50_ms": 16.823, "size_mb": 195.68},
    "ivf_flat": {"recall_at_10": 0.882, "p50_ms": 1.467, "size_mb": 199.30},
    "pq": {"recall_at_10": 0.7463, "p50_ms": 4.691, "size_mb": 6.90},
    "ivf_pq": {"recall_at_10": 0.746, "p50_ms": 2.315, "size_mb": 10.52},
    "hnsw": {"recall_at_10": 0.9938, "p50_ms": 0.95, "size_mb": 213.02},
}

LOGGER = logging.getLogger(__name__)

_EXCLUDED_MERGE_FIELDS = {"vector_id", "chunk_id", "chunk_type", "chunk_text", "embedding"}

# Client-facing message for unexpected retrieval/chat failures. The real
# exception is always logged server-side (LOGGER.exception) — this constant
# is what reaches the HTTP response, so internal file paths, config values,
# or provider connection details never leak to API clients.
_SERVICE_UNAVAILABLE_DETAIL = "retrieval temporarily unavailable"


def _client_ip(request: Request, settings: Settings) -> str:
    # X-Forwarded-For is client-settable and only trustworthy when a single
    # trusted reverse proxy (Render, etc.) sits in front of this service and
    # is confirmed to set it as "client, proxy1, proxy2..." — the first
    # entry is then the real client. Without that confirmation (the
    # trust_forwarded_for setting), honoring it lets any caller pick a fresh
    # rate-limit bucket per request just by sending a different header value.
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(request: Request, service_container: ServiceContainer) -> None:
    settings = service_container.settings
    if not settings.rate_limit_enabled:
        return
    allowed, retry_after = service_container.rate_limiter.check(_client_ip(request, settings))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests — please slow down and try again shortly.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def _merge_laptop_record(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse a laptop's chunk rows into one display-ready record plus
    the per-chunk-type text (summary/pros/cons/review/spec), so the
    frontend doesn't need to parse raw chunk arrays itself."""
    if not chunks:
        return {}
    canonical = next((chunk for chunk in chunks if chunk.get("chunk_type") == "spec"), chunks[0])
    merged = {key: value for key, value in canonical.items() if key not in _EXCLUDED_MERGE_FIELDS}
    content_by_type: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        text = chunk.get("chunk_text")
        if text:
            content_by_type[str(chunk.get("chunk_type") or "other")].append(str(text))
    merged["content_by_type"] = dict(content_by_type)
    return merged


def create_app(
    settings: Settings | None = None,
    container: ServiceContainer | None = None,
) -> FastAPI:
    configure_logging()
    app_settings = settings or Settings.from_env()
    services = container or ServiceContainer(app_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await asyncio.to_thread(services.initialize)
        yield
        await services.generator.aclose()

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            LOGGER.exception(
                "request failed method=%s path=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        else:
            duration_ms = (time.perf_counter() - started) * 1000
            log = LOGGER.warning if response.status_code >= 500 else LOGGER.info
            log(
                "request method=%s path=%s status=%d duration_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        service_container: ServiceContainer = request.app.state.services
        ready = (
            service_container.embeddings.ready
            and service_container.indexes.ready
            and service_container.metadata_ready
        )
        return HealthResponse(
            status="ready" if ready else "degraded",
            version=app_settings.app_version,
            embedding_model=app_settings.embedding_model,
            embedding_ready=service_container.embeddings.ready,
            faiss_ready=service_container.indexes.ready,
            metadata_backend=app_settings.metadata_backend,
            metadata_ready=service_container.metadata_ready,
            qdrant_ready=service_container.qdrant_ready,
            llm_providers=service_container.generator.configured_providers,
            errors=service_container.startup_errors,
        )

    @app.get("/ready", response_model=HealthResponse)
    async def readiness(request: Request) -> HealthResponse:
        response = await health(request)
        if response.status != "ready":
            raise HTTPException(status_code=503, detail=response.model_dump())
        return response

    @app.get("/settings/indexes", response_model=IndexSettingsResponse)
    async def index_settings() -> IndexSettingsResponse:
        labels = {
            IndexType.FLAT: "Flat (Exact K-NN)",
            IndexType.IVF_FLAT: "IVF Flat",
            IndexType.PQ: "Product Quantization",
            IndexType.IVF_PQ: "IVF + PQ",
            IndexType.HNSW: "HNSW Flat",
        }
        options = []
        for index_type in IndexType:
            parameters = {}
            if index_type in {IndexType.IVF_FLAT, IndexType.IVF_PQ}:
                parameters["nprobe"] = {"default": app_settings.default_nprobe, "min": 1, "max": 512}
            if index_type == IndexType.HNSW:
                parameters["ef_search"] = {"default": app_settings.default_ef_search, "min": 1, "max": 1024}
            options.append(
                IndexOption(
                    id=index_type,
                    label=labels[index_type],
                    default=index_type.value == app_settings.default_index,
                    available=(
                        index_type.value in services.indexes.manifest.get("indexes", {})
                        if services.indexes.manifest.get("indexes") is not None
                        else (app_settings.artifact_dir / app_settings.index_files[index_type.value]).exists()
                    ),
                    parameters=parameters,
                    benchmark=BENCHMARKS[index_type.value],
                )
            )
        return IndexSettingsResponse(
            candidate_k=app_settings.candidate_k,
            final_top_k=app_settings.default_top_k,
            default_index=IndexType(app_settings.default_index),
            indexes=options,
        )

    @app.post("/retrieve", response_model=RetrievalResponse)
    async def retrieve(payload: SearchRequest, request: Request) -> RetrievalResponse:
        service_container: ServiceContainer = request.app.state.services
        _enforce_rate_limit(request, service_container)
        try:
            response, _ = await service_container.require_retrieval().retrieve(payload)
            return response
        except Exception as exc:
            LOGGER.exception("Retrieval request failed")
            raise HTTPException(status_code=503, detail=_SERVICE_UNAVAILABLE_DETAIL) from exc

    @app.post("/chat", response_model=ChatResponse)
    async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
        service_container: ServiceContainer = request.app.state.services
        _enforce_rate_limit(request, service_container)
        try:
            return await service_container.require_rag().chat(payload)
        except Exception as exc:
            LOGGER.exception("Chat request failed")
            raise HTTPException(status_code=503, detail=_SERVICE_UNAVAILABLE_DETAIL) from exc

    @app.post("/chat/stream")
    async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
        """Same request/response contract as /chat, but delivered as
        Server-Sent Events: a "recommendations" event as soon as retrieval
        finishes, then "answer"/"card_insights" as each LLM call completes,
        then a final "done" event carrying the complete response (identical
        in shape to a non-streaming /chat call). Progressive events are a
        head start for the UI, not a separate source of truth."""
        service_container: ServiceContainer = request.app.state.services
        _enforce_rate_limit(request, service_container)

        async def sse() -> AsyncIterator[str]:
            try:
                async for event, data in service_container.require_rag().chat_stream(payload):
                    yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
            except Exception:
                LOGGER.exception("Streaming chat request failed")
                yield f"event: error\ndata: {json.dumps({'detail': _SERVICE_UNAVAILABLE_DETAIL})}\n\n"

        return StreamingResponse(
            sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/laptops")
    async def list_laptops(
        request: Request,
        search: str | None = None,
        brands: list[str] = Query(default_factory=list),
        min_price_usd: float | None = Query(default=None, ge=0),
        max_price_usd: float | None = Query(default=None, ge=0),
        min_ram_gb: float | None = Query(default=None, ge=0),
        min_storage_gb: float | None = Query(default=None, ge=0),
        min_vram_gb: float | None = Query(default=None, ge=0),
        gpu_tags: list[str] = Query(default_factory=list),
        operating_systems: list[str] = Query(default_factory=list),
        sort: Literal["price-asc", "price-desc", "name"] = "name",
        limit: int = Query(default=24, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        service_container: ServiceContainer = request.app.state.services
        if not service_container.metadata:
            raise HTTPException(status_code=503, detail="Metadata storage is unavailable.")
        filters = SearchFilters(
            min_price_usd=min_price_usd,
            max_price_usd=max_price_usd,
            min_ram_gb=min_ram_gb,
            min_storage_gb=min_storage_gb,
            min_vram_gb=min_vram_gb,
            brands=brands,
            gpu_tags=gpu_tags,
            operating_systems=operating_systems,
        )
        laptops, total = await asyncio.to_thread(
            service_container.metadata.catalog_page,
            filters,
            search,
            sort,
            limit,
            offset,
        )
        page = [
            {key: value for key, value in item.items() if key not in _EXCLUDED_MERGE_FIELDS}
            for item in laptops
        ]
        facets = await asyncio.to_thread(service_container.laptop_facets)
        return {"total": total, "limit": limit, "offset": offset, "items": page, "facets": facets}

    @app.get("/laptops/{laptop_id}")
    async def laptop(laptop_id: int, request: Request):
        service_container: ServiceContainer = request.app.state.services
        _enforce_rate_limit(request, service_container)
        if not service_container.metadata:
            raise HTTPException(status_code=503, detail="Metadata storage is unavailable.")
        points = await asyncio.to_thread(service_container.metadata.get_laptop, laptop_id)
        if not points:
            raise HTTPException(status_code=404, detail="Laptop not found.")
        return {"laptop_id": laptop_id, "laptop": _merge_laptop_record(points), "chunks": points}

    @app.get("/laptops/{laptop_id}/similar")
    async def similar_laptops(
        laptop_id: int,
        request: Request,
        limit: int = Query(default=5, ge=1, le=20),
    ):
        service_container: ServiceContainer = request.app.state.services
        _enforce_rate_limit(request, service_container)
        if not service_container.metadata or not service_container.indexes.ready:
            raise HTTPException(status_code=503, detail="Retrieval is not configured.")
        index_type = IndexType(app_settings.default_index)
        vector = await asyncio.to_thread(
            service_container.indexes.reconstruct_laptop_vector, index_type, laptop_id
        )
        if vector is None:
            raise HTTPException(status_code=404, detail="Laptop not found in the vector index.")
        hits = await asyncio.to_thread(
            service_container.indexes.search_laptops,
            index_type,
            vector,
            limit + 1,
            app_settings.default_nprobe,
            app_settings.default_ef_search,
        )
        hits = [hit for hit in hits if hit.vector_id != laptop_id][:limit]
        laptop_ids = [hit.vector_id for hit in hits]
        points = await asyncio.to_thread(service_container.metadata.get_laptops, laptop_ids)
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for point in points:
            group_id = point.get("laptop_id")
            if group_id is not None:
                grouped[int(group_id)].append(point)
        similarity_by_id = {hit.vector_id: hit.similarity for hit in hits}
        results = []
        for candidate_id in laptop_ids:
            merged = _merge_laptop_record(grouped.get(candidate_id, []))
            if merged:
                merged["similarity"] = round(similarity_by_id.get(candidate_id, 0.0), 6)
                results.append(merged)
        return {"laptop_id": laptop_id, "similar": results}

    @app.get("/insights/specifications")
    async def specification_insights(
        request: Request,
        item: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
    ):
        service_container: ServiceContainer = request.app.state.services
        return {"rules": await asyncio.to_thread(service_container.insights.get, item, limit)}

    @app.get("/cache/stats")
    async def cache_stats(request: Request):
        service_container: ServiceContainer = request.app.state.services
        return service_container.cache.stats()

    return app


app = create_app()
