# Thread Bot Testing & Regression Policy

Testing is evidence for the content pipeline, not only a green command. Changes must be verified against the execution path they can affect.

## Local checks

Run the smallest useful check first:

python -m unittest discover -s tests -v
python -m py_compile bot.py strategy_runner.py content_engine.py main.py

For changes that affect dependencies, workflows, or packaging, run the corresponding repository/CI check as well.

## Content-engine contracts

Tests must cover both legacy and typed paths. Typed regression coverage should include:

- every supported POST_TYPE is accepted;
- an unknown post type is rejected;
- each type has its own idea and quality dimensions;
- hard idea dimensions are enforced per type;
- claim-free engagement questions can pass factuality and claim-integrity checks;
- generic low-specificity questions fail the relevant typed stress contract;
- OPINION and PREDICTION claims can be evidence-free when labeled;
- mixed opinion plus factual claims still require evidence for the factual claim;
- contradicted claims and central unverified claims are rejected;
- OPINION/PREDICTION confidence does not dilute factual confidence;
- unknown angle types fail validation;
- malformed nested draft/stress/type-check payloads fail closed;
- typed prompts contain the orchestrator-selected contract;
- typed evaluation records the post type and uses the matching rubric.

## State and diversity

Strategy tests must verify that successful publication records the selected post type and engagement mechanism. Existing state must remain readable, and the persistent strategy cursor must continue advancing only after successful generation.

## Bug fixes

A meaningful bug fix should have a regression test that fails for the old behavior and passes for the corrected behavior. Do not delete, weaken, or broaden tolerances merely to make CI green.

## Network and provider failures

Provider calls use bounded retries. Transport failures and malformed provider output may receive a single retry when the operation is side-effect free. Semantic validation failures must use the same bounded retry and still fail closed after the retry.

## Workflow verification

Every pull request and every push to main must execute the test job. Strategy execution is separate and may run only for scheduled/manual executions or an explicit run-bot push. The strategy job must depend on the successful test job.

## Final verification

Before merging:

regression test
    ↓
affected test suite
    ↓
full test suite
    ↓
CI for the final commit
    ↓
review complete diff and status

A skipped verification job is not evidence of success. If local execution is unavailable, state that explicitly and use actual GitHub Actions results as the available verification evidence. Never report unverified tests as passing.
