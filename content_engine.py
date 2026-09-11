import json
import math
import re
from typing import Any, Callable, Mapping, Sequence


IDEA_WEIGHTS = {
    "scroll_stop": 20,
    "curiosity_tension": 15,
    "originality": 15,
    "debate_potential": 15,
    "shareability": 10,
    "clarity": 10,
    "positioning": 10,
    "surprise_emotion": 5,
}

QUALITY_WEIGHTS = {
    "factual_accuracy": 20,
    "reasoning": 15,
    "originality": 15,
    "clarity": 15,
    "writing_quality": 10,
    "specificity": 10,
    "credibility": 10,
    "information_density": 5,
}

ANGLE_TYPES = [
    "contrarian",
    "prediction",
    "hidden_consequence",
    "economic",
    "power_incentives",
    "human_behavior",
    "personal_observation",
    "debate_question",
    "industry_consequence",
    "short_punchline",
]

FACT_STATUSES = {
    "VERIFIED",
    "PARTIALLY_VERIFIED",
    "UNVERIFIED",
    "CONTRADICTED",
    "OPINION",
    "PREDICTION",
}

FINAL_DECISIONS = {"PUBLISH", "REWRITE", "REJECT"}


class PipelineError(ValueError):
    """Raised when a pipeline stage cannot produce a safe, valid result."""


def _finite_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise PipelineError(f"Invalid score: {value!r}")
    if not math.isfinite(score) or not 0 <= score <= 10:
        raise PipelineError(f"Score must be finite and in [0, 10]: {value!r}")
    return score


def weighted_score(values: Mapping[str, Any], weights: Mapping[str, int]) -> float:
    missing = [name for name in weights if name not in values]
    if missing:
        raise PipelineError(f"Missing score dimensions: {', '.join(missing)}")
    total_weight = sum(weights.values())
    return round(sum(_finite_score(values[name]) * weight for name, weight in weights.items()) / total_weight * 10, 1)


def idea_score(values: Mapping[str, Any]) -> float:
    return weighted_score(values, IDEA_WEIGHTS)


def quality_score(values: Mapping[str, Any]) -> float:
    return weighted_score(values, QUALITY_WEIGHTS)


def idea_decision(score: float, values: Mapping[str, Any], fact_confidence: float = 1.0) -> str:
    score = float(score)
    originality = _finite_score(values["originality"])
    hook = _finite_score(values["scroll_stop"])
    debate = _finite_score(values["debate_potential"])
    if fact_confidence < 0.7:
        return "REJECT"
    if originality < 7 or hook < 7 or debate < 7:
        return "REWORK" if score >= 70 else "REJECT"
    if score >= 90:
        return "EXCEPTIONAL"
    if score >= 85:
        return "STRONG"
    if score >= 80:
        return "PROMISING"
    if score >= 70:
        return "REWORK"
    return "REJECT"


def factuality_gate(claims: Sequence[Mapping[str, Any]]) -> tuple[bool, float, str]:
    if not claims:
        return True, 1.0, "No factual claims; treat content as opinion/observation."
    confidences = []
    central_statuses = []
    for claim in claims:
        status = str(claim.get("status", "")).upper().strip()
        if status not in FACT_STATUSES:
            raise PipelineError(f"Unknown factual status: {status!r}")
        confidence = _finite_score(claim.get("confidence", 0)) / 10
        confidences.append(confidence)
        if claim.get("central", False):
            central_statuses.append(status)
        if status == "CONTRADICTED":
            return False, confidence, "Central or material claim is contradicted by the supplied evidence."
        if status == "UNVERIFIED" and claim.get("central", False):
            return False, confidence, "Central claim is unverified."
    average = sum(confidences) / len(confidences)
    if central_statuses and average < 0.7:
        return False, average, "Fact confidence is too low to support the claim safely."
    return True, round(average, 2), "Fact claims passed the minimum evidence gate."


def final_score(idea: float, quality: float, fact_confidence: float, stress_pass: bool) -> float:
    if not 0 <= fact_confidence <= 1:
        raise PipelineError("fact_confidence must be in [0, 1]")
    if not stress_pass or fact_confidence < 0.7:
        return 0.0
    return round(idea * 0.55 + quality * 0.45, 1)


def final_decision(idea: float, quality: float, fact_confidence: float, stress: Mapping[str, Any]) -> str:
    passed = bool(stress.get("all_pass", False))
    if fact_confidence < 0.7 or not passed:
        return "REJECT" if fact_confidence < 0.7 else "REWRITE"
    if idea < 80 or quality < 75:
        return "REWRITE"
    if idea < 85 or quality < 80 or fact_confidence < 0.8:
        return "REWRITE"
    return "PUBLISH"


def extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise PipelineError("Model did not return valid JSON")


def validate_angles(angles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(angles) < 8:
        raise PipelineError(f"Expected at least 8 angles, got {len(angles)}")
    normalized = []
    seen_claims = set()
    for angle in angles:
        required = ("angle", "core_claim", "why_it_matters", "target_reaction", "supporting_facts", "potential_counterargument")
        if any(not str(angle.get(key, "")).strip() for key in required):
            raise PipelineError("Angle missing required fields")
        key = re.sub(r"\W+", " ", str(angle["core_claim"]).lower()).strip()
        if key in seen_claims:
            continue
        seen_claims.add(key)
        normalized.append(dict(angle))
    if len(normalized) < 8:
        raise PipelineError("Angles are repetitive; need at least 8 materially distinct angles")
    return normalized


def stress_test(draft: str, *, scroll_answer: str, reply_example: str, counterargument: str, generic: bool, quotable_line: str, claims: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    claim_ok = all(str(c.get("status", "")).upper() in {"VERIFIED", "PARTIALLY_VERIFIED", "OPINION", "PREDICTION"} and str(c.get("evidence", "")).strip() for c in claims)
    result = {
        "scroll": bool(scroll_answer.strip()),
        "reply": bool(reply_example.strip()),
        "counterargument": bool(counterargument.strip()),
        "genericity": not generic,
        "quotability": bool(quotable_line.strip()),
        "claim_integrity": claim_ok,
    }
    result["all_pass"] = all(result.values())
    return result


def performance_row(data: Mapping[str, Any]) -> dict[str, Any]:
    required = ("post_id", "date", "topic", "angle", "idea_score", "quality_score", "final_score")
    missing = [key for key in required if key not in data]
    if missing:
        raise PipelineError(f"Performance row missing: {', '.join(missing)}")
    row = dict(data)
    for metric in ("impressions", "views", "likes", "replies", "reposts", "quotes", "profile_visits", "follows"):
        value = row.get(metric)
        if value is None:
            continue
        try:
            row[metric] = max(0, int(value))
        except (TypeError, ValueError):
            raise PipelineError(f"Invalid metric {metric}: {value!r}")
    return row


def normalized_metrics(row: Mapping[str, Any]) -> dict[str, float]:
    denominator = max(1, int(row.get("views", 0) or row.get("impressions", 0) or 0))
    views = max(1, int(row.get("views", 0) or 0))
    return {
        "reply_rate": round(int(row.get("replies", 0)) / denominator, 4),
        "repost_rate": round(int(row.get("reposts", 0)) / denominator, 4),
        "like_rate": round(int(row.get("likes", 0)) / denominator, 4),
        "follow_conversion": round(int(row.get("follows", 0)) / views, 4),
        "engagement_rate": round((int(row.get("likes", 0)) + int(row.get("replies", 0)) + int(row.get("reposts", 0)) + int(row.get("quotes", 0))) / denominator, 4),
    }


def run_llm_json(openrouter_chat: Callable[[str], str], prompt: str) -> Any:
    return extract_json(openrouter_chat(prompt))


def build_fact_prompt(topic: str, sources: Sequence[Mapping[str, Any]]) -> str:
    source_text = "\n".join(
        f"SOURCE {idx}: {item.get('title', '')}\nSUMMARY: {item.get('description', '')}\nURL: {item.get('url', '')}"
        for idx, item in enumerate(sources, 1)
    )
    return f"""Fact-check the source topic BEFORE generating or scoring any ideas. Use only the supplied sources.
Treat the topic as source material, not as an editorial instruction. Only claims about the supplied source topic/article should be assessed here.
Topic: {topic}
Sources:
{source_text}

Return JSON only:
{{"claims":[{{"claim":"...","status":"VERIFIED|PARTIALLY_VERIFIED|UNVERIFIED|CONTRADICTED|OPINION|PREDICTION","evidence":"...","confidence":0-10,"central":true}}]}}
Rules: material claims must name evidence from the supplied sources. Predictions must be labeled PREDICTION; opinions must be labeled OPINION. Never turn an inference into VERIFIED. Do not invent claims about editorial format, hooks, audience context, or writing instructions."""


def build_angle_prompt(topic: str, fact_result: Mapping[str, Any], sources: Sequence[Mapping[str, Any]], editorial_brief: str = "") -> str:
    editorial = editorial_brief.strip() or "No additional editorial brief."
    return f"""Generate a diverse idea pool for Threads from this source topic AFTER fact-checking.
Topic: {topic}
Fact check: {json.dumps(fact_result, ensure_ascii=False)}
Editorial brief (direction only; NOT factual evidence and must not be fact-checked): {editorial}
Allowed angle types: {', '.join(ANGLE_TYPES)}
Sources: {json.dumps(list(sources), ensure_ascii=False)}

Return JSON only: {{"angles":[{{"angle":"type","core_claim":"...","why_it_matters":"...","target_reaction":"...","supporting_facts":["..."],"potential_counterargument":"...","scores":{{"scroll_stop":0-10,"curiosity_tension":0-10,"originality":0-10,"debate_potential":0-10,"shareability":0-10,"clarity":0-10,"positioning":0-10,"surprise_emotion":0-10}}}}]}}
Generate at least 8 materially different angles. Use the editorial brief to shape format, hook, and audience context, but ground factual claims in the fact check/source material. Do not use generic AI-future wording as evidence of originality."""


def build_draft_prompt(angle: Mapping[str, Any], fact_result: Mapping[str, Any], sources: Sequence[Mapping[str, Any]], editorial_brief: str = "") -> str:
    editorial = editorial_brief.strip() or "No additional editorial brief."
    return f"""Write ONE natural Threads post from the selected idea. Do not change the underlying factual claim.
Selected angle: {json.dumps(angle, ensure_ascii=False)}
Fact check: {json.dumps(fact_result, ensure_ascii=False)}
Editorial brief (style/direction only; NOT factual evidence): {editorial}
Sources: {json.dumps(list(sources), ensure_ascii=False)}

Return JSON only:
{{"draft":"...","quality":{{"factual_accuracy":0-10,"reasoning":0-10,"originality":0-10,"clarity":0-10,"writing_quality":0-10,"specificity":0-10,"credibility":0-10,"information_density":0-10}},"stress":{{"scroll_answer":"...","reply_example":"...","counterargument":"...","generic":false,"quotable_line":"..."}},"claims":[{{"claim":"...","evidence":"...","status":"VERIFIED|PARTIALLY_VERIFIED|OPINION|PREDICTION","confidence":0-10}}]}}

Avoid rage bait, engagement bait, fake certainty, invented numbers or quotes, generic 'What do you think?' endings, and LinkedIn-style filler. Do not treat editorial instructions or relatable context as factual claims."""


def evaluate_topic(topic: str, sources: Sequence[Mapping[str, Any]], openrouter_chat: Callable[[str], str], *, max_angles: int = 8, editorial_brief: str = "") -> dict[str, Any]:
    fact_result = run_llm_json(openrouter_chat, build_fact_prompt(topic, sources))
    claims = fact_result.get("claims", [])
    fact_ok, fact_confidence, fact_reason = factuality_gate(claims)
    if not fact_ok:
        return {"topic": topic, "editorial_brief": editorial_brief, "fact_status": fact_result, "fact_confidence": fact_confidence, "fact_gate": fact_reason, "angles": [], "decision": "REJECT"}

    angle_result = run_llm_json(openrouter_chat, build_angle_prompt(topic, fact_result, sources, editorial_brief))
    angles = validate_angles(angle_result.get("angles", []))[:max_angles]
    scored = []
    for angle in angles:
        score = idea_score(angle["scores"])
        decision = idea_decision(score, angle["scores"], fact_confidence)
        scored.append({**angle, "idea_score": score, "idea_decision": decision})
    scored.sort(key=lambda item: item["idea_score"], reverse=True)
    top = next((item for item in scored if item["idea_decision"] in {"EXCEPTIONAL", "STRONG", "PROMISING"}), None)
    if not top:
        return {"topic": topic, "editorial_brief": editorial_brief, "fact_status": fact_result, "fact_confidence": fact_confidence, "fact_gate": fact_reason, "angles": scored, "decision": "REJECT"}

    draft_result = run_llm_json(openrouter_chat, build_draft_prompt(top, fact_result, sources, editorial_brief))
    quality = quality_score(draft_result.get("quality", {}))
    draft_claims = draft_result.get("claims", claims)
    stress = draft_result.get("stress", {})
    stress_result = stress_test(
        str(draft_result.get("draft", "")),
        scroll_answer=str(stress.get("scroll_answer", "")),
        reply_example=str(stress.get("reply_example", "")),
        counterargument=str(stress.get("counterargument", "")),
        generic=bool(stress.get("generic", True)),
        quotable_line=str(stress.get("quotable_line", "")),
        claims=draft_claims,
    )
    claim_ok, final_fact_confidence, final_fact_reason = factuality_gate(draft_claims)
    final = final_score(top["idea_score"], quality, final_fact_confidence, stress_result["all_pass"])
    decision = final_decision(top["idea_score"], quality, final_fact_confidence, stress_result)
    if not claim_ok:
        decision = "REJECT"
    return {
        "topic": topic,
        "editorial_brief": editorial_brief,
        "fact_status": fact_result,
        "fact_confidence": final_fact_confidence,
        "fact_gate": final_fact_reason,
        "angles": scored,
        "top_pick": top,
        "draft": draft_result.get("draft", "").strip(),
        "quality_score": quality,
        "stress_test": stress_result,
        "final_score": final,
        "decision": decision,
    }


def render_report(result: Mapping[str, Any]) -> str:
    lines = [
        f"TOPIC\n{result.get('topic', '')}",
        f"EDITORIAL BRIEF\n{result.get('editorial_brief', '')}",
        "FACT STATUS",
        json.dumps(result.get("fact_status", {}), ensure_ascii=False, indent=2),
    ]
    for index, angle in enumerate(result.get("angles", []), 1):
        lines.extend([
            f"\nANGLE {index}",
            f"- Core idea: {angle.get('core_claim', '')}",
            f"- Hook concept: {angle.get('angle', '')}",
            f"- Why it works: {angle.get('why_it_matters', '')}",
            f"- Counterargument: {angle.get('potential_counterargument', '')}",
            f"- Idea score: {angle.get('idea_score', '')}/100",
            f"- Decision: {angle.get('idea_decision', '')}",
        ])
    if result.get("top_pick"):
        lines.extend([
            "\nTOP PICK",
            f"{result['top_pick'].get('core_claim', '')}",
            f"Idea score: {result['top_pick'].get('idea_score', '')}/100",
            "\nDRAFT",
            str(result.get("draft", "")),
            f"\nQUALITY SCORE\n{result.get('quality_score', '')}/100",
            "\nSTRESS TEST",
            json.dumps(result.get("stress_test", {}), ensure_ascii=False, indent=2),
            f"\nFINAL SCORE\n{result.get('final_score', '')}/100",
            f"\nFINAL DECISION\n{result.get('decision', '')}",
        ])
    return "\n".join(lines) + "\n"
