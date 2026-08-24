# CSE488 Project Context So Far

Last updated: 2026-08-18

## Project Objective

Build a fast, explainable laptop-only RAG backend that converts natural-language
requests and structured constraints into grounded laptop recommendations.

The backend provides:

- Strict explicit metadata filtering.
- Semantic and hybrid retrieval.
- Unique-laptop FAISS candidate search.
- Chunk-level evidence reranking.
- Transparent price, preference, and specification scores.
- Groq, Gemini, or retrieval-only chat output.
- Reproducible quality and latency evaluation.

## Current Status

- The optimized laptop RAG backend implementation is complete.
- Docker container `laptop-rag-test` is healthy with Qdrant configured.
- API base URL: `http://127.0.0.1:7860`.
- Swagger UI: `http://127.0.0.1:7860/docs`.
- Embeddings, FAISS, local metadata filtering, and Qdrant are ready.
- Gemini is configured; Groq is not configured in the current environment.
- All 32 automated tests pass.
- Python compilation passes.
- The architecture and optimization reports are updated.
- The backend meets most technical RAG requirements, but the complete course
  project is not yet submission-ready because frontend integration, human
  evaluation, distributed embedding evidence, scope confirmation, and final
  reporting remain incomplete.

## Term Project Requirements Audit

The implementation was compared with `Term_Project_Description.pdf` on
2026-08-18.

| Requirement | Status | Current evidence or gap |
| --- | --- | --- |
| Minimum 1,500-2,000 devices | Pass | `Dataset/imputed_dataset.csv` contains 8,485 unique laptop rows. |
| Structured and unstructured fields | Pass | Price, CPU, RAM, storage, GPU, display, battery, summaries, pros, cons, and reviews exist. |
| Phones and laptops | Confirmed laptop-only (team decision) | The team has decided to scope this project to laptops only. The 8,485-row laptop dataset alone exceeds the rubric's combined 1,500-2,000 device minimum; no phone data was collected. |
| Data source and collection report | Missing | The dataset and Kaggle origin are referenced, but no formal collection methodology report was found. |
| Spark cleaning and normalization | Partial | The notebook uses Spark over an already KNN-imputed catalog; raw collection/cleaning evidence should be documented. |
| Spark MinHashLSH deduplication | Pass | `deduplicate_chunks.py` executed over 63,998 chunks and removed zero same-laptop, same-type near-duplicates. |
| Spark UDF/mapPartitions chunking | Pass | Paragraph-aware, token-constrained chunking is implemented with a Spark UDF. |
| Distributed `pandas_udf` embeddings | Implemented, not verified | The Linux/Colab path exists, but the recorded Windows execution mode does not prove distributed execution. |
| Embeddings and metadata in Parquet | Pass | 63,998 normalized 768-dimensional chunk embeddings are persisted. |
| FAISS indexes and comparison | Pass | Flat, IVF Flat, PQ, IVF+PQ, and HNSW artifacts and benchmark results exist. |
| Written index justification | Pass | The notebook and `IVF_Flat_Indexing_Justification.docx` contain the comparison and rationale. |
| FastAPI RAG backend | Pass | Query parsing, BGE embedding, FAISS retrieval, hard filters, reranking, and grounded generation are implemented. |
| Retrieved context shown with answer | Backend pass | Responses include source chunks and citations; frontend real-API integration is still incomplete. |
| Chat-style web frontend | Partial | React UI exists, but it defaults to mock mode and its real API contract does not match FastAPI. |
| 30 hand-labeled queries | Missing | 40 queries exist, but their relevant IDs are Flat-KNN pseudo-labels rather than human judgments. |
| Precision@k and Recall@k | Provisional | Metrics are computed correctly, but final course claims require human labels. |
| Qualitative answer evaluation | Partial | 15 answers and a rubric exist, but human reviewer scores are missing. |
| End-to-end deployment | Local only | Docker/Qdrant is healthy locally; no public Render or Hugging Face deployment exists. |
| Hybrid-search stretch goal | Pass | Explicit metadata filters constrain laptop-level FAISS retrieval. |
| FP-Growth stretch goal | Pass | 259 itemsets and 371 rules are exposed through `/insights/specifications`. |
| Semantic-cache stretch goal | Implemented | Compatible `/chat` responses can be reused; a dedicated hit-rate/latency benchmark is still desirable. |

### Frontend Integration Gap

The backend exposes:

```text
POST /retrieve
POST /chat
GET /laptops/{laptop_id}
GET /insights/specifications
```

The frontend real-API services currently expect:

```text
POST /api/recommend
GET /api/laptops
GET /api/laptops/{id}
GET /api/laptops/{id}/similar
```

The request schemas also differ: the frontend sends `query` and camelCase
filter fields, while the backend expects `message` and snake_case filters. The
frontend defaults to `VITE_USE_MOCK_API=true`, so the current UI is not yet an
end-to-end client for the real RAG backend.

## Project Layout

```text
CSE488 Project/
|- Backend/       FastAPI, retrieval services, FAISS artifacts, tests, scripts
|- Frontend/      React/Vite chat and laptop discovery interface
|- Dataset/       8,485-row imputed laptop catalog
|- Notebook/      Spark chunking/embedding notebook and ANN benchmarks
|- description/   Architecture, metrics, and optimization reports
|- BackUp/        Previous project copies
|- CONTEXT_SO_FAR.md
`- Term_Project_Description.pdf
```

Generated folders such as `.venv`, `.git`, and `__pycache__` are not part of the
logical architecture.

## Request Contract

The main retrieval request uses `message` and optional `filters`:

```json
{
  "message": "Recommend a laptop for programming",
  "filters": {
    "max_price_usd": 1200,
    "min_ram_gb": 16,
    "min_storage_gb": 512
  },
  "index_type": "hnsw",
  "top_k": 5
}
```

Important behavior:

- A top-level `semantic_query` request field is not accepted.
- The backend derives `semantic_query` from `message`.
- Unknown request and filter fields are rejected.
- `top_k` is limited to 1 through 5.
- Explicit filters are hard constraints by default.
- `allow_filter_relaxation` defaults to `false`.
- `include_diagnostics` defaults to `false`.
- Enabling `include_diagnostics` runs an additional global pre-filter search and
  populates `pre_filter_candidates`.

## Query Parsing

The parser produces:

- `original_query`: normalized original user text.
- `semantic_query`: structured values removed for semantic relevance.
- `embedding_query`: semantic text plus explicit structured constraints.
- `filters`: explicit hard constraints.
- `inferred_filters`: soft opposite price or weight bounds.
- `locked_fields`: fields that cannot be relaxed.
- `warnings`: parser and inference explanations.

Explicit constraints are used for metadata eligibility. Inferred opposite price
and weight bounds affect ranking only and never reject an otherwise eligible
laptop.

Supported filters include:

```text
min_price_usd
max_price_usd
min_ram_gb
min_storage_gb
min_weight_kg
max_weight_kg
brands
excluded_brands
gpu_tags
excluded_gpu_tags
storage_types
operating_systems
```

## Retrieval Architecture

The semantic and hybrid flow is:

1. Parse the request and separate explicit constraints from semantic intent.
2. Generate normalized BGE vectors using `BAAI/bge-base-en-v1.5`.
3. For hybrid requests, create one filter-aware vector and one semantic-only
   vector in a batched `encode_many()` call.
4. Filter eligible laptop IDs using laptop-level metadata.
5. Search up to 100 unique laptops in the selected laptop-level FAISS index.
6. Fetch all relevant source chunks for those laptops.
7. Reconstruct chunk vectors in a batch and score both query vectors against
   one shared vector matrix.
8. Pool the three strongest chunks for each laptop.
9. Apply price, soft-preference, and specification scoring.
10. Return up to 20 unique `candidate_hits` and up to 5 final recommendations.

The following invariant is enforced:

```text
every recommendation laptop_id exists in candidate_hits
```

Filter-only requests skip embeddings and FAISS and rank matching laptop metadata
deterministically.

## Data and FAISS Artifacts

Verified source and artifact counts:

```text
8,485 unique rows in Dataset/imputed_dataset.csv
63,998 chunk vectors
6,778 unique laptop vectors
```

The 8,485-row catalog satisfies the course minimum, but the current chunk and
FAISS artifacts cover 6,778 unique laptops. The 1,707-row difference should be
explained or reconciled in the data-processing report before submission.

Laptop-level indexes:

```text
laptop_flat.index
laptop_ivf_flat.index
laptop_pq.index
laptop_ivf_pq.index
laptop_hnsw.index
```

Each laptop vector is the normalized mean of that laptop's chunk vectors.
Laptop-level retrieval prevents duplicate chunks from consuming candidate
slots.

Default candidate settings:

```text
candidate_k = 20
top_k = 5
search_k = max(candidate_k * 5, top_k * 20) = 100
```

## Metadata Architecture

In Qdrant mode, the backend uses `artifacts/laptop_metadata.parquet` as a compact
6,778-row eligibility sidecar and uses Qdrant Cloud for source payloads.

This avoids scrolling and deduplicating all 63,998 chunk payloads to determine
which laptops satisfy explicit constraints. If the sidecar is missing, direct
Qdrant filtering remains available as a fallback.

In local Parquet mode, `LocalParquetMetadataStore` maintains:

- A full vector metadata frame.
- A deduplicated laptop frame for eligibility filtering.
- A precomputed `laptop_id -> vector_ids` mapping.

`HybridQdrantMetadataStore` combines local laptop filtering with Qdrant source
retrieval.

## Embedding and Retrieval Optimizations

Implemented optimizations:

- Added batched `EmbeddingService.encode_many()`.
- Added a bounded exact-text embedding cache.
- Increased `INDEX_CACHE_SIZE` from 1 to 2.
- Preloaded the default laptop and chunk FAISS index pair.
- Replaced per-vector `reconstruct()` calls with `reconstruct_batch()`.
- Added `FaissIndexManager.score_vectors_multi()`.
- Scored semantic and filter-aware queries from one reconstructed matrix.
- Reduced local hard filtering from 63,998 chunk rows to 6,778 laptop rows.
- Added the compact laptop metadata sidecar for Qdrant deployments.
- Added a bounded laptop source-payload cache.
- Removed a redundant strict-filter metadata round trip when relaxation is off.
- Made global pre-filter diagnostics opt-in.
- Added stage-level `timings_ms` to retrieval responses.

## Chunk and Laptop Scoring

Chunk score:

```text
chunk_score =
    0.65 * semantic_score
  + 0.35 * filter_aware_score
```

Top-three evidence pooling:

```text
laptop_text_score =
    0.60 * best_chunk_score
  + 0.25 * second_chunk_score
  + 0.15 * third_chunk_score
```

Final score with an explicit price constraint:

```text
final_score =
    0.55 * laptop_text_score
  + 0.20 * price_fit_score
  + 0.10 * soft_preference_score
  + 0.15 * spec_score
```

Final score without an explicit price constraint:

```text
final_score =
    0.75 * laptop_text_score
  + 0.10 * soft_preference_score
  + 0.15 * spec_score
```

Specification score weights:

```text
CPU: 30%
RAM: 20%
GPU: 20%
Storage: 15%
Display: 10%
Battery: 5%
```

Missing specification fields cause available weights to be renormalized rather
than automatically producing a zero score.

## Response Diagnostics

Retrieval responses expose total `retrieval_latency_ms` plus the stages that
were executed in `timings_ms`:

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

An additional `diagnostics` timing is present when
`include_diagnostics=true`.

## Performance Results

The controlled before/after evaluation used 225 requests across all five FAISS
families.

| Index | Baseline p50 | Optimized p50 | Reduction | Speedup |
| --- | ---: | ---: | ---: | ---: |
| Flat | 552.658 ms | 128.604 ms | 76.7% | 4.30x |
| IVF Flat | 582.898 ms | 49.949 ms | 91.4% | 11.67x |
| PQ | 452.876 ms | 56.937 ms | 87.4% | 7.95x |
| IVF PQ | 456.498 ms | 51.629 ms | 88.7% | 8.84x |
| HNSW | 563.200 ms | 53.682 ms | 90.5% | 10.49x |

Live Docker/Qdrant HNSW verification for the same repeated request:

```text
Before sidecar:
  cold retrieval: 6273.540 ms
  warm retrieval: 3354.488 ms

After all optimizations:
  cold retrieval: 3701.576 ms
  warm retrieval: 75.534 ms

Warm reduction: 97.7%
Warm speedup: 44.41x
```

The cold request can still include model, index, and uncached Qdrant payload
costs. Warm requests reuse resident indexes, cached embeddings, and cached
source payloads.

## Evaluation and Verification

Completed verification:

- 32 automated tests passed.
- Python compilation passed.
- 225 optimized evaluation requests completed with zero errors.
- Hard-filter satisfaction remained 100%.
- Candidate laptop IDs remained unique.
- Final recommendations remained a subset of candidate hits.
- Outlier rejection behavior was preserved.
- Docker readiness and live Qdrant retrieval were verified.

The evaluation relevance labels are Flat-KNN pseudo-labels. They demonstrate
that optimization preserved measured retrieval behavior, but they are not an
independent human relevance judgment.

## Known Limitations

- Independent human-labeled relevance judgments are not available.
- The outlier evaluation currently contains only five queries and should be
  expanded to at least 30.
- The frontend's real routes, request schema, and response schema do not match
  the current FastAPI contract; mock mode remains the default.
- The current retrieval artifacts contain 6,778 unique laptops from an 8,485-row
  source catalog. Root cause identified: `Notebook/vector_db_ann_retrieval.ipynb`
  never persisted the embedded chunk DataFrame before its `.count()`/`.write()`
  calls, so Spark's local[2] round-robin partitioning could re-execute the
  pipeline and silently drop an exact half of the 127,996 chunks on write —
  confirmed exact (100% match) against the 3,348 single-chunk (all-text-fields-
  null) laptops, which are the only ones that can vanish entirely under that
  split. A `.persist(StorageLevel.DISK_ONLY)` fix plus a hard write/reread
  assertion have been applied to the notebook; pending a Colab re-run to verify
  and rebuild the downstream artifacts.
- A formal dataset source, collection, cleaning, and schema report was not found.
- The project is laptop-only by team decision (see Term Project Requirements
  Audit above); the description discusses mobile and laptop recommendation, but
  the laptop dataset alone exceeds the rubric's minimum device count.
- Groq is not configured in the current environment.
- Gemini and retrieval-only fallback are available.
- Distributed `pandas_udf` execution has not been verified.
- The 15 captured generated answers have not received human rubric scores.
- Public Render or Hugging Face deployment has not been performed.
- Cold Qdrant requests remain network-bound when source payloads are uncached.
- Final team-member contribution records and external-code citations still need
  to be included in the final report.

## Important Files

| Responsibility | Path |
| --- | --- |
| Official term requirements | `Term_Project_Description.pdf` |
| Source laptop catalog | `Dataset/imputed_dataset.csv` |
| Spark chunking, embedding, and FAISS notebook | `Notebook/vector_db_ann_retrieval.ipynb` |
| ANN benchmark results | `Notebook/benchmark_results.csv` |
| ANN benchmark charts | `Notebook/Charts/` |
| FastAPI routes | `Backend/app/main.py` |
| Request and response models | `Backend/app/models.py` |
| Query parsing | `Backend/app/services/parser.py` |
| Retrieval and scoring | `Backend/app/services/retrieval.py` |
| FAISS management | `Backend/app/services/faiss_manager.py` |
| Embeddings and embedding cache | `Backend/app/services/embeddings.py` |
| Local metadata backend | `Backend/app/services/local_metadata_store.py` |
| Qdrant backend | `Backend/app/services/qdrant_store.py` |
| Hybrid metadata backend | `Backend/app/services/hybrid_metadata_store.py` |
| Chat orchestration and semantic cache | `Backend/app/services/rag.py` |
| LLM generation | `Backend/app/services/generator.py` |
| Laptop sidecar builder | `Backend/scripts/build_laptop_metadata.py` |
| Laptop index builder | `Backend/scripts/build_laptop_indexes.py` |
| Evaluation script | `Backend/scripts/evaluate_backend_metrics.py` |
| Human-label input format | `Backend/evaluation/queries.template.jsonl` |
| Current pseudo-labeled queries | `Backend/evaluation/queries.jsonl` |
| Qualitative scoring rubric | `Backend/evaluation/qualitative_review_rubric.md` |
| Existing requirements audit | `Backend/evaluation/backend_requirements_status.md` |
| Laptop metadata sidecar | `Backend/artifacts/laptop_metadata.parquet` |
| Frontend recommendation API adapter | `Frontend/src/services/recommendationService.ts` |
| Frontend laptop API adapter | `Frontend/src/services/laptopService.ts` |
| Frontend API configuration | `Frontend/src/services/apiClient.ts` |
| Architecture document | `description/RAG_Query_to_JSON_Architecture.md` |
| Optimization report | `description/performance_optimization_report.md` |
| Baseline metrics | `description/backend_metrics_report.md` |
| Optimized metrics | `description/backend_metrics_report_optimized.md` |
| Detailed optimized metrics | `description/backend_metrics_report_optimized.json` |

## Suggested Next Steps

1. Connect the React frontend to `/chat`, `/retrieve`, and `/laptops/{id}`, or
   add intentional compatibility routes and response adapters to FastAPI.
2. Create at least 30 independently human-labeled queries with graded relevant
   laptop IDs, then rerun Precision@k, Recall@k, nDCG@5, and MRR.
3. Score the 15 captured generated answers with the qualitative review rubric.
4. Run the embedding notebook with `USE_PANDAS_UDF=true` on Linux, WSL, or
   Colab and retain Spark execution evidence.
5. ~~Reconcile why 1,707 source catalog rows are absent from current retrieval
   artifacts.~~ Root cause identified and fix applied to the notebook (see
   Known Limitations above); still needs a Colab run to verify and rebuild
   `build_artifacts.py`, `build_laptop_metadata.py`, `build_laptop_indexes.py`,
   threshold calibration, FP-Growth, and the Qdrant upload against the
   corrected chunk set.
6. Write the dataset source, collection, cleaning, schema, and curation report.
7. ~~Obtain explicit approval for laptop-only scope or add mobile-phone support.~~
   Settled: team has confirmed laptop-only scope (see Term Project Requirements
   Audit above).
8. Expand the outlier set and run cold-start, concurrency, cache hit-rate, and
   Qdrant-region latency benchmarks.
9. Deploy publicly only after secrets, CORS, provider settings, citations, and
   team contribution records are reviewed.
