# Backend Performance Optimization Report

## Scope

This report compares the same 225-request evaluation before and after backend
performance optimization:

- 40 retrieval queries.
- 5 outlier queries.
- 5 FAISS index families.
- 45 requests per index.
- In-process FastAPI execution using the same Parquet metadata artifact.
- Concurrency fixed at 1 so latency is not distorted by queueing.

Baseline data is stored in:

```text
description/backend_metrics_report.json
```

Optimized data is stored in:

```text
description/backend_metrics_report_optimized.json
```

## Implemented Optimizations

### FAISS

- Increased the resident index cache from one entry to two entries so a laptop
  index and its matching chunk index can remain loaded together.
- Preloads the default laptop/chunk index pair during startup.
- Replaced Python loops calling `reconstruct()` once per vector with FAISS
  `reconstruct_batch()`.
- Added multi-query chunk scoring so semantic-only and filter-aware queries use
  one reconstructed vector matrix.
- Normalizes and scores selected vectors with batched NumPy matrix operations.

### Embeddings

- Added `encode_many()` to generate semantic and filter-aware vectors in one
  model call.
- Added a bounded exact-text embedding cache.
- Serialized model inference with a lock because the tokenizer is not
  thread-safe in the current runtime.
- Repeated queries now reuse normalized vectors instead of invoking BGE again.

### Metadata

- Local hard filtering now scans 6,778 unique laptop rows instead of 63,998
  chunk rows.
- Added a precomputed `laptop_id -> vector_ids` mapping for local source lookup.
- Replaced slow Pandas `iterrows()` conversion with bulk record conversion.
- Added a bounded immutable laptop-payload cache shared by Parquet and Qdrant
  retrieval paths.
- Qdrant eligibility scans request only `laptop_id` instead of full payloads.
- Added `laptop_metadata.parquet`, containing one filterable row per laptop.
- Qdrant deployments use the local laptop sidecar for hard-filter eligibility
  and retain Qdrant for source payload retrieval.

### Request Path

- Global pre-filter candidate diagnostics are now opt-in through:

```json
{
  "include_diagnostics": true
}
```

- Normal requests avoid the duplicate global laptop search and metadata fetch.
- Added `timings_ms` to retrieval responses for stage-level profiling.

## Controlled Benchmark Results

| Index | Before p50 | After p50 | p50 Reduction | Speedup | Before p95 | After p95 | p95 Reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Flat | 552.658 ms | 128.604 ms | 76.7% | 4.30x | 698.341 ms | 211.406 ms | 69.7% |
| IVF Flat | 582.898 ms | 49.949 ms | 91.4% | 11.67x | 690.046 ms | 77.826 ms | 88.7% |
| PQ | 452.876 ms | 56.937 ms | 87.4% | 7.95x | 584.353 ms | 78.142 ms | 86.6% |
| IVF PQ | 456.498 ms | 51.629 ms | 88.7% | 8.84x | 558.112 ms | 78.298 ms | 86.0% |
| HNSW | 563.200 ms | 53.682 ms | 90.5% | 10.49x | 684.384 ms | 105.558 ms | 84.6% |

Flat carries more cold embedding and exact-vector work. HNSW and IVF Flat now
provide the best quality/latency combination in this controlled evaluation.

## Quality Preservation

The optimized run preserved the baseline metrics exactly after a cache
correctness check:

| Metric | Flat | IVF Flat | PQ | IVF PQ | HNSW |
| --- | ---: | ---: | ---: | ---: | ---: |
| Precision@5 | 0.095 | 0.095 | 0.070 | 0.070 | 0.095 |
| Recall@5 | 0.095 | 0.095 | 0.070 | 0.070 | 0.095 |
| nDCG@5 | 0.112 | 0.112 | 0.083 | 0.086 | 0.114 |
| MRR | 0.243 | 0.243 | 0.182 | 0.207 | 0.247 |
| Candidate Recall@20 | 0.140 | 0.135 | 0.125 | 0.125 | 0.140 |
| Hard-filter satisfaction | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Unique candidate rate | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Final subset rate | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Outlier rejection | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

The relevance labels are still Flat-KNN pseudo-labels. They prove behavior was
preserved by optimization, not final human relevance quality.

## Warm Stage Timing

Representative HNSW warm timings from the optimized Docker/Qdrant run:

| Stage | Average |
| --- | ---: |
| Query parsing | 0.342 ms |
| Cached embedding lookup | 0.470 ms |
| Laptop metadata filtering | 5.874 ms |
| Laptop vector search | 22.324 ms |
| Laptop metadata fetch | 7.970 ms |
| Chunk vector scoring | 17.449 ms |
| Filtering and final reranking | 16.172 ms |

The difference between total endpoint latency and retrieval timing is roughly
3-4 ms, indicating that FastAPI/Pydantic JSON overhead is no longer a major
bottleneck for the default response.

## Live Qdrant Verification

The same HNSW request was executed twice in Docker against Qdrant Cloud.

### Before laptop metadata sidecar

```text
cold retrieval: 6273.540 ms
warm retrieval: 3354.488 ms
warm metadata filter: 3128.421 ms
```

### After laptop metadata sidecar

```text
cold retrieval: 3701.576 ms
warm retrieval: 75.534 ms
warm metadata filter: 3.809 ms
```

This isolated change produced:

```text
cold reduction: 41.0%
warm reduction: 97.7%
warm speedup: 44.41x
```

The cold request still fetches source payloads for unseen candidates from
Qdrant. The warm request reuses the bounded source payload cache.

## Response Timing Example

Optimized responses now expose:

```json
{
  "timings_ms": {
    "parse": 0.342,
    "embedding": 0.470,
    "metadata_filter": 5.874,
    "laptop_search": 22.324,
    "metadata_fetch": 7.970,
    "chunk_score": 17.449,
    "filter_and_rerank": 16.172
  }
}
```

Docker timing differs from in-process timing because the container and host
share CPU and because Qdrant source payloads cross the network.

## Remaining Opportunities

1. Create a compact local `laptop_id -> chunk vector IDs` artifact and fetch
   Qdrant source text only for the reranked top 20, not the initial top 100.
2. Precompute CPU, GPU, display, and battery component scores in the laptop
   artifact to reduce request-time string parsing.
3. Add a compact response mode that omits candidate metadata and source text
   unless diagnostics are requested.
4. Benchmark GPU embedding inference if a CUDA device is available.
5. Run controlled cold-start, concurrency, and Qdrant-region latency tests.

## Verification

```text
32 automated tests passed
225 optimized evaluation requests completed
0 evaluation errors
all quality and constraint invariants preserved
Docker Qdrant request returned 20 unique candidates and 5 final recommendations
```
