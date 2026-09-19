# Threads Content Engine

The scheduled strategy runner uses a staged content pipeline:

TOPIC → FACT CHECK → ANGLES → POST TYPE → TYPE-SPECIFIC IDEA SCORE → TOP IDEA → DRAFT → TYPE-SPECIFIC QUALITY SCORE → TYPE-SPECIFIC STRESS TEST → FINAL DECISION

The levels are kept separate:

- Topic: source material or editorial subject.
- Fact: a claim plus evidence, status, and confidence.
- Angle: a distinct editorial interpretation.
- Post type: the editorial objective selected by the strategy layer.
- Idea: an angle scored against the selected post type.
- Draft: written copy selected from the top eligible idea.
- Quality: execution scored against the selected post type.
- Decision: PUBLISH, REWRITE, or REJECT.

## Post-type contract

Post type is chosen by the deterministic strategy layer. The LLM cannot choose its own validation contract.

Supported post types:

- NEWS
- OPINION
- ENGAGEMENT_QUESTION
- DEBATE
- EXPERIENCE
- COMPARISON
- EXPLANATION
- PREDICTION
- RELATABLE

Each type owns its own idea weights, quality weights, hard idea dimensions, and stress checks in POST_TYPE_CONTRACTS in content_engine.py. The scoring engine still uses the same deterministic weighted-score mechanism, but the dimensions change with the editorial objective.

The current strategy mapping is:

| Strategy slot | Post type |
|---|---|
| builder_experience | EXPERIENCE |
| humor | RELATABLE |
| opinion_observation | OPINION |
| question | ENGAGEMENT_QUESTION |
| news_explainer | EXPLANATION |
| gaming | ENGAGEMENT_QUESTION |

Gaming remains a domain/context signal, not a post type.

## Factuality gate

Allowed claim statuses are VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, CONTRADICTED, OPINION, and PREDICTION.

Factual statuses require evidence. A contradicted claim fails the gate. A central unverified claim fails the gate. Opinions and predictions may be evidence-free when explicitly labeled.

Fact confidence is calculated only from evidence-bearing factual statuses. OPINION and PREDICTION confidence values do not lower the factuality score.

Claim-free content is valid for formats such as engagement questions. An empty claim set returns a safe factuality result and does not fail claim-integrity stress checks.

## Boundary validation

LLM output is untrusted data and is validated before it reaches the next stage.

- JSON objects are validated before dereferencing.
- Claims require a valid status, non-empty claim text, confidence, and boolean central flag.
- Factual claims require evidence.
- Angle types must belong to ANGLE_TYPES.
- Angle arrays need at least 8 materially distinct core claims.
- Score dimensions must be finite values in [0, 10].
- Typed draft stress payloads require explicit boolean type checks.
- Malformed provider output receives at most one retry through the existing retry path, then fails closed.

## Stress testing

Every typed post has common safety checks for draft presence, a usable opening, genericity, and claim integrity, plus type-specific checks.

Examples:

- ENGAGEMENT_QUESTION: replyability, specificity, conversation quality.
- OPINION: position clarity, counterargument, specificity.
- EXPERIENCE: concreteness, narrative interest, relatability.
- COMPARISON: alternative clarity, trade-off, decision interest.
- PREDICTION: prediction framing, uncertainty clarity, reasoning.
- EXPLANATION: clarity, usefulness, source grounding.

A question therefore does not need to contain a counterargument or a quotable line merely because those checks made sense for the previous universal stress contract.

## Idea and quality decisions

Typed idea scores use the selected type contract. Hard idea dimensions must each be at least 7/10 and the weighted score must reach the existing progression thresholds.

Legacy APIs remain available:

- idea_score(values)
- quality_score(values)
- idea_decision(...)
- evaluate_topic(..., post_type=None)

Passing a post_type activates the new contract; omitting it preserves legacy behavior.

Publishing still requires:

- idea score >= 85
- quality score >= 80
- fact confidence >= 0.80
- every relevant stress check passes
- a non-empty draft

The final score remains:

final_score = idea_score × 0.55 + quality_score × 0.45

The formula is only active after factuality and stress gates pass.

## State and diversity

The strategy state now records:

- recent_post_types
- recent_engagement_patterns
- strategy_last_post_type
- strategy_last_engagement_pattern

Existing strategy cursor, title history, source history, and recent content topics remain intact.

Engagement patterns include mechanisms such as PROJECT_SHARE, PREFERENCE, SCENARIO_CHOICE, CONSTRAINT_WORKAROUND, POSITION, RECOGNITION_HUMOR, and DISCOVERY. This is deterministic state tracking, not an ML recommender.

## Runtime output

The publishable text remains state/latest_threads.txt and is not polluted with metadata.

The evaluation artifact is state/latest_content_evaluation.txt and now records the post type, typed scores, stress checks, and final decision.

Performance metrics remain diagnostic observations. No statistical learning or claim of guaranteed virality is introduced.
