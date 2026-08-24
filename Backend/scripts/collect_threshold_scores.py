from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


INDEXES = ("flat", "ivf_flat", "pq", "ivf_pq", "hnsw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect per-index outlier scores from /retrieve.")
    parser.add_argument("in_domain", type=Path)
    parser.add_argument("outliers", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    parser.add_argument("--output", type=Path, default=Path("evaluation/threshold_scores.jsonl"))
    parser.add_argument("--in-process", action="store_true")
    return parser.parse_args()


def load_queries(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    args = parse_args()
    in_domain = load_queries(args.in_domain)
    outliers = load_queries(args.outliers)
    rows = []
    if args.in_process:
        from fastapi.testclient import TestClient

        from app.main import create_app

        client_context = TestClient(create_app())
    else:
        client_context = httpx.Client(base_url=args.base_url, timeout=180)
    with client_context as client:
        for index in INDEXES:
            for row, in_domain_flag in [
                *[(item, True) for item in in_domain],
                *[(item, False) for item in outliers],
            ]:
                message = row.get("query") or row.get("message")
                payload = {"index_type": index, "filters": row.get("filters", {})}
                if message:
                    payload["message"] = message
                response = client.post("/retrieve", json=payload)
                response.raise_for_status()
                result = response.json()
                rows.append(
                    {
                        "index": index,
                        "query": message or "",
                        "top_similarity": result.get("top_similarity"),
                        "in_domain": in_domain_flag,
                    }
                )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    print(args.output)


if __name__ == "__main__":
    main()
