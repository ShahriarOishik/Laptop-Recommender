from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from app.models import SearchFilters


class LocalParquetMetadataStore:
    """Local development adapter with the same contract as the Qdrant store."""

    def __init__(self, path: Path, *, require_unique_laptops: bool = False) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Local metadata artifact was not found: {path}")
        schema = pq.ParquetFile(path).schema_arrow
        columns = [name for name in schema.names if name != "embedding"]
        frame = pq.read_table(path, columns=columns).to_pandas()
        if "vram_capacity_gb" not in frame:
            frame["vram_capacity_gb"] = (
                frame["gpu_full"].map(self._vram_capacity_gb)
                if "gpu_full" in frame
                else np.nan
            )
        if frame["vector_id"].duplicated().any():
            raise ValueError("Local metadata vector_id values must be unique.")
        if require_unique_laptops and frame["laptop_id"].duplicated().any():
            raise ValueError("Laptop metadata must contain exactly one row per laptop_id.")
        self.path = path
        self.frame = frame.set_index("vector_id", drop=False)
        self.laptops = frame.drop_duplicates("laptop_id").set_index("laptop_id", drop=False)
        self._laptop_vector_ids = {
            int(laptop_id): group["vector_id"].to_numpy(dtype=np.int64)
            for laptop_id, group in frame.groupby("laptop_id", sort=False)
        }

    def health(self, expected_dimension: int = 768, expected_count: int | None = None) -> bool:
        del expected_dimension
        if expected_count is not None and len(self.frame) != expected_count:
            raise ValueError(
                f"Local metadata contains {len(self.frame)} rows; expected {expected_count}."
            )
        return True

    def retrieve(self, ids: list[int]) -> list[dict[str, Any]]:
        available = [vector_id for vector_id in ids if vector_id in self.frame.index]
        if not available:
            return []
        return self._records(self.frame.loc[available])

    def filter_candidates(self, ids: list[int], filters: SearchFilters) -> list[dict[str, Any]]:
        available = [vector_id for vector_id in ids if vector_id in self.frame.index]
        if not available:
            return []
        frame = self._filter_frame(filters, self.frame.loc[available])
        return self._records(frame)

    def matching_vector_ids(self, filters: SearchFilters) -> list[int]:
        frame = self._filter_frame(filters, self.frame)
        return [int(value) for value in frame["vector_id"].tolist()]

    def matching_laptop_ids(self, filters: SearchFilters) -> list[int]:
        frame = self._filter_frame(filters, self.laptops)
        return [int(value) for value in frame["laptop_id"].tolist()]

    def filter_all(self, filters: SearchFilters) -> list[dict[str, Any]]:
        return self._records(self._filter_frame(filters, self.laptops))

    def catalog_page(
        self,
        filters: SearchFilters,
        search: str | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        frame = self._filter_frame(filters, self.laptops).reset_index(drop=True)
        needle = (search or "").strip()
        if needle and not frame.empty:
            brand = frame.get("brand", pd.Series("", index=frame.index)).fillna("").astype(str)
            model = frame.get("model", pd.Series("", index=frame.index)).fillna("").astype(str)
            frame = frame[(brand + " " + model).str.contains(needle, case=False, regex=False)]

        total = len(frame)
        if sort == "name":
            brand = frame.get("brand", pd.Series("", index=frame.index)).fillna("").astype(str)
            model = frame.get("model", pd.Series("", index=frame.index)).fillna("").astype(str)
            frame = (
                frame.assign(_catalog_name=(brand + " " + model).str.casefold())
                .sort_values(
                    ["_catalog_name", "laptop_id"],
                    ascending=[True, True],
                    kind="mergesort",
                )
                .drop(columns="_catalog_name")
            )
        elif sort in {"price-asc", "price-desc"}:
            frame = frame.sort_values(
                ["price_usd", "laptop_id"],
                ascending=[sort == "price-asc", True],
                na_position="last",
                kind="mergesort",
            )
        else:
            raise ValueError(f"Unsupported catalog sort: {sort!r}")

        return self._records(frame.iloc[offset : offset + limit]), total

    def catalog_facets(self) -> dict[str, list[str]]:
        brands = self._distinct_strings("brand_normalized")
        systems = self._distinct_strings("os_normalized")
        gpu_tags: set[str] = set()
        if "gpu_tags" in self.laptops:
            for tags in self.laptops["gpu_tags"].dropna():
                if isinstance(tags, str):
                    tags = [tags]
                gpu_tags.update(str(tag) for tag in tags if tag)
        return {
            "brands": brands,
            "gpu_tags": sorted(gpu_tags),
            "operating_systems": systems,
        }

    def _distinct_strings(self, column: str) -> list[str]:
        if column not in self.laptops:
            return []
        return sorted(str(value) for value in self.laptops[column].dropna().unique() if value)

    @staticmethod
    def _filter_frame(filters: SearchFilters, source: pd.DataFrame) -> pd.DataFrame:
        frame = source
        values = filters.model_dump()
        if values["min_price_usd"] is not None:
            frame = frame[frame["price_usd"] >= values["min_price_usd"]]
        if values["max_price_usd"] is not None:
            frame = frame[frame["price_usd"] <= values["max_price_usd"]]
        if values["min_ram_gb"] is not None:
            frame = frame[frame["ram_capacity_gb"] >= values["min_ram_gb"]]
        if values["min_storage_gb"] is not None:
            frame = frame[frame["storage_capacity_gb"] >= values["min_storage_gb"]]
        if values["min_vram_gb"] is not None:
            frame = frame[frame["vram_capacity_gb"] >= values["min_vram_gb"]]
        if values["min_weight_kg"] is not None:
            frame = frame[frame["weight_kg"] >= values["min_weight_kg"]]
        if values["max_weight_kg"] is not None:
            frame = frame[frame["weight_kg"] <= values["max_weight_kg"]]
        if values["brands"]:
            frame = frame[frame["brand_normalized"].isin(values["brands"])]
        if values["operating_systems"]:
            frame = frame[frame["os_normalized"].isin(values["operating_systems"])]
        # Guard the .map()-based filters with `not frame.empty`: pandas can't
        # infer a lambda's return dtype from zero rows, so .map() on an
        # already-empty Series comes back float64 (not bool) — and indexing
        # a DataFrame with a non-boolean empty Series is silently treated as
        # "select these (zero) columns", dropping every column, not just
        # rows. That corrupted frame then KeyErrors on the next column
        # access. Skipping the map when already empty is a no-op filter-wise
        # (nothing to check) and sidesteps the pandas quirk entirely.
        if values["storage_types"] and not frame.empty:
            frame = frame[
                frame["storage_types"].map(
                    lambda items: LocalParquetMetadataStore._has_any(
                        items, values["storage_types"]
                    )
                )
            ]
        if values["gpu_tags"] and not frame.empty:
            frame = frame[
                frame["gpu_tags"].map(
                    lambda items: LocalParquetMetadataStore._has_any(items, values["gpu_tags"])
                )
            ]
        if values["excluded_brands"]:
            frame = frame[~frame["brand_normalized"].isin(values["excluded_brands"])]
        if values["excluded_gpu_tags"] and not frame.empty:
            frame = frame[
                ~frame["gpu_tags"].map(
                    lambda items: LocalParquetMetadataStore._has_any(
                        items, values["excluded_gpu_tags"]
                    )
                )
            ]
        return frame

    def get_laptop(self, laptop_id: int) -> list[dict[str, Any]]:
        vector_ids = self._laptop_vector_ids.get(int(laptop_id))
        return self._records(self.frame.loc[vector_ids]) if vector_ids is not None else []

    def get_laptops(self, laptop_ids: list[int]) -> list[dict[str, Any]]:
        arrays = [self._laptop_vector_ids[value] for value in dict.fromkeys(laptop_ids) if value in self._laptop_vector_ids]
        if not arrays:
            return []
        return self._records(self.frame.loc[np.concatenate(arrays)])

    @classmethod
    def _records(cls, frame: pd.DataFrame) -> list[dict[str, Any]]:
        return [
            {key: cls._clean(value) for key, value in record.items()}
            for record in frame.to_dict(orient="records")
        ]

    @staticmethod
    def _record(row: pd.Series) -> dict[str, Any]:
        return {key: LocalParquetMetadataStore._clean(value) for key, value in row.to_dict().items()}

    @staticmethod
    def _has_any(items: Any, required: list[str]) -> bool:
        if items is None:
            return False
        if isinstance(items, np.ndarray):
            items = items.tolist()
        return bool(set(items) & set(required))

    @staticmethod
    def _vram_capacity_gb(value: Any) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB)\s*VRAM\b", str(value), re.I)
        if not match:
            return None
        amount = float(match.group(1))
        return amount / 1024 if match.group(2).lower() == "mb" else amount

    @staticmethod
    def _clean(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
