# Backend and FAISS Evaluation Report

Generated: `2026-08-24T19:40:57.887354+00:00`

## Evaluation Scope

- Labeled query rows: `40`
- Outlier rows: `5`
- Indexes evaluated: `flat, ivf_flat, pq, ivf_pq, hnsw`
- Execution environment: `in-process:parquet`
- Label source: `human_judgment`
- Relevance metrics use independently supplied human judgments.

## Index Results

| Index | P@1 | P@3 | P@5 | Recall@5 | nDCG@5 | MRR | MAP@5 | Candidate Recall@20 | Filter Satisfaction | Unique Candidates | Final Subset | Latency p50 ms | Latency p95 ms | Outlier Rejection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| flat | 0.050 | 0.025 | 0.020 | 0.007 | 0.026 | 0.068 | 0.013 | 0.015 | 1.000 | 1.000 | 1.000 | 108.932 | 157.565 | 1.000 |
| ivf_flat | 0.050 | 0.025 | 0.020 | 0.007 | 0.026 | 0.068 | 0.013 | 0.015 | 1.000 | 1.000 | 1.000 | 114.378 | 173.535 | 1.000 |
| pq | 0.125 | 0.050 | 0.030 | 0.010 | 0.048 | 0.125 | 0.030 | 0.017 | 1.000 | 1.000 | 1.000 | 136.163 | 187.786 | 1.000 |
| ivf_pq | 0.075 | 0.025 | 0.015 | 0.005 | 0.025 | 0.075 | 0.015 | 0.008 | 1.000 | 1.000 | 1.000 | 128.327 | 193.481 | 1.000 |
| hnsw | 0.050 | 0.025 | 0.020 | 0.007 | 0.026 | 0.068 | 0.013 | 0.015 | 1.000 | 1.000 | 1.000 | 109.744 | 154.399 | 1.000 |

## Interpretation

- `P@k`, `Recall@k`, `nDCG@5`, `MRR`, and `MAP@5` measure agreement with the supplied relevance judgments.
- `Candidate Recall@20` measures whether labeled relevant laptops enter the unique candidate set before final top-five selection.
- `Filter Satisfaction` should be 1.0 for explicit hard filters.
- `Unique Candidates` and `Final Subset` should both be 1.0 after the laptop-level index change.
- `Outlier Rejection` is based on only the supplied outlier set and should be expanded before using it as a production claim.

## Limitations

1. Relevance is binary; the order of IDs in each judgment list is not treated as graded relevance.
2. Current outlier coverage is only five queries.
3. Latency is end-to-end for the stated execution environment and includes metadata, embedding, FAISS, and reranking work; it is not comparable to isolated notebook FAISS timings.
4. Threshold calibration and final evaluation should use separate query splits.

## Recommended Acceptance Gates

- Hard-filter satisfaction: `100%`.
- Unique candidate rate: `100%`.
- Final recommendations contained in candidate top 20: `100%`.
- Human-labeled nDCG@5 and Recall@5 reported for every index.
- Outlier false-accept rate reported on at least 30 outliers.
- Warm and cold p50/p95 latency reported separately.
