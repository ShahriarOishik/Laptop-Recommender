from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select per-index outlier thresholds from labeled scores.")
    parser.add_argument("scores", type=Path, help="JSONL with index, top_similarity, and in_domain fields")
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/index_manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/calibrated_thresholds.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = [json.loads(line) for line in args.scores.read_text(encoding="utf-8").splitlines() if line.strip()]
    thresholds = {}
    for index in sorted({row["index"] for row in rows}):
        index_rows = [row for row in rows if row["index"] == index]
        candidates = sorted({float(row["top_similarity"]) for row in index_rows})
        best = None
        for threshold in candidates:
            true_positive = sum(row["in_domain"] and row["top_similarity"] >= threshold for row in index_rows)
            false_positive = sum(not row["in_domain"] and row["top_similarity"] >= threshold for row in index_rows)
            false_negative = sum(row["in_domain"] and row["top_similarity"] < threshold for row in index_rows)
            precision = true_positive / max(true_positive + false_positive, 1)
            recall = true_positive / max(true_positive + false_negative, 1)
            f1 = 2 * precision * recall / max(precision + recall, np.finfo(float).eps)
            if best is None or f1 > best[0]:
                best = (f1, threshold, precision, recall)
        thresholds[index] = {
            "threshold": best[1],
            "f1": round(best[0], 4),
            "precision": round(best[2], 4),
            "recall": round(best[3], 4),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(thresholds, indent=2), encoding="utf-8")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest["similarity_thresholds"] = {
        index: values["threshold"] for index, values in thresholds.items()
    }
    manifest["threshold_status"] = "calibrated"
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
