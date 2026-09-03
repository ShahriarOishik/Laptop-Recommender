# Laptop Recommender System

A Retrieval-Augmented Generation (RAG) laptop recommendation system built for
CSE488 (Big Data Analytics). Natural-language requests like *"lightweight
laptop under $800 for college"* are parsed into structured constraints,
retrieved against a FAISS/Qdrant vector index over 8,485 real laptop
listings, re-ranked with transparent price/spec/preference scoring, and
answered with an LLM-generated, citation-backed explanation — never a
free-floating, ungrounded answer. It exists to demonstrate an end-to-end big
data + RAG pipeline: deduplication and chunking with Apache Spark, embedding
with `BAAI/bge-base-en-v1.5`, multiple FAISS index types benchmarked against
each other, and a production-shaped FastAPI + React application on top.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-open-ec4899?style=for-the-badge&logo=vercel&logoColor=white)](https://laptop-recommender.vercel.app)
[![Repository](https://img.shields.io/badge/Repository-GitHub-4f46e5?style=for-the-badge&logo=github&logoColor=white)](https://github.com/ShahriarOishik/Laptop-Recommender)

## Live Demo

[Open the deployed laptop recommender](https://laptop-recommender.vercel.app)

## Technical Stack

| Area | Technologies |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| Backend | Python, FastAPI, Uvicorn |
| Retrieval | Sentence Transformers, BAAI/bge-base-en-v1.5, FAISS, Qdrant |
| Data Processing | Apache Spark, pandas, PyArrow |
| AI Providers | Groq, Gemini, OpenRouter |
| Delivery | REST, Server-Sent Events, GitHub Actions |

## Dependencies

### Backend

Install the pinned dependency ranges from `Backend/requirements.txt`:

- FastAPI and Uvicorn
- Pydantic
- NumPy, pandas, and PyArrow
- FAISS and Qdrant Client
- Sentence Transformers
- HTTPX and python-dotenv

### Frontend

Install the dependencies from `Frontend/package.json`:

- React and React DOM
- React Router and TanStack React Query
- Tailwind CSS
- Lucide React and clsx
- TypeScript, Vite, Vitest, and Testing Library

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Installation Guide](#installation-guide)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)
  - [Backend Environment Variables](#backend-environment-variables)
  - [Frontend Environment Variables](#frontend-environment-variables)
- [Running Tests](#running-tests)
- [Rebuilding Data Artifacts](#rebuilding-data-artifacts)
- [Reports & Documentation](#reports--documentation)
- [Contributing Guidelines](#contributing-guidelines)
- [License](#license)

## Features

- **Hybrid retrieval** — semantic (text only), filter-only (structured
  constraints only), and hybrid (both) search modes, each with its own
  tuned ranking blend of semantic similarity, spec/value quality, price fit,
  and soft preferences.
- **Budget-aware, not budget-blind** — a stated price ceiling is treated as a
  strong preference: if too few laptops fit exactly, the search widens the
  price band slightly and still ranks in-budget options first.
- **Grounded, cited answers** — every recommendation traces back to the
  specific retrieved chunk it came from; the LLM is never asked to invent
  a laptop that wasn't retrieved.
- **Resilient 3-tier LLM fallback** — Groq → Gemini → OpenRouter, each with
  retries, a per-provider time budget, and a circuit breaker so a degraded
  provider is skipped instead of re-discovered on every request. With no
  keys configured at all, the API still returns a deterministic,
  retrieval-only grounded answer.
- **Conversational follow-ups** — "why is the first one better?", "make it
  cheaper", "no GPU requirement anymore" are handled from conversation state
  without needing to re-describe the whole request.
- **Streaming responses** — recommendation cards render as soon as retrieval
  finishes, while the LLM explanation streams in afterward over SSE.
- **5 benchmarked FAISS index types** (flat, IVF-flat, PQ, IVF-PQ, HNSW) plus
  optional Qdrant Cloud, so retrieval-quality/latency trade-offs are
  measurable, not assumed.

## Architecture

```
                         ┌─────────────────────────┐
                         │   React 19 + TypeScript  │
                         │   (Frontend/)            │
                         └────────────┬─────────────┘
                                      │ REST + SSE
                         ┌────────────▼─────────────┐
                         │       FastAPI             │
                         │       (Backend/)          │
                         │                           │
                         │  parser → intent → gate   │
                         │  → retrieval → generation │
                         └─────┬───────────────┬─────┘
                               │               │
                 ┌─────────────▼───┐   ┌───────▼──────────────┐
                 │ FAISS / Qdrant  │   │ Groq → Gemini →       │
                 │ (BGE embeddings)│   │ OpenRouter (circuit-  │
                 │                 │   │ breaker + budgets)    │
                 └─────────────────┘   └───────────────────────┘
```

The dataset (`Dataset/`) is deduplicated and chunked with Apache Spark
(`Notebook/`), embedded with `sentence-transformers`, and indexed into FAISS
and Qdrant (`Backend/scripts/`). See `Backend/README.md` for the full
retrieval pipeline and `Notebook/IVF_Flat_Indexing_Justification.docx` for
the index-selection rationale.

## Project Structure

```
CSE488 Project/
├── Backend/            FastAPI RAG API (retrieval, generation, chat)
│   ├── app/            Application code (routers, services, models)
│   ├── scripts/        Data pipeline: dedup, chunk, embed, index, evaluate
│   ├── tests/          unittest suite
│   └── artifacts/      FAISS indexes + metadata (built locally, gitignored)
├── Frontend/            React 19 + TypeScript + Vite SPA
│   └── src/            Components, pages, services, tests
├── .github/workflows/   CI (lint, type-check, test, build)
├── Dataset/             Raw laptop listing dataset
├── Notebook/            Spark dedup/chunking + FAISS benchmarking notebook
├── description/         Generated evaluation/metrics reports
└── Term_Project_Description.pdf   Original assignment brief
```

## Installation Guide

### Prerequisites

- Python 3.11+ (developed on 3.13)
- Node.js 20+ and npm
- Git

### Backend Setup

```bash
cd Backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env        # Windows; use `cp` on macOS/Linux
```

Fill in `.env` (see [Configuration](#configuration)). Then either build the
data artifacts yourself (see [Rebuilding Data Artifacts](#rebuilding-data-artifacts))
or point `ARTIFACT_BASE_URL`/`LOCAL_METADATA_FILE` at a pre-built copy —
`Backend/artifacts/*.index` and the large `*.parquet` files are not committed
to this repository (see `Backend/.gitignore`).

```bash
uvicorn app.main:app --host 0.0.0.0 --port 7860
```

The API is now at `http://localhost:7860`, with interactive docs at `/docs`.

### Frontend Setup

```bash
cd Frontend
npm install
copy .env.example .env.local   # Windows; use `cp` on macOS/Linux
npm run dev
```

The app is now at `http://localhost:5173` and expects the backend at the URL
set in `VITE_API_BASE_URL` (default `http://localhost:7860`).

## Usage Examples

**Ask for a recommendation (non-streaming):**

```bash
curl -X POST http://localhost:7860/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "lightweight laptop under $800 for college"}'
```

**Combine free text with structured filters (hybrid search):**

```bash
curl -X POST http://localhost:7860/chat \
  -H "Content-Type: application/json" \
  -d '{
        "message": "quiet laptop for programming",
        "filters": {"max_price_usd": 1200, "min_ram_gb": 16}
      }'
```

**Follow up in the same conversation:**

```bash
curl -X POST http://localhost:7860/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "why is the first one better?", "conversation_id": "<id from previous response>"}'
```

**Stream a response (Server-Sent Events):**

```bash
curl -N -X POST http://localhost:7860/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "gaming laptop with RTX graphics under $1500"}'
```

**Browse laptops directly:**

```bash
curl "http://localhost:7860/laptops?min_ram_gb=16&max_price_usd=1500&limit=10"
```

In the UI (`http://localhost:5173`), the same flows are available through the
chat panel (type a request, or use `/suggest <text>` to force a fresh search
using the current filter panel), the **Explore** page for direct browsing and
filtering, and **Compare**/**Shortlist** for side-by-side evaluation.

## Configuration

### Backend Environment Variables

Copy `Backend/.env.example` to `Backend/.env` and fill in as needed — every
variable has an inline comment there. The most relevant ones:

| Variable | Purpose | Default |
|---|---|---|
| `PORT` | API port | `7860` |
| `EMBEDDING_MODEL` | Sentence-transformers model for query/document embeddings | `BAAI/bge-base-en-v1.5` |
| `DEFAULT_INDEX` | Which FAISS index to search by default | `hnsw` |
| `ARTIFACT_DIR` / `ARTIFACT_BASE_URL` | Local path or remote URL for FAISS indexes/metadata | `./artifacts` |
| `METADATA_BACKEND` | `parquet` (local file) or `qdrant` | `parquet` |
| `QDRANT_URL` / `QDRANT_API_KEY` | Qdrant Cloud connection (optional; local dev works without it) | unset |
| `GROQ_API_KEY` / `GROQ_MODEL` | 1st LLM fallback tier | unset |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | 2nd LLM fallback tier | unset |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | 3rd LLM fallback tier (free-tier model) | unset |
| `LLM_PROVIDER_BUDGET_SECONDS` | Max seconds spent on one provider before falling through | `15` |
| `LLM_CIRCUIT_FAILURE_THRESHOLD` / `LLM_CIRCUIT_COOLDOWN_SECONDS` | Circuit breaker tuning | `3` / `30` |
| `CACHE_ENABLED` | Semantic response cache | `true` |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins | `http://localhost:3000,http://localhost:5173` |

**No LLM key is required to run the API.** Without any of `GROQ_API_KEY`,
`GEMINI_API_KEY`, or `OPENROUTER_API_KEY` set, `/chat` still returns a
grounded, retrieval-only answer built directly from the retrieved evidence.

### Frontend Environment Variables

Copy `Frontend/.env.example` to `Frontend/.env.local`:

| Variable | Purpose | Default |
|---|---|---|
| `VITE_API_BASE_URL` | Backend base URL | `http://localhost:7860` |
| `VITE_USE_MOCK_API` | Run against a built-in deterministic mock instead of the real backend | `false` |

## Running Tests

**Backend** (from `Backend/`, with the virtualenv activated):

```bash
python -m unittest discover -s tests -p "test_*.py"
```

**Frontend** (from `Frontend/`):

```bash
npm test          # single run
npm run test:watch # watch mode
```

CI runs the frontend suite automatically on every push/PR via
`.github/workflows/ci.yml`.

## Rebuilding Data Artifacts

The FAISS indexes and metadata files under `Backend/artifacts/` are not
committed (several are 100–220 MB). To rebuild them locally from
`Dataset/imputed_dataset.csv`:

```bash
cd Backend
pip install -r requirements-tools.txt
python scripts/deduplicate_chunks.py
python scripts/build_artifacts.py --chunks ../Notebook/vector_db_artifacts/deduplicated_chunks
```

Optionally build FP-Growth insights and upload to Qdrant Cloud:

```bash
python scripts/build_fp_growth.py
python scripts/upload_qdrant.py --recreate
```

See `Backend/README.md` for the full data pipeline, deployment notes, and API
reference.

## Reports & Documentation

Beyond the code, this repo carries a written record of how it was evaluated and improved —
useful if you want to understand *why* something is built the way it is, not just how to run it:

| File | What it is |
|---|---|
| `EVALUATION_REPORT.md` | Rubric-compliance + engineering audit, with live-verified numbers for retrieval quality, dataset completeness, and the artifact rebuild. |
| `AUDIT_REPORT_2026-08-23.md` | A separate, code-level audit (correctness bugs, backend↔frontend contract drift, one security finding), independent of the rubric review above. |
| `REMEDIATION_CHANGELOG.md` | What was fixed from the evaluation report, and why, in Problem → Root Cause → Fix → Outcome form. |
| `AUDIT_REMEDIATION_CHANGELOG.md` | Same format, for what was fixed from the code audit. |
| `CONTEXT_SO_FAR.md` | Running project context/decisions log. |
| `TEAM_TODO.md` | Manual steps still open — hand-labeling, index-justification doc reconciliation, data-collection methodology write-up — that need a human, not more code. |
| `OCI_DEPLOYMENT_GUIDE.md` | Beginner-friendly, step-by-step guide to deploying both backend and frontend on Oracle Cloud's Always Free tier. |
| `HUGGINGFACE_DEPLOYMENT_GUIDE.md` | Alternative free deployment guide (Hugging Face Spaces + Vercel) — no cloud capacity issues, no credit card. |

## Contributing Guidelines

1. **Bugs and feature requests** — open a GitHub Issue with clear
   reproduction steps (for bugs) or motivation (for features).
2. **Pull requests**:
   - Branch from `main`: `git checkout -b fix/short-description`.
   - Keep changes focused — one logical change per PR.
   - Add or update tests for any behavior change (`Backend/tests/`,
     `Frontend/src/**/*.test.tsx`).
   - Run the full test suite for whichever side you touched before opening
     the PR (see [Running Tests](#running-tests)).
   - Write a commit message that explains *why*, not just *what*.
3. **Code style**:
   - Backend: standard PEP 8 Python; prefer explicit, typed Pydantic models
     over loosely-typed dicts at API boundaries.
   - Frontend: TypeScript strict mode; run `npm run lint` (oxlint) before
     committing.
4. **Secrets** — never commit `.env` files or real API keys. Use
   `.env.example` to document new variables.

## License

Released under the [MIT License](LICENSE).
