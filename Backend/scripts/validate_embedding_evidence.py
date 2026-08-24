from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Validate embedding Parquet evidence.")
    parser.add_argument(
        "--records",
        type=Path,
        default=project_root / "Backend" / "artifacts" / "qdrant_records.parquet",
    )
    parser.add_argument(
        "--notebook",
        type=Path,
        default=project_root / "Notebook" / "vector_db_ann_retrieval.ipynb",
    )
    parser.add_argument(
        "--execution-mode",
        choices=("pandas_udf", "driver_batch", "unknown"),
        default="unknown",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "Backend" / "evaluation" / "embedding_evidence.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    table = pq.read_table(args.records, columns=["vector_id", "chunk_id", "embedding"])
    embeddings = table.column("embedding").to_pylist()
    null_count = sum(value is None for value in embeddings)
    dimensions = sorted({len(value) for value in embeddings if value is not None})
    vectors = (
        np.asarray([value for value in embeddings if value is not None], dtype=np.float32)
        if null_count < len(embeddings)
        else np.empty((0, 0), dtype=np.float32)
    )
    norms = np.linalg.norm(vectors, axis=1) if len(vectors) else np.array([], dtype=np.float32)
    notebook_text = args.notebook.read_text(encoding="utf-8")
    evidence = {
        "records": str(args.records),
        "rows": len(embeddings),
        "null_embeddings": null_count,
        "dimensions": dimensions,
        "norm_min": round(float(norms.min()), 6) if len(norms) else None,
        "norm_max": round(float(norms.max()), 6) if len(norms) else None,
        "norm_mean": round(float(norms.mean()), 6) if len(norms) else None,
        "pandas_udf_source_present": "@pandas_udf" in notebook_text,
        "execution_mode": args.execution_mode,
        "distributed_execution_verified": args.execution_mode == "pandas_udf",
        "platform": platform.platform(),
        "note": (
            "The artifact is numerically valid, but distributed pandas_udf execution is only "
            "verified when --execution-mode pandas_udf is supplied from a Linux/WSL/Colab run."
        ),
    }
    if null_count or dimensions != [768] or not len(norms) or not np.allclose(norms, 1.0, atol=1e-3):
        raise ValueError(f"Embedding validation failed: {evidence}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
