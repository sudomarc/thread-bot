# Pipeline invariants

The content engine treats LLM responses as untrusted data.

## Retryable failures

Retries are bounded and selected by pipeline stage. A semantic validation failure must identify the stage and error code; human-readable messages are diagnostic only.

## Claims

`VERIFIED`, `PARTIALLY_VERIFIED`, `UNVERIFIED`, and `CONTRADICTED` claims require evidence. `OPINION` and `PREDICTION` claims do not require evidence, but must retain their explicit status. `CONTRADICTED` and unsafe `UNVERIFIED` claims fail the factuality gate.

## Angles

An angle must have one of the configured angle types. The published idea pool must contain at least eight accepted angles and at least eight distinct angle types. Rewording the same claim under different labels is not sufficient.
