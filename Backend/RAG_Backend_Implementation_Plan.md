# RAG Backend Implementation Plan

## Scope

The backend recommends laptops only. It uses `BAAI/bge-base-en-v1.5` for
normalized 768-dimensional embeddings, FAISS for similarity retrieval, and
Qdrant Cloud for persistent vectors, metadata filtering, and source payloads.

## Retrieval

1. Parse explicit metadata constraints and semantic preferences.
2. For filter-only requests, apply frontend filters to all metadata without embedding
   or FAISS, then return deterministic laptop-level results.
3. For semantic requests, embed the query with BGE and search the selected FAISS index.
4. For hybrid requests, prefilter the complete metadata set and constrain FAISS to the
   approved vector IDs before ranking.
5. Reject an outlier query when its best score is below the calibrated threshold.
6. Remove individual candidates below that threshold.
7. Preserve hard UI filters and locked `must`, `required`, or `only` constraints.
8. Group chunks by `laptop_id`, preserve semantic ranking, and return up to five laptops.
9. Generate a source-grounded answer with Groq, falling back to Gemini, then
   OpenRouter, and finally retrieval-only output.

IVF Flat is the default. Flat IP, PQ, IVF+PQ, and HNSW can be selected per
frontend request. IVF indexes accept `nprobe`; HNSW accepts `ef_search`.

## Shared IDs

Every chunk receives a deterministic integer `vector_id`. That value is used by
all FAISS indexes and as the Qdrant point ID. The original `chunk_id` and
`laptop_id` remain in the payload and mapping Parquet file.

## Stretch Goals

Spark FP-Growth runs offline over laptop-level specification transactions and
publishes association rules through `/insights/specifications`. An in-memory
semantic LRU cache reuses responses only when filters, index settings, dataset
version, prompt version, and model version are compatible.

## Data processing and evaluation

Spark MinHashLSH runs before artifact rebuilding and writes duplicate-pair, group,
and metrics artifacts. The current conservative policy only removes near-duplicate
chunks within the same laptop and chunk type so identical review language across
different products does not erase valid recommendations.

Use at least 30 hand-labeled laptop queries plus unrelated outlier queries.
Measure precision and recall at 1, 3, and 5; p50 and p95 latency; filter
satisfaction; average relaxation level; five-result success rate; outlier false
accept/reject rates; cache hit rate; and cache latency improvement for all five
indexes.

## Deployment

The same Docker image runs on Hugging Face Spaces, Render, or another container
host. Platform differences are environment variables only. Indexes may be
bundled in `artifacts/`, mounted, or downloaded lazily through
`ARTIFACT_BASE_URL`.

Full review documents are not duplicated into every Qdrant point. Each point
stores its own `chunk_text` plus compact laptop specifications, summary, pros,
and cons; this preserves grounding while fitting free-tier storage more safely.
