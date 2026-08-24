from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IndexType(str, Enum):
    FLAT = "flat"
    IVF_FLAT = "ivf_flat"
    PQ = "pq"
    IVF_PQ = "ivf_pq"
    HNSW = "hnsw"


class ChatIntent(str, Enum):
    NEW_RECOMMENDATION = "new_recommendation"
    FOLLOW_UP = "follow_up"
    UPDATED_REQUIREMENTS = "updated_requirements"
    GENERAL_QUESTION = "general_question"


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_price_usd: float | None = Field(default=None, ge=0)
    max_price_usd: float | None = Field(default=None, ge=0)
    min_ram_gb: float | None = Field(default=None, ge=0)
    min_storage_gb: float | None = Field(default=None, ge=0)
    min_vram_gb: float | None = Field(default=None, ge=0)
    min_weight_kg: float | None = Field(default=None, gt=0)
    max_weight_kg: float | None = Field(default=None, gt=0)
    brands: list[str] = Field(default_factory=list)
    gpu_tags: list[str] = Field(default_factory=list)
    excluded_brands: list[str] = Field(default_factory=list)
    excluded_gpu_tags: list[str] = Field(default_factory=list)
    storage_types: list[str] = Field(default_factory=list)
    operating_systems: list[str] = Field(default_factory=list)

    @field_validator(
        "brands",
        "gpu_tags",
        "excluded_brands",
        "excluded_gpu_tags",
        "storage_types",
        "operating_systems",
    )
    @classmethod
    def normalize_values(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip().lower() for value in values if value.strip()))

    def active_fields(self) -> set[str]:
        return {
            name
            for name, value in self.model_dump().items()
            if value is not None and value != []
        }

    def subset(self, fields: set[str]) -> "SearchFilters":
        values = {
            name: value
            for name, value in self.model_dump().items()
            if name in fields
        }
        return SearchFilters(**values)

    @model_validator(mode="after")
    def validate_ranges(self) -> "SearchFilters":
        if (
            self.min_price_usd is not None
            and self.max_price_usd is not None
            and self.min_price_usd > self.max_price_usd
        ):
            raise ValueError("min_price_usd cannot exceed max_price_usd")
        if (
            self.min_weight_kg is not None
            and self.max_weight_kg is not None
            and self.min_weight_kg > self.max_weight_kg
        ):
            raise ValueError("min_weight_kg cannot exceed max_weight_kg")
        return self


class ParsedQuery(BaseModel):
    original_query: str
    semantic_query: str
    embedding_query: str = ""
    semantic_constraints: list[str] = Field(default_factory=list)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    inferred_filters: SearchFilters = Field(default_factory=SearchFilters)
    locked_fields: set[str] = Field(default_factory=set)
    confidence: float = Field(default=1.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str | None = Field(default=None, max_length=2000)
    index_type: IndexType | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    nprobe: int | None = Field(default=None, ge=1, le=512)
    ef_search: int | None = Field(default=None, ge=1, le=1024)
    min_cosine_similarity: float | None = Field(default=None, ge=-1, le=1)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    allow_filter_relaxation: bool = False
    include_diagnostics: bool = False

    @model_validator(mode="after")
    def require_query_or_filters(self) -> "SearchRequest":
        if not (self.message and self.message.strip()) and not self.filters.active_fields():
            raise ValueError("message or at least one filter is required")
        if self.message is not None:
            self.message = self.message.strip() or None
        if (
            self.filters.min_price_usd is not None
            and self.filters.max_price_usd is not None
            and self.filters.min_price_usd > self.filters.max_price_usd
        ):
            raise ValueError("min_price_usd cannot exceed max_price_usd")
        return self


class ChatRequest(SearchRequest):
    conversation_id: str | None = Field(default=None, max_length=64)
    # Restores an exact previously suggested set after process restart or
    # expiry. Loading these IDs never performs semantic retrieval.
    grounding_laptop_ids: list[int] = Field(default_factory=list, max_length=20)
    # Set when the user explicitly invoked the "/suggest" command on the
    # frontend. True always runs a fresh FAISS retrieval for this turn;
    # False never does, even if the message text reads like a new
    # recommendation request. It is answered from the last retrieved set,
    # or with instructions to explicitly request retrieval when no set exists.
    force_retrieval: bool = False


class SourceChunk(BaseModel):
    vector_id: int
    chunk_id: str
    laptop_id: int
    chunk_type: str | None = None
    score: float | None = None
    semantic_score: float | None = None
    filter_aware_score: float | None = None
    text: str


class LaptopRecommendation(BaseModel):
    laptop_id: int
    brand: str
    model: str
    price_usd: float | None = None
    score: float | None = None
    semantic_score: float | None = None
    filter_aware_score: float | None = None
    constraint_fit_score: float | None = None
    soft_preference_score: float | None = None
    value_score: float | None = None
    price_fit_score: float | None = None
    spec_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceChunk] = Field(default_factory=list)


class RetrievalCandidate(BaseModel):
    vector_id: int
    laptop_id: int | None = None
    chunk_id: str | None = None
    chunk_type: str | None = None
    brand: str | None = None
    model: str | None = None
    price_usd: float | None = None
    score: float
    semantic_score: float | None = None
    filter_aware_score: float | None = None
    constraint_fit_score: float | None = None
    soft_preference_score: float | None = None
    value_score: float | None = None
    price_fit_score: float | None = None
    spec_score: float | None = None
    passed_similarity_threshold: bool = True
    text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    status: str = "ok"
    message: str | None = None
    search_mode: str = "semantic"
    index_used: IndexType | None = None
    candidate_k: int | None = 20
    metadata_match_count: int | None = None
    pre_filter_candidates: list[RetrievalCandidate] = Field(default_factory=list)
    candidate_hits: list[RetrievalCandidate] = Field(default_factory=list)
    requested_top_k: int
    matched_count: int
    filter_level: int | None = None
    filter_name: str | None = None
    relaxed_filters: list[str] = Field(default_factory=list)
    parsed_query: ParsedQuery
    top_similarity: float | None = None
    top_ranking_score: float | None = None
    similarity_threshold: float | None = None
    outlier: bool = False
    recommendations: list[LaptopRecommendation] = Field(default_factory=list)
    retrieval_latency_ms: float
    timings_ms: dict[str, float] = Field(default_factory=dict)


class CardInsight(BaseModel):
    match_reason: str
    strengths: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


class ChatResponse(RetrievalResponse):
    answer: str
    provider: str
    cache_hit: bool = False
    conversation_id: str
    intent: ChatIntent = ChatIntent.NEW_RECOMMENDATION
    referenced_laptop_ids: list[int] = Field(default_factory=list)
    card_insights: dict[int, CardInsight] = Field(default_factory=dict)


class IndexOption(BaseModel):
    id: IndexType
    label: str
    default: bool = False
    available: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)
    benchmark: dict[str, Any] = Field(default_factory=dict)


class IndexSettingsResponse(BaseModel):
    candidate_k: int
    final_top_k: int
    default_index: IndexType
    indexes: list[IndexOption]


class HealthResponse(BaseModel):
    status: str
    version: str
    embedding_model: str
    embedding_ready: bool
    faiss_ready: bool
    metadata_backend: str
    metadata_ready: bool
    qdrant_ready: bool
    llm_providers: list[str]
    errors: list[str] = Field(default_factory=list)
