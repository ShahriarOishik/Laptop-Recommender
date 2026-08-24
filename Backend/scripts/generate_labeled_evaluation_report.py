from __future__ import annotations

import argparse
import csv
import json
import os
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


INDEX_LABELS = {
    "flat": "Flat",
    "ivf_flat": "IVF Flat",
    "pq": "PQ",
    "ivf_pq": "IVF + PQ",
    "hnsw": "HNSW",
}
COLORS = {
    "flat": "#355070",
    "ivf_flat": "#2a9d8f",
    "pq": "#e9c46a",
    "ivf_pq": "#f4a261",
    "hnsw": "#e76f51",
}


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Create charts and a report from backend metrics JSON.")
    parser.add_argument(
        "metrics",
        type=Path,
        help="JSON produced by scripts/evaluate_backend_metrics.py",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=root / "description" / "hand_labeled_evaluation_report.md",
    )
    parser.add_argument(
        "--charts-dir",
        type=Path,
        default=root / "description" / "hand_labeled_evaluation_charts",
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        default=root / "description" / "hand_labeled_evaluation_summary.csv",
    )
    parser.add_argument(
        "--per-query-csv",
        type=Path,
        default=root / "description" / "hand_labeled_per_query_metrics.csv",
    )
    return parser.parse_args()


def metric(summary: dict[str, Any], name: str) -> float:
    value = summary.get(name)
    return float(value) if value is not None else 0.0


def percent(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.2f}%"


def number(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def bootstrap_ci(values: list[float], samples: int = 5000) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])
    rng = random.Random(488)
    means = sorted(
        statistics.mean(rng.choice(values) for _ in values)
        for _ in range(samples)
    )
    return means[int(0.025 * (samples - 1))], means[int(0.975 * (samples - 1))]


def chart_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 180,
            "font.size": 9,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.alpha": 0.22,
        }
    )


def save_chart(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def grouped_bars(
    report: dict[str, Any],
    fields: list[tuple[str, str]],
    title: str,
    ylabel: str,
    output: Path,
) -> None:
    indexes = report["indexes"]
    x = np.arange(len(indexes))
    width = 0.78 / len(fields)
    plt.figure(figsize=(9.5, 4.8))
    all_values: list[float] = []
    for position, (field, label) in enumerate(fields):
        values = [metric(report["summaries"][index], field) for index in indexes]
        all_values.extend(values)
        offset = (position - (len(fields) - 1) / 2) * width
        bars = plt.bar(x + offset, values, width, label=label, alpha=0.9)
        for bar, value in zip(bars, values):
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.008,
                f"{value:.3f}",
                ha="center",
                va="bottom",
                fontsize=7,
                rotation=90 if len(fields) > 3 else 0,
            )
    plt.xticks(x, [INDEX_LABELS[index] for index in indexes])
    chart_max = max(all_values, default=0)
    plt.ylim(0, min(1.0, max(0.1, chart_max * 1.35)))
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend(frameon=False, ncol=len(fields), loc="upper center", bbox_to_anchor=(0.5, -0.12))
    save_chart(output)


def latency_chart(report: dict[str, Any], output: Path) -> None:
    indexes = report["indexes"]
    x = np.arange(len(indexes))
    endpoint_p50 = [report["summaries"][index]["latency_ms"]["p50"] for index in indexes]
    endpoint_p95 = [report["summaries"][index]["latency_ms"]["p95"] for index in indexes]
    retrieval_p50 = [report["summaries"][index]["retrieval_latency_ms"]["p50"] for index in indexes]
    width = 0.24
    plt.figure(figsize=(9.5, 4.8))
    plt.bar(x - width, endpoint_p50, width, label="Endpoint p50", color="#355070")
    plt.bar(x, endpoint_p95, width, label="Endpoint p95", color="#e76f51")
    plt.bar(x + width, retrieval_p50, width, label="Backend retrieval p50", color="#2a9d8f")
    plt.xticks(x, [INDEX_LABELS[index] for index in indexes])
    plt.ylabel("Milliseconds")
    plt.title("End-to-End and Backend-Reported Latency")
    plt.legend(frameon=False)
    save_chart(output)


def pareto_chart(report: dict[str, Any], output: Path) -> None:
    plt.figure(figsize=(7.5, 5.2))
    for index in report["indexes"]:
        summary = report["summaries"][index]
        x = summary["latency_ms"]["p50"]
        y = metric(summary, "ndcg_at_5")
        plt.scatter(x, y, s=95, color=COLORS[index], edgecolor="white", linewidth=0.8, zorder=3)
        plt.annotate(INDEX_LABELS[index], (x, y), xytext=(6, 5), textcoords="offset points")
    plt.xlabel("Endpoint latency p50 (ms, lower is better)")
    plt.ylabel("nDCG@5 (higher is better)")
    plt.title("Ranking Quality vs. Latency")
    save_chart(output)


def heatmap(report: dict[str, Any], output: Path) -> None:
    labeled = [row for row in report["results"] if row.get("ok") and not row.get("is_outlier")]
    query_order = list(dict.fromkeys(row["query"] for row in labeled))
    by_key = {(row["index"], row["query"]): row for row in labeled}
    matrix = np.array(
        [
            [float(by_key.get((index, query), {}).get("ndcg_at_5", np.nan)) for query in query_order]
            for index in report["indexes"]
        ]
    )
    plt.figure(figsize=(13, 3.6))
    image = plt.imshow(matrix, aspect="auto", cmap="viridis", vmin=0, vmax=1)
    plt.yticks(np.arange(len(report["indexes"])), [INDEX_LABELS[index] for index in report["indexes"]])
    plt.xticks(np.arange(len(query_order)), [str(i + 1) for i in range(len(query_order))], fontsize=7)
    plt.xlabel("Labeled query number")
    plt.title("Per-Query nDCG@5 Heatmap")
    colorbar = plt.colorbar(image, pad=0.01)
    colorbar.set_label("nDCG@5")
    save_chart(output)


def write_summary_csv(report: dict[str, Any], path: Path) -> None:
    fields = [
        "index",
        "precision_at_1",
        "precision_at_3",
        "precision_at_5",
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "ndcg_at_5",
        "mrr",
        "map_at_5",
        "success_at_5",
        "candidate_recall_at_20",
        "latency_p50_ms",
        "latency_p95_ms",
        "retrieval_latency_p50_ms",
        "outlier_rejection_rate",
        "hard_filter_satisfaction_rate",
        "error_rate",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in report["indexes"]:
            summary = report["summaries"][index]
            writer.writerow(
                {
                    "index": index,
                    **{field: summary.get(field) for field in fields[1:12]},
                    "latency_p50_ms": summary["latency_ms"]["p50"],
                    "latency_p95_ms": summary["latency_ms"]["p95"],
                    "retrieval_latency_p50_ms": summary["retrieval_latency_ms"]["p50"],
                    "outlier_rejection_rate": summary.get("outlier_rejection_rate"),
                    "hard_filter_satisfaction_rate": summary.get("hard_filter_satisfaction_rate"),
                    "error_rate": summary.get("error_rate"),
                }
            )


def write_per_query_csv(report: dict[str, Any], path: Path) -> None:
    fields = [
        "query_number",
        "index",
        "query",
        "precision_at_1",
        "precision_at_3",
        "precision_at_5",
        "recall_at_5",
        "ndcg_at_5",
        "mrr",
        "average_precision_at_5",
        "success_at_5",
        "candidate_recall_at_20",
        "latency_ms",
        "retrieval_latency_ms",
        "returned_laptop_ids",
    ]
    rows = [row for row in report["results"] if row.get("ok") and not row.get("is_outlier")]
    query_numbers = {query: i + 1 for i, query in enumerate(dict.fromkeys(row["query"] for row in rows))}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "query_number": query_numbers[row["query"]],
                    **{field: row.get(field) for field in fields[1:-1]},
                    "returned_laptop_ids": " ".join(map(str, row.get("returned_laptop_ids", []))),
                }
            )


def markdown_table(headers: list[str], rows: Iterable[list[str]], align_right: set[int] | None = None) -> str:
    align_right = align_right or set()
    separator = ["---:" if i in align_right else "---" for i in range(len(headers))]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(separator) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def report_markdown(
    report: dict[str, Any],
    charts_dir: Path,
    report_path: Path,
    summary_csv: Path,
    per_query_csv: Path,
) -> str:
    indexes = report["indexes"]
    summaries = report["summaries"]
    labeled = [row for row in report["results"] if row.get("ok") and not row.get("is_outlier")]
    outliers = [row for row in report["results"] if row.get("ok") and row.get("is_outlier")]
    queries = list(dict.fromkeys(row["query"] for row in labeled))
    relevant_ids = {value for row in labeled if row["index"] == indexes[0] for value in row.get("relevant_laptop_ids", [])}
    judgments = sum(len(row.get("relevant_laptop_ids", [])) for row in labeled if row["index"] == indexes[0])

    best_quality = max(indexes, key=lambda index: metric(summaries[index], "ndcg_at_5"))
    fastest = min(indexes, key=lambda index: summaries[index]["latency_ms"]["p50"])
    quality_floor = metric(summaries[best_quality], "ndcg_at_5") * 0.95
    balanced = min(
        (index for index in indexes if metric(summaries[index], "ndcg_at_5") >= quality_floor),
        key=lambda index: summaries[index]["latency_ms"]["p50"],
    )

    by_query: dict[str, list[float]] = defaultdict(list)
    for row in labeled:
        by_query[row["query"]].append(float(row.get("ndcg_at_5", 0)))
    query_difficulty = sorted(
        ((query, statistics.mean(values)) for query, values in by_query.items()),
        key=lambda item: item[1],
    )

    report_dir = report_path.resolve().parent

    def relative_link(path: Path) -> str:
        return Path(os.path.relpath(path.resolve(), report_dir)).as_posix()

    relative_charts = relative_link(charts_dir)
    lines = [
        "# Hand-Labeled Laptop Retrieval Evaluation",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Executive Summary",
        "",
        f"This evaluation measures five FAISS configurations against **{len(queries)} hand-labeled queries**, "
        f"**{judgments} binary relevance judgments**, and **{len(outliers) // len(indexes)} out-of-domain queries**. "
        f"It uses the corrected artifact set with **{report['artifact_manifest']['laptop_vector_count']:,} laptops** "
        f"and **{report['artifact_manifest']['chunk_vector_count']:,} text chunks**.",
        "",
        f"- **Highest ranking quality:** {INDEX_LABELS[best_quality]} with nDCG@5 "
        f"`{metric(summaries[best_quality], 'ndcg_at_5'):.3f}`.",
        f"- **Lowest median endpoint latency:** {INDEX_LABELS[fastest]} at "
        f"`{summaries[fastest]['latency_ms']['p50']:.1f} ms` p50.",
        "- **Production recommendation:** none from this relevance run. The best nDCG@5 is below `0.05`, "
        "and the bootstrap intervals overlap; label/artifact alignment and candidate generation should be audited before choosing an index on quality.",
        f"- **Exploratory quality/latency point:** {INDEX_LABELS[balanced]} is within 5% of the best observed "
        f"nDCG@5 and has `{summaries[balanced]['latency_ms']['p50']:.1f} ms` p50 latency, but this is not an acceptance result.",
        f"- **Outlier rejection:** best observed rate is `{max(metric(summaries[index], 'outlier_rejection_rate') for index in indexes):.3f}`; "
        "this is only exploratory because the outlier set has five queries.",
        "",
        "## Evaluation Design",
        "",
        markdown_table(
            ["Item", "Value"],
            [
                ["Label provenance", report["dataset"]["label_source"]],
                ["Labeled queries", str(len(queries))],
                ["Relevant IDs per query", "15"],
                ["Total query-item relevance judgments", str(judgments)],
                ["Unique judged-relevant laptops", str(len(relevant_ids))],
                ["Out-of-domain queries", str(len(outliers) // len(indexes))],
                ["Indexes", ", ".join(INDEX_LABELS[index] for index in indexes)],
                ["Final cutoff", "Top 5 recommendations"],
                ["Candidate cutoffs", "Top 10 and top 20"],
                ["Execution", report["base_url"]],
                ["Discarded warm-up passes", str(report.get("warmup_runs", 0))],
            ],
        ),
        "",
        "Each query was sent to `/retrieve` with `top_k=5` and diagnostics enabled. The same query set "
        "was evaluated independently against Flat, IVF Flat, Product Quantization (PQ), IVF + PQ, and HNSW. "
        "Metrics are macro-averaged across queries, so each query contributes equally.",
        "",
        "### Metric Definitions",
        "",
        "- **Precision@k:** relevant returned laptops divided by k.",
        "- **Recall@k:** relevant returned laptops divided by all 15 judged-relevant laptops for that query.",
        "- **nDCG@5:** rank-sensitive gain normalized by the ideal top-five ordering; binary relevance is used.",
        "- **MRR:** reciprocal rank of the first relevant result.",
        "- **MAP@5:** mean of per-query average precision through rank five.",
        "- **Success@5:** fraction of queries with at least one relevant result in the top five.",
        "- **Candidate Recall@20:** fraction of judged-relevant items entering the pre-reranking candidate set.",
        "- **Endpoint latency:** evaluator-observed request time, including parsing, embedding, metadata work, FAISS, and reranking.",
        "",
        "Because each query has 15 relevant labels but only five returned slots, the mathematical ceiling for "
        "Recall@5 is `5/15 = 0.333`. Precision@5 and nDCG@5 are therefore more intuitive measures of top-five quality.",
        "",
        "## Aggregate Results",
        "",
        markdown_table(
            ["Index", "P@1", "P@3", "P@5", "R@5", "nDCG@5", "MRR", "MAP@5", "Success@5"],
            [
                [
                    INDEX_LABELS[index],
                    number(summaries[index].get("precision_at_1")),
                    number(summaries[index].get("precision_at_3")),
                    number(summaries[index].get("precision_at_5")),
                    number(summaries[index].get("recall_at_5")),
                    number(summaries[index].get("ndcg_at_5")),
                    number(summaries[index].get("mrr")),
                    number(summaries[index].get("map_at_5")),
                    percent(summaries[index].get("success_at_5")),
                ]
                for index in indexes
            ],
            set(range(1, 9)),
        ),
        "",
        f"![Precision and recall by cutoff]({relative_charts}/quality_at_k.png)",
        "",
        f"![Rank-sensitive metrics]({relative_charts}/ranking_metrics.png)",
        "",
        "### Bootstrap Uncertainty",
        "",
        "The intervals below are nonparametric 95% bootstrap confidence intervals over the 40 query rows "
        "(5,000 deterministic resamples). They quantify query-sampling uncertainty, not labeling uncertainty.",
        "",
    ]

    ci_rows = []
    for index in indexes:
        index_rows = [row for row in labeled if row["index"] == index]
        ndcg_values = [float(row["ndcg_at_5"]) for row in index_rows]
        p5_values = [float(row["precision_at_5"]) for row in index_rows]
        ndcg_ci = bootstrap_ci(ndcg_values)
        p5_ci = bootstrap_ci(p5_values)
        ci_rows.append(
            [
                INDEX_LABELS[index],
                f"{statistics.mean(ndcg_values):.3f} [{ndcg_ci[0]:.3f}, {ndcg_ci[1]:.3f}]",
                f"{statistics.mean(p5_values):.3f} [{p5_ci[0]:.3f}, {p5_ci[1]:.3f}]",
            ]
        )
    lines.extend(
        [
            markdown_table(["Index", "nDCG@5 mean [95% CI]", "P@5 mean [95% CI]"], ci_rows, {1, 2}),
            "",
            "## Candidate Retrieval and Reranking",
            "",
            markdown_table(
                ["Index", "Candidate P@10", "Candidate R@10", "Candidate P@20", "Candidate R@20", "Final subset rate"],
                [
                    [
                        INDEX_LABELS[index],
                        number(summaries[index].get("candidate_precision_at_10")),
                        number(summaries[index].get("candidate_recall_at_10")),
                        number(summaries[index].get("candidate_precision_at_20")),
                        number(summaries[index].get("candidate_recall_at_20")),
                        percent(summaries[index].get("final_subset_rate")),
                    ]
                    for index in indexes
                ],
                {1, 2, 3, 4, 5},
            ),
            "",
            f"![Candidate recall]({relative_charts}/candidate_recall.png)",
            "",
            "Candidate Recall@20 diagnoses whether judged-relevant items were available to the final reranker. "
            f"Here, even the best Candidate Recall@20 is only `{max(metric(summaries[index], 'candidate_recall_at_20') for index in indexes):.3f}`. "
            "The dominant issue is therefore upstream candidate generation and/or alignment between the judgment IDs "
            "and the current artifact set; reranking cannot select relevant laptops that never enter its pool.",
            "",
            "## Latency",
            "",
            markdown_table(
                ["Index", "Endpoint mean", "Endpoint p50", "Endpoint p95", "Endpoint p99", "Retrieval p50", "Retrieval p95"],
                [
                    [
                        INDEX_LABELS[index],
                        f"{summaries[index]['latency_ms']['mean']:.1f} ms",
                        f"{summaries[index]['latency_ms']['p50']:.1f} ms",
                        f"{summaries[index]['latency_ms']['p95']:.1f} ms",
                        f"{summaries[index]['latency_ms']['p99']:.1f} ms",
                        f"{summaries[index]['retrieval_latency_ms']['p50']:.1f} ms",
                        f"{summaries[index]['retrieval_latency_ms']['p95']:.1f} ms",
                    ]
                    for index in indexes
                ],
                {1, 2, 3, 4, 5, 6},
            ),
            "",
            f"![Latency comparison]({relative_charts}/latency_comparison.png)",
            "",
            f"![Quality-latency tradeoff]({relative_charts}/quality_latency_tradeoff.png)",
            "",
            f"These are warm-process, single-request (`concurrency=1`) in-process measurements after "
            f"`{report.get('warmup_runs', 0)}` discarded full pass(es) on this machine. "
            "They are appropriate for relative index comparison but should not be presented as public-deployment "
            "SLA measurements. Network latency is excluded by the in-process transport.",
            "",
            "## Operational Invariants",
            "",
            markdown_table(
                ["Index", "Errors", "Hard-filter satisfaction", "Unique candidates", "Final subset", "Outlier rejection"],
                [
                    [
                        INDEX_LABELS[index],
                        percent(summaries[index].get("error_rate")),
                        percent(summaries[index].get("hard_filter_satisfaction_rate")),
                        percent(summaries[index].get("unique_candidate_rate")),
                        percent(summaries[index].get("final_subset_rate")),
                        percent(summaries[index].get("outlier_rejection_rate")),
                    ]
                    for index in indexes
                ],
                {1, 2, 3, 4, 5},
            ),
            "",
            "The error rate should be 0%. Hard-filter satisfaction checks the structured constraints inferred by "
            "the backend against returned metadata. Unique-candidate and final-subset rates validate retrieval "
            "pipeline invariants rather than relevance quality.",
            "",
            "## Per-Query Analysis",
            "",
            f"![Per-query nDCG heatmap]({relative_charts}/per_query_ndcg_heatmap.png)",
            "",
            "### Five Most Difficult Queries",
            "",
            markdown_table(
                ["Query", "Mean nDCG@5 across indexes"],
                [[query.replace("|", "\\|"), f"{score:.3f}"] for query, score in query_difficulty[:5]],
                {1},
            ),
            "",
            "### Five Strongest Queries",
            "",
            markdown_table(
                ["Query", "Mean nDCG@5 across indexes"],
                [[query.replace("|", "\\|"), f"{score:.3f}"] for query, score in reversed(query_difficulty[-5:])],
                {1},
            ),
            "",
            "The heatmap reveals whether failures are systematic across every index (usually query interpretation, "
            "judgment mismatch, or reranking) or isolated to compressed/approximate indexes (an ANN quality issue).",
            "",
            "## Interpretation",
            "",
            "1. **Index choice:** no index clears a defensible relevance threshold. PQ has the highest point estimate, "
            "but its confidence interval overlaps the other indexes and nDCG@5 remains below 0.05.",
            "2. **Top-five focus:** nDCG@5, P@5, MAP@5, and Success@5 are the primary product-facing metrics. Raw "
            "Recall@5 is intentionally capped at 0.333 by the evaluation design.",
            "3. **Retrieval vs. reranking:** Candidate Recall@20 is extremely weak, so first verify that the labeled "
            "laptop IDs and current artifacts describe the same catalog, then inspect query parsing/filters and widen "
            "ANN search breadth (`nprobe`, `efSearch`, candidate count) before tuning reranking weights.",
            "4. **Outliers:** rejection results are encouraging only if consistently high, but five examples are too few "
            "for a production false-accept claim.",
            "",
            "## Limitations",
            "",
            "1. Relevance is binary. The order of `relevant_laptop_ids` is ignored and no graded relevance levels were supplied.",
            "2. The 40 queries are sufficient for the course requirement but still produce broad confidence intervals for close index comparisons.",
            "3. The judgment pool may omit relevant laptops that were never presented to annotators; unjudged returned items are treated as non-relevant.",
            "4. Only five out-of-domain queries were evaluated. At least 30 diverse outliers are recommended for a stable rejection estimate.",
            "5. The same broader query family was previously used for threshold calibration; a separate held-out test split would reduce evaluation leakage.",
            "6. Latency is measured in-process on one machine after model startup. Cold-start, concurrent-load, network, and hosted-deployment latency are not represented.",
            "7. Statistical intervals reflect variation across queries only; they do not measure annotator disagreement. Multiple assessors or agreement statistics would strengthen the labels.",
            "",
            "## Reproducibility Artifacts",
            "",
            f"- Raw metrics JSON: `{relative_link(Path(report['_metrics_path']))}`",
            f"- Aggregate metrics CSV: `{relative_link(summary_csv)}`",
            f"- Per-query metrics CSV: `{relative_link(per_query_csv)}`",
            f"- Charts: `{relative_charts}`",
            "- Labels: `Backend/evaluation/queries.jsonl`",
            "- Outliers: `Backend/evaluation/outliers.jsonl`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    report = json.loads(args.metrics.read_text(encoding="utf-8"))
    report["_metrics_path"] = args.metrics
    args.charts_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    chart_style()

    grouped_bars(
        report,
        [
            ("precision_at_1", "P@1"),
            ("precision_at_3", "P@3"),
            ("precision_at_5", "P@5"),
            ("recall_at_5", "Recall@5"),
        ],
        "Human-Labeled Precision and Recall",
        "Macro-average",
        args.charts_dir / "quality_at_k.png",
    )
    grouped_bars(
        report,
        [
            ("ndcg_at_5", "nDCG@5"),
            ("mrr", "MRR"),
            ("map_at_5", "MAP@5"),
            ("success_at_5", "Success@5"),
        ],
        "Rank-Sensitive Retrieval Quality",
        "Macro-average",
        args.charts_dir / "ranking_metrics.png",
    )
    grouped_bars(
        report,
        [
            ("candidate_recall_at_10", "Candidate Recall@10"),
            ("candidate_recall_at_20", "Candidate Recall@20"),
            ("recall_at_5", "Final Recall@5"),
        ],
        "Candidate Retrieval vs. Final Recall",
        "Macro-average recall",
        args.charts_dir / "candidate_recall.png",
    )
    latency_chart(report, args.charts_dir / "latency_comparison.png")
    pareto_chart(report, args.charts_dir / "quality_latency_tradeoff.png")
    heatmap(report, args.charts_dir / "per_query_ndcg_heatmap.png")
    write_summary_csv(report, args.summary_csv)
    write_per_query_csv(report, args.per_query_csv)
    args.report.write_text(
        report_markdown(report, args.charts_dir, args.report, args.summary_csv, args.per_query_csv),
        encoding="utf-8",
    )
    print(args.report)
    print(args.charts_dir)
    print(args.summary_csv)
    print(args.per_query_csv)


if __name__ == "__main__":
    main()
