Data Collection Methodology

## Overview

The dataset backing this project (`Dataset/imputed_dataset.csv`, 8,485 rows, 27 columns)
combines two sources:

1. A **public baseline dataset**, providing an initial set of structured laptop
   specifications and pricing.
2. **Data scraped independently by the team**, adding further listings and/or enriching the
   public baseline with additional structured and unstructured fields (reviews, pros/cons,
   summaries).

This satisfies the term project's requirement (`Term_Project_Description.pdf`, §3.1) for a
"Publicly available dataset + Student-Owned" combination, and the resulting 8,485 rows exceed
the rubric's stated minimum of 1,500–2,000 device entries.

## Public baseline

`[TODO: confirm]` The project description cites `kaggle.com/datasets/muhammetvarl/laptop-price`
as a reference starting point for this dataset category. Confirm whether this is the actual
public source used, or name the correct one, including:
- Exact dataset URL / DOI / citation
- License terms (and whether attribution is required in the final report)
- Number of rows/columns contributed by this source alone
- Date the public dataset was retrieved

## Team-scraped data

`[TODO: fill in]` Details only the team has:
- Which site(s) or source(s) were scraped
- Scraping tool/library used (e.g. BeautifulSoup, Scrapy, Selenium, manual collection)
- Date range over which scraping was performed
- Which fields came from scraping specifically (e.g. `review`, `summary`, `pros`, `cons`, or
  additional device rows entirely)
- Any rate-limiting, robots.txt, or terms-of-service considerations that were followed

## Combining the two sources

`[TODO: fill in]` How overlaps and conflicts between the public baseline and the team's own
scraped data were reconciled — for example:
- Was the join key a laptop's brand+model string, or something else?
- When both sources had data for the same device, which source took precedence?
- Were there rows present in one source but not the other, and how were those handled?

## Known data quality notes (already established during evaluation)

- 3,348 of 8,485 rows have no free-text `review`, `summary`, `pros`, or `cons` — these entries
  have only structured spec fields.
- The imputed dataset used by the RAG pipeline (`imputed_dataset.csv`) is a KNN-imputed version
  of the raw collected data — `[TODO: fill in]` describe what fields were imputed and the
  imputation method, if not already documented elsewhere.
- A live investigation found roughly 55-60% of generated review/spec text chunks are exact
  duplicates across different (but near-identical variant) listings — consistent with
  templated review text being reused across RAM/storage configuration variants of the same
  base model, rather than a data-collection error. See `EVALUATION_REPORT.md` Finding 2 for
  detail.

## Schema

27 columns: `id, brand, model, cpu_full, gpu_full, ram_full, storage, display_full, battery,
weight_kg, os, connectivity, camera, extras, summary, pros, cons, review,
display_brightness_nits, ram_capacity_gb, display_size_inches, display_resolution_width,
display_resolution_height, dimension_height_mm, dimension_width_mm, dimension_depth_mm,
price_usd`.
