from __future__ import annotations

from app.config import Settings
from app.services.artifact_store import ArtifactStore
from app.services.cache import SemanticCache
from app.services.conversation_store import ConversationStore
from app.services.embeddings import EmbeddingService
from app.services.faiss_manager import FaissIndexManager
from app.services.generator import GroundedGenerator
from app.services.hybrid_metadata_store import HybridQdrantMetadataStore
from app.services.insights import SpecificationInsights
from app.services.local_metadata_store import LocalParquetMetadataStore
from app.services.metadata import MetadataStore
from app.services.parser import QueryParser
from app.services.qdrant_store import QdrantMetadataStore
from app.services.rag import RagService
from app.services.rate_limiter import RateLimiter
from app.services.retrieval import RetrievalService


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.artifacts = ArtifactStore(settings.artifact_dir, settings.artifact_base_url)
        self.embeddings = EmbeddingService(settings)
        self.indexes = FaissIndexManager(settings, self.artifacts)
        self.parser = QueryParser(self.indexes.manifest.get("range_statistics", {}))
        self.generator = GroundedGenerator(settings)
        self.cache = SemanticCache(settings.cache_max_entries, settings.cache_similarity_threshold)
        self.conversations = ConversationStore()
        self.insights = SpecificationInsights(self.artifacts)
        self.rate_limiter = RateLimiter(
            settings.rate_limit_requests, settings.rate_limit_window_seconds
        )
        self.metadata: MetadataStore | None = None
        self.retrieval: RetrievalService | None = None
        self.rag: RagService | None = None
        self.startup_errors: list[str] = []
        self.qdrant_ready = False
        self.metadata_ready = False
        self.faiss_ready = False
        self._facets_cache: dict[str, list[str]] | None = None

    def initialize(self) -> None:
        try:
            if self.settings.metadata_backend == "parquet":
                if not self.settings.local_metadata_file:
                    raise ValueError("LOCAL_METADATA_FILE is required for the Parquet backend.")
                metadata = LocalParquetMetadataStore(self.settings.local_metadata_file)
            elif self.settings.metadata_backend == "qdrant":
                qdrant = QdrantMetadataStore(self.settings)
                laptop_metadata = LocalParquetMetadataStore(
                    self.artifacts.ensure("laptop_metadata.parquet"),
                    require_unique_laptops=True,
                )
                expected_laptop_count = self.indexes.manifest.get("laptop_vector_count")
                laptop_metadata.health(
                    expected_count=(
                        int(expected_laptop_count)
                        if expected_laptop_count is not None
                        else None
                    )
                )
                metadata = HybridQdrantMetadataStore(qdrant, laptop_metadata)
            else:
                raise ValueError(
                    f"Unsupported METADATA_BACKEND: {self.settings.metadata_backend!r}"
                )
            expected_count = self.indexes.manifest.get("vector_count")
            self.metadata_ready = metadata.health(
                expected_dimension=self.settings.embedding_dimension,
                expected_count=int(expected_count) if expected_count is not None else None,
            )
            self.qdrant_ready = (
                self.metadata_ready and self.settings.metadata_backend == "qdrant"
            )
            self.metadata = metadata
        except Exception as exc:
            self.metadata = None
            self.qdrant_ready = False
            self.metadata_ready = False
            self.startup_errors.append(f"Metadata: {exc}")
        if self.settings.load_resources_on_startup:
            try:
                self.embeddings.load()
            except Exception as exc:
                self.startup_errors.append(f"Embedding model: {exc}")
            try:
                self.indexes.load_default()
                self.faiss_ready = True
            except Exception as exc:
                self.startup_errors.append(f"FAISS: {exc}")
        if self.metadata:
            self.retrieval = RetrievalService(
                self.settings,
                self.embeddings,
                self.parser,
                self.indexes,
                self.metadata,
            )
            self.rag = RagService(
                self.settings,
                self.embeddings,
                self.parser,
                self.retrieval,
                self.generator,
                self.cache,
                self.conversations,
            )

    def require_retrieval(self) -> RetrievalService:
        if not self.retrieval or not self.metadata_ready:
            raise RuntimeError("Retrieval metadata is not configured or reachable.")
        return self.retrieval

    def require_rag(self) -> RagService:
        if not self.rag or not self.metadata_ready:
            raise RuntimeError("RAG metadata is not configured or reachable.")
        return self.rag

    def laptop_facets(self) -> dict[str, list[str]]:
        """Distinct brand/GPU/OS values for the Explore-page filter panel.
        Cached for the process lifetime since artifacts are static once loaded."""
        if self._facets_cache is None:
            if not self.metadata:
                return {"brands": [], "gpu_tags": [], "operating_systems": []}
            self._facets_cache = self.metadata.catalog_facets()
        return self._facets_cache
