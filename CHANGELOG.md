# Changelog

All notable changes to Thread Bot are documented here.

## [2.0.0] — 2026-08-25

### Added
- Hardened multi-topic news collection covering cybersecurity, technology/AI, and gaming.
- Source-grounded LLM generation with strict post parsing and validation.
- Quality scoring and regeneration for weak generations.
- Optional Hugging Face image enrichment that cannot block a successful content run.
- UTF-8-safe email generation and attachments.
- Atomic state persistence with `last_run_at` tracking.
- Historical article/title tracking to reduce repeated content.
- Unit-test suite covering parser, Unicode, email MIME, state handling, and content validation.
- GitHub Actions artifacts for generated reports and sources.

### Changed
- Consolidated the maintained implementation into `bot.py`; `main.py` is now a compatibility entrypoint.
- Moved runtime dependencies into `requirements.txt` and constrained supported versions.
- Reworked the GitHub Actions workflow around modern Actions versions, dependency installation, tests-before-run, concurrency control, timeouts, and resilient state pushes.
- Preserved Unicode instead of stripping legitimate punctuation from generated content.
- Made Gmail, image generation, scoring, and other enrichment failures non-fatal when the core report is still valid.
- Reduced duplicate and stale article selection by filtering recent URLs and requiring current source material.
- Expanded project documentation and operational guidance.

### Fixed
- Gmail failures caused by invalid credentials or ASCII-only email encoding.
- LLM outputs containing missing, duplicated, or malformed post blocks.
- Quality-scoring paths that could return unusable scores for parsed output.
- State corruption risk during interrupted writes.
- Git `non-fast-forward` failures when workflow state updates raced with repository changes.
- Runtime failures caused by unavailable or retired Hugging Face image models.
- CI regressions that previously reached production execution without automated tests.

## [Unreleased]

Changes after 2.0.0 will be collected here.
