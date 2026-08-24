from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate candidate laptop IDs for human relevance labeling."
    )
    parser.add_argument("queries", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("evaluation/queries.labeling.jsonl")
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = [
        json.loads(line)
        for line in args.queries.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    labeled = []
    with TestClient(create_app()) as client:
        for row in rows:
            payload = {"filters": row.get("filters", {})}
            if row.get("query") or row.get("message"):
                payload["message"] = row.get("query") or row.get("message")
            response = client.post("/retrieve", json=payload)
            response.raise_for_status()
            result = response.json()
            labeled.append(
                {
                    "query": row.get("query") or row.get("message") or "",
                    "filters": row.get("filters", {}),
                    "candidate_laptop_ids": [
                        item["laptop_id"] for item in result.get("recommendations", [])
                    ],
                    "relevant_laptop_ids": [],
                    "labeling_note": "Replace relevant_laptop_ids after human review.",
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row) + "\n" for row in labeled), encoding="utf-8"
    )
    print(args.output)


if __name__ == "__main__":
    main()
