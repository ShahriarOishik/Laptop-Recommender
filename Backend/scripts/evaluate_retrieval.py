from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import httpx


INDEXES = ("flat", "ivf_flat", "pq", "ivf_pq", "hnsw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the deployed retrieval endpoint.")
    parser.add_argument("queries", type=Path)
    parser.add_argument("--base-url", default="http://localhost:7860")
    parser.add_argument("--output", type=Path, default=Path("evaluation/results.csv"))
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--in-process", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queries = [json.loads(line) for line in args.queries.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(queries) < 30:
        raise ValueError("The course evaluation requires at least 30 hand-labeled queries.")
    if any(not row.get("relevant_laptop_ids") for row in queries):
        raise ValueError("Every query must include at least one hand-labeled relevant_laptop_id.")

    results = []
    if args.in_process:
        from fastapi.testclient import TestClient

        from app.main import create_app

        client_context = TestClient(create_app())
    else:
        client_context = httpx.Client(base_url=args.base_url, timeout=args.timeout)
    with client_context as client:
        for index in INDEXES:
            for row in queries:
                response = client.post(
                    "/retrieve",
                    json={
                        **(
                            {"message": row.get("query") or row.get("message")}
                            if row.get("query") or row.get("message")
                            else {}
                        ),
                        "index_type": index,
                        "top_k": 5,
                        "filters": row.get("filters", {}),
                    },
                )
                response.raise_for_status()
                payload = response.json()
                returned = [item["laptop_id"] for item in payload["recommendations"]]
                relevant = set(int(value) for value in row["relevant_laptop_ids"])
                result = {
                    "index": index,
                    "query": row.get("query") or row.get("message") or "",
                    "search_mode": payload.get("search_mode"),
                    "retrieval_latency_ms": payload["retrieval_latency_ms"],
                    "filter_level": payload.get("filter_level"),
                    "metadata_match_count": payload.get("metadata_match_count"),
                    "outlier": payload["outlier"],
                    "returned_count": len(returned),
                }
                for k in (1, 3, 5):
                    top = returned[:k]
                    matches = len(set(top) & relevant)
                    result[f"precision_at_{k}"] = matches / max(len(top), 1)
                    result[f"recall_at_{k}"] = matches / len(relevant)
                results.append(result)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(args.output)


if __name__ == "__main__":
    main()
