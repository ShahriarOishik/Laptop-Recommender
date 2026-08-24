Remediation Changelog

Chronological record of every change made to this project during the evaluation +
remediation pass, why it was made, exactly how, and the verified outcome. Companion document
to `EVALUATION_REPORT.md` (the rubric/audit assessment) — this file is the "what actually
happened" log.

---

## 1. Chunk-count drop (127,996 → 63,998 chunks)

**Problem:** `Notebook/vector_db_ann_retrieval.ipynb` reported 127,996 chunks after
chunking+embedding, but only 63,998 survived a parquet write/reread — exactly half.

**Root cause found:** Spark's `local[2]` round-robin partitioning applied to a
never-persisted DataFrame let the embed+write pipeline silently re-execute a second time on
write. A laptop with ≥2 chunks always survives (representatives land in both partitions); only
single-chunk laptops (all of review/summary/pros/cons null) could vanish entirely.
**Confirmed, not guessed**: a free local set-intersection check showed all 1,707 laptops
missing from the artifacts were *exactly* the 3,348 all-fields-null laptops — 100% match, zero
exceptions.

**Fix:** Added `.persist(StorageLevel.DISK_ONLY)` right after the embedding step in
`Notebook/vector_db_ann_retrieval.ipynb`, before any `.count()`/`.write()` could re-trigger the
pipeline, plus a hard assertion comparing pre-write and post-write-reread row counts.

**Outcome (live-verified):** Re-ran the full notebook — **127,996 / 127,996 rows survived**,
assertion passed, 0 rows lost.

---

## 2. Google Drive write reliability (found while fixing #1)

**Problem:** After the fix above, the in-session write/reread assertion passed, but a
*separate* Colab session later failed reading the same file from Drive with
`Parquet file size is 0 bytes` on one part-file.

**Root cause found:** Writing large distributed Spark parquet output directly to Google
Drive's FUSE mount is unreliable — the in-session read was served from a local cache that
never fully synced to Drive's actual cloud storage before the runtime ended.

**Fix:** Changed the notebook so Spark writes to local Colab disk first
(`/content/vector_db_artifacts`), then a separate cell copies the already-complete, verified
file to Drive as a plain atomic `shutil.copytree`, with its own independent non-zero-byte
check. Extended the same pattern to the secondary outputs (`chunks_preview.csv`,
`benchmark_results.csv`, `charts/`), which had the same exposure but hadn't yet failed.

**Outcome (live-verified):** Re-ran the full pipeline end-to-end — printed confirmation
`copied chunks.parquet to Drive: ... (434.9 MB across 2 part files)`, and the downstream
rebuild notebook successfully read this file with no errors.

---

## 3. Duplicate chunk texts depressing recall (34,838–76,210 of ~64–128K chunks)

**Problem:** ~55–60% of chunks are exact-duplicate text shared across *different* laptops
(near-identical listing variants), and the notebook's own recall@k benchmark penalized an
index for retrieving the "other" identical copy of a duplicate — the notebook's own words:
recall "tie-depressed."

**Investigation:** Traced the actual retrieval code (`Backend/app/services/retrieval.py`,
`main.py`'s `/laptops/{id}` route) before deciding on a fix. Found that deleting duplicate
rows (the obvious-looking fix) would silently remove real content from whichever laptop
doesn't keep the "canonical" copy, breaking that laptop's own detail page — for no retrieval
benefit, since production search is per-laptop (mean-pooled vectors, top-3 chunks only) and
cross-laptop duplicates can never compete for a slot there. The harm is purely a benchmark
artifact.

**Fix:** Changed recall@k/precision@k scoring in the benchmark cells (Qdrant-vs-FAISS check,
the nprobe/efSearch parameter sweeps, and the main benchmark) to compare duplicate-text
**group membership** instead of literal chunk identity, normalized by the count of distinct
groups being compared against (not raw k) — so a perfect index still scores exactly 1.0
against itself even with internal ties. No chunk data was touched.

**Outcome (live-verified):**
- Qdrant-vs-FAISS-exact recall@10: **0.7560 → 1.0000**; self-hit@1: **0.4100 → 1.0000**.
- Main benchmark mean recall@10 across 5 indexes: **~0.79–0.83 → 0.943**; recall now
  saturates at k=1 (0.964).

---

## 4. Dataset/artifact gap (8,485 dataset rows vs. 6,778 laptops in artifacts)

**Problem:** 1,707 laptops present in `Dataset/imputed_dataset.csv` never appeared in the
built FAISS/laptop artifacts.

**Root cause:** Same as #1 — a 20-row sample showed 100% null-review, consistent with the
round-robin partition loss hitting single-chunk laptops. Confirmed by the exact 1,707-laptop
set-intersection match in #1's investigation.

**Fix:** None needed beyond #1 — fixing the chunk-write bug fixed this automatically once the
artifacts were rebuilt.

**Outcome (live-verified):** Post-rebuild `index_manifest.json` reports
**`laptop_vector_count: 8485`** (was 6,778); independently confirmed by
`laptop_metadata.parquet` reporting 8,485 unique `laptop_id`s. All 5 main + 5 per-laptop FAISS
indexes now cover the complete dataset.

---

## 5. Circular FAISS index-selection logic (M3 rubric deliverable)

**Problem:** The notebook's "final index choice" logic always picked Flat, because Flat *is*
the ground truth used to compute every other index's recall (guaranteed exactly 1.0 against
itself). The accompanying prose argued Flat was "unnecessary for a served chatbot" in the same
paragraph that recommended it — internally contradictory, and unrelated to the actual
IVF/HNSW numbers.

**Fix (applied by the user, based on a suggested approach):** Changed the selector from
"highest recall@10, tie-broken by latency" (which never actually reaches the tie-break, since
Flat is never truly tied) to "require recall@10 ≥ 0.95, then pick the fastest index that
clears that bar."

**Outcome (live-verified):** Selector now correctly picks **HNSW**: 99.38% recall@10 at
0.95ms p50 (vs. Flat's 100% at 35.52ms) — a real, defensible, non-circular production choice,
matching what the surrounding prose had been arguing for all along.

**Known remaining inconsistency (not fixed, by team's choice):** the standalone
`Notebook/IVF_Flat_Indexing_Justification.docx` filename implies IVF Flat was chosen — still
disagrees with the notebook's actual (now-correct) conclusion. Team chose to reconcile this
prose themselves.

---

## 6. Missing `numpy` import in `build_laptop_indexes.py`

**Problem:** Found live during the artifact rebuild — `Backend/scripts/build_laptop_indexes.py`
uses `np.sqrt(...)` but never imports `numpy`, failing immediately with
`NameError: name 'np' is not defined` on every real (fresh-subprocess) invocation.

**Fix:** Added `import numpy as np` to the script.

**Outcome (verified):** Re-ran `build_laptop_indexes.py` — completed successfully, all 5
per-laptop indexes built (8,485 vectors each).

---

## 7. Backend artifact rebuild

**What:** Rebuilt everything downstream of the corrected `chunks.parquet`:
`build_artifacts.py` (5 main FAISS indexes + `qdrant_records.parquet` +
`vector_id_mapping.parquet`), `build_laptop_metadata.py` (`laptop_metadata.parquet`),
`build_laptop_indexes.py` (5 per-laptop FAISS indexes), `build_fp_growth.py` (association
rules), and `scripts/upload_qdrant.py --recreate` (Qdrant Cloud re-upload).

**Why:** All of these were built from the old, incomplete 63,998-chunk/6,778-laptop data and
needed regenerating against the corrected 127,996-chunk/8,485-laptop data.

**Outcome (live-verified):**
- `vector_count: 127996`, `laptop_vector_count: 8485` in the rebuilt manifest.
- All 10 index files (5 main + 5 per-laptop) built with correct sizes.
- `Qdrant collection 'laptop_chunks' contains 127996 points` — exact match after re-upload.
- Rebuilt artifacts downloaded and swapped into local `Backend/artifacts/`; the previous
  (stale) artifacts backed up to `archive/old_artifacts/` rather than deleted.

---

## 8. Rate limiter hit during offline threshold calibration

**Problem:** `scripts/collect_threshold_scores.py` fires ~225 rapid `/retrieve` calls in a
tight loop (5 index types × ~45 queries). The backend's own rate limiter (20 requests per 60s,
`app/config.py`, meant for real end-user traffic) started returning `429 Too Many Requests`
after the 20th call, crashing the script before it could write its output — which then cascaded
into `FileNotFoundError` in the two downstream cells that read that output.

**Fix:** Set `RATE_LIMIT_ENABLED=false` for this specific offline batch-evaluation run only —
not a change to the app's real defaults.

**Outcome (live-verified):** Full chain completed cleanly — 225/225 scores collected, no
errors.

---

## 9. Threshold recalibration

**What:** Regenerated `Backend/artifacts/calibrated_thresholds.json` against the corrected
vector space, using `scripts/collect_threshold_scores.py` + `scripts/calibrate_thresholds.py`
against the 40 in-domain queries + outlier set.

**Important clarification found during this work:** neither `calibrated_thresholds.json` nor
`calibrated_thresholds_final.json` is actually read by the running application — the real,
live threshold values come from `index_manifest.json`'s own `similarity_thresholds` field
(read by `app/services/faiss_manager.py`), which was already correctly regenerated as part of
the artifact rebuild (#7). `calibrated_thresholds.json` is evidence/documentation only.
`calibrated_thresholds_final.json` has zero references anywhere in the codebase — left alone,
since nothing depends on it and its original purpose is unknown.

**Outcome (live-verified):** All 5 indexes report **f1 = precision = recall = 1.0** against
the labeled query set. File placed at `Backend/artifacts/calibrated_thresholds.json`.

---

## 10. Hand-labeled query worksheet (rubric requires ≥30 hand-labeled queries)

**What:** Regenerated `Backend/evaluation/queries.labeling.jsonl` (via
`scripts/suggest_relevance_labels.py`) against the corrected artifacts, then built
`Backend/evaluation/query_labeling_worksheet.csv` — one row per query, 5 candidates each with
resolved brand/model/price/CPU/GPU/RAM/storage details, plus blank Y/N columns for marking
relevance.

**Why not fully completed here:** Actual relevance judgment is a human call that shouldn't be
fabricated or approximated — the worksheet exists so the team's actual labeling work is just
filling in Y/N, not building the lookup infrastructure from scratch.

**Outcome (verified):** 40/40 queries, 5 candidates each, **0 unresolved candidate lookups**
against the corrected 8,485-laptop metadata.

---

## 11. Qualitative answer scoring sheet

**What:** Merged the 15 captured `/chat` answers (`qualitative_answers.jsonl`) with the
existing scoring rubric's 10 criteria into `Backend/evaluation/qualitative_scoring_sheet.csv`
— one row per answer, one blank column per criterion, plus the answer text and cited sources
for context.

**Why not fully completed here:** Same reasoning as #10 — scoring quality/hallucination/
grounding is a human judgment call.

**Outcome:** Sheet generated, verified to open cleanly with all 15 rows and 10 rubric columns.

---

## 12. Data-collection methodology draft (rubric requires this report)

**What:** Drafted `Backend/evaluation/data_collection_methodology.md` stating the confirmed
facts (public dataset baseline + team's own scraped data, 8,485 rows / 27 columns), with
explicit `[TODO]` placeholders for details only the team has (exact public source, scraping
site/tool, date range, source-reconciliation method).

**Why not fully completed here:** The specific facts needed weren't available — asked the user
directly rather than inventing plausible-sounding details.

**Outcome:** Draft exists, ready for the team to fill in the marked gaps.

---

## 13. Scope decision documented as settled

**What:** Updated `CONTEXT_SO_FAR.md` (the rubric-audit table, the known-limitations list, and
the suggested-next-steps list) and the evaluation report to state laptop-only scope as a final
team decision, with the rationale that the laptop dataset alone exceeds the rubric's combined
device-count minimum — removed "needs confirmation" framing.

**Outcome:** Documentation now consistent with the team's actual decision; no longer reads as
an open question.

---

## 14. Documentation fixes (stale docs vs. actual code)

Reviewed interactively with the user before applying, in order:

1. **`Frontend/README.md`** — full rewrite. Removed false claims that mock mode is the
   default (`.env.example` actually defaults to `VITE_USE_MOCK_API=false`) and that no test
   suite/CI exists (5 Vitest files + a working GitHub Actions workflow exist). Regenerated the
   entire "Backend API Contract" section from the real DTOs in `src/types/api.ts` and the real
   service code — the old version documented a fictional `/api/recommend` contract matching
   neither the real backend nor the actual frontend code (a leftover from when the frontend was
   a separate standalone repo). Fixed the clone instructions (same monorepo now, not a separate
   repo) and the license claim (root MIT `LICENSE`, not "unspecified").
2. **`Backend/README.md`** — added the OpenRouter third LLM fallback tier (code already had it,
   docs didn't) and the three missing documented endpoints (`/chat/stream`, `/laptops`,
   `/laptops/{id}/similar`).
3. **`RAG_Backend_Implementation_Plan.md`** — same OpenRouter-tier fix.

**Outcome:** All five originally-scoped doc issues fixed and verified against the actual code
each claim refers to.

---

## 15. Frontend run and manual verification

**What:** Installed frontend dependencies, started the Vite dev server, and drove the UI via
browser automation (not just launched) — clicked a suggested prompt and confirmed a full
recommendation flow rendered correctly (5 ranked laptops, match scores, "why this matches"
reasoning with met/partial/unmet requirement badges, refine buttons, follow-up questions),
verified via both the accessibility tree and a visual screenshot.

**Why mock mode:** No local backend was started for this — doing so would load the ~440MB BGE
embedding model plus a FAISS index into RAM on a machine with very little free memory at the
time (as low as ~217MB free at points during this session). Mock mode is the frontend's own
documented, safe offline path.

**Cleanup:** The temporary `Frontend/.env.local` (created only to enable mock mode for this
demo) was deleted afterward, restoring the real default (`VITE_USE_MOCK_API=false`).

**Outcome:** Confirmed the frontend UI itself renders and functions correctly end-to-end; the
real-backend integration path specifically was not exercised in this pass.

---

## 16. Investigation: is the price-filter "soft" behavior a bug?

**Question raised:** why do over-budget laptops still appear in recommendations?

**Finding:** Not a bug — both the mock engine and the real backend deliberately use soft
budget scoring with disclosed relaxation (a laptop over budget gets a degraded score and an
explicit "unmet"/"partial" label, rather than being excluded outright), matching the rubric's
own "progressive relaxation" requirement.

**Real gap found during this investigation:** the real backend computes and returns
`relaxed_filters` and a human-readable explanatory `message` (e.g. "Not enough laptops matched
your exact budget...") in `ChatResponse` (`Backend/app/models.py`), but the frontend's
TypeScript `ChatResponseDTO` type never declares these fields and no frontend code reads them
— so when the real backend relaxes a budget, that explanation is silently dropped in the UI,
unlike the mock's transparent per-card disclosure. **Not fixed** — flagged for the team's
awareness; no code change was made since scope/priority wasn't confirmed.

---

## 17. Live acceptance suite re-run against rebuilt artifacts (closes the report's open caveat)

**Problem:** `check_backend.py`'s full live acceptance suite (health, all 5 index types'
retrieval, locked/hybrid/relaxed filtering, GPU exclusion, outlier rejection, request
validation, FP-Growth insights, laptop lookup, chat, semantic cache — 22 checks total) had only
ever been run against the *original* pre-fix artifacts (20–22/22, C-1). After the Finding 1–3/9
rebuild, it had never been re-run against the corrected `rebuilt_artifacts` — a real gap, since
nothing about the rebuild's correctness had been confirmed through the actual
request → retrieve → respond path, only through index/count/threshold-specific checks.

**Root cause:** the suite eagerly loads all 5 chunk-level + 5 laptop-level FAISS indexes
(~1.7GB on disk) plus the BGE embedding model via `sentence-transformers`/torch on startup
(`LOAD_RESOURCES_ON_STARTUP=true` is the default) — too heavy to run locally on a 7.6GB-RAM,
no-swap machine that was already sitting under 1GB available. Run instead on Colab
(`colab_check_backend_notebook.ipynb`), in-process (`TestClient`, CPU-only), pointed at
`rebuilt_artifacts` on Drive via the same `repo_code.zip` used for the calibration run (verified
current — `Backend/app/` has zero uncommitted diffs from HEAD; the only Backend code change all
session, `build_laptop_indexes.py`'s `numpy` import, was already patched into that zip).

**Bug found and fixed while preparing the notebook:** the generated summary-printing cell used
an unnecessary backslash-escaped quote inside an f-string expression (`c[\'name\']`) — invalid
in Python < 3.12 (backslashes aren't allowed inside `{}` in f-strings). No escaping was needed
at all since the outer string was double-quoted and the dict key single-quoted. Fixed to
`c['name']` directly in both the notebook and its generator script.

**Outcome:** **22/22 checks passed**, including both semantic-cache checks that had failed in
C-1 (Finding 4) — not reproduced under this run. Confirms the rebuild changed nothing about
request-handling correctness. `EVALUATION_REPORT.md`'s C-2 table and "open caveat" note updated
to reflect the resolved status.

**Security note (unresolved, flagged to the user):** the downloaded/replaced copy of
`colab_check_backend_notebook.ipynb` came back with real-looking Groq/Gemini/OpenRouter API
keys pasted (commented out, but present in plaintext) into the "Optional: LLM provider keys"
cell. The file is gitignored, so it won't reach this repo's history, but the keys are still
sitting in plaintext on disk and in Colab's own autosaved copy on Drive. Recommended: rotate all
three keys, and use Colab's Secrets manager (not notebook cells) for any future run that needs
live LLM credentials. Not acted on without the user's confirmation.

---

## Files changed this session (for reference)

- `Notebook/vector_db_ann_retrieval.ipynb` — persist fix, Drive-copy fix, tie-tolerant scoring,
  Drive-mount integration, `Filter`/`FieldCondition`/`Range` import fix (pre-existing bug),
  index-selector fix (recall-floor + fastest).
- `Backend/scripts/build_laptop_indexes.py` — missing `numpy` import.
- `Backend/artifacts/` — fully rebuilt (all indexes, `qdrant_records.parquet`,
  `laptop_metadata.parquet`, `vector_id_mapping.parquet`, `calibrated_thresholds.json`); old
  version preserved at `archive/old_artifacts/`.
- `Backend/evaluation/threshold_scores.jsonl`, `queries.labeling.jsonl` — regenerated.
- `Backend/evaluation/query_labeling_worksheet.csv`,
  `Backend/evaluation/qualitative_scoring_sheet.csv`,
  `Backend/evaluation/data_collection_methodology.md` — new.
- `Frontend/README.md` — full rewrite.
- `Backend/README.md`, `Backend/RAG_Backend_Implementation_Plan.md` — OpenRouter tier +
  endpoint list fixes.
- `CONTEXT_SO_FAR.md` — scope decision + Finding 1/3 status updates.
- `EVALUATION_REPORT.md` — this changelog's companion, updated with all final verified numbers.
- `.gitignore` — excludes throwaway Colab-run notebook copies and the code-only zip used to
  sideload the private repo into Colab (all contain live credentials at some point), including
  `colab_check_backend_notebook.ipynb` (new).
- `archive/` (new) — `old_artifacts/`, `vector_db_ann_retrieval_pre_selector_fix.ipynb`.

**Not committed to git** — all of the above are uncommitted working-tree changes, per the
user's explicit choice to defer committing until after further polishing.
