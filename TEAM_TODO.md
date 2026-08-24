# Team TODO — Manual Steps Only the Team Can Complete

Three items from the evaluation remain open because they need either human judgment or facts
that only the team has. Nothing here needs code changes or Colab — all local, no GPU.

---

## 1. Hand-label the 40-query worksheet

**File:** `Backend/evaluation/query_labeling_worksheet.csv`
**Rubric requirement:** ≥30 hand-labeled queries with relevance judgments.

**What it is:** 40 rows, each a query the RAG pipeline was actually asked, with up to 5
candidate laptops the system retrieved for it. Columns per row:

```
row_id, query,
candidate_1_laptop_id, candidate_1_details, candidate_1_relevant_Y_N,
candidate_2_laptop_id, candidate_2_details, candidate_2_relevant_Y_N,
... (through candidate_5)
```

`candidate_N_details` is already resolved to a readable string, e.g.
`Dell XPS 13 | $1,199 | Intel Core i7-1360P | Intel Iris Xe | 16GB LPDDR5 | 512GB SSD` — you
don't need to look anything else up.

**How to do it:**
1. Open the CSV in a spreadsheet tool (Excel, Google Sheets, LibreOffice Calc).
2. For each row, read the `query` column, then for each of the up to 5 candidates, decide: does
   this laptop genuinely satisfy what the query asked for?
3. Fill in `Y` or `N` in each `candidate_N_relevant_Y_N` cell. Leave it blank only if that
   candidate slot is empty (not every row has 5 candidates).
4. Judge against the query's stated intent, not against what the system's own score implied —
   you're building independent ground truth, not checking the system's work.
5. When in doubt on a borderline case (e.g., a laptop that's close but slightly over budget),
   write a one-line rationale in a scratch column if you want a record, then decide `Y`/`N`
   anyway — the sheet needs a decision per cell, not a maybe.
6. Save as CSV (not xlsx) when done, keeping the same filename and column structure so any
   downstream script that reads it (e.g., a future precision/recall calculation against these
   labels) still works.

**Time estimate:** ~40 queries × up to 5 judgments each = up to 200 yes/no calls. Budget
1-2 hours for a careful first pass; faster on a second pass once the judgment criteria feel
consistent.

---

## 2. Score the 15 qualitative answers

**File:** `Backend/evaluation/qualitative_scoring_sheet.csv`
**Rubric requirement:** qualitative evaluation of generated answers against a defined rubric.

**What it is:** 15 rows, each a real chat answer the system generated (query, filters, the
generated `answer` text, which laptops it recommended, provider used, etc.), with 10 blank
rubric-criterion columns to score:

```
relevance_to_request, factual_correctness, grounding_in_sources,
source_citation_validity, hard_constraint_adherence,
completeness_of_justification, clarity_and_usefulness,
disclosure_of_relaxed_filters, appropriate_refusal_for_outliers,
hallucination_severity_5_is_none
```

Plus a free-text `reviewer_notes` column at the end.

**Where the criteria are defined:** `Backend/evaluation/qualitative_review_rubric.md` — read
this first. It defines what each of the 10 columns actually means and the 1-5 scale.

**How to do it:**
1. Open `qualitative_review_rubric.md` and `qualitative_scoring_sheet.csv` side by side.
2. For each of the 15 rows: read the `query`, `filters`, `answer`, and `recommended_laptops`
   columns together — you need the full context, not just the answer text in isolation, to
   judge things like `hard_constraint_adherence` or `factual_correctness`.
3. Score each of the 10 criteria columns 1-5 per the rubric's definitions.
4. Use `reviewer_notes` for anything that doesn't fit a number — a specific hallucinated spec
   you caught, a citation that pointed to the wrong laptop, etc. This is useful evidence for the
   final report even if it's not itself a rubric score.
5. `hallucination_severity_5_is_none` is inverted from the others — 5 means *no* hallucination
   found, 1 means severe. Don't average it the same direction as the rest without accounting for
   that if you compute a summary score.
6. Save as CSV, same filename/structure.

**Time estimate:** 15 rows × 10 criteria, but each row needs you to actually read the sourced
laptop specs to check `factual_correctness`/`grounding_in_sources` — budget more like 10-15
minutes per row, so roughly 2.5-4 hours total for a careful pass.

---

## 3. Reconcile `IVF_Flat_Indexing_Justification.docx`

**File:** `Notebook/IVF_Flat_Indexing_Justification.docx`
**Rubric requirement (M3):** written justification for the chosen FAISS index type.

**What changed underneath this document:** the index-selection logic in
`Notebook/vector_db_ann_retrieval.ipynb` had a circular-reasoning bug — it always picked the
fastest index without a recall floor, which is why "IVF Flat" was originally selected and named
in this document's title. That bug is now fixed (recall-floor-then-fastest selection), and the
new fixed logic selects **HNSW** instead:

| Metric | Old selection (IVF Flat) | New selection (HNSW) |
|---|---|---|
| recall@10 | ~88.2% | **99.38%** |
| recall@1 | — | **99.67%** |
| p50 latency | ~1.47ms | **0.95ms** |
| p95 latency | — | **1.60ms** |

So the document's current title and any prose arguing for IVF Flat specifically no longer
matches what the notebook actually recommends. `Backend/app/config.py`'s `DEFAULT_INDEX` has
since been updated to `hnsw` to match — this doc is the one remaining piece still saying
"IVF Flat."

**How to reconcile it:**
1. Open `Notebook/vector_db_ann_retrieval.ipynb` and find the final index-selection cell (the
   one computing `RECALL_THRESHOLD`, filtering candidates by it, then picking the
   fastest-latency survivor) — this is the source of truth for the numbers above and the exact
   selection methodology to describe.
2. Rename the document (or at minimum, retitle its content) to reflect the actual chosen index
   — e.g. `HNSW_Indexing_Justification.docx`, or keep the filename and just fix the title/body if
   you'd rather not break any existing references to the old filename.
3. Rewrite the justification section to argue for HNSW using the real numbers above: better
   recall *and* better latency than every alternative (Flat, IVF Flat, PQ, IVF+PQ) benchmarked in
   the notebook, chosen via a recall-floor (≥95%) then fastest-latency selection rule — mention
   explicitly that this is not a latency-only or recall-only pick, but the fastest option among
   those that clear a real accuracy bar, since that's the M3 rubric's actual ask.
4. Keep whatever general structure/sections the original document already had (background on
   FAISS index types, tradeoffs table, etc.) — only the conclusion, chosen index, and supporting
   numbers need to change, not the whole document.
5. If the document currently has a tradeoffs table comparing index types, pull the exact numbers
   from `Notebook/vector_db_ann_artifacts/benchmark_results.csv` (or the corresponding cell
   output in the notebook) rather than re-deriving them, so the document and the notebook can't
   drift apart again.

**Time estimate:** 30-60 minutes if the document's existing structure is reused and only the
numbers/conclusion change.

---

## 4. Fill in `data_collection_methodology.md`'s TODOs

**File:** `Backend/evaluation/data_collection_methodology.md`
**Rubric requirement (§3.1):** documented data collection methodology for a "Publicly available
dataset + Student-Owned" combination.

This file is already drafted with the parts that could be determined from the data itself (row
counts, schema, known data-quality findings). Three sections are marked `[TODO]` because they
need facts only the team has:

**Public baseline section** — confirm or correct:
- Is `kaggle.com/datasets/muhammetvarl/laptop-price` (the dataset the project description cites
  as an example) the actual source used, or was a different public dataset used?
- Exact dataset URL / DOI / citation
- License terms, and whether attribution is required in the final report
- How many of the 8,485 rows / which of the 27 columns came from this source specifically
- Date the public dataset was retrieved

**Team-scraped data section** — fill in:
- Which site(s) were scraped
- What tool/library was used (BeautifulSoup, Scrapy, Selenium, manual collection, etc.)
- Date range the scraping was performed over
- Which specific fields came from scraping (`review`, `summary`, `pros`, `cons`? additional rows
  entirely?)
- Any rate-limiting / robots.txt / terms-of-service considerations followed

**Combining the two sources section** — describe:
- What was the join key between the two sources (brand+model string? something else?)
- When both sources had data for the same device, which one took precedence?
- Were there rows present in only one source, and how were those handled?

**One more small `[TODO]`** in the "Known data quality notes" section: what fields were
KNN-imputed in `Dataset/imputed_dataset.csv` and what imputation method was used, if this isn't
already documented somewhere else in the repo.

**How to do it:** open the file directly and replace each `[TODO: ...]` block with the actual
answer — the surrounding prose is already written to read naturally once the placeholders are
filled in. No new sections needed unless there's something genuinely not covered by the existing
structure.

**Time estimate:** 15-30 minutes if you already know these facts; longer only if you need to dig
up the original scraping notes/scripts to reconstruct them.
