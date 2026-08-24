# Qualitative Answer Review

Score each captured answer from 1 (poor) to 5 (excellent):

- Relevance to the request
- Factual correctness against returned metadata and sources
- Grounding in retrieved source chunks
- Source citation validity
- Hard-constraint adherence
- Completeness of justification
- Clarity and usefulness
- Disclosure of relaxed filters
- Appropriate refusal for outlier queries
- Hallucination severity, where 5 means no hallucination

Review the records in `qualitative_answers.jsonl`. Record scores and reviewer
notes in a separate file so the raw API output remains unchanged.
