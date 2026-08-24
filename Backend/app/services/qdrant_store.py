from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from qdrant_client import QdrantClient, models

from app.config import Settings
from app.models import SearchFilters


class QdrantMetadataStore:
    def __init__(self, settings: Settings) -> None:
        if not settings.qdrant_url and not settings.qdrant_local_path:
            raise ValueError("QDRANT_URL or QDRANT_LOCAL_PATH is required.")
        self.collection = settings.qdrant_collection
        self.metadata_only = bool(
            not settings.qdrant_url
            and settings.qdrant_local_path
            and settings.qdrant_local_metadata_only
        )
        if settings.qdrant_url:
            parsed = urlparse(settings.qdrant_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("QDRANT_URL must be a complete http(s) URL.")
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout=settings.qdrant_timeout,
            )
        else:
            settings.qdrant_local_path.parent.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(settings.qdrant_local_path))

    def health(self, expected_dimension: int = 768, expected_count: int | None = None) -> bool:
        info = self.client.get_collection(self.collection)
        vectors = info.config.params.vectors
        if self.metadata_only:
            vectors_valid = vectors == {}
        else:
            vectors_valid = hasattr(vectors, "size") and int(vectors.size) == expected_dimension
        if not vectors_valid:
            raise ValueError(
                f"Qdrant collection dimension does not match expected {expected_dimension}."
            )
        if not self.metadata_only and vectors.distance != models.Distance.COSINE:
            raise ValueError("Qdrant collection must use cosine distance.")
        count = self.client.count(self.collection, exact=True).count
        if expected_count is not None and count != expected_count:
            raise ValueError(f"Qdrant contains {count} points; expected {expected_count}.")
        return True

    def retrieve(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids:
            return []
        points = self.client.retrieve(
            collection_name=self.collection,
            ids=ids,
            with_payload=True,
            with_vectors=False,
        )
        return [self._point(point) for point in points]

    def get_laptop(self, laptop_id: int) -> list[dict[str, Any]]:
        points = []
        offset = None
        while True:
            page, offset = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="laptop_id", match=models.MatchValue(value=laptop_id)
                        )
                    ]
                ),
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points.extend(page)
            if offset is None:
                break
        return [self._point(point) for point in points]

    def filter_candidates(self, ids: list[int], filters: SearchFilters) -> list[dict[str, Any]]:
        if not ids:
            return []
        return self._scroll_points(self._build_filter(filters, ids))

    def matching_vector_ids(self, filters: SearchFilters) -> list[int]:
        return [int(point["vector_id"]) for point in self._scroll_points(self._build_filter(filters))]

    def matching_laptop_ids(self, filters: SearchFilters) -> list[int]:
        points = self._scroll_points(
            self._build_filter(filters), payload_fields=["laptop_id"]
        )
        return list(dict.fromkeys(int(point["laptop_id"]) for point in points))

    def filter_all(self, filters: SearchFilters) -> list[dict[str, Any]]:
        return self._scroll_points(self._build_filter(filters))

    def catalog_page(
        self,
        filters: SearchFilters,
        search: str | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        del filters, search, sort, limit, offset
        raise RuntimeError(
            "Catalog listing requires the laptop_metadata.parquet sidecar; "
            "Qdrant chunk payloads are not a laptop catalog."
        )

    def catalog_facets(self) -> dict[str, list[str]]:
        raise RuntimeError(
            "Catalog facets require the laptop_metadata.parquet sidecar."
        )

    def get_laptops(self, laptop_ids: list[int]) -> list[dict[str, Any]]:
        if not laptop_ids:
            return []
        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="laptop_id",
                    match=models.MatchAny(any=[int(value) for value in laptop_ids]),
                )
            ]
        )
        return self._scroll_points(scroll_filter)

    def _build_filter(
        self, filters: SearchFilters, ids: list[int] | None = None
    ) -> models.Filter | None:
        conditions: list[models.Condition] = []
        excluded_conditions: list[models.Condition] = []
        if ids is not None:
            conditions.append(models.HasIdCondition(has_id=ids))
        values = filters.model_dump()
        if values["min_price_usd"] is not None or values["max_price_usd"] is not None:
            conditions.append(
                models.FieldCondition(
                    key="price_usd",
                    range=models.Range(
                        gte=values["min_price_usd"],
                        lte=values["max_price_usd"],
                    ),
                )
            )
        if values["min_ram_gb"] is not None:
            conditions.append(
                models.FieldCondition(
                    key="ram_capacity_gb", range=models.Range(gte=values["min_ram_gb"])
                )
            )
        if values["min_storage_gb"] is not None:
            conditions.append(
                models.FieldCondition(
                    key="storage_capacity_gb", range=models.Range(gte=values["min_storage_gb"])
                )
            )
        if values["min_vram_gb"] is not None:
            conditions.append(
                models.FieldCondition(
                    key="vram_capacity_gb", range=models.Range(gte=values["min_vram_gb"])
                )
            )
        if values["min_weight_kg"] is not None or values["max_weight_kg"] is not None:
            conditions.append(
                models.FieldCondition(
                    key="weight_kg",
                    range=models.Range(
                        gte=values["min_weight_kg"],
                        lte=values["max_weight_kg"],
                    ),
                )
            )
        for key, field in (
            ("brand_normalized", "brands"),
            ("gpu_tags", "gpu_tags"),
            ("storage_types", "storage_types"),
            ("os_normalized", "operating_systems"),
        ):
            if values[field]:
                conditions.append(
                    models.FieldCondition(key=key, match=models.MatchAny(any=values[field]))
                )
        for key, field in (
            ("brand_normalized", "excluded_brands"),
            ("gpu_tags", "excluded_gpu_tags"),
        ):
            if values[field]:
                excluded_conditions.append(
                    models.FieldCondition(key=key, match=models.MatchAny(any=values[field]))
                )
        if not conditions and not excluded_conditions:
            return None
        return models.Filter(must=conditions, must_not=excluded_conditions)

    def _scroll_points(
        self,
        scroll_filter: models.Filter | None,
        payload_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        points = []
        offset = None
        while True:
            page, offset = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=scroll_filter,
                limit=1000,
                offset=offset,
                with_payload=payload_fields or True,
                with_vectors=False,
            )
            points.extend(page)
            if offset is None:
                break
        return [self._point(point) for point in points]

    @staticmethod
    def _point(point) -> dict[str, Any]:
        payload = dict(point.payload or {})
        payload["vector_id"] = int(point.id)
        return payload
