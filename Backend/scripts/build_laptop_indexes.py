from __future__ import annotations

import json
import time
from pathlib import Path

import faiss
import numpy as np
import pandas as pd

from build_artifacts import build_index, build_laptop_vectors


INDEX_NAMES = ("flat", "ivf_flat", "pq", "ivf_pq", "hnsw")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    records = pd.read_parquet(artifacts / "qdrant_records.parquet", columns=["laptop_id", "embedding"])
    vectors, laptop_ids = build_laptop_vectors(records)
    training_size = max(1, min(len(vectors), int(len(vectors) * 0.7)))
    training_vectors = vectors[:training_size]
    nlist = min(1011, max(1, int(4 * np.sqrt(len(vectors)))))
    manifest = json.loads((artifacts / "index_manifest.json").read_text(encoding="utf-8"))
    manifest["laptop_vector_count"] = int(len(vectors))
    manifest["laptop_indexes"] = {}

    for name in INDEX_NAMES:
        started = time.perf_counter()
        index, train_seconds, build_seconds = build_index(
            name,
            vectors,
            laptop_ids,
            training_vectors,
            nlist,
            96,
            32,
        )
        output_path = artifacts / f"laptop_{name}.index"
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
        print(f"built laptop_{name}: {index.ntotal} vectors")

    (artifacts / "index_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
