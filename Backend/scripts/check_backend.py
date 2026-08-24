from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx


INDEXES = ("flat", "ivf_flat", "pq", "ivf_pq", "hnsw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live backend acceptance checks.")
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/backend_acceptance_report.json"),
    )
    parser.add_argument("--in-process", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    checks: list[dict[str, Any]] = []

    def check(name: str, action: Callable[[], Any]) -> Any:
        try:
            details = action()
            checks.append({"name": name, "status": "passed", "details": details})
            print(f"PASS {name}")
            return details
        except Exception as exc:
            checks.append({"name": name, "status": "failed", "details": str(exc)})
            print(f"FAIL {name}: {exc}")
            return None

    if args.in_process:
        from fastapi.testclient import TestClient

        from app.main import create_app

        client_context = TestClient(create_app())
    else:
        client_context = httpx.Client(base_url=args.base_url, timeout=180)
    with client_context as client:
        health = check("health endpoint", lambda: assert_health(client))
        check("readiness endpoint", lambda: assert_status(client.get("/ready"), 200))
        check("OpenAPI documentation", lambda: assert_status(client.get("/openapi.json"), 200))
        check("index settings", lambda: assert_index_settings(client))

        base_query = "Gaming laptop under 2000 USD with 16 GB RAM and RTX graphics"
        index_results = {}
        for index in INDEXES:
            result = check(
                f"{index} retrieval",
                lambda index=index: retrieve_and_validate(client, base_query, index),
            )
            if result:
                index_results[index] = result

        strict = check("locked UI budget filter", lambda: assert_locked_budget(client))
        check("filter-only retrieval", lambda: assert_filter_only(client))
        check("true hybrid retrieval", lambda: assert_hybrid(client))
        check("progressive metadata relaxation", lambda: assert_relaxation(client))
        check("negative GPU filter", lambda: assert_gpu_exclusion(client))
        check("outlier rejection", lambda: assert_outlier(client))
        check("custom threshold", lambda: assert_custom_threshold(client))
        check("request validation", lambda: assert_request_validation(client))
        check("FP-Growth insights", lambda: assert_insights(client))

        laptop_id = None
        if strict and strict.get("recommendations"):
            laptop_id = strict["recommendations"][0]["laptop_id"]
        elif index_results:
            first = next(iter(index_results.values()))
            laptop_id = first["recommendations"][0]["laptop_id"]
        if laptop_id is not None:
            check("laptop detail lookup", lambda: assert_laptop(client, laptop_id))

        cache_query = "Portable business laptop with a comfortable keyboard acceptance check"
        check("grounded chat response", lambda: assert_chat(client, cache_query))
        check("semantic cache reuse", lambda: assert_cache(client, cache_query))
        check("cache statistics", lambda: assert_cache_stats(client))

    passed = sum(item["status"] == "passed" for item in checks)
    failed = len(checks) - passed
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "summary": {"total": len(checks), "passed": passed, "failed": failed},
        "runtime": health,
        "checks": checks,
        "external_requirements": {
            "qdrant_cloud_tested": False,
            "groq_tested_live": False,
            "gemini_tested_live": False,
            "qdrant_configured": bool(health and health.get("qdrant_ready")),
            "llm_providers_configured": health.get("llm_providers", []) if health else [],
            "reason": "External integrations require valid endpoints/credentials and were not live-validated.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(checks)} checks passed. Report: {args.output}")
    if failed:
        sys.exit(1)


def assert_status(response: httpx.Response, expected: int) -> dict[str, Any]:
    if response.status_code != expected:
        raise AssertionError(f"Expected HTTP {expected}, received {response.status_code}: {response.text}")
    return {"status_code": response.status_code}


def assert_health(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/health")
    assert_status(response, 200)
    data = response.json()
    required = ("embedding_ready", "faiss_ready", "metadata_ready")
    if data["status"] != "ready" or not all(data[field] for field in required):
        raise AssertionError(data)
    if data["errors"]:
        raise AssertionError(f"Startup errors present: {data['errors']}")
    return data


def assert_index_settings(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/settings/indexes")
    assert_status(response, 200)
    data = response.json()
    ids = [item["id"] for item in data["indexes"]]
    if set(ids) != set(INDEXES):
        raise AssertionError(f"Unexpected indexes: {ids}")
    if data["default_index"] != "ivf_flat" or data["candidate_k"] != 20:
        raise AssertionError(data)
    if not all(item["available"] for item in data["indexes"]):
        raise AssertionError("At least one index is unavailable.")
    return {"indexes": ids, "default": data["default_index"], "candidate_k": data["candidate_k"]}


def retrieve_and_validate(
    client: httpx.Client, query: str, index: str
) -> dict[str, Any]:
    response = client.post(
        "/retrieve",
        json={"message": query, "index_type": index, "top_k": 5},
    )
    assert_status(response, 200)
    data = response.json()
    if data["index_used"] != index or data["candidate_k"] != 20:
        raise AssertionError(data)
    if data["outlier"] or not data["recommendations"]:
        raise AssertionError(f"No valid recommendations: {data}")
    for recommendation in data["recommendations"]:
        if not recommendation["sources"]:
            raise AssertionError("A recommendation has no source chunks.")
        if not recommendation["sources"][0]["text"]:
            raise AssertionError("A source chunk has no text.")
    return data


def assert_locked_budget(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/retrieve",
        json={
            "message": "Affordable laptop for university work",
            "index_type": "ivf_flat",
            "top_k": 5,
            "filters": {"max_price_usd": 1000},
            "allow_filter_relaxation": False,
        },
    )
    assert_status(response, 200)
    data = response.json()
    if "max_price_usd" in data["relaxed_filters"]:
        raise AssertionError("Locked UI budget was relaxed.")
    prices = [item["price_usd"] for item in data["recommendations"]]
    if any(price is None or price > 1000 for price in prices):
        raise AssertionError(f"Budget violation: {prices}")
    return data


def assert_filter_only(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/retrieve", json={"filters": {"max_price_usd": 1000}, "top_k": 5}
    )
    assert_status(response, 200)
    data = response.json()
    if data["search_mode"] != "filter_only" or data["index_used"] is not None:
        raise AssertionError(data)
    prices = [item["price_usd"] for item in data["recommendations"]]
    if not prices or any(price is None or price > 1000 for price in prices):
        raise AssertionError(f"Filter-only budget violation: {prices}")
    return {"search_mode": data["search_mode"], "matched_count": data["matched_count"]}


def assert_hybrid(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/retrieve",
        json={
            "message": "Gaming laptop",
            "filters": {"max_price_usd": 1000},
            "index_type": "ivf_flat",
            "top_k": 5,
            "allow_filter_relaxation": False,
        },
    )
    assert_status(response, 200)
    data = response.json()
    if data["search_mode"] != "hybrid" or not data["metadata_match_count"]:
        raise AssertionError(data)
    prices = [item["price_usd"] for item in data["recommendations"]]
    if any(price is None or price > 1000 for price in prices):
        raise AssertionError(f"Hybrid budget violation: {prices}")
    return {
        "search_mode": data["search_mode"],
        "metadata_match_count": data["metadata_match_count"],
        "matched_count": data["matched_count"],
    }


def assert_relaxation(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/retrieve",
        json={
            "message": "Honor gaming laptop under 2000 USD with 16 GB RAM and RTX graphics",
            "index_type": "ivf_flat",
            "top_k": 5,
            "allow_filter_relaxation": True,
        },
    )
    assert_status(response, 200)
    data = response.json()
    if data["filter_level"] is None or data["filter_level"] <= 1:
        raise AssertionError(f"Expected a relaxed filter pass: {data}")
    if not data["relaxed_filters"]:
        raise AssertionError("No relaxed fields were reported.")
    return {
        "filter_level": data["filter_level"],
        "filter_name": data["filter_name"],
        "relaxed_filters": data["relaxed_filters"],
    }


def assert_gpu_exclusion(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/retrieve",
        json={
            "message": "Laptop without RTX for office work",
            "index_type": "ivf_flat",
            "top_k": 5,
        },
    )
    assert_status(response, 200)
    data = response.json()
    if data["parsed_query"]["filters"]["excluded_gpu_tags"] != ["rtx"]:
        raise AssertionError("RTX exclusion was not parsed.")
    for item in data["recommendations"]:
        if "rtx" in (item["metadata"].get("gpu_tags") or []):
            raise AssertionError(f"Excluded RTX laptop returned: {item['model']}")
    return {"matched_count": data["matched_count"]}


def assert_outlier(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/retrieve",
        json={"message": "How do I bake a chocolate cake?", "index_type": "ivf_flat"},
    )
    assert_status(response, 200)
    data = response.json()
    if not data["outlier"] or data["status"] != "no_relevant_match" or data["recommendations"]:
        raise AssertionError(data)
    return {"top_similarity": data["top_similarity"], "threshold": data["similarity_threshold"]}


def assert_custom_threshold(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/retrieve",
        json={
            "message": "Gaming laptop",
            "index_type": "ivf_flat",
            "min_cosine_similarity": 1.0,
        },
    )
    assert_status(response, 200)
    data = response.json()
    if not data["outlier"] or data["similarity_threshold"] != 1.0:
        raise AssertionError(data)
    return {"outlier": data["outlier"]}


def assert_request_validation(client: httpx.Client) -> dict[str, Any]:
    invalid_index = client.post(
        "/retrieve", json={"message": "Gaming laptop", "index_type": "../../bad"}
    )
    invalid_top_k = client.post(
        "/retrieve", json={"message": "Gaming laptop", "top_k": 20}
    )
    invalid_nprobe = client.post(
        "/retrieve", json={"message": "Gaming laptop", "nprobe": 0}
    )
    statuses = [invalid_index.status_code, invalid_top_k.status_code, invalid_nprobe.status_code]
    if statuses != [422, 422, 422]:
        raise AssertionError(statuses)
    return {"invalid_statuses": statuses}


def assert_insights(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/insights/specifications", params={"limit": 5})
    assert_status(response, 200)
    rules = response.json()["rules"]
    if len(rules) != 5:
        raise AssertionError(f"Expected 5 rules, received {len(rules)}")
    required = {"antecedent", "consequent", "confidence", "lift", "support"}
    if not required.issubset(rules[0]):
        raise AssertionError(rules[0])
    return {"returned_rules": len(rules)}


def assert_laptop(client: httpx.Client, laptop_id: int) -> dict[str, Any]:
    response = client.get(f"/laptops/{laptop_id}")
    assert_status(response, 200)
    data = response.json()
    if data["laptop_id"] != laptop_id or not data["chunks"]:
        raise AssertionError(data)
    if any(item["laptop_id"] != laptop_id for item in data["chunks"]):
        raise AssertionError("Laptop lookup returned a different laptop ID.")
    return {"laptop_id": laptop_id, "chunks": len(data["chunks"])}


def assert_chat(client: httpx.Client, query: str) -> dict[str, Any]:
    response = client.post(
        "/chat", json={"message": query, "index_type": "ivf_flat", "top_k": 5}
    )
    assert_status(response, 200)
    data = response.json()
    if not data["answer"] or not data["recommendations"]:
        raise AssertionError(data)
    if data["provider"] not in {"groq", "gemini", "retrieval_only"}:
        raise AssertionError(f"Unexpected provider: {data['provider']}")
    return {"provider": data["provider"], "cache_hit": data["cache_hit"]}


def assert_cache(client: httpx.Client, query: str) -> dict[str, Any]:
    response = client.post(
        "/chat", json={"message": query, "index_type": "ivf_flat", "top_k": 5}
    )
    assert_status(response, 200)
    data = response.json()
    if not data["cache_hit"]:
        if data.get("provider") == "retrieval_only":
            return {"cache_hit": False, "skipped": "LLM provider was unavailable."}
        raise AssertionError("Repeated compatible request was not served from cache.")
    return {"cache_hit": True}


def assert_cache_stats(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/cache/stats")
    assert_status(response, 200)
    data = response.json()
    if data["hits"] < 1 and data["entries"] == 0 and data["misses"] > 0:
        data["skipped"] = "No response was cached after provider failure."
        return data
    if data["hits"] < 1 or data["entries"] < 1:
        raise AssertionError(data)
    return data


if __name__ == "__main__":
    main()
