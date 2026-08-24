from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pyarrow.dataset as ds
from pyspark.ml.feature import HashingTF, MinHashLSH
from pyspark.sql import SparkSession, functions as F


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Detect and conservatively remove near-duplicate chunks with Spark MinHashLSH."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=project_root / "Notebook" / "Chunks.Perquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "Notebook" / "vector_db_artifacts" / "deduplicated_chunks",
    )
    parser.add_argument(
        "--pairs-output",
        type=Path,
        default=project_root / "Notebook" / "vector_db_artifacts" / "dedup_pairs",
    )
    parser.add_argument(
        "--groups-output",
        type=Path,
        default=project_root / "Notebook" / "vector_db_artifacts" / "dedup_groups",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=project_root / "Notebook" / "vector_db_artifacts" / "dedup_metrics.json",
    )
    parser.add_argument("--jaccard-distance", type=float, default=0.20)
    parser.add_argument("--num-hash-tables", type=int, default=32)
    parser.add_argument("--num-features", type=int, default=1 << 18)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spark = (
        SparkSession.builder.appName("LaptopChunkMinHashLSH")
        .config("spark.driver.memory", "4g")
        .config("spark.executor.memory", "4g")
        .config("spark.sql.shuffle.partitions", "32")
        .getOrCreate()
    )
    try:
        parquet_sources = (
            [str(path) for path in sorted(args.input.glob("*.parquet"))]
            if args.input.is_dir()
            else [str(args.input)]
        )
        if not parquet_sources:
            raise FileNotFoundError(f"No Parquet files found in {args.input}")
        source = (
            ds.dataset(parquet_sources, format="parquet")
            .to_table()
            .to_pandas()
            .sort_values("chunk_id")
            .reset_index(drop=True)
        )
        required = {"laptop_id", "chunk_id", "chunk_type", "chunk_text"}
        missing = sorted(required - set(source.columns))
        if missing:
            raise ValueError(f"Chunk input is missing columns: {missing}")
        if source["chunk_id"].duplicated().any():
            raise ValueError("chunk_id must be unique before stable IDs can be generated.")
        source.insert(0, "vector_id", np.arange(len(source), dtype=np.int64))
        source["_tokens"] = source.apply(
            lambda row: [
                *re.sub(r"[^a-z0-9]+", " ", str(row["chunk_text"] or "").lower()).split(),
                f"__laptop_{int(row['laptop_id'])}",
                f"__type_{row['chunk_type']}",
            ],
            axis=1,
        )
        chunks = spark.createDataFrame(
            source[["vector_id", "laptop_id", "chunk_type", "_tokens"]]
        )
        prepared = chunks.filter(F.size("_tokens") > 2)
        hashing = HashingTF(
            inputCol="_tokens",
            outputCol="_features",
            binary=True,
            numFeatures=args.num_features,
        )
        vectors = hashing.transform(prepared).select(
            "vector_id", "laptop_id", "chunk_type", "_features"
        )
        lsh = MinHashLSH(
            inputCol="_features",
            outputCol="_hashes",
            numHashTables=args.num_hash_tables,
            seed=args.seed,
        ).fit(vectors)
        pairs = (
            lsh.approxSimilarityJoin(
                vectors.alias("left"),
                vectors.alias("right"),
                args.jaccard_distance,
                distCol="jaccard_distance",
            )
            .filter(F.col("datasetA.vector_id") < F.col("datasetB.vector_id"))
            .filter(F.col("datasetA.laptop_id") == F.col("datasetB.laptop_id"))
            .filter(F.col("datasetA.chunk_type") == F.col("datasetB.chunk_type"))
            .select(
                F.col("datasetA.vector_id").cast("long").alias("left_vector_id"),
                F.col("datasetB.vector_id").cast("long").alias("right_vector_id"),
                F.col("datasetA.laptop_id").cast("long").alias("laptop_id"),
                F.col("datasetA.chunk_type").alias("chunk_type"),
                F.col("jaccard_distance").cast("double"),
            )
        )
        # Only remove near-duplicates belonging to the same laptop and chunk type.
        # Similar review text across different laptops remains independently searchable.
        pair_rows = pairs.select("left_vector_id", "right_vector_id").collect()
        parent: dict[int, int] = {}

        def find(value: int) -> int:
            parent.setdefault(value, value)
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: int, right: int) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[max(left_root, right_root)] = min(left_root, right_root)

        for row in pair_rows:
            union(int(row.left_vector_id), int(row.right_vector_id))

        aliases = []
        for value in sorted(parent):
            canonical = find(value)
            if value != canonical:
                aliases.append((value, canonical))
        canonical_ids = {canonical for _, canonical in aliases}
        duplicate_ids = {duplicate for duplicate, _ in aliases}

        for path in (args.output, args.pairs_output, args.groups_output):
            path.parent.mkdir(parents=True, exist_ok=True)
        deduplicated_frame = source[~source["vector_id"].isin(sorted(duplicate_ids))].drop(
            columns=["vector_id", "_tokens"]
        )
        deduplicated_frame.to_parquet(args.output, index=False)
        pd.DataFrame(
            [row.asDict() for row in pairs.collect()]
        ).to_parquet(args.pairs_output, index=False)
        pd.DataFrame(aliases, columns=["duplicate_vector_id", "canonical_vector_id"]).to_parquet(
            args.groups_output, index=False
        )

        input_count = len(source)
        output_count = len(deduplicated_frame)
        metrics = {
            "input_rows": input_count,
            "output_rows": output_count,
            "removed_rows": input_count - output_count,
            "reduction_fraction": round((input_count - output_count) / max(input_count, 1), 6),
            "candidate_pairs_same_laptop_chunk_type": len(pair_rows),
            "duplicate_rows_removed": len(duplicate_ids),
            "canonical_groups": len(canonical_ids),
            "jaccard_distance_threshold": args.jaccard_distance,
            "num_hash_tables": args.num_hash_tables,
            "num_features": args.num_features,
            "seed": args.seed,
            "scope": "same laptop_id and chunk_type only",
        }
        args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(json.dumps(metrics, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
