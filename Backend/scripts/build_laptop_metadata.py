from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build one metadata row per laptop.")
    parser.add_argument(
        "--records",
        type=Path,
        default=root / "artifacts" / "qdrant_records.parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "artifacts" / "laptop_metadata.parquet",
    )
    args = parser.parse_args()

    schema = pq.ParquetFile(args.records).schema_arrow
    columns = [name for name in schema.names if name != "embedding"]
    records = pd.read_parquet(args.records, columns=columns)
    laptops = records.sort_values(
        ["laptop_id", "chunk_type"],
        key=lambda values: values.map({"spec": 0}).fillna(1)
        if values.name == "chunk_type"
        else values,
    ).drop_duplicates("laptop_id")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    laptops.to_parquet(args.output, index=False)
    print(f"wrote {len(laptops)} laptops to {args.output}")


if __name__ == "__main__":
    main()
