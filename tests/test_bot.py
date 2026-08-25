import os
import tempfile
import unittest
from unittest.mock import patch

import bot


class BotUnitTests(unittest.TestCase):
    def test_clean_text_preserves_unicode(self):
        text = bot.clean_text("Take-Two’s GTA 6 — c’est réel.\x00")
        self.assertIn("’", text)
        self.assertIn("—", text)
        self.assertNotIn("\x00", text)

    def test_parse_posts_requires_exact_sequence(self):
        raw = """POST 1
Headline one
A short post.
KEYWORDS: one
TOPIC_TAG: current_news
SOURCE: NEWS 1

POST 2
Headline two
Another short post.
KEYWORDS: two
TOPIC_TAG: relatable
SOURCE: NONE

POST 3
Headline three
Third post.
KEYWORDS: three
TOPIC_TAG: current_news
SOURCE: NEWS 2

POST 4
Headline four
Fourth post.
KEYWORDS: four
TOPIC_TAG: relatable
SOURCE: NONE

POST 5
Headline five
Fifth post.
KEYWORDS: five
TOPIC_TAG: current_news
SOURCE: NEWS 3
"""
        old_total = bot.TOTAL_POSTS
        bot.TOTAL_POSTS = 5
        try:
            posts = bot.parse_posts(raw)
        finally:
            bot.TOTAL_POSTS = old_total
        self.assertEqual([p["number"] for p in posts], [1, 2, 3, 4, 5])
        self.assertEqual(posts[0]["source"], "NEWS 1")

    def test_validate_posts_requires_gaming_source(self):
        old_total = bot.TOTAL_POSTS
        bot.TOTAL_POSTS = 3
        articles = [
            {"category": "cybersecurity"},
            {"category": "technology"},
            {"category": "gaming"},
        ]
        posts = [
            {"number": 1, "body": "one", "title": "one", "source": "NEWS 1", "topic_tag": "current_news"},
            {"number": 2, "body": "two", "title": "two", "source": "NEWS 2", "topic_tag": "current_news"},
            {"number": 3, "body": "three", "title": "three", "source": "NEWS 1", "topic_tag": "current_news"},
        ]
        bot.TOTAL_POSTS = 3
        try:
            with self.assertRaises(ValueError):
                bot.validate_posts(posts, articles)
        finally:
            bot.TOTAL_POSTS = old_total

    def test_state_save_is_atomic(self):
        state = {
            "recent_relatable_topic_tags": [],
            "recent_post_titles": [],
            "seen_article_urls": [],
            "last_run_at": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            old_path = bot.STATE_FILE_PATH
            bot.STATE_FILE_PATH = os.path.join(directory, "history.json")
            try:
                bot.save_state(state)
                loaded = bot.load_state()
                self.assertTrue(loaded["last_run_at"])
                self.assertTrue(os.path.exists(bot.STATE_FILE_PATH))
            finally:
                bot.STATE_FILE_PATH = old_path

    def test_email_uses_utf8(self):
        self.assertEqual(bot.MIMEText("é — ", "plain", "utf-8").get_content_charset(), "utf-8")


if __name__ == "__main__":
    unittest.main()
