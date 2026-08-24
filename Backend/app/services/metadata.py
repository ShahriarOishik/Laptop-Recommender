from __future__ import annotations

from typing import Any, Protocol

from app.models import SearchFilters


class MetadataStore(Protocol):
    def health(self, expected_dimension: int = 768, expected_count: int | None = None) -> bool:
        ...

    def retrieve(self, ids: list[int]) -> list[dict[str, Any]]:
        ...

    def filter_candidates(self, ids: list[int], filters: SearchFilters) -> list[dict[str, Any]]:
        ...

    def matching_vector_ids(self, filters: SearchFilters) -> list[int]:
        ...

    def matching_laptop_ids(self, filters: SearchFilters) -> list[int]:
        ...

    def filter_all(self, filters: SearchFilters) -> list[dict[str, Any]]:
        ...

    def catalog_page(
        self,
        filters: SearchFilters,
        search: str | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        ...

    def catalog_facets(self) -> dict[str, list[str]]:
        ...

    def get_laptop(self, laptop_id: int) -> list[dict[str, Any]]:
        ...

    def get_laptops(self, laptop_ids: list[int]) -> list[dict[str, Any]]:
        ...
