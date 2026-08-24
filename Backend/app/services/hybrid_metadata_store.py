from __future__ import annotations

from typing import Any

from app.models import SearchFilters
from app.services.local_metadata_store import LocalParquetMetadataStore
from app.services.qdrant_store import QdrantMetadataStore


class HybridQdrantMetadataStore:
    """Use local laptop metadata for filters and Qdrant for source payloads."""

    def __init__(
        self,
        qdrant: QdrantMetadataStore,
        laptop_metadata: LocalParquetMetadataStore,
    ) -> None:
        self.qdrant = qdrant
        self.laptop_metadata = laptop_metadata

    def health(self, expected_dimension: int = 768, expected_count: int | None = None) -> bool:
        return self.qdrant.health(expected_dimension, expected_count)

    def retrieve(self, ids: list[int]) -> list[dict[str, Any]]:
        return self.qdrant.retrieve(ids)

    def filter_candidates(
        self, ids: list[int], filters: SearchFilters
    ) -> list[dict[str, Any]]:
        return self.qdrant.filter_candidates(ids, filters)

    def matching_vector_ids(self, filters: SearchFilters) -> list[int]:
        return self.qdrant.matching_vector_ids(filters)

    def matching_laptop_ids(self, filters: SearchFilters) -> list[int]:
        return self.laptop_metadata.matching_laptop_ids(filters)

    def filter_all(self, filters: SearchFilters) -> list[dict[str, Any]]:
        return self.laptop_metadata.filter_all(filters)

    def catalog_page(
        self,
        filters: SearchFilters,
        search: str | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        return self.laptop_metadata.catalog_page(filters, search, sort, limit, offset)

    def catalog_facets(self) -> dict[str, list[str]]:
        return self.laptop_metadata.catalog_facets()

    def get_laptop(self, laptop_id: int) -> list[dict[str, Any]]:
        return self.qdrant.get_laptop(laptop_id)

    def get_laptops(self, laptop_ids: list[int]) -> list[dict[str, Any]]:
        return self.qdrant.get_laptops(laptop_ids)
