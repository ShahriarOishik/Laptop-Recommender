from dataclasses import replace

import pandas as pd
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import ServiceContainer
from app.main import create_app


def _catalog_frame() -> pd.DataFrame:
    rows = [
        (1, 30, "Acer", "Swift", 700.0, "acer"),
        (2, 10, "Dell", "XPS", 1200.0, "dell"),
        (3, 20, "Asus", "Zenbook", 700.0, "asus"),
        (4, 40, "Lenovo", "ThinkPad", None, "lenovo"),
        (5, 30, "Acer", "Swift", 700.0, "acer"),
    ]
    return pd.DataFrame(
        [
            {
                "vector_id": vector_id,
                "laptop_id": laptop_id,
                "brand": brand,
                "model": model,
                "price_usd": price,
                "brand_normalized": normalized,
                "ram_capacity_gb": 16.0,
                "storage_capacity_gb": 512.0,
                "storage_types": ["ssd"],
                "gpu_tags": [],
                "weight_kg": 1.5,
                "os_normalized": "windows",
            }
            for vector_id, laptop_id, brand, model, price, normalized in rows
        ]
    )


def _client(tmp_path) -> TestClient:
    metadata_path = tmp_path / "metadata.parquet"
    _catalog_frame().to_parquet(metadata_path, index=False)
    settings = replace(
        Settings(),
        artifact_dir=tmp_path / "artifacts",
        metadata_backend="parquet",
        local_metadata_file=metadata_path,
        load_resources_on_startup=False,
        rate_limit_enabled=False,
    )
    return TestClient(create_app(settings, ServiceContainer(settings)))


def test_catalog_pagination_reaches_each_unique_laptop_once(tmp_path):
    with _client(tmp_path) as client:
        first = client.get("/laptops", params={"limit": 2, "offset": 0, "sort": "price-asc"})
        second = client.get("/laptops", params={"limit": 2, "offset": 2, "sort": "price-asc"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 4
    ids = [item["laptop_id"] for item in first.json()["items"] + second.json()["items"]]
    assert ids == [20, 30, 10, 40]
    assert len(ids) == len(set(ids))


def test_catalog_search_filter_total_and_name_sort(tmp_path):
    with _client(tmp_path) as client:
        response = client.get(
            "/laptops",
            params=[("search", "e"), ("brands", "dell"), ("sort", "name")],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["laptop_id"] for item in body["items"]] == [10]


def test_catalog_rejects_unknown_sort(tmp_path):
    with _client(tmp_path) as client:
        response = client.get("/laptops", params={"sort": "newest"})

    assert response.status_code == 422
