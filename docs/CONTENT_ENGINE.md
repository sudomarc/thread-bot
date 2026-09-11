# Threads Content Engine

The scheduled strategy runner now uses a staged content pipeline:

`TOPIC → FACT CHECK → ANGLES → IDEA SCORE → TOP IDEA → DRAFT → QUALITY SCORE → STRESS TEST → FINAL DECISION`

The levels are kept separate:

- **Topic**: the source material or editorial subject.
- **Fact**: a claim plus evidence, status, and confidence.
- **Angle**: a distinct editorial interpretation of the topic.
- **Idea**: an angle with a weighted 0–100 score.
- **Draft**: the written Threads copy selected from the top eligible idea.
- **Score**: idea score, quality score, and final score are stored separately.
- **Decision**: `PUBLISH`, `REWRITE`, or `REJECT`.
- **Result**: real post metrics can be appended later for calibration.

## Idea scoring

The engine calculates the idea score in code from 0–10 component ratings:

| Dimension | Weight |
|---|---:|
| Scroll-stop / hook | 20 |
| Curiosity / tension | 15 |
| Originality | 15 |
| Debate potential | 15 |
| Shareability | 10 |
| Clarity | 10 |
| Positioning / identity | 10 |
| Surprise / emotion | 5 |

The weighted average is multiplied by 10, so `10/10` on every dimension equals `100/100`.

An angle is not eligible for normal progression when originality, hook, or debate potential is below 7/10. Fact confidence below 0.70 also blocks the idea.

## Factuality gate

Allowed claim statuses are `VERIFIED`, `PARTIALLY_VERIFIED`, `UNVERIFIED`, `CONTRADICTED`, `OPINION`, and `PREDICTION`.

A contradicted material claim or an unverified central claim is rejected. Predictions and opinions are allowed only when labeled as such. The engine never converts an inference into a verified claim merely because the idea scores highly.

## Quality scoring

The quality score is independently calculated from:

- factual accuracy 20%
- reasoning 15%
- originality 15%
- clarity 15%
- writing quality 10%
- specificity 10%
- credibility 10%
- information density 5%

## Final scoring and decisions

`final_score = idea_score × 0.55 + quality_score × 0.45`, but the formula is only active after the factuality gate and stress tests pass.

Publishing additionally requires:

- idea score ≥ 85
- quality score ≥ 80
- fact confidence ≥ 0.80
- every stress test passed

The final decision is then exactly one of:

- `PUBLISH`: strong idea and draft, adequate evidence, all tests pass.
- `REWRITE`: the concept is viable but the idea/draft/stress result needs improvement.
- `REJECT`: the factuality gate fails or no eligible idea exists.

A `REWRITE` result is never published by the strategy runner; it receives one additional rewrite/evaluation pass.

## Stress tests

The draft is checked for a concrete scroll reason, a plausible reply, a reasonable counterargument, non-generic wording, a quotable line, and claim/evidence integrity.

## Performance feedback

`strategy_runner.record_performance()` stores real metrics without claiming that any one metric equals "virality". It also derives reply rate, repost rate, like rate, follow conversion, and engagement rate.

The stored schema supports later comparisons between predicted scores and actual outcomes. No statistical learning is claimed or performed until real performance data exists.

## Runtime output

The normal publishable text remains `state/latest_threads.txt`. The new evaluation artifact is `state/latest_content_evaluation.txt`, which contains the topic, fact status, angles, top pick, scores, stress test, and final decision.
