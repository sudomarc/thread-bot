from datetime import datetime, timezone

import bot
from content_engine import evaluate_topic, normalized_metrics, performance_row, render_report


STRATEGY_TARGETS = {
    "views": "20,000-30,000 / 30 days",
    "spectators": "12,000+ / 30 days",
    "followers": "75-150 / 30 days",
    "conversion": "0.3-0.6% views-to-followers",
    "posts": "20-25 / 30 days",
}

STRATEGY_POSTS = [
    ("news_opinion", "technology", "AI isn't replacing everyone. It's changing who can build what.", "Take a strong, defensible position on the supplied story and invite disagreement."),
    ("question", None, "What's one AI product you genuinely couldn't live without anymore?", "Ask a simple question that makes AI/tech people want to answer from experience."),
    ("humor", None, "Me: I'll only use AI for 5 minutes.", "Write a short, highly relatable tech/AI joke using the supplied story as context."),
    ("gaming", "gaming", "AI NPCs could change gaming more than better graphics ever did.", "Use a current gaming story to make a forward-looking claim about games and AI."),
    ("big_idea", "technology", "The internet is entering a weird phase.", "Turn the supplied story into a broader observation about AI, the internet, or software."),
    ("news_explainer", "technology", "Something interesting is happening in AI right now.", "Explain the supplied story in plain English, then say why it matters to builders/users."),
    ("question", None, "What are you actually building with AI right now?", "Ask builders to share projects. Optimize for replies, not a lecture."),
    ("humor", None, "Developers when the code works on the first try:", "Write a short developer/AI joke grounded in the supplied story."),
    ("news_opinion", "cybersecurity", "Security gets interesting when the easiest attack is also the cheapest.", "Give a sharp security/technology take grounded in the supplied current story."),
    ("ai_observation", None, "We're making the distance between 'I have an idea' and 'I built it' smaller.", "Write a concise observation about AI lowering the barrier to building."),
    ("gaming", "gaming", "What game would you want an AI-powered NPC to actually remember you in?", "Use the gaming source as context, but make the post primarily a question that invites stories."),
    ("big_idea", "technology", "Most people don't need a better model. They need to use the one they have better.", "Make a provocative but useful point about AI usage, grounded in the current story."),
    ("news_explainer", "cybersecurity", "This security story matters for one reason:", "Explain the practical implication of the supplied cybersecurity story without fearmongering."),
    ("question", None, "If AI became 10x smarter tomorrow, what would you actually use it for?", "Invite concrete answers. Avoid generic 'make the world better' responses."),
    ("humor", None, "Me opening my code after asking AI to 'just fix one thing'...", "Write a concise coding/AI joke using the current story as context."),
    ("news_opinion", "gaming", "We're probably underestimating what games can become.", "Turn the current gaming story into a strong opinion about the future of games."),
    ("ai_observation", None, "The best AI users aren't always the smartest people in the room.", "Make a concise point about better questions, workflows, or judgment."),
    ("news_opinion", "technology", "Hot take: most AI products are adding features faster than people can build habits around them.", "Take a clear position using the supplied current story as evidence or context."),
    ("question", None, "What tech trend do you think everyone is overhyping right now?", "Create a debate-friendly question for the AI/tech audience, informed by the supplied story."),
    ("big_idea", "technology", "One person can build what used to require a team.", "Use the current story to frame what one builder can now do with AI/software."),
]

PIPELINE_REPORT_PATH = "state/latest_content_evaluation.txt"


def _pick_article(articles, category):
    if category:
        matches = [item for item in articles if item.get("category") == category]
        if matches:
            return matches[0]
    preferred = [item for item in articles if item.get("category") == "technology"]
    return (preferred or articles)[0]


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


def _resilient_openrouter_chat(prompt, timeout=60):
    try:
        return bot.openrouter_chat(prompt, timeout=timeout)
    except RuntimeError as exc:
        if str(exc) != "OpenRouter returned empty content":
            raise
        print("OpenRouter returned an empty payload; retrying once within the provider resilience budget.")
        return bot.openrouter_chat(prompt, timeout=timeout)


def _run_pipeline(topic, article, editorial_brief=""):
    return evaluate_topic(topic, [article], _resilient_openrouter_chat, editorial_brief=editorial_brief)


def generate_strategy_threads(articles, state):
    cursor = int(state.get("strategy_cursor", 0))
    recipe = STRATEGY_POSTS[cursor % len(STRATEGY_POSTS)]
    kind, preferred_category, _, _ = recipe
    article = _pick_article(articles, preferred_category)
    relatable_topic = _fresh_topic(state) if preferred_category is None else None
    topic = _topic_from_slot(recipe, article)
    editorial_brief = _editorial_brief_from_slot(recipe, relatable_topic)

    result = _run_pipeline(topic, article, editorial_brief)
    if result.get("decision") == "REWRITE":
        rewrite_brief = f"{editorial_brief} Rewrite pass: preserve the strongest defensible claim, increase specificity and tension, and remove generic wording."
        result = _run_pipeline(topic, article, rewrite_brief)
    if result.get("decision") != "PUBLISH":
        with open(PIPELINE_REPORT_PATH, "w", encoding="utf-8") as handle:
            handle.write(render_report(result))
        raise RuntimeError(f"Content pipeline decision: {result.get('decision', 'UNKNOWN')}")

    with open(PIPELINE_REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(render_report(result))

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
