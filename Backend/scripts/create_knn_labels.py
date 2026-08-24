from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create reproducible KNN-derived relevance labels for evaluation."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("evaluation/queries.annotation.template.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/queries.jsonl"),
    )
    parser.add_argument("--top-k", type=int, default=5)
    return parser.parse_args()


def load_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def semantic_fallback_query(query: str) -> str:
    text = query
    text = re.sub(
        r"\b(?:under|below|less than|at most|no more than|up to|over|above|more than|at least|between|from)\b[^,.;]*?(?:\$?\d[\d,.]*\s*(?:k|usd|dollars?|gb|tb|kg)?)",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b\d+(?:\.\d+)?\s*(?:gb|tb|kg|usd|hz)\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:rtx|gtx|radeon|arc|rx)\s*\d*\w*\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:must have|required|only|non-negotiable|with|at least)\b", " ", text, flags=re.I)
    text = " ".join(text.split())
    return text or "laptop recommendation"


def main() -> None:
    args = parse_args()
    rows = load_rows(args.input)
    if len(rows) < 30:
        raise ValueError("At least 30 queries are required for evaluation.")

    labeled: list[dict] = []
    with TestClient(create_app()) as client:
        for row in rows:
            query = row.get("query") or row.get("message") or ""
            payload: dict = {
                "index_type": "flat",
                "top_k": args.top_k,
                "filters": row.get("filters", {}),
            }
            if query.strip():
                payload["message"] = query
            response = client.post("/retrieve", json=payload)
            response.raise_for_status()
            result = response.json()
            recommendations = result.get("recommendations", [])
            if not recommendations:
                fallback_query = semantic_fallback_query(query)
                fallback = client.post(
                    "/retrieve",
                    json={
                        "message": fallback_query,
                        "index_type": "flat",
                        "top_k": args.top_k,
                        "filters": row.get("filters", {}),
                    },
                )
                fallback.raise_for_status()
                result = fallback.json()
                recommendations = result.get("recommendations", [])
                if not recommendations:
                    raise ValueError(f"KNN returned no labels for query: {query}")
            knn_query = query if result.get("parsed_query", {}).get("original_query") == query else semantic_fallback_query(query)
            labeled.append(
                {
                    "query": query,
                    "filters": row.get("filters", {}),
                    "relevant_laptop_ids": [
                        int(item["laptop_id"]) for item in recommendations
                    ],
                    "knn_scores": [float(item["score"]) for item in recommendations],
                    "knn_query": knn_query,
                    "label_source": "flat_exact_knn_pseudo_label",
                    "label_warning": (
                        "Automatically generated from exact Flat KNN; these are pseudo-labels, "
                        "not independent human relevance judgments."
                    ),
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in labeled),
        encoding="utf-8",
    )
    print(f"Wrote {len(labeled)} KNN-labeled queries to {args.output}")


if __name__ == "__main__":
    main()
