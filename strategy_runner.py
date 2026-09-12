from datetime import datetime, timezone

import bot
from content_engine import PipelineError, evaluate_topic, normalized_metrics, performance_row, render_report


STRATEGY_TARGETS = {
    "views": "20,000-30,000 / 30 days",
    "spectators": "12,000+ / 30 days",
    "followers": "75-150 / 30 days",
    "conversion": "0.3-0.6% views-to-followers",
    "posts": "20-25 / 30 days",
}

# Observed winning pattern: AI/tech + a concrete builder constraint or experience +
# a strong hook. The mix keeps humor/conversation while reducing generic news posts.
STRATEGY_MIX = {
    "builder_experience": 8,
    "humor": 4,
    "opinion_observation": 4,
    "question": 2,
    "news_explainer": 1,
    "gaming": 1,
}

STRATEGY_POSTS = [
    ("builder_experience", "technology", "I shouldn't be able to build this with the resources I have.", "Turn the supplied story into a concrete builder-perspective post. Focus on a real constraint, workaround, leverage point, or surprising result. Use first person only when the supplied material or configured creator context supports it; never invent hardware, spending, actions, or results."),
    ("builder_experience", "technology", "The interesting part isn't the AI. It's what a small builder can do with it.", "Frame the supplied story through the lens of a resource-constrained builder. Make the constraint visible, then show the practical leverage. Do not invent personal facts."),
    ("builder_experience", "technology", "A weak setup can still do a ridiculous amount with the right workflow.", "Extract a practical lesson for a small or solo builder from the supplied story. Prefer a concrete trade-off over generic AI hype. Do not fabricate the creator's setup."),
    ("builder_experience", "technology", "I thought the hardware would be the bottleneck. It wasn't.", "Use the supplied story to explore how software, AI tools, automation, or workflow can move a bottleneck. First-person wording is allowed only when supported; otherwise use an observational framing."),
    ("builder_experience", "technology", "This is what AI changes for people without a giant budget.", "Translate the supplied story into a resource-constrained builder perspective: what becomes possible, what remains hard, and what trade-off matters. Keep claims source-grounded."),
    ("builder_experience", "technology", "One person can now get surprisingly close to what used to require a team.", "Use the supplied story as evidence/context for solo-builder leverage. Be specific about the mechanism and avoid unsupported productivity or cost claims."),
    ("builder_experience", "technology", "The hack isn't having better hardware. It's removing the bottleneck.", "Find the most defensible bottleneck/workaround in the supplied story and turn it into a concise builder lesson. Do not invent a personal anecdote."),
    ("builder_experience", "technology", "Trying to build with limited resources teaches you what the tool is actually good at.", "Make the post feel lived-in and practical without fabricating personal experience. Center a real constraint, what the technology changes, and the remaining limitation."),
    ("humor", None, "Me: I'll only use AI for 5 minutes.", "Write a short, highly relatable tech/AI joke using the supplied story as context. No invented factual claims."),
    ("humor", None, "Developers when the code works on the first try:", "Write a short developer/AI joke grounded in the supplied story. Keep it punchy and recognizable."),
    ("humor", None, "Me opening my code after asking AI to 'just fix one thing'...", "Write a concise coding/AI joke using the current story as context. Avoid generic setup if the source offers a better specific joke."),
    ("humor", None, "Having AI do one tiny task was a mistake.", "Turn the supplied story into a relatable AI/developer humor post. Keep the joke short enough to scan immediately."),
    ("opinion_observation", "technology", "AI isn't replacing everyone. It's changing who can build what.", "Take a strong, defensible position on the supplied story and invite disagreement. Make the consequence for builders explicit."),
    ("opinion_observation", "technology", "The distance between 'I have an idea' and 'I built it' keeps shrinking.", "Write a concise observation about AI lowering the barrier to building, grounded in the supplied story."),
    ("opinion_observation", "technology", "Most people don't need a better model. They need to use the one they have better.", "Make a provocative but useful point about AI usage, grounded in the current story."),
    ("opinion_observation", "technology", "Hot take: most AI products add features faster than people can build habits around them.", "Take a clear position using the supplied current story as evidence or context. Avoid hype and explain the trade-off."),
    ("question", None, "What are you actually building with AI right now?", "Ask builders to share projects. Optimize for replies, not a lecture. Use the source only as context and never invent details about commenters."),
    ("question", None, "What AI tool genuinely earns a place in your daily workflow?", "Ask for concrete experiences rather than generic favorites. Make the question easy to answer in one sentence."),
    ("news_explainer", "cybersecurity", "This security story matters for one reason:", "Explain the supplied cybersecurity story in plain English, then give the practical implication without fearmongering or unsupported technical claims."),
    ("gaming", "gaming", "What game would you want an AI-powered NPC to actually remember you in?", "Use the gaming source as context, but make the post primarily a question that invites stories and debate."),
]

PIPELINE_REPORT_PATH = "state/latest_content_evaluation.txt"

ARTICLE_RELEVANCE_KEYWORDS = {
    "builder_experience": {
        "ai", "artificial intelligence", "developer", "coding", "code", "software", "automation", "workflow",
        "model", "open source", "api", "cloud", "gpu", "chip", "semiconductor", "startup", "robotics",
        "tool", "platform", "computer", "hardware", "infrastructure",
    },
    "opinion_observation": {
        "ai", "artificial intelligence", "developer", "coding", "software", "automation", "model", "openai",
        "anthropic", "nvidia", "google", "microsoft", "apple", "cloud", "startup", "open source",
    },
    "humor": {"ai", "developer", "coding", "software", "game", "gaming", "internet", "tech"},
    "question": {"ai", "developer", "coding", "software", "game", "gaming", "tech", "technology"},
    "news_explainer": {"security", "cybersecurity", "ransomware", "breach", "vulnerability", "zero-day", "hacker", "malware", "phishing", "data leak"},
    "gaming": {"game", "gaming", "gta", "playstation", "xbox", "nintendo", "steam", "esports", "rockstar", "rockstar games"},
}


def _article_relevance(article, strategy_kind):
    keywords = ARTICLE_RELEVANCE_KEYWORDS.get(strategy_kind, set())
    if not keywords:
        return 0
    text = f"{article.get('title', '')} {article.get('description', '')}".lower()
    return sum(1 for keyword in keywords if keyword in text)


def _pick_article(articles, category, strategy_kind=None):
    if not articles:
        raise RuntimeError("No articles available for strategy selection")
    candidates = [item for item in articles if category and item.get("category") == category] if category else list(articles)
    if not candidates:
        candidates = list(articles)

    if strategy_kind:
        ranked = sorted(
            enumerate(candidates),
            key=lambda pair: (_article_relevance(pair[1], strategy_kind), -pair[0]),
            reverse=True,
        )
        best_score = _article_relevance(ranked[0][1], strategy_kind)
        if best_score > 0:
            return ranked[0][1]
    return candidates[0]


def _fresh_topic(state):
    used = set(state.get("recent_relatable_topic_tags", []))
    topics = [item for item in bot.RELATABLE_TOPICS if item[0] not in used]
    return (topics or bot.RELATABLE_TOPICS)[0]


def _topic_from_slot(recipe, article):
    return f"{article['title']}. {article.get('description', '')}".strip()


def _editorial_brief_from_slot(recipe, relatable_topic):
    kind, _, hook, instruction = recipe
    parts = [
        f"Format: {kind}.",
        f"Hook direction: {hook}.",
        f"Editorial instruction: {instruction}.",
        "Creator-safety rule: editorial context is not factual evidence. never invent hardware, spending, actions, results, quotes, or experiences. If first-person wording is unsupported, use an observational or general-builder framing instead.",
    ]
    if relatable_topic:
        parts.append(f"Relatable context: {relatable_topic[1]}.")
    return " ".join(parts)


def record_performance(state, data):
    row = performance_row(data)
    row["normalized"] = normalized_metrics(row)
    history = state.setdefault("performance_history", [])
    history.append(row)
    state["performance_history"] = history[-200:]
    return row


def _is_retryable_provider_error(error):
    message = str(error).lower()
    return "openrouter returned empty content" in message or "openrouter returned no choices" in message


def _provider_stage(prompt):
    text = str(prompt or "").lstrip().lower()
    if text.startswith("fact-check"):
        return "fact_check"
    if text.startswith("generate a diverse idea pool"):
        return "angles"
    if text.startswith("write one natural threads post"):
        return "draft"
    return "unknown"


def _provider_error_kind(error):
    message = str(error).lower()
    if "empty content" in message:
        return "empty_response"
    if "no choices" in message:
        return "missing_choices"
    if "http 4" in message:
        return "http_4xx"
    if "http 5" in message:
        return "http_5xx"
    return type(error).__name__.lower()


def _instrument_provider(provider, attempt):
    def call(prompt):
        stage = _provider_stage(prompt)
        print(
            f"PIPELINE event=provider_request stage={stage} provider=openrouter "
            f"model=openrouter/free attempt={attempt}"
        )
        try:
            content = provider(prompt)
        except Exception as error:
            print(
                f"PIPELINE event=provider_response stage={stage} outcome=error "
                f"error_kind={_provider_error_kind(error)}"
            )
            raise
        content_length = len(content) if isinstance(content, str) else -1
        print(
            f"PIPELINE event=provider_response stage={stage} outcome=ok "
            f"content_chars={content_length}"
        )
        return content

    call._provider = provider
    return call


def _diagnose_result(result):
    diagnosed = dict(result)
    decision = str(diagnosed.get("decision", "UNKNOWN")).upper()
    if decision != "REJECT":
        return diagnosed

    fact_confidence = diagnosed.get("fact_confidence")
    fact_reason = str(diagnosed.get("fact_gate", "")).strip()
    if isinstance(fact_confidence, (int, float)) and fact_confidence < 0.7:
        diagnosed["stage"] = "fact_check"
        diagnosed["rejection_reason"] = fact_reason or "Fact confidence is below the 0.70 safety threshold."
        diagnosed["recoverable"] = "contradicted" not in diagnosed["rejection_reason"].lower()
        return diagnosed

    angles = diagnosed.get("angles") or []
    if angles and not diagnosed.get("top_pick"):
        best = max(angles, key=lambda item: float(item.get("idea_score", 0)))
        best_score = float(best.get("idea_score", 0))
        best_decision = str(best.get("idea_decision", "REJECT"))
        diagnosed["stage"] = "idea_selection"
        diagnosed["rejection_reason"] = (
            f"No eligible idea met the idea gate; best_idea_score={best_score:.1f}/100 "
            f"best_idea_decision={best_decision} required_score>=80 and hard dimensions "
            "scroll_stop, originality, and debate_potential must each be >=7/10."
        )
        diagnosed["recoverable"] = True
        return diagnosed

    stress = diagnosed.get("stress_test") or {}
    if stress and not bool(stress.get("all_pass", False)):
        failed = [name for name, passed in stress.items() if name != "all_pass" and not bool(passed)]
        diagnosed["stage"] = "stress_test"
        diagnosed["rejection_reason"] = (
            "Stress test failed: " + ", ".join(failed or ["unknown_check"]) + "."
        )
        diagnosed["recoverable"] = True
        return diagnosed

    diagnosed["stage"] = "final_decision"
    diagnosed["rejection_reason"] = diagnosed.get("rejection_reason") or fact_reason or "Final decision rejected the pipeline result."
    diagnosed["recoverable"] = True
    return diagnosed


def _log_pipeline_result(result):
    result = _diagnose_result(result)
    keys = ",".join(sorted(str(key) for key in result.keys()))
    print(
        f"PIPELINE event=parsed_result outcome=ok decision={result.get('decision', 'UNKNOWN')} "
        f"keys={keys}"
    )

    fact_gate = result.get("fact_gate")
    if fact_gate is not None:
        confidence = result.get("fact_confidence", "unknown")
        outcome = "reject" if result.get("stage") == "fact_check" else "pass"
        print(
            f"PIPELINE event=validation_result stage=fact_check outcome={outcome} "
            f"fact_confidence={confidence}"
        )

    angles = result.get("angles") or []
    if angles:
        eligible = sum(1 for angle in angles if angle.get("idea_decision") in {"EXCEPTIONAL", "STRONG", "PROMISING"})
        print(
            f"PIPELINE event=quality_scoring stage=idea_selection angles={len(angles)} "
            f"eligible={eligible} best_idea_score={max(float(a.get('idea_score', 0)) for a in angles):.1f}"
        )

    if "quality_score" in result or "final_score" in result:
        print(
            f"PIPELINE event=quality_scoring stage=final "
            f"quality_score={result.get('quality_score', 'unknown')} "
            f"final_score={result.get('final_score', 'unknown')}"
        )

    if result.get("decision") == "REJECT":
        print(
            f"PIPELINE event=decision outcome=REJECT stage={result.get('stage', 'unknown')} "
            f"recoverable={bool(result.get('recoverable', False))}"
        )
        print(
            f"PIPELINE event=rejection_reason stage={result.get('stage', 'unknown')} "
            f"reason={result.get('rejection_reason', 'unknown')}"
        )
    else:
        print(f"PIPELINE event=decision outcome={result.get('decision', 'UNKNOWN')} stage=final_decision")
    return result


def _write_pipeline_report(result):
    result = _diagnose_result(result)
    with open(PIPELINE_REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(
            "PIPELINE DIAGNOSTICS\n"
            f"STAGE: {result.get('stage', 'unknown')}\n"
            f"DECISION: {result.get('decision', 'UNKNOWN')}\n"
            f"RECOVERABLE: {bool(result.get('recoverable', False))}\n"
            f"REJECTION REASON: {result.get('rejection_reason', '')}\n\n"
        )
        handle.write(render_report(result))


def _retry_brief(editorial_brief, error):
    message = str(error).lower()
    if "angles are repetitive" in message or "expected at least 8 angles" in message:
        return (
            f"{editorial_brief} "
            "ANGLE DIVERSITY RETRY: regenerate the angle pool from the same source facts. "
            "Return at least 10 angles using at least 8 different allowed angle types. "
            "The first 8 accepted angles must have different angle types and materially different core_claims. "
            "Do not restate the same thesis with different wording. Vary the mechanism, stakeholder, consequence, "
            "time horizon, incentive, behavior, trade-off, or question being explored. "
            "Keep every supporting fact grounded in the supplied fact check/source material."
        ).strip()
    if "no eligible idea met the idea gate" in message:
        return (
            f"{editorial_brief} "
            "IDEA GATE RETRY: the previous angle pool produced no publishable idea. "
            "Generate at least 10 materially different angles, but prioritize angles that can satisfy the existing idea gate. "
            "Each angle must have scroll_stop >= 7, originality >= 7, debate_potential >= 7, and a weighted idea score >= 80. "
            "Do not inflate scores without changing the underlying angle. Improve the actual hook, originality, and debate value. "
            "Keep all factual claims grounded in the supplied fact check and sources."
        ).strip()
    if _is_retryable_provider_error(error):
        return (
            f"{editorial_brief} "
            "PROVIDER OUTPUT RETRY: the previous provider response contained no usable text. "
            "Return one complete valid JSON object with every required field explicitly populated. "
            "Do not return an empty response, null content, markdown, or explanation outside the JSON object."
        ).strip()
    return (
        f"{editorial_brief} "
        "VALIDATION RETRY: the previous model response violated the required JSON/data contract. "
        "Return every required field explicitly; for each factual claim, include claim, status, evidence, "
        "confidence, and central. Never leave status blank. Do not omit required fields."
    ).strip()


def _evaluate_with_diagnostics(topic, article, editorial_brief, provider, attempt):
    result = evaluate_topic(
        topic,
        [article],
        _instrument_provider(provider, attempt),
        editorial_brief=editorial_brief,
    )
    return _log_pipeline_result(result)


def _run_pipeline(topic, article, editorial_brief=""):
    try:
        result = _evaluate_with_diagnostics(
            topic, article, editorial_brief, bot.openrouter_chat_json, attempt=1
        )
    except PipelineError as first_error:
        print(
            f"PIPELINE event=validation_result outcome=error stage=validation "
            f"error_kind={_provider_error_kind(first_error)}"
        )
        retry_brief = _retry_brief(editorial_brief, first_error)
        print(
            f"PIPELINE event=retry trigger=validation_or_provider_error attempt=2 "
            f"error_kind={_provider_error_kind(first_error)}"
        )
        try:
            result = _evaluate_with_diagnostics(
                topic, article, retry_brief,
                _retry_openrouter_chat if _is_retryable_provider_error(first_error) else bot.openrouter_chat_json,
                attempt=2,
            )
            return result
        except Exception as retry_error:
            print(
                f"PIPELINE event=final_outcome outcome=FAILURE stage=validation_or_provider "
                f"error_kind={_provider_error_kind(retry_error)}"
            )
            raise PipelineError(
                f"Pipeline retry failed after {type(first_error).__name__}: "
                f"{type(retry_error).__name__}: {retry_error}"
            ) from retry_error
    except RuntimeError as first_error:
        if not _is_retryable_provider_error(first_error):
            print(
                f"PIPELINE event=final_outcome outcome=FAILURE stage=provider "
                f"error_kind={_provider_error_kind(first_error)}"
            )
            raise
        retry_brief = _retry_brief(editorial_brief, first_error)
        print(
            f"PIPELINE event=retry trigger=provider_error attempt=2 "
            f"error_kind={_provider_error_kind(first_error)}"
        )
        try:
            result = _evaluate_with_diagnostics(
                topic, article, retry_brief, _retry_openrouter_chat, attempt=2
            )
            return result
        except Exception as retry_error:
            print(
                f"PIPELINE event=final_outcome outcome=FAILURE stage=provider "
                f"error_kind={_provider_error_kind(retry_error)}"
            )
            raise PipelineError(
                f"Pipeline provider output failed: {type(first_error).__name__}; "
                f"retry failed: {type(retry_error).__name__}: {retry_error}"
            ) from retry_error

    result = _diagnose_result(result)
    if result.get("decision") != "REJECT" or not result.get("recoverable", False):
        print(
            f"PIPELINE event=final_outcome outcome={result.get('decision', 'UNKNOWN')} "
            f"stage={result.get('stage', 'final_decision')}"
        )
        return result

    retry_brief = _retry_brief(editorial_brief, result["rejection_reason"])
    print(
        f"PIPELINE event=retry trigger=decision_reject attempt=2 "
        f"stage={result.get('stage', 'unknown')} reason={result.get('rejection_reason', 'unknown')}"
    )
    try:
        retried = _evaluate_with_diagnostics(
            topic, article, retry_brief, bot.openrouter_chat_json, attempt=2
        )
        final_result = _diagnose_result(retried)
        print(
            f"PIPELINE event=final_outcome outcome={final_result.get('decision', 'UNKNOWN')} "
            f"stage={final_result.get('stage', 'final_decision')}"
        )
        return final_result
    except Exception as retry_error:
        print(
            f"PIPELINE event=final_outcome outcome=FAILURE stage=decision_retry "
            f"error_kind={_provider_error_kind(retry_error)}"
        )
        raise PipelineError(
            f"Pipeline rejection retry failed: {type(retry_error).__name__}: {retry_error}"
        ) from retry_error


def _retry_openrouter_chat(prompt):
    """Retry JSON stages without provider-enforced JSON mode; content_engine still validates JSON."""
    return bot.openrouter_chat(prompt, json_mode=False)


def generate_strategy_threads(articles, state):
    cursor = int(state.get("strategy_cursor", 0))
    recipe = STRATEGY_POSTS[cursor % len(STRATEGY_POSTS)]
    kind, preferred_category, _, _ = recipe
    article = _pick_article(articles, preferred_category, kind)
    relatable_topic = _fresh_topic(state) if preferred_category is None else None
    topic = _topic_from_slot(recipe, article)
    editorial_brief = _editorial_brief_from_slot(recipe, relatable_topic)

    result = _run_pipeline(topic, article, editorial_brief)
    if result.get("decision") == "REWRITE":
        rewrite_brief = f"{editorial_brief} Rewrite pass: preserve the strongest defensible claim, increase specificity and tension, and remove generic wording."
        result = _run_pipeline(topic, article, rewrite_brief)
    result = _diagnose_result(result)
    if result.get("decision") != "PUBLISH":
        _write_pipeline_report(result)
        raise RuntimeError(
            f"Content pipeline decision: {result.get('decision', 'UNKNOWN')} "
            f"stage={result.get('stage', 'unknown')} "
            f"reason={result.get('rejection_reason', 'unspecified')}"
        )

    _write_pipeline_report(result)

    post = {
        "number": 1,
        "title": result["top_pick"]["core_claim"],
        "body": result["draft"],
        "keywords": [kind, article.get("category", "technology")],
        "topic_tag": "current_news",
        "source": "NEWS 1",
        "idea_score": result["top_pick"]["idea_score"],
        "quality_score": result["quality_score"],
        "final_score": result["final_score"],
        "decision": result["decision"],
        "fact_confidence": result["fact_confidence"],
    }
    state["strategy_cursor"] = cursor + 1
    state["strategy_last_format"] = kind
    state["strategy_last_run_at"] = datetime.now(timezone.utc).isoformat()
    state["strategy_targets"] = STRATEGY_TARGETS
    state["strategy_mix"] = STRATEGY_MIX
    state["last_pipeline_decision"] = result["decision"]
    state["last_pipeline_scores"] = {
        "idea_score": post["idea_score"],
        "quality_score": post["quality_score"],
        "final_score": post["final_score"],
        "fact_confidence": post["fact_confidence"],
    }
    state.setdefault("recent_content_topics", []).append(article.get("title", topic))
    print(
        f"Strategy slot {cursor + 1}: {kind} / {preferred_category or 'relatable'} "
        f"idea={post['idea_score']:.1f} quality={post['quality_score']:.1f} "
        f"final={post['final_score']:.1f} decision={post['decision']}"
    )
    return post["body"], [post]


def main():
    bot.generate_threads = generate_strategy_threads
    bot.TOTAL_POSTS = 1
    bot.IMAGE_POST_COUNT = min(bot.IMAGE_POST_COUNT, 1)
    bot.main()


if __name__ == "__main__":
    main()
