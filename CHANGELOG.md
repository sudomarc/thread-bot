# Changelog

All notable changes to Thread Bot are documented here.

## [2.1.0] — 2026-09-03

### Added
- URL canonicalization and publication-time validation for fetched news.
- Explicit runtime validation for required secrets.
- Configurable Hugging Face image model via `HF_IMAGE_MODEL`.
- Opt-in LLM quality scoring through `ENABLE_LLM_SCORING`.
- Stronger unit coverage for URL normalization, parser metadata, duplicate sources, state schema, and source-report consistency.

### Changed
- NewsAPI authentication now uses the `X-Api-Key` header and an explicit `to` cutoff.
- The generator now requires unique news sources, valid topic tags, sequential post numbering, and consistent `TOPIC_TAG`/`SOURCE` pairs.
- Recent titles are included in generation context to reduce repeated posts.
- Only source articles actually used by generated posts enter history, and the sources report now matches the generated content.
- State schema is versioned at `2` while remaining backward-compatible with the previous history structure.
- Routine code pushes no longer trigger a complete bot execution; the workflow runs on schedule or manual dispatch.
- GitHub Actions upgraded to Node 24-compatible `checkout@v7`, `setup-python@v7`, and `upload-artifact@v7`.
- State commits occur only after a successful bot run.

### Fixed
- A source could previously be recorded in history even when the LLM never cited it.
- `latest_sources.txt` could describe candidate articles that were not actually used.
- Duplicate NEWS source markers could pass validation.
- Unknown or mismatched `TOPIC_TAG` values could pass validation.
- Article URLs with tracking parameters could evade deduplication.
- Future or malformed publication timestamps could enter the news pool.
- The previous default scoring behavior could multiply OpenRouter traffic on every generation retry.
- Repository maintenance pushes could unnecessarily launch a full content-generation run.

## [2.0.0] — 2026-08-25

See the previous release notes for the initial hardened multi-topic runner, source-grounded generation, atomic state handling, optional enrichment, and CI stabilization.
