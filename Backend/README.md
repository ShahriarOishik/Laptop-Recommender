---
title: Laptop Recommendation RAG API
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# Laptop Recommendation RAG API

FastAPI backend using BGE embeddings, selectable FAISS indexes, Qdrant Cloud
metadata filtering, a Groq/Gemini/OpenRouter generation fallback chain,
FP-Growth insights, and semantic caching.

## Local setup

```bash
python -m venv .venv
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 7860
```

For local development, set `QDRANT_LOCAL_PATH`. For production, remove that
setting and configure `QDRANT_URL` plus `QDRANT_API_KEY`. LLM keys are optional:
without them, `/chat` returns grounded retrieval-only output.

`QDRANT_LOCAL_METADATA_ONLY=true` avoids duplicating FAISS vectors in embedded
Qdrant during local development. Cloud upload always stores the full BGE vectors.
For the fastest local startup, use `METADATA_BACKEND=parquet` with
`LOCAL_METADATA_FILE=./artifacts/qdrant_records.parquet`. The retrieval service
uses the same metadata-store interface, so production requires no code change.

## Search modes

The API derives the search mode from the request:

- Semantic: provide `message` without frontend filters.
- Filter-only: provide `filters` without `message`; this skips embeddings and FAISS.
- Hybrid: provide both `message` and `filters`; metadata filters are applied to the
  complete candidate set before constrained FAISS ranking.

Frontend filters are hard constraints. The one exception is price: if
`allow_filter_relaxation` is true (the frontend sends this by default, unless
the user turns on "Strict budget") and an exact budget matches too few
laptops, the price band is automatically widened and the response reports
this via `message` and `relaxed_filters: ["price_range"]` — never silent.
With `allow_filter_relaxation=false`, budget stays a true hard constraint and
a too-strict budget returns fewer (or zero) results instead. For example:

```json
{
  "message": "quiet laptop for programming",
  "filters": {"max_price_usd": 1200, "min_ram_gb": 16}
}
```

## Build data artifacts

Install tooling dependencies and build all indexes:

```bash
python -m pip install -r requirements-tools.txt
python scripts/build_artifacts.py
```

Run the conservative Spark MinHashLSH pass before rebuilding artifacts:

```bash
python scripts/deduplicate_chunks.py
python scripts/build_artifacts.py --chunks ../Notebook/vector_db_artifacts/deduplicated_chunks
```

Upload the generated vectors and payloads to Qdrant Cloud:

```bash
python scripts/upload_qdrant.py --recreate
```

Build FP-Growth insights:

```bash
python scripts/build_fp_growth.py
```

After the team labels at least 30 queries in the format shown by
`evaluation/queries.template.jsonl`, evaluate all five indexes against a running
backend:

```bash
python scripts/evaluate_retrieval.py evaluation/queries.jsonl
```

Generate candidate IDs for human labeling with:

```bash
python -m scripts.suggest_relevance_labels evaluation/queries.annotation.template.jsonl
```

Supporting evidence tools are available as `scripts/validate_embedding_evidence.py`,
`scripts/collect_threshold_scores.py`, and `scripts/evaluate_answers.py`.

## Deploy

- Hugging Face Spaces: create a Docker Space and upload the contents of this directory — see
  `../HUGGINGFACE_DEPLOYMENT_GUIDE.md` for a full beginner-friendly walkthrough (backend +
  frontend, free forever, no credit card).
- Render: use `render.yaml` or deploy the included `Dockerfile` (free tier's 512MB RAM is too
  small for this project's actual usage — use a paid Render plan, or one of the free guides
  above instead).
- Oracle Cloud (OCI) Always Free tier: see `../OCI_DEPLOYMENT_GUIDE.md` for a full
  beginner-friendly walkthrough (backend + frontend, no cost).
- Other Docker hosts: set `PORT`, mount or download artifacts, and provide the same secrets.

For small images, host indexes in a Hugging Face model/dataset repository and
set `ARTIFACT_BASE_URL` to its raw `resolve/main` URL. The backend downloads an
index only when it is selected.

## API

- `GET /health`
- `GET /ready`
- `GET /settings/indexes`
- `POST /retrieve`
- `POST /chat`
- `POST /chat/stream` (Server-Sent Events version of `/chat`)
- `GET /laptops` (paginated/filterable list with facets)
- `GET /laptops/{laptop_id}`
- `GET /laptops/{laptop_id}/similar`
- `GET /insights/specifications`
- `GET /cache/stats`

Interactive documentation is available at `/docs`.
