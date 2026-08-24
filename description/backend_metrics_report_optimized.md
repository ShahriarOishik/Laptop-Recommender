# Backend and FAISS Evaluation Report

Generated: `2026-08-17T18:54:15.529858+00:00`

## Evaluation Scope

- Labeled query rows: `40`
- Outlier rows: `5`
- Indexes evaluated: `flat, ivf_flat, pq, ivf_pq, hnsw`
- Execution environment: `in-process:parquet`
- Label source: `flat_exact_knn_pseudo_label`
- Relevance metrics are provisional because the current labels are Flat-KNN pseudo-labels, not independent human judgments.

## Index Results

| Index | P@1 | P@3 | P@5 | Recall@5 | nDCG@5 | MRR | Candidate Recall@20 | Filter Satisfaction | Unique Candidates | Final Subset | Latency p50 ms | Latency p95 ms | Outlier Rejection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| flat | 0.175 | 0.133 | 0.095 | 0.095 | 0.112 | 0.242 | 0.140 | 1.000 | 1.000 | 1.000 | 128.604 | 211.406 | 1.000 |
| ivf_flat | 0.175 | 0.133 | 0.095 | 0.095 | 0.112 | 0.242 | 0.135 | 1.000 | 1.000 | 1.000 | 49.949 | 77.826 | 1.000 |
| pq | 0.150 | 0.075 | 0.070 | 0.070 | 0.083 | 0.182 | 0.125 | 1.000 | 1.000 | 1.000 | 56.937 | 78.142 | 1.000 |
| ivf_pq | 0.150 | 0.092 | 0.070 | 0.070 | 0.086 | 0.207 | 0.125 | 1.000 | 1.000 | 1.000 | 51.629 | 78.298 | 1.000 |
| hnsw | 0.175 | 0.133 | 0.095 | 0.095 | 0.114 | 0.247 | 0.140 | 1.000 | 1.000 | 1.000 | 53.682 | 105.558 | 1.000 |

## Interpretation

- `P@k` and `Recall@k` measure agreement with the available pseudo-labels; they are not human relevance scores.
- `Candidate Recall@20` measures whether labeled relevant laptops enter the unique candidate set before final top-five selection.
- `Filter Satisfaction` should be 1.0 for explicit hard filters.
- `Unique Candidates` and `Final Subset` should both be 1.0 after the laptop-level index change.
- `Outlier Rejection` is based on only the supplied outlier set and should be expanded before using it as a production claim.

## Limitations

1. The current 40 relevance labels were generated from exact Flat KNN and are explicitly marked as pseudo-labels.
2. Independent human labels are still required for final precision, recall, and nDCG claims.
3. Current outlier coverage is only five queries.
4. Latency is end-to-end for the stated execution environment and includes metadata, embedding, FAISS, and reranking work; it is not comparable to isolated notebook FAISS timings.
5. Threshold calibration and final evaluation should use separate query splits.

## Recommended Acceptance Gates

- Hard-filter satisfaction: `100%`.
- Unique candidate rate: `100%`.
- Final recommendations contained in candidate top 20: `100%`.
- Human-labeled nDCG@5 and Recall@5 reported for every index.
- Outlier false-accept rate reported on at least 30 outliers.
- Warm and cold p50/p95 latency reported separately.
