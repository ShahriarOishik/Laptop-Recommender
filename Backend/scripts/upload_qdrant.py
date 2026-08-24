from __future__ import annotations

import argparse
import math
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import pyarrow.dataset as ds
from qdrant_client import QdrantClient, models
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")


def parse_args() -> argparse.Namespace:
    backend_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Upload production BGE vectors to Qdrant Cloud.")
    parser.add_argument("--records", type=Path, default=backend_root / "artifacts" / "qdrant_records.parquet")
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "laptop_chunks"))
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--no-wait", action="store_true", help="Submit asynchronous upserts.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backend_root = BACKEND_ROOT
    url = os.getenv("QDRANT_URL")
    local_path_value = os.getenv("QDRANT_LOCAL_PATH")
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("QDRANT_URL must be a complete http(s) URL.")
        client = QdrantClient(url=url, api_key=os.getenv("QDRANT_API_KEY"), timeout=60)
    elif local_path_value:
        local_path = Path(local_path_value)
        if not local_path.is_absolute():
            local_path = (backend_root / local_path).resolve()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(local_path))
    else:
        raise ValueError("QDRANT_URL or QDRANT_LOCAL_PATH is required.")
    metadata_only = bool(
        not url
        and os.getenv("QDRANT_LOCAL_METADATA_ONLY", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if args.recreate and client.collection_exists(args.collection):
        client.delete_collection(args.collection)
    if not client.collection_exists(args.collection):
        client.create_collection(
            collection_name=args.collection,
            vectors_config=(
                {}
                if metadata_only
                else models.VectorParams(size=768, distance=models.Distance.COSINE)
            ),
            )

    existing_ids = set()
    if not args.recreate:
        offset = None
        while True:
            page, offset = client.scroll(
                collection_name=args.collection,
                limit=1000,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            existing_ids.update(int(point.id) for point in page)
            if offset is None:
                break

    dataset = ds.dataset(args.records, format="parquet")
    uploaded = len(existing_ids)
    for batch in dataset.to_batches(batch_size=args.batch_size):
        points = []
        for record in batch.to_pylist():
            vector = record.pop("embedding")
            vector_id = int(record["vector_id"])
            if vector_id in existing_ids:
                continue
            payload = {key: clean(value) for key, value in record.items() if key != "vector_id"}
            points.append(
                models.PointStruct(
                    id=vector_id,
                    vector={} if metadata_only else vector,
                    payload=payload,
                )
            )
        if not points:
            continue
        for attempt in range(3):
            try:
                client.upsert(
                    collection_name=args.collection,
                    points=points,
                    wait=not args.no_wait,
                )
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        uploaded += len(points)
        existing_ids.update(point.id for point in points)
        print(f"uploaded {uploaded}", flush=True)

    create_payload_indexes(client, args.collection)
    count = client.count(args.collection, exact=True).count
    if args.no_wait:
        deadline = time.time() + 300
        while count != uploaded and time.time() < deadline:
            time.sleep(5)
            count = client.count(args.collection, exact=True).count
    if count != uploaded:
        raise ValueError(f"Qdrant contains {count} points; uploaded {uploaded}.")
    print(f"Qdrant collection {args.collection!r} contains {count} points", flush=True)
    client.close()


def create_payload_indexes(client: QdrantClient, collection: str) -> None:
    fields = {
        "laptop_id": models.PayloadSchemaType.INTEGER,
        "brand_normalized": models.PayloadSchemaType.KEYWORD,
        "price_usd": models.PayloadSchemaType.FLOAT,
        "ram_capacity_gb": models.PayloadSchemaType.FLOAT,
        "storage_capacity_gb": models.PayloadSchemaType.FLOAT,
        "storage_types": models.PayloadSchemaType.KEYWORD,
        "gpu_tags": models.PayloadSchemaType.KEYWORD,
        "weight_kg": models.PayloadSchemaType.FLOAT,
        "os_normalized": models.PayloadSchemaType.KEYWORD,
    }
    for field, schema in fields.items():
        client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema=schema,
            wait=True,
        )


def clean(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


if __name__ == "__main__":
    main()
