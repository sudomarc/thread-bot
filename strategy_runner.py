from datetime import datetime, timezone

import bot


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
    ("humor", None, "Me: I'll only use AI for 5 minutes.", "Write a short, highly relatable tech/AI joke. Keep it human and punchy."),
    ("gaming", "gaming", "AI NPCs could change gaming more than better graphics ever did.", "Use a current gaming story to make a forward-looking claim about games and AI."),
    ("big_idea", "technology", "The internet is entering a weird phase.", "Turn the supplied story into a broader observation about AI, the internet, or software. End with a discussion question."),
    ("news_explainer", "technology", "Something interesting is happening in AI right now.", "Explain the supplied story in plain English, then say why it matters to builders/users."),
    ("question", None, "What are you actually building with AI right now?", "Ask builders to share projects. Optimize for replies, not a lecture."),
    ("humor", None, "Developers when the code works on the first try:", "Write a short developer/AI relatable joke. One setup, one punchline."),
    ("news_opinion", "cybersecurity", "Security gets interesting when the easiest attack is also the cheapest.", "Give a sharp security/technology take grounded in the supplied current story."),
    ("ai_observation", None, "We're making the distance between 'I have an idea' and 'I built it' smaller.", "Write a concise observation about AI lowering the barrier to building."),
    ("gaming", "gaming", "What game would you want an AI-powered NPC to actually remember you in?", "Use the gaming source only as context, but make the post primarily a question that invites stories."),
    ("big_idea", "technology", "Most people don't need a better model. They need to use the one they have better.", "Make a provocative but useful point about AI usage, grounded when possible in the current story."),
    ("news_explainer", "cybersecurity", "This security story matters for one reason:", "Explain the practical implication of the supplied cybersecurity story without fearmongering."),
    ("question", None, "If AI became 10x smarter tomorrow, what would you actually use it for?", "Invite concrete answers. Avoid generic 'make the world better' responses."),
    ("humor", None, "Me opening my code after asking AI to 'just fix one thing'...", "Write a concise coding/AI joke with a recognizable punchline."),
    ("news_opinion", "gaming", "We're probably underestimating what games can become.", "Turn the current gaming story into a strong opinion about the future of games."),
    ("ai_observation", None, "The best AI users aren't always the smartest people in the room.", "Make a concise point about better questions, workflows, or judgment rather than raw intelligence."),
    ("news_opinion", "technology", "Hot take: most AI products are adding features faster than people can build habits around them.", "Take a clear position using the supplied current story as evidence or context."),
    ("question", None, "What tech trend do you think everyone is overhyping right now?", "Create a debate-friendly question for the AI/tech audience."),
    ("big_idea", "technology", "One person can build what used to require a team.", "Use the current story to frame what one builder can now do with AI/software. End with a question."),
]


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


def _build_prompt(recipe, article, relatable_topic, source_marker):
    kind, _, hook, instruction = recipe
    article_block = (
        f"SOURCE ARTICLE\nCATEGORY: {article['category']}\nTITLE: {article['title']}\n"
        f"SUMMARY: {article['description']}\nPUBLISHED: {article['published']}\nURL: {article['url']}"
    )
    topic_block = "NONE"
    if relatable_topic:
        topic_block = f"{relatable_topic[0]}: {relatable_topic[1]}"
    tag = "current_news" if source_marker != "NONE" else relatable_topic[0]
    return f"""You are writing ONE English-language Threads post for an AI/tech/gaming/internet audience.

30-DAY STRATEGY TARGETS:
- Views: {STRATEGY_TARGETS['views']}
- Followers: {STRATEGY_TARGETS['followers']}
- Views-to-followers conversion: {STRATEGY_TARGETS['conversion']}
- Posting cadence: 5 targeted posts per week

TODAY'S FORMAT: {kind}
HOOK DIRECTION: {hook}
EDITORIAL INSTRUCTION: {instruction}

The supplied audience is primarily adults interested in AI and technology, with strong gaming overlap. Write for discovery first, then conversion: make the post worth following the account for.

Rules:
- Sound like a real person, not a company or newswire.
- Strong first line. Avoid generic introductions.
- Prefer short lines and readable spacing.
- Do not over-explain.
- For questions, make the question the reason to reply.
- For humor, keep it concise and relatable.
- For news, use only the supplied article facts. Never invent quotes, numbers, motives, or details.
- For rumors/leaks, clearly label them as reported/alleged.
- Do not provide stolen credentials, leaked files, piracy links, or instructions for accessing stolen material.
- Do not use hashtags unless genuinely useful; the bot's metadata is separate.

RELATABLE TOPIC OPTION: {topic_block}

{article_block}

Output ONLY:
POST 1
<title/opening line>
<2-6 short lines of post text>
KEYWORDS: keyword1, keyword2
TOPIC_TAG: {tag}
SOURCE: {source_marker}
"""


def _validate_strategy_post(posts, article, source_marker, topic_tag, previous_titles):
    if len(posts) != 1 or posts[0].get("number") != 1:
        raise ValueError("Strategy generation must produce exactly one POST 1")
    post = posts[0]
    body = bot.clean_text(post.get("body"))
    if not body:
        raise ValueError("Strategy post is empty")
    if len(body) > 1500:
        raise ValueError("Strategy post is excessively long")
    if post.get("source", "").strip().upper() != source_marker:
        raise ValueError(f"Strategy post must use SOURCE: {source_marker}")
    if post.get("topic_tag", "").strip() != topic_tag:
        raise ValueError(f"Strategy post must use TOPIC_TAG: {topic_tag}")
    key = bot.title_key(post.get("title"))
    if not key:
        raise ValueError("Strategy post has no title")
    previous = {bot.title_key(title) for title in previous_titles if title}
    if key in previous:
        raise ValueError("Strategy post repeated a recent title")
    return True


def generate_strategy_threads(articles, state):
    cursor = int(state.get("strategy_cursor", 0))
    recipe = STRATEGY_POSTS[cursor % len(STRATEGY_POSTS)]
    kind, preferred_category, _, _ = recipe

    news_kinds = {"news_opinion", "news_explainer", "gaming"}
    use_source = kind in news_kinds or preferred_category is not None
    article = _pick_article(articles, preferred_category) if use_source else _pick_article(articles, "technology")
    article_index = articles.index(article) + 1
    source_marker = f"NEWS {article_index}" if use_source else "NONE"
    relatable_topic = _fresh_topic(state) if not use_source else None
    topic_tag = "current_news" if use_source else relatable_topic[0]

    last_error = None
    for attempt in range(1, bot.MAX_GENERATION_ATTEMPTS + 1):
        try:
            prompt = _build_prompt(recipe, article, relatable_topic, source_marker)
            raw = bot.openrouter_chat(prompt)
            posts = bot.parse_posts(raw)
            _validate_strategy_post(posts, article, source_marker, topic_tag, state.get("recent_post_titles", []))
            candidate = posts[0]["body"].strip()
            state["strategy_cursor"] = cursor + 1
            state["strategy_last_format"] = kind
            state["strategy_last_run_at"] = datetime.now(timezone.utc).isoformat()
            state["strategy_targets"] = STRATEGY_TARGETS
            print(f"Strategy slot {cursor + 1}: {kind} / {preferred_category or 'relatable'}")
            return candidate, posts
        except Exception as exc:
            last_error = exc
            print(f"Strategy generation attempt {attempt}/{bot.MAX_GENERATION_ATTEMPTS} rejected: {type(exc).__name__}: {exc}")

    raise RuntimeError(f"All strategy generation attempts failed: {last_error}")


def main():
    bot.generate_threads = generate_strategy_threads
    bot.TOTAL_POSTS = 1
    bot.IMAGE_POST_COUNT = min(bot.IMAGE_POST_COUNT, 1)
    bot.main()


if __name__ == "__main__":
    main()
