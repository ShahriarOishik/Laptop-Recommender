from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture grounded /chat answers for human review.")
    parser.add_argument("queries", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    parser.add_argument("--output", type=Path, default=Path("evaluation/qualitative_answers.jsonl"))
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--in-process", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queries = [
        json.loads(line)
        for line in args.queries.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][: args.limit]
    rows = []
    if args.in_process:
        from fastapi.testclient import TestClient

        from app.main import create_app

        client_context = TestClient(create_app())
    else:
        client_context = httpx.Client(base_url=args.base_url, timeout=180)
    with client_context as client:
        for row in queries:
            message = row.get("query") or row.get("message")
            payload = {"filters": row.get("filters", {})}
            if message:
                payload["message"] = message
            response = client.post("/chat", json=payload)
            record = {
                "query": message or "",
                "filters": row.get("filters", {}),
                "http_status": response.status_code,
            }
            if response.is_success:
                result = response.json()
                record.update(
                    {
                        "answer": result.get("answer", ""),
                        "provider": result.get("provider"),
                        "search_mode": result.get("search_mode"),
                        "recommendations": result.get("recommendations", []),
                        "relaxed_filters": result.get("relaxed_filters", []),
                        "retrieval_latency_ms": result.get("retrieval_latency_ms"),
                        "cache_hit": result.get("cache_hit", False),
                    }
                )
            else:
                record["error"] = response.text
            rows.append(record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
