import unittest
from unittest.mock import patch

import strategy_runner


class StrategyRunnerTests(unittest.TestCase):
    def test_strategy_contains_20_slots_for_four_weeks(self):
        self.assertEqual(len(strategy_runner.STRATEGY_POSTS), 20)

    def test_strategy_targets_match_30_day_plan(self):
        self.assertEqual(strategy_runner.STRATEGY_TARGETS["followers"], "75-150 / 30 days")
        self.assertEqual(strategy_runner.STRATEGY_TARGETS["conversion"], "0.3-0.6% views-to-followers")
        self.assertEqual(strategy_runner.STRATEGY_TARGETS["posts"], "20-25 / 30 days")

    def test_fresh_topic_skips_recent_topic(self):
        state = {"recent_relatable_topic_tags": [strategy_runner.bot.RELATABLE_TOPICS[0][0]]}
        topic = strategy_runner._fresh_topic(state)
        self.assertNotEqual(topic[0], strategy_runner.bot.RELATABLE_TOPICS[0][0])

    def test_pick_article_prefers_requested_category(self):
        articles = [
            {"category": "technology", "title": "tech", "description": "", "published": "", "url": ""},
            {"category": "gaming", "title": "game", "description": "", "published": "", "url": ""},
        ]
        self.assertEqual(strategy_runner._pick_article(articles, "gaming")["title"], "game")

    def test_parse_single_strategy_post_accepts_one_post(self):
        raw = """Here is the draft:
POST 1
A better AI workflow matters more than another benchmark.
Most people are still learning how to use the models they already have.
The interesting part is what this changes for builders.
KEYWORDS: AI, builders
TOPIC_TAG: current_news
SOURCE: NEWS 2
"""
        posts = strategy_runner._parse_single_strategy_post(raw)
        self.assertEqual(posts[0]["number"], 1)
        self.assertEqual(posts[0]["title"], "A better AI workflow matters more than another benchmark.")
        self.assertEqual(posts[0]["keywords"], ["AI", "builders"])
        self.assertEqual(posts[0]["topic_tag"], "current_news")
        self.assertEqual(posts[0]["source"], "NEWS 2")

    def test_parse_single_strategy_post_rejects_extra_posts(self):
        raw = """POST 1
One title
One body.
KEYWORDS: one
TOPIC_TAG: current_news
SOURCE: NEWS 1

POST 2
Another title
Another body.
KEYWORDS: two
TOPIC_TAG: current_news
SOURCE: NEWS 2
"""
        with self.assertRaisesRegex(ValueError, "exactly one post"):
            strategy_runner._parse_single_strategy_post(raw)

    def test_validate_strategy_rejects_repeat_title(self):
        post = [{
            "number": 1,
            "title": "Same title",
            "body": "Same title\nA post.",
            "source": "NEWS 1",
            "topic_tag": "current_news",
        }]
        with self.assertRaisesRegex(ValueError, "repeated"):
            strategy_runner._validate_strategy_post(
                post,
                {"category": "technology"},
                "NEWS 1",
                "current_news",
                ["Same title"],
            )

    def test_generate_strategy_threads_advances_cursor_after_success(self):
        articles = [{
            "category": "gaming",
            "title": "A current gaming story",
            "description": "A useful summary.",
            "published": "2026-09-11T10:00:00Z",
            "url": "https://example.com/story",
        }]
        state = {"strategy_cursor": 3, "recent_post_titles": [], "recent_relatable_topic_tags": []}
        raw = """POST 1
AI NPCs could change gaming.
This is a concise test post.
KEYWORDS: gaming, AI
TOPIC_TAG: current_news
SOURCE: NEWS 1
"""
        with patch.object(strategy_runner.bot, "openrouter_chat", return_value=raw):
            content, posts = strategy_runner.generate_strategy_threads(articles, state)
        self.assertIn("AI NPCs", content)
        self.assertEqual(posts[0]["source"], "NEWS 1")
        self.assertEqual(state["strategy_cursor"], 4)

    def test_all_strategy_slots_use_current_news_for_single_post_validation(self):
        for _, _, _, _ in strategy_runner.STRATEGY_POSTS:
            self.assertEqual("current_news", strategy_runner._build_prompt(
                ("question", None, "hook", "instruction"),
                {"category": "technology", "title": "title", "description": "summary", "published": "date", "url": "url"},
                None,
                "NEWS 1",
            ).split("TOPIC_TAG: ")[1].splitlines()[0])


if __name__ == "__main__":
    unittest.main()
