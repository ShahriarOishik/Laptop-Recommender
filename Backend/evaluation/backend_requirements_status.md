# Backend Requirements Status

Verified in-process against the local API on 2026-08-17. No persistent server is
left running after verification.

## Working and Verified

| Requirement | Status | Evidence |
|---|---|---|
| FastAPI backend | Passed | `/health`, `/ready`, `/docs`, and OpenAPI return successfully. |
| Query embedding | Passed | `BAAI/bge-base-en-v1.5` loads and returns normalized 768-dimensional vectors. |
| FAISS retrieval | Passed | Flat, IVF Flat, PQ, IVF+PQ, and HNSW all return source-backed results. |
| IVF Flat default | Passed | `/settings/indexes` reports IVF Flat as default. |
| Frontend-selectable indexes API | Passed | Every index can be selected per request with validated parameters. |
| Fixed candidate search | Passed | Every retrieval response reports `candidate_k=20`. |
| Shared stable IDs | Passed | All saved indexes reload and return IDs that map to metadata records. |
| Similarity threshold | Passed | Weak candidates are removed and an unrelated recipe query is rejected. |
| Query parser | Passed | Structured constraints are extracted into filters and removed from `semantic_query`; explicit constraints are strict by default. |
| Metadata filtering | Passed | Numeric, keyword, and exclusion filters work locally and in constrained hybrid retrieval. |
| True hybrid retrieval | Passed | Frontend hard filters prefilter all eligible vector IDs before constrained FAISS ranking. |
| Filter-only retrieval | Passed | Requests containing only frontend filters skip embeddings and FAISS. |
| Progressive relaxation | Passed | Relaxable fields are removed in passes until five unique laptops are found. |
| Locked constraints | Passed | UI and mandatory constraints survive every relaxation pass. |
| Laptop deduplication | Passed | Final results are grouped by `laptop_id`. |
| Source context | Passed | Every recommendation contains source chunk IDs, text, and similarity scores. |
| Grounded prompt construction | Passed | Generator receives only retrieved records and source chunks. |
| Groq to Gemini fallback logic | Passed by automated test | Simulated Groq failure invokes Gemini successfully. |
| Retrieval-only fallback | Passed | Local chat works without external LLM keys. |
| Semantic cache | Passed | Repeated compatible chat requests produce cache hits. |
| FP-Growth endpoint | Passed | 259 itemsets and 371 rules were generated; API returns rule fields. |
| Laptop detail endpoint | Passed | `/laptops/{laptop_id}` returns only the requested laptop's chunks. |
| Input validation | Passed | Invalid index names, `top_k`, and `nprobe` values return HTTP 422. |
| Artifact integrity | Passed | All five rebuilt indexes contain 63,998 vectors and reload successfully; IVF indexes have direct maps for constrained search. |
| Spark MinHashLSH execution | Passed with no removals | `scripts/deduplicate_chunks.py` ran on the chunk artifact; no near-duplicates were found within the same laptop and chunk type. |
| Embedding artifact validation | Passed | 63,998 non-null normalized 768-dimensional embeddings validated by `scripts/validate_embedding_evidence.py`. |
| Distributed pandas UDF evidence | Not verified locally | The notebook contains the pandas UDF path, but this Windows run is recorded as `execution_mode=unknown`; a Linux/WSL/Colab run is still required for distributed execution evidence. |
| Threshold calibration | Calibrated provisionally | Per-index thresholds were written from 225 in-domain/outlier classification queries; final retrieval evaluation still requires human relevance labels. |

## Implemented but Not Live-Tested

| Requirement | Status | Reason |
|---|---|---|
| Qdrant Cloud adapter | Passed | Collection `laptop_chunks` contains 63,998 points with 768-dimensional Cosine vectors; Qdrant acceptance report passed 22/22. |
| Live Groq generation | Blocked externally | Direct provider verification returned HTTP 404; rotate the exposed key and confirm a currently supported model. |
| Live Gemini generation | Blocked externally | Direct provider verification returned HTTP 404; rotate the exposed key and confirm a currently supported model. |
| Docker deployment | Passed locally | Image built as `laptop-rag-api`; Qdrant-backed container health and 22/22 HTTP acceptance checks passed. |

## Still Required for Course Completion

| Requirement | Status | Required action |
|---|---|---|
| 30 hand-labeled retrieval queries | KNN pseudo-labels available; human labels still required | `evaluation/queries.jsonl` contains 40 exact Flat KNN labels and explicitly marks them as pseudo-labels. |
| Precision@k and recall@k on human relevance labels | Provisional only | `evaluation/retrieval_results_knn_pseudo.csv` was generated, but these scores are not independent because labels came from KNN. |
| Threshold calibration | Complete provisionally | `artifacts/calibrated_thresholds_final.json` and calibrated manifest values were generated from the final query/outlier score set. |
| Qualitative generated-answer evaluation | Captured, not scored | `evaluation/qualitative_answers.jsonl` contains 15 responses; live calls fell back to retrieval-only and reviewer scores are still needed. |
| Online deployment | Not run | Local Docker validation passed; no public Render/Hugging Face deployment was created. |
| Laptop-only scope approval | Needs confirmation | The term description requests phones and laptops; this implementation is laptop-only. |

## Verification Commands

```text
python -m unittest discover -s tests -v
python scripts/check_backend.py
```

Latest result: 25 automated tests passed, 22 Parquet acceptance checks passed, and 22 Qdrant/Docker HTTP acceptance checks passed.
