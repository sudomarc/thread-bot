# Thread Bot Testing & Regression Policy

Testing is evidence for the content pipeline, not only a green command. Changes must be verified against the execution path they can affect.

## Local checks

Run the smallest useful check first:

```bash
python -m unittest discover -s tests -v
python -m py_compile bot.py strategy_runner.py content_engine.py main.py
```

For changes that affect dependencies, workflows, or packaging, run the corresponding repository/CI check as well.

## Bug fixes

A meaningful bug fix should have a regression test that fails for the old behavior and passes for the corrected behavior. Do not delete, weaken, or broaden tolerances merely to make CI green.

## Content-engine boundary tests

The content engine should test:

- malformed, fenced, and prose-wrapped LLM JSON;
- wrong JSON top-level types;
- missing or malformed nested arrays/objects;
- non-finite and out-of-range scores;
- missing evidence for factual claims;
- contradicted claims and unverified central claims;
- empty drafts and failed stress-test requirements;
- source reuse and invalid source identifiers;
- invalid performance metrics, including fractional and boolean values;
- zero-view metric normalization;
- deterministic scoring and decision thresholds.

## Network and provider failures

Provider calls use bounded retries. Tests should cover retryable HTTP responses, exhausted retry budgets, malformed provider payloads, empty responses, and permanent failures. Retries must not turn a failed provider operation into a false success.

## State and workflow verification

The scheduled workflow must run tests before executing the strategy slot and must persist state only after successful generation. Changes to state/report behavior should verify atomic writes and final artifact consistency.

## Final verification

Before merging a change:

```text
regression test
    ↓
affected test suite
    ↓
full test suite
    ↓
CI for the final commit
    ↓
review complete diff and status
```

If local execution is unavailable, say so explicitly and use current GitHub Actions results as the available verification evidence. Never report unverified tests as passing.
