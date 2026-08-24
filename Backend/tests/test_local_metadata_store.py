import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.models import SearchFilters
from app.services.local_metadata_store import LocalParquetMetadataStore


class LocalMetadataStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "metadata.parquet"
        pd.DataFrame(
            [
                {
                    "vector_id": 1,
                    "laptop_id": 10,
                    "brand_normalized": "dell",
                    "price_usd": 900.0,
                    "ram_capacity_gb": 16.0,
                    "storage_capacity_gb": 512.0,
                    "storage_types": ["ssd", "nvme"],
                    "gpu_tags": ["rtx", "rtx 4060"],
                    "gpu_full": "NVIDIA GeForce RTX 4060 - 8 GB VRAM",
                    "weight_kg": 1.8,
                    "os_normalized": "windows",
                },
                {
                    "vector_id": 2,
                    "laptop_id": 20,
                    "brand_normalized": "lenovo",
                    "price_usd": 700.0,
                    "ram_capacity_gb": 8.0,
                    "storage_capacity_gb": 256.0,
                    "storage_types": ["ssd"],
                    "gpu_tags": [],
                    "gpu_full": "Integrated Intel Graphics",
                    "weight_kg": 1.4,
                    "os_normalized": "linux",
                },
            ]
        ).to_parquet(self.path, index=False)
        self.store = LocalParquetMetadataStore(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_retrieves_only_requested_ids(self):
        records = self.store.retrieve([2])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["vector_id"], 2)

    def test_applies_numeric_and_keyword_filters(self):
        records = self.store.filter_candidates(
            [1, 2],
            SearchFilters(
                max_price_usd=1000,
                min_ram_gb=16,
                storage_types=["nvme"],
                gpu_tags=["rtx 4060"],
            ),
        )
        self.assertEqual([record["vector_id"] for record in records], [1])

    def test_applies_negative_filters(self):
        records = self.store.filter_candidates(
            [1, 2], SearchFilters(excluded_gpu_tags=["rtx"])
        )
        self.assertEqual([record["vector_id"] for record in records], [2])

    def test_applies_minimum_weight(self):
        records = self.store.filter_candidates([1, 2], SearchFilters(min_weight_kg=1.6))
        self.assertEqual([record["vector_id"] for record in records], [1])

    def test_derives_and_filters_minimum_vram_from_gpu_text(self):
        records = self.store.filter_candidates([1, 2], SearchFilters(min_vram_gb=6))
        self.assertEqual([record["vector_id"] for record in records], [1])
        self.assertEqual(records[0]["vram_capacity_gb"], 8.0)

    def test_health_validates_count(self):
        self.assertTrue(self.store.health(expected_count=2))
        with self.assertRaises(ValueError):
            self.store.health(expected_count=3)

    def test_chained_filters_reducing_to_zero_rows_do_not_crash(self):
        """Regression test: pandas' .map() can't infer a lambda's return
        dtype from zero rows, so calling it on an already-empty frame (e.g.
        after an earlier price/RAM filter left nothing) comes back float64
        instead of bool — and indexing a DataFrame with a non-boolean empty
        Series silently drops every *column*, not just rows. The next
        column access (`frame["laptop_id"]`) then raises KeyError. A price
        filter far below every laptop's price, combined with a gpu_tags
        filter, used to crash matching_laptop_ids/filter_all/
        filter_candidates instead of returning zero results."""
        filters = SearchFilters(max_price_usd=1, gpu_tags=["rtx"])

        ids = self.store.matching_laptop_ids(filters)
        self.assertEqual(ids, [])

        records = self.store.filter_all(filters)
        self.assertEqual(records, [])

        records = self.store.filter_candidates([1, 2], filters)
        self.assertEqual(records, [])

    def test_chained_filters_with_storage_type_reducing_to_zero_do_not_crash(self):
        filters = SearchFilters(max_price_usd=1, storage_types=["ssd"])
        self.assertEqual(self.store.matching_laptop_ids(filters), [])

    def test_chained_filters_with_excluded_gpu_reducing_to_zero_do_not_crash(self):
        filters = SearchFilters(max_price_usd=1, excluded_gpu_tags=["rtx"])
        self.assertEqual(self.store.matching_laptop_ids(filters), [])

    def test_catalog_page_deduplicates_chunks_and_slices_after_sorting(self):
        duplicate = pd.read_parquet(self.path).iloc[[0]].copy()
        duplicate["vector_id"] = 3
        pd.concat([pd.read_parquet(self.path), duplicate], ignore_index=True).to_parquet(
            self.path, index=False
        )
        store = LocalParquetMetadataStore(self.path)

        first, total = store.catalog_page(
            SearchFilters(), None, "price-asc", limit=1, offset=0
        )
        second, second_total = store.catalog_page(
            SearchFilters(), None, "price-asc", limit=1, offset=1
        )

        self.assertEqual(total, 2)
        self.assertEqual(second_total, 2)
        self.assertEqual([first[0]["laptop_id"], second[0]["laptop_id"]], [20, 10])

    def test_catalog_page_search_total_and_name_sort_are_deterministic(self):
        frame = pd.read_parquet(self.path)
        frame["brand"] = ["Dell", "Lenovo"]
        frame["model"] = ["Zulu", "Alpha"]
        frame.to_parquet(self.path, index=False)
        store = LocalParquetMetadataStore(self.path)

        records, total = store.catalog_page(
            SearchFilters(max_price_usd=800), "len", "name", limit=24, offset=0
        )

        self.assertEqual(total, 1)
        self.assertEqual([record["laptop_id"] for record in records], [20])

    def test_laptop_sidecar_rejects_duplicate_laptop_ids(self):
        duplicate = pd.read_parquet(self.path).iloc[[0]].copy()
        duplicate["vector_id"] = 3
        pd.concat([pd.read_parquet(self.path), duplicate], ignore_index=True).to_parquet(
            self.path, index=False
        )

        with self.assertRaisesRegex(ValueError, "one row per laptop_id"):
            LocalParquetMetadataStore(self.path, require_unique_laptops=True)


if __name__ == "__main__":
    unittest.main()
