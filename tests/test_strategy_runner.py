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

    def test_validate_strategy_rejects_repeat_title(self):
        post = [{
            "number": 1,
            "title": "Same title",
            "body": "Same title\nA post.",
            "source": "NONE",
            "topic_tag": "ai_hype_fatigue",
        }]
        with self.assertRaisesRegex(ValueError, "repeated"):
            strategy_runner._validate_strategy_post(
                post,
                {"category": "technology"},
                "NONE",
                "ai_hype_fatigue",
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


if __name__ == "__main__":
    unittest.main()
