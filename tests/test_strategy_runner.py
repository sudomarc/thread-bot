import json
import unittest
from unittest.mock import patch

import content_engine
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

    def test_record_performance_normalizes_metrics(self):
        state = {}
        row = strategy_runner.record_performance(state, {
            "post_id": "p1",
            "date": "2026-09-11",
            "topic": "AI",
            "angle": "economic",
            "idea_score": 90,
            "quality_score": 85,
            "final_score": 88,
            "views": 1000,
            "likes": 50,
            "replies": 20,
            "reposts": 10,
            "quotes": 5,
            "follows": 10,
        })
        self.assertEqual(row["normalized"]["reply_rate"], 0.02)
        self.assertEqual(len(state["performance_history"]), 1)

    def test_generate_strategy_threads_runs_fact_angle_and_draft_stages(self):
        articles = [{
            "category": "gaming",
            "title": "A current gaming story",
            "description": "A useful summary.",
            "published": "2026-09-11T10:00:00Z",
            "url": "https://example.com/story",
        }]
        state = {"strategy_cursor": 3, "recent_post_titles": [], "recent_relatable_topic_tags": []}
        angles = []
        for index in range(8):
            scores = {key: 9 for key in content_engine.IDEA_WEIGHTS}
            angles.append({
                "angle": f"angle_{index}",
                "core_claim": f"Distinct claim {index}",
                "why_it_matters": "Specific consequence",
                "target_reaction": "Reasonable disagreement",
                "supporting_facts": ["A supplied fact"],
                "potential_counterargument": "A reasonable counterargument",
                "scores": scores,
            })
        responses = [
            json.dumps({"claims": [{"claim": "The story happened", "status": "VERIFIED", "evidence": "A useful summary.", "confidence": 9, "central": True}]}),
            json.dumps({"angles": angles}),
            json.dumps({
                "draft": "A specific take on why this gaming story changes the economics of the next wave of games.",
                "quality": {key: 9 for key in content_engine.QUALITY_WEIGHTS},
                "stress": {
                    "scroll_answer": "The opening makes a concrete claim.",
                    "reply_example": "A reader could disagree about the business impact.",
                    "counterargument": "Better technology does not guarantee adoption.",
                    "generic": False,
                    "quotable_line": "The interesting shift is who controls the constraint.",
                },
                "claims": [{"claim": "The story happened", "status": "VERIFIED", "evidence": "A useful summary.", "confidence": 9, "central": True}],
            }),
        ]
        with patch.object(strategy_runner.bot, "openrouter_chat", side_effect=responses):
            with patch.object(strategy_runner, "PIPELINE_REPORT_PATH", "/tmp/thread-bot-evaluation.txt"):
                content, posts = strategy_runner.generate_strategy_threads(articles, state)
        self.assertIn("specific take", content)
        self.assertEqual(posts[0]["decision"], "PUBLISH")
        self.assertGreaterEqual(posts[0]["idea_score"], 90)
        self.assertEqual(state["strategy_cursor"], 4)


if __name__ == "__main__":
    unittest.main()
