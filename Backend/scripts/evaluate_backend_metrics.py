from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
from dataclasses import replace
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


INDEXES = ("flat", "ivf_flat", "pq", "ivf_pq", "hnsw")
FINAL_K = (1, 3, 5)
CANDIDATE_K = (10, 20)


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Evaluate end-to-end retrieval quality and API behavior.")
    parser.add_argument(
        "--queries",
        type=Path,
        default=root / "evaluation" / "queries.jsonl",
    )
    parser.add_argument(
        "--outliers",
        type=Path,
        default=root / "evaluation" / "outliers.jsonl",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("description/backend_metrics_report.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("description/backend_metrics_report.md"),
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=0,
        help="Discard this many complete passes before collecting latency and quality metrics.",
    )
    parser.add_argument(
        "--label-source",
        default=None,
        help="Provenance for relevance judgments, for example 'human_judgment'.",
    )
    parser.add_argument(
        "--human-labels",
        action="store_true",
        help="Mark the supplied relevance judgments as independently human-labeled.",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Run through FastAPI in-process with the local Parquet metadata backend.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def request_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    index: str,
    row: dict[str, Any],
    is_outlier: bool,
) -> dict[str, Any]:
    query = row.get("query") or row.get("message") or ""
    body = {
        "message": query,
        "filters": row.get("filters", {}),
        "index_type": index,
        "top_k": 5,
        "include_diagnostics": True,
    }
    async with semaphore:
        started = asyncio.get_running_loop().time()
        try:
            response = await client.post("/retrieve", json=body)
            elapsed = (asyncio.get_running_loop().time() - started) * 1000
            response.raise_for_status()
            payload = response.json()
            return evaluate_response(index, query, row, payload, elapsed, is_outlier)
        except Exception as exc:
            return {
                "ok": False,
                "index": index,
                "query": query,
                "is_outlier": is_outlier,
                "latency_ms": round((asyncio.get_running_loop().time() - started) * 1000, 3),
                "error": str(exc),
            }


def evaluate_response(
    index: str,
    query: str,
    row: dict[str, Any],
    payload: dict[str, Any],
    elapsed_ms: float,
    is_outlier: bool,
) -> dict[str, Any]:
    recommendations = payload.get("recommendations", [])
    candidate_hits = payload.get("candidate_hits", [])
    returned_ids = [int(item["laptop_id"]) for item in recommendations if item.get("laptop_id") is not None]
    candidate_ids = [int(item["laptop_id"]) for item in candidate_hits if item.get("laptop_id") is not None]
    relevant = {int(value) for value in row.get("relevant_laptop_ids", [])}
    parsed_filters = payload.get("parsed_query", {}).get("filters", {})
    hard_filter_rate = filter_satisfaction_rate(recommendations, parsed_filters)
    result: dict[str, Any] = {
        "ok": True,
        "index": index,
        "query": query,
        "is_outlier": is_outlier,
        "label_source": row.get("label_source"),
        "status": payload.get("status"),
        "search_mode": payload.get("search_mode"),
        "latency_ms": round(elapsed_ms, 3),
        "retrieval_latency_ms": payload.get("retrieval_latency_ms"),
        "returned_count": len(returned_ids),
        "candidate_count": len(candidate_ids),
        "candidate_unique_count": len(set(candidate_ids)),
        "returned_laptop_ids": returned_ids,
        "candidate_laptop_ids": candidate_ids,
        "relevant_laptop_ids": sorted(relevant),
        "metadata_match_count": payload.get("metadata_match_count"),
        "outlier": bool(payload.get("outlier")),
        "relaxed_filters": payload.get("relaxed_filters", []),
        "hard_filter_satisfaction_rate": hard_filter_rate,
        "final_subset_of_candidates": set(returned_ids).issubset(set(candidate_ids)),
        "top_similarity": payload.get("top_similarity"),
        "top_ranking_score": payload.get("top_ranking_score"),
        "similarity_threshold": payload.get("similarity_threshold"),
        "average_spec_score": average_field(recommendations, "spec_score"),
        "average_price_fit_score": average_field(recommendations, "price_fit_score"),
        "timings_ms": payload.get("timings_ms", {}),
    }
    if not is_outlier and relevant:
        for k in FINAL_K:
            matches = len(set(returned_ids[:k]) & relevant)
            result[f"precision_at_{k}"] = matches / k
            result[f"recall_at_{k}"] = matches / len(relevant)
        for k in CANDIDATE_K:
            matches = len(set(candidate_ids[:k]) & relevant)
            result[f"candidate_precision_at_{k}"] = matches / k
            result[f"candidate_recall_at_{k}"] = matches / len(relevant)
        result["success_at_5"] = bool(set(returned_ids[:5]) & relevant)
        result["mrr"] = reciprocal_rank(returned_ids, relevant)
        result["ndcg_at_5"] = ndcg_at_k(returned_ids, relevant, 5)
        result["average_precision_at_5"] = average_precision_at_k(returned_ids, relevant, 5)
    return result


def average_field(items: list[dict[str, Any]], field: str) -> float | None:
    values = [float(item[field]) for item in items if item.get(field) is not None]
    return round(statistics.mean(values), 6) if values else None


def filter_satisfaction_rate(
    recommendations: list[dict[str, Any]], filters: dict[str, Any]
) -> float | None:
    if not recommendations:
        return None
    passed = sum(1 for item in recommendations if satisfies_filters(item, filters))
    return round(passed / len(recommendations), 6)


def satisfies_filters(item: dict[str, Any], filters: dict[str, Any]) -> bool:
    metadata = item.get("metadata", {})
    price = item.get("price_usd")
    if filters.get("min_price_usd") is not None and (price is None or price < filters["min_price_usd"]):
        return False
    if filters.get("max_price_usd") is not None and (price is None or price > filters["max_price_usd"]):
        return False
    for field, metadata_field in (
        ("min_ram_gb", "ram_capacity_gb"),
        ("min_storage_gb", "storage_capacity_gb"),
        ("min_vram_gb", "vram_capacity_gb"),
        ("min_weight_kg", "weight_kg"),
    ):
        minimum = filters.get(field)
        actual = metadata.get(metadata_field)
        if minimum is not None and (actual is None or actual < minimum):
            return False
    maximum_weight = filters.get("max_weight_kg")
    actual_weight = metadata.get("weight_kg")
    if maximum_weight is not None and (actual_weight is None or actual_weight > maximum_weight):
        return False
    brand = str(metadata.get("brand_normalized", item.get("brand", ""))).lower()
    if filters.get("brands") and brand not in {str(value).lower() for value in filters["brands"]}:
        return False
    if brand in {str(value).lower() for value in filters.get("excluded_brands", [])}:
        return False
    gpu_tags = metadata.get("gpu_tags", [])
    if isinstance(gpu_tags, str):
        gpu_tags = [gpu_tags]
    gpu_tags = {str(value).lower() for value in gpu_tags}
    if filters.get("gpu_tags") and not gpu_tags.intersection(
        {str(value).lower() for value in filters["gpu_tags"]}
    ):
        return False
    if gpu_tags.intersection(
        {str(value).lower() for value in filters.get("excluded_gpu_tags", [])}
    ):
        return False
    if filters.get("storage_types"):
        storage_types = metadata.get("storage_types", [])
        if isinstance(storage_types, str):
            storage_types = [storage_types]
        if not set(filters["storage_types"]).intersection(str(value).lower() for value in storage_types):
            return False
    if filters.get("operating_systems"):
        operating_system = str(metadata.get("os_normalized", "")).lower()
        if operating_system not in {str(value).lower() for value in filters["operating_systems"]}:
            return False
    return True


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in results if row.get("ok")]
    values = lambda field: [float(row[field]) for row in successful if row.get(field) is not None]
    summary: dict[str, Any] = {
        "requests": len(results),
        "successful_requests": len(successful),
        "error_rate": round(1 - len(successful) / max(len(results), 1), 6),
        "latency_ms": latency_summary(values("latency_ms")),
        "retrieval_latency_ms": latency_summary(values("retrieval_latency_ms")),
        "average_returned_count": round(statistics.mean(values("returned_count")), 6)
        if values("returned_count")
        else None,
        "average_candidate_count": round(statistics.mean(values("candidate_count")), 6)
        if values("candidate_count")
        else None,
        "unique_candidate_rate": mean_boolean(
            row.get("candidate_count") == row.get("candidate_unique_count") for row in successful
        ),
        "final_subset_rate": mean_boolean(
            row.get("final_subset_of_candidates", False) for row in successful
        ),
        "hard_filter_satisfaction_rate": mean_optional(
            row.get("hard_filter_satisfaction_rate") for row in successful
        ),
        "average_spec_score": mean_optional(row.get("average_spec_score") for row in successful),
        "average_price_fit_score": mean_optional(
            row.get("average_price_fit_score") for row in successful
        ),
        "average_relaxed_fields": round(
            statistics.mean(len(row.get("relaxed_filters", [])) for row in successful), 6
        )
        if successful
        else None,
        "average_stage_timings_ms": {
            stage: mean_optional(
                row.get("timings_ms", {}).get(stage) for row in successful
            )
            for stage in (
                "parse",
                "embedding",
                "metadata_filter",
                "laptop_search",
                "metadata_fetch",
                "chunk_score",
                "filter_and_rerank",
                "diagnostics",
            )
            if any(row.get("timings_ms", {}).get(stage) is not None for row in successful)
        },
    }
    labeled = [
        row
        for row in successful
        if not row.get("is_outlier") and row.get("precision_at_1") is not None
    ]
    for k in FINAL_K:
        summary[f"precision_at_{k}"] = mean_optional(row.get(f"precision_at_{k}") for row in labeled)
        summary[f"recall_at_{k}"] = mean_optional(row.get(f"recall_at_{k}") for row in labeled)
    for k in CANDIDATE_K:
        summary[f"candidate_precision_at_{k}"] = mean_optional(
            row.get(f"candidate_precision_at_{k}") for row in labeled
        )
        summary[f"candidate_recall_at_{k}"] = mean_optional(
            row.get(f"candidate_recall_at_{k}") for row in labeled
        )
    summary["success_at_5"] = mean_boolean(row.get("success_at_5", False) for row in labeled)
    summary["mrr"] = mean_optional(row.get("mrr") for row in labeled)
    summary["ndcg_at_5"] = mean_optional(row.get("ndcg_at_5") for row in labeled)
    summary["map_at_5"] = mean_optional(row.get("average_precision_at_5") for row in labeled)
    outliers = [row for row in successful if row.get("is_outlier")]
    summary["outlier_rejection_rate"] = mean_boolean(row.get("outlier", False) for row in outliers)
    return summary


def latency_summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "mean": round(statistics.mean(ordered), 3),
        "p50": round(percentile(ordered, 0.50), 3),
        "p95": round(percentile(ordered, 0.95), 3),
        "p99": round(percentile(ordered, 0.99), 3),
    }


def percentile(values: list[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    interpolation = position - lower
    return values[lower] + (values[upper] - values[lower]) * interpolation


def reciprocal_rank(returned_ids: list[int], relevant: set[int]) -> float:
    for rank, laptop_id in enumerate(returned_ids, start=1):
        if laptop_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(returned_ids: list[int], relevant: set[int], k: int) -> float:
    gains = [1.0 if laptop_id in relevant else 0.0 for laptop_id in returned_ids[:k]]
    dcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))
    ideal_length = min(k, len(relevant))
    if ideal_length == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_length))
    return round(dcg / idcg, 6)


def average_precision_at_k(returned_ids: list[int], relevant: set[int], k: int) -> float:
    if not relevant:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for rank, laptop_id in enumerate(returned_ids[:k], start=1):
        if laptop_id in relevant:
            hits += 1
            precision_sum += hits / rank
    return round(precision_sum / min(len(relevant), k), 6)


def mean_optional(values) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    return round(statistics.mean(cleaned), 6) if cleaned else None


def mean_boolean(values) -> float | None:
    values = list(values)
    return round(sum(bool(value) for value in values) / len(values), 6) if values else None


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Backend and FAISS Evaluation Report",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Evaluation Scope",
        "",
        f"- Labeled query rows: `{report['dataset']['labeled_queries']}`",
        f"- Outlier rows: `{report['dataset']['outliers']}`",
        f"- Indexes evaluated: `{', '.join(report['indexes'])}`",
        f"- Execution environment: `{report['base_url']}`",
        f"- Label source: `{report['dataset']['label_source']}`",
        (
            "- Relevance metrics use independently supplied human judgments."
            if report["dataset"]["human_labels_available"]
            else "- Relevance metrics are provisional because independent human judgments were not declared."
        ),
        "",
        "## Index Results",
        "",
        "| Index | P@1 | P@3 | P@5 | Recall@5 | nDCG@5 | MRR | MAP@5 | Candidate Recall@20 | Filter Satisfaction | Unique Candidates | Final Subset | Latency p50 ms | Latency p95 ms | Outlier Rejection |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for index in report["indexes"]:
        summary = report["summaries"][index]
        lines.append(
            "| {index} | {p1} | {p3} | {p5} | {r5} | {ndcg} | {mrr} | {map5} | {cr20} | {filters} | {unique} | {subset} | {p50} | {p95} | {outlier} |".format(
                index=index,
                p1=fmt(summary.get("precision_at_1")),
                p3=fmt(summary.get("precision_at_3")),
                p5=fmt(summary.get("precision_at_5")),
                r5=fmt(summary.get("recall_at_5")),
                ndcg=fmt(summary.get("ndcg_at_5")),
                mrr=fmt(summary.get("mrr")),
                map5=fmt(summary.get("map_at_5")),
                cr20=fmt(summary.get("candidate_recall_at_20")),
                filters=fmt(summary.get("hard_filter_satisfaction_rate")),
                unique=fmt(summary.get("unique_candidate_rate")),
                subset=fmt(summary.get("final_subset_rate")),
                p50=fmt((summary.get("latency_ms") or {}).get("p50")),
                p95=fmt((summary.get("latency_ms") or {}).get("p95")),
                outlier=fmt(summary.get("outlier_rejection_rate")),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `P@k`, `Recall@k`, `nDCG@5`, `MRR`, and `MAP@5` measure agreement with the supplied relevance judgments.",
            "- `Candidate Recall@20` measures whether labeled relevant laptops enter the unique candidate set before final top-five selection.",
            "- `Filter Satisfaction` should be 1.0 for explicit hard filters.",
            "- `Unique Candidates` and `Final Subset` should both be 1.0 after the laptop-level index change.",
            "- `Outlier Rejection` is based on only the supplied outlier set and should be expanded before using it as a production claim.",
            "",
            "## Limitations",
            "",
            "1. Relevance is binary; the order of IDs in each judgment list is not treated as graded relevance.",
            "2. Current outlier coverage is only five queries.",
            "3. Latency is end-to-end for the stated execution environment and includes metadata, embedding, FAISS, and reranking work; it is not comparable to isolated notebook FAISS timings.",
            "4. Threshold calibration and final evaluation should use separate query splits.",
            "",
            "## Recommended Acceptance Gates",
            "",
            "- Hard-filter satisfaction: `100%`.",
            "- Unique candidate rate: `100%`.",
            "- Final recommendations contained in candidate top 20: `100%`.",
            "- Human-labeled nDCG@5 and Recall@5 reported for every index.",
            "- Outlier false-accept rate reported on at least 30 outliers.",
            "- Warm and cold p50/p95 latency reported separately.",
        ]
    )
    return "\n".join(lines) + "\n"


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    queries = load_jsonl(args.queries)
    outliers = load_jsonl(args.outliers)
    if len(queries) < 30:
        raise ValueError("Evaluation requires at least 30 labeled queries.")
    if any(not row.get("relevant_laptop_ids") for row in queries):
        raise ValueError("Every labeled query must include relevant_laptop_ids.")
    declared_source = args.label_source or "unspecified"
    queries = [
        {**row, "label_source": row.get("label_source") or declared_source}
        for row in queries
    ]
    rows = [(row, False) for row in queries] + [(row, True) for row in outliers]
    semaphore = asyncio.Semaphore(max(args.concurrency, 1))
    client_context: httpx.AsyncClient
    report_base_url = args.base_url
    if args.in_process:
        from app.config import Settings
        from app.main import create_app

        base_settings = Settings.from_env()
        settings = replace(
            base_settings,
            metadata_backend="parquet",
            local_metadata_file=base_settings.artifact_dir / "qdrant_records.parquet",
            rate_limit_enabled=False,
        )
        app = create_app(settings)
        await asyncio.to_thread(app.state.services.initialize)
        client_context = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://in-process",
            timeout=args.timeout,
        )
        report_base_url = "in-process:parquet"
    else:
        client_context = httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout)

    async with client_context as client:
        for _ in range(max(args.warmup_runs, 0)):
            warmup_tasks = [
                request_one(client, semaphore, index, row, is_outlier)
                for index in INDEXES
                for row, is_outlier in rows
            ]
            await asyncio.gather(*warmup_tasks)
        tasks = [
            request_one(client, semaphore, index, row, is_outlier)
            for index in INDEXES
            for row, is_outlier in rows
        ]
        results = await asyncio.gather(*tasks)

    by_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_index[result["index"]].append(result)
    from app.config import Settings

    manifest_path = Settings.from_env().artifact_dir / "index_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": report_base_url,
        "warmup_runs": max(args.warmup_runs, 0),
        "indexes": list(INDEXES),
        "dataset": {
            "labeled_queries": len(queries),
            "outliers": len(outliers),
            "label_source": declared_source,
            "human_labels_available": bool(args.human_labels),
        },
        "artifact_manifest": {
            "chunk_vector_count": manifest.get("vector_count"),
            "laptop_vector_count": manifest.get("laptop_vector_count"),
            "chunk_indexes": manifest.get("indexes", {}),
            "laptop_indexes": manifest.get("laptop_indexes", {}),
        },
        "summaries": {index: aggregate(by_index[index]) for index in INDEXES},
        "results": results,
    }


def main() -> None:
    args = parse_args()
    report = asyncio.run(run(args))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown_report(report), encoding="utf-8")
    print(args.json_output)
    print(args.markdown_output)


if __name__ == "__main__":
    main()
