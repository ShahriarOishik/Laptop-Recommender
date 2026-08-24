from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from build_artifacts import build_range_statistics


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Update range statistics in an existing artifact manifest.")
    parser.add_argument("--records", type=Path, default=project_root / "artifacts" / "qdrant_records.parquet")
    parser.add_argument("--manifest", type=Path, default=project_root / "artifacts" / "index_manifest.json")
    args = parser.parse_args()

    records = pd.read_parquet(args.records, columns=["laptop_id", "price_usd", "weight_kg"])
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest["range_statistics"] = build_range_statistics(records)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["range_statistics"], indent=2))


if __name__ == "__main__":
    main()
