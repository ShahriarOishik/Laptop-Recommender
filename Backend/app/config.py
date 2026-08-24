from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_ROOT / ".env")


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    return int(value) if value else default


def _as_float(value: str | None, default: float) -> float:
    return float(value) if value else default


@dataclass(frozen=True)
class Settings:
    app_name: str = "Laptop Recommendation RAG API"
    app_version: str = "0.1.0"
    environment: str = "development"
    backend_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1])
    artifact_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1] / "artifacts")
    artifact_base_url: str | None = None

    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dimension: int = 768
    embedding_device: str | None = None
    load_resources_on_startup: bool = True

    default_index: str = "ivf_flat"
    candidate_k: int = 20
    default_top_k: int = 5
    default_nprobe: int = 64
    default_ef_search: int = 256
    # Holds one laptop-level + one chunk-level index per cache slot. Must
    # cover all 5 index types (x2) or switching index types thrashes the
    # cache on every request that doesn't use the default.
    index_cache_size: int = 10
    default_similarity_threshold: float = 0.60

    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_local_path: Path | None = None
    qdrant_local_metadata_only: bool = False
    qdrant_collection: str = "laptop_chunks"
    qdrant_timeout: float = 20.0
    metadata_backend: str = "qdrant"
    local_metadata_file: Path | None = None

    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    # Third fallback tier, tried only if both Groq and Gemini fail or are
    # unconfigured. OpenRouter fronts many providers behind one OpenAI-
    # compatible endpoint; the ":free" suffix models cost nothing (rate-limited).
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-oss-20b:free"
    llm_timeout: float = 45.0
    # Caps how long the retry loop spends on ONE provider (3 attempts with
    # backoff) before moving to the next tier. Without this, a degraded
    # provider (steady 429s) can burn its full 3-attempt backoff on each of
    # 3 providers — observed taking 96s end to end under real rate-limit
    # pressure — before ever reaching a working fallback.
    llm_provider_budget_seconds: float = 15.0
    # Circuit breaker: after this many consecutive failures, a provider is
    # skipped entirely (no attempt, no budget spent) for the cooldown
    # window, then re-tried once as a trial. Without this, a provider stuck
    # in a rate-limit/outage window gets rediscovered — and pays its full
    # retry budget — on every single request instead of once per window.
    llm_circuit_failure_threshold: int = 3
    llm_circuit_cooldown_seconds: float = 30.0

    cache_enabled: bool = True
    cache_max_entries: int = 128
    cache_similarity_threshold: float = 0.96
    dataset_version: str = "v1"
    prompt_version: str = "v1"

    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://localhost:5173")

    # Per-client-IP sliding-window limits on the expensive endpoints
    # (embedding + FAISS + LLM calls). Cheap read endpoints (/health,
    # /laptops, /settings/indexes) are not limited.
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 20
    rate_limit_window_seconds: float = 60.0
    # X-Forwarded-For is an ordinary client-settable header — only honor it
    # when a trusted single-hop reverse proxy (Render, etc.) is confirmed to
    # sit in front of this service and set it correctly. Left False by
    # default so a direct-to-backend deployment (local dev, a bare Docker
    # run) can't have its rate limit bypassed by spoofing the header.
    trust_forwarded_for: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        backend_root = Path(__file__).resolve().parents[1]
        artifact_dir = Path(os.getenv("ARTIFACT_DIR", backend_root / "artifacts")).resolve()
        origins = tuple(
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
            ).split(",")
            if origin.strip()
        )
        local_path_value = os.getenv("QDRANT_LOCAL_PATH")
        local_path = Path(local_path_value) if local_path_value else None
        if local_path is not None and not local_path.is_absolute():
            local_path = (backend_root / local_path).resolve()
        metadata_file_value = os.getenv("LOCAL_METADATA_FILE")
        metadata_file = Path(metadata_file_value) if metadata_file_value else None
        if metadata_file is not None and not metadata_file.is_absolute():
            metadata_file = (backend_root / metadata_file).resolve()
        return cls(
            environment=os.getenv("ENVIRONMENT", "development"),
            backend_root=backend_root,
            artifact_dir=artifact_dir,
            artifact_base_url=os.getenv("ARTIFACT_BASE_URL") or None,
            embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5"),
            embedding_dimension=_as_int(os.getenv("EMBEDDING_DIMENSION"), 768),
            embedding_device=os.getenv("EMBEDDING_DEVICE") or None,
            load_resources_on_startup=_as_bool(os.getenv("LOAD_RESOURCES_ON_STARTUP"), True),
            default_index=os.getenv("DEFAULT_INDEX", "ivf_flat"),
            candidate_k=_as_int(os.getenv("CANDIDATE_K"), 20),
            default_top_k=_as_int(os.getenv("DEFAULT_TOP_K"), 5),
            default_nprobe=_as_int(os.getenv("DEFAULT_NPROBE"), 64),
            default_ef_search=_as_int(os.getenv("DEFAULT_EF_SEARCH"), 256),
            index_cache_size=_as_int(os.getenv("INDEX_CACHE_SIZE"), 10),
            default_similarity_threshold=_as_float(
                os.getenv("DEFAULT_SIMILARITY_THRESHOLD"), 0.60
            ),
            qdrant_url=os.getenv("QDRANT_URL") or None,
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            qdrant_local_path=local_path,
            qdrant_local_metadata_only=_as_bool(
                os.getenv("QDRANT_LOCAL_METADATA_ONLY"), False
            ),
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "laptop_chunks"),
            qdrant_timeout=_as_float(os.getenv("QDRANT_TIMEOUT"), 20.0),
            metadata_backend=os.getenv("METADATA_BACKEND", "qdrant").strip().lower(),
            local_metadata_file=metadata_file,
            groq_api_key=os.getenv("GROQ_API_KEY") or None,
            groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
            openrouter_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b:free"),
            llm_timeout=_as_float(os.getenv("LLM_TIMEOUT"), 45.0),
            llm_provider_budget_seconds=_as_float(os.getenv("LLM_PROVIDER_BUDGET_SECONDS"), 15.0),
            llm_circuit_failure_threshold=_as_int(os.getenv("LLM_CIRCUIT_FAILURE_THRESHOLD"), 3),
            llm_circuit_cooldown_seconds=_as_float(os.getenv("LLM_CIRCUIT_COOLDOWN_SECONDS"), 30.0),
            cache_enabled=_as_bool(os.getenv("CACHE_ENABLED"), True),
            cache_max_entries=_as_int(os.getenv("CACHE_MAX_ENTRIES"), 128),
            cache_similarity_threshold=_as_float(
                os.getenv("CACHE_SIMILARITY_THRESHOLD"), 0.96
            ),
            dataset_version=os.getenv("DATASET_VERSION", "v1"),
            prompt_version=os.getenv("PROMPT_VERSION", "v1"),
            cors_origins=origins,
            rate_limit_enabled=_as_bool(os.getenv("RATE_LIMIT_ENABLED"), True),
            rate_limit_requests=_as_int(os.getenv("RATE_LIMIT_REQUESTS"), 20),
            rate_limit_window_seconds=_as_float(os.getenv("RATE_LIMIT_WINDOW_SECONDS"), 60.0),
            trust_forwarded_for=_as_bool(os.getenv("TRUST_FORWARDED_FOR"), False),
        )

    @property
    def index_files(self) -> dict[str, str]:
        return {
            "flat": "flat.index",
            "ivf_flat": "ivf_flat.index",
            "pq": "pq.index",
            "ivf_pq": "ivf_pq.index",
            "hnsw": "hnsw.index",
        }
