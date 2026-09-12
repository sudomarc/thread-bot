# Threads Content Engine

The scheduled strategy runner uses a staged content pipeline:

`TOPIC → FACT CHECK → ANGLES → IDEA SCORE → TOP IDEA → DRAFT → QUALITY SCORE → STRESS TEST → FINAL DECISION`

LLM output is untrusted data. Deterministic validation owns the publication invariants.

## Boundary validation

- Required JSON objects, arrays, and nested objects must have the expected shape.
- Scores are finite and within documented ranges.
- Factual statuses require evidence.
- `OPINION` and `PREDICTION` claims are allowed without evidence when explicitly labeled.
- Contradicted claims and unverified central claims fail the factuality gate.
- Drafts must be non-empty and pass every stress check.
- Performance counters must be non-negative integers.

## Angle diversity

Every accepted angle must use a configured angle type. The accepted pool must contain at least eight angles and at least eight distinct angle types. Duplicate or near-duplicate claims are insufficient even when wording differs.

## Factuality gate

Allowed statuses are `VERIFIED`, `PARTIALLY_VERIFIED`, `UNVERIFIED`, `CONTRADICTED`, `OPINION`, and `PREDICTION`. Factual statuses require evidence; opinions and predictions do not. A contradicted claim or unsafe unverified central claim fails closed.

## Scoring

Idea and quality scores are calculated deterministically in code. Final scoring is only active after factuality and stress gates pass. Publishing requires idea score ≥ 85, quality score ≥ 80, fact confidence ≥ 0.80, every stress check to pass, and a non-empty draft.
