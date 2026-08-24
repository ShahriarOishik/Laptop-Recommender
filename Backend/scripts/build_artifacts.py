from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


INDEX_NAMES = ("flat", "ivf_flat", "pq", "ivf_pq", "hnsw")


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Build deployable FAISS and Qdrant artifacts.")
    parser.add_argument("--chunks", type=Path, default=project_root / "Notebook" / "Chunks.Perquet")
    parser.add_argument("--catalog", type=Path, default=project_root / "Dataset" / "imputed_dataset.csv")
    parser.add_argument("--output", type=Path, default=project_root / "Backend" / "artifacts")
    parser.add_argument("--indexes", nargs="+", choices=INDEX_NAMES, default=list(INDEX_NAMES))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--training-fraction", type=float, default=0.70)
    parser.add_argument("--nlist", type=int)
    parser.add_argument("--pq-m", type=int, default=96)
    parser.add_argument("--hnsw-m", type=int, default=32)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for stale_index in args.output.glob("*.index"):
        stale_index.unlink()
    (args.output / "index_manifest.json").unlink(missing_ok=True)
    if args.chunks.is_dir():
        parquet_files = sorted(args.chunks.glob("*.parquet"))
        if not parquet_files:
            raise FileNotFoundError(f"No Parquet data files found in {args.chunks}.")
        chunks = pq.read_table([str(path) for path in parquet_files]).to_pandas()
    else:
        chunks = pd.read_parquet(args.chunks)
    chunks = chunks.sort_values("chunk_id").reset_index(drop=True)
    if chunks.empty:
        raise ValueError("Chunk dataset is empty.")
    if chunks["chunk_id"].duplicated().any():
        raise ValueError("chunk_id must be unique before stable IDs can be generated.")

    chunks.insert(0, "vector_id", np.arange(len(chunks), dtype=np.int64))
    vectors = np.ascontiguousarray(np.vstack(chunks["embedding"].values), dtype=np.float32)
    if vectors.shape[1] != 768:
        raise ValueError(f"Expected 768-dimensional BGE vectors, found {vectors.shape[1]}.")
    faiss.normalize_L2(vectors)
    chunks["embedding"] = list(vectors)

    records = enrich_metadata(chunks, args.catalog)
    records.to_parquet(args.output / "qdrant_records.parquet", index=False)
    records.drop(columns=["embedding"]).drop_duplicates("laptop_id").to_parquet(
        args.output / "laptop_metadata.parquet", index=False
    )
    records[["vector_id", "chunk_id", "laptop_id"]].to_parquet(
        args.output / "vector_id_mapping.parquet", index=False
    )

    rng = np.random.default_rng(args.seed)
    train_size = max(1, min(len(vectors), int(len(vectors) * args.training_fraction)))
    train_ids = rng.choice(len(vectors), size=train_size, replace=False)
    training_vectors = np.ascontiguousarray(vectors[train_ids])
    nlist = args.nlist or max(1, int(4 * math.sqrt(len(vectors))))
    laptop_vectors, laptop_ids = build_laptop_vectors(records)
    laptop_training_size = max(1, min(len(laptop_vectors), int(len(laptop_vectors) * args.training_fraction)))
    laptop_training_vectors = np.ascontiguousarray(laptop_vectors[:laptop_training_size])
    laptop_nlist = min(nlist, max(1, int(4 * math.sqrt(len(laptop_vectors)))))

    manifest = {
        "model": "BAAI/bge-base-en-v1.5",
        "dimension": 768,
        "normalized": True,
        "metric": "inner_product",
        "vector_count": len(vectors),
        "default_index": "ivf_flat",
        "candidate_k": 20,
        "ivf_nlist": nlist,
        "ivf_nprobe": 64,
        "pq_m": args.pq_m,
        "hnsw_m": args.hnsw_m,
        "hnsw_ef_search": 256,
        "similarity_thresholds": {
            "flat": 0.60,
            "ivf_flat": 0.60,
            "pq": 0.56,
            "ivf_pq": 0.56,
            "hnsw": 0.60,
        },
        "threshold_status": "initial values; calibrate with labeled in-domain and outlier queries",
        "range_statistics": build_range_statistics(records),
        "laptop_vector_count": len(laptop_vectors),
        "indexes": {},
        "laptop_indexes": {},
    }
    vector_ids = records["vector_id"].to_numpy(dtype=np.int64)
    for name in args.indexes:
        started = time.perf_counter()
        index, train_seconds, build_seconds = build_index(
            name,
            vectors,
            vector_ids,
            training_vectors,
            nlist,
            args.pq_m,
            args.hnsw_m,
        )
        output_path = args.output / f"{name}.index"
        faiss.write_index(index, str(output_path))
        manifest["indexes"][name] = {
            "file": output_path.name,
            "metric": "inner_product",
            "train_seconds": round(train_seconds, 3),
            "build_seconds": round(build_seconds, 3),
            "total_seconds": round(time.perf_counter() - started, 3),
            "size_bytes": output_path.stat().st_size,
            "ntotal": int(index.ntotal),
        }
        print(f"built {name}: {index.ntotal} vectors, {output_path.stat().st_size / 1e6:.2f} MB")

    for name in args.indexes:
        started = time.perf_counter()
        index, train_seconds, build_seconds = build_index(
            name,
            laptop_vectors,
            laptop_ids,
            laptop_training_vectors,
            laptop_nlist,
            args.pq_m,
            args.hnsw_m,
        )
        output_path = args.output / f"laptop_{name}.index"
        faiss.write_index(index, str(output_path))
        manifest["laptop_indexes"][name] = {
            "file": output_path.name,
            "metric": "inner_product",
            "train_seconds": round(train_seconds, 3),
            "build_seconds": round(build_seconds, 3),
            "total_seconds": round(time.perf_counter() - started, 3),
            "size_bytes": output_path.stat().st_size,
            "ntotal": int(index.ntotal),
        }
        print(f"built laptop_{name}: {index.ntotal} vectors, {output_path.stat().st_size / 1e6:.2f} MB")

    with (args.output / "index_manifest.json").open("w", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2)
    print(f"artifacts written to {args.output}")


def build_index(
    name: str,
    vectors: np.ndarray,
    vector_ids: np.ndarray,
    training_vectors: np.ndarray,
    nlist: int,
    pq_m: int,
    hnsw_m: int,
):
    dimension = vectors.shape[1]
    if dimension % pq_m != 0:
        raise ValueError(f"PQ m={pq_m} must divide embedding dimension {dimension}.")

    if name == "flat":
        base = faiss.IndexFlatIP(dimension)
    elif name == "ivf_flat":
        base = faiss.IndexIVFFlat(
            faiss.IndexFlatIP(dimension), dimension, nlist, faiss.METRIC_INNER_PRODUCT
        )
    elif name == "pq":
        base = faiss.IndexPQ(dimension, pq_m, 8, faiss.METRIC_INNER_PRODUCT)
    elif name == "ivf_pq":
        base = faiss.IndexIVFPQ(
            faiss.IndexFlatIP(dimension),
            dimension,
            nlist,
            pq_m,
            8,
            faiss.METRIC_INNER_PRODUCT,
        )
    elif name == "hnsw":
        base = faiss.IndexHNSWFlat(dimension, hnsw_m, faiss.METRIC_INNER_PRODUCT)
        base.hnsw.efConstruction = 200
        base.hnsw.efSearch = 256
    else:
        raise ValueError(f"Unsupported index: {name}")

    train_started = time.perf_counter()
    if not base.is_trained:
        base.train(training_vectors)
    train_seconds = time.perf_counter() - train_started
    index = faiss.IndexIDMap2(base)
    build_started = time.perf_counter()
    index.add_with_ids(vectors, vector_ids)
    build_seconds = time.perf_counter() - build_started
    if index.ntotal != len(vectors):
        raise ValueError(f"Index {name} contains {index.ntotal} vectors; expected {len(vectors)}.")
    if name in {"ivf_flat", "ivf_pq"}:
        # Required for exact constrained reconstruction during hybrid search.
        base.make_direct_map()
    return index, train_seconds, build_seconds


def enrich_metadata(chunks: pd.DataFrame, catalog_path: Path) -> pd.DataFrame:
    catalog_columns = [
        "id", "cpu_full", "gpu_full", "ram_full", "storage", "display_full",
        "battery", "weight_kg", "os", "connectivity", "summary", "pros", "cons",
        "ram_capacity_gb", "display_size_inches", "display_resolution_width",
        "display_resolution_height", "price_usd",
    ]
    catalog = pd.read_csv(catalog_path, usecols=catalog_columns, low_memory=False).rename(
        columns={"id": "laptop_id", "price_usd": "catalog_price_usd"}
    )
    records = chunks.merge(catalog, on="laptop_id", how="left", validate="many_to_one")
    records["price_usd"] = records["price_value"].fillna(records["catalog_price_usd"])
    records["brand_normalized"] = records["brand"].fillna("").str.strip().str.lower()
    records["os_normalized"] = records["os"].fillna("").map(normalize_os)
    records["storage_capacity_gb"] = records["storage"].map(first_capacity_gb)
    records["storage_types"] = records["storage"].map(storage_types)
    records["gpu_tags"] = records["gpu_full"].map(gpu_tags)
    records["vram_capacity_gb"] = records["gpu_full"].map(vram_capacity_gb)
    records = records.drop(columns=["catalog_price_usd", "price_value", "price_currency"])
    return records


def build_laptop_vectors(records: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    grouped = records.groupby("laptop_id", sort=True)
    laptop_ids = grouped.size().index.to_numpy(dtype=np.int64)
    vectors = np.ascontiguousarray(
        np.vstack(
            grouped["embedding"].apply(
                lambda values: np.mean(np.vstack(values), axis=0)
            ).values
        ),
        dtype=np.float32,
    )
    faiss.normalize_L2(vectors)
    return vectors, laptop_ids


def build_range_statistics(records: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Persist robust laptop-level ranges instead of chunk-weighted statistics."""
    laptop_values = records.groupby("laptop_id", as_index=False).agg(
        price_usd=("price_usd", "median"),
        weight_kg=("weight_kg", "median"),
    )
    statistics: dict[str, dict[str, float]] = {}
    for field in ("price_usd", "weight_kg"):
        values = pd.to_numeric(laptop_values[field], errors="coerce").dropna()
        if values.empty:
            continue
        median = float(values.median())
        mad = float((values - median).abs().median())
        standard_deviation = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        robust_std = 1.4826 * mad if mad > 0 else standard_deviation
        statistics[field] = {
            "count": float(len(values)),
            "min": float(values.min()),
            "max": float(values.max()),
            "median": median,
            "std": standard_deviation,
            "robust_std": robust_std,
            "p10": float(values.quantile(0.10)),
            "p90": float(values.quantile(0.90)),
        }
    return statistics


def first_capacity_gb(value: object) -> float | None:
    text = str(value)
    capacities = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(TB|GB)", text, re.I):
        if re.search(r"\bfree\b", text[match.end():match.end() + 12], re.I):
            continue
        amount = float(match.group(1))
        capacities.append(amount * 1024 if match.group(2).lower() == "tb" else amount)
    if not capacities:
        return None
    return sum(capacities)


def vram_capacity_gb(value: object) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB)\s*VRAM\b", str(value), re.I)
    if not match:
        return None
    amount = float(match.group(1))
    return amount / 1024 if match.group(2).lower() == "mb" else amount


def storage_types(value: object) -> list[str]:
    lower = str(value).lower()
    return [kind for kind in ("nvme", "ssd", "hdd") if kind in lower]


def gpu_tags(value: object) -> list[str]:
    lower = str(value).lower()
    tags: list[str] = []
    for family in ("rtx", "gtx", "radeon", "rx", "arc", "integrated"):
        if re.search(rf"\b{family}\b", lower):
            tags.append(family)
    tags.extend(match.group(0).replace("  ", " ") for match in re.finditer(r"\b(?:rtx|gtx|rx)\s*\d{3,4}\w*\b", lower))
    return list(dict.fromkeys(tags))


def normalize_os(value: object) -> str:
    lower = str(value).lower()
    for system in ("windows", "linux", "macos", "chrome os"):
        if system in lower:
            return system
    return lower.strip()


if __name__ == "__main__":
    main()
