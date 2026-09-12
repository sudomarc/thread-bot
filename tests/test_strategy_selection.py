import unittest

import strategy_runner


class StrategySelectionTests(unittest.TestCase):
    def test_builder_slot_skips_irrelevant_technology_story(self):
        articles = [
            {
                "category": "technology",
                "title": "Joint CSIR-UGC NET June 2026 result announced",
                "description": "Candidates can download their examination scorecards.",
            },
            {
                "category": "technology",
                "title": "Open source AI coding tool adds local model support",
                "description": "Developers can run an AI model in a coding workflow.",
            },
        ]
        selected = strategy_runner._pick_article(articles, "technology", "builder_experience")
        self.assertEqual(selected["title"], "Open source AI coding tool adds local model support")

    def test_relevance_score_is_zero_for_unrelated_story(self):
        article = {
            "category": "technology",
            "title": "University exam result announced",
            "description": "Candidates can download their scorecards.",
        }
        self.assertEqual(strategy_runner._article_relevance(article, "builder_experience"), 0)


if __name__ == "__main__":
    unittest.main()
