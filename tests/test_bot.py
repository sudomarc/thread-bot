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

    def test_canonicalize_url_removes_tracking(self):
        self.assertEqual(
            bot.canonicalize_url("HTTPS://Example.COM/a/?utm_source=x&b=2&fbclid=y#frag"),
            "https://example.com/a?b=2",
        )

    def test_parse_posts_keeps_keywords_and_sequence(self):
        raw = """POST 1
Headline one
A short post.
KEYWORDS: one, two
TOPIC_TAG: current_news
SOURCE: NEWS 1

POST 2
Headline two
Another short post.
KEYWORDS: three
TOPIC_TAG: imposter_syndrome
SOURCE: NONE

POST 3
Headline three
Third post.
KEYWORDS: four
TOPIC_TAG: current_news
SOURCE: NEWS 3
"""
        with patch.object(bot, "TOTAL_POSTS", 3):
            posts = bot.parse_posts(raw)
        self.assertEqual([p["number"] for p in posts], [1, 2, 3])
        self.assertEqual(posts[0]["keywords"], ["one", "two"])

    def test_validate_rejects_duplicate_source(self):
        articles = [{"category": "gaming"}, {"category": "technology"}, {"category": "cybersecurity"}]
        posts = [
            {"number": 1, "body": "one", "title": "one", "source": "NEWS 1", "topic_tag": "current_news"},
            {"number": 2, "body": "two", "title": "two", "source": "NEWS 1", "topic_tag": "current_news"},
            {"number": 3, "body": "three", "title": "three", "source": "NEWS 3", "topic_tag": "current_news"},
        ]
        with patch.object(bot, "TOTAL_POSTS", 3):
            with self.assertRaisesRegex(ValueError, "Source reused"):
                bot.validate_posts(posts, articles)

    def test_validate_requires_gaming_source(self):
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
        with patch.object(bot, "TOTAL_POSTS", 3):
            with self.assertRaises(ValueError):
                bot.validate_posts(posts, articles)

    def test_state_save_is_atomic_and_preserves_schema(self):
        state = bot.default_state()
        with tempfile.TemporaryDirectory() as directory:
            old_path = bot.STATE_FILE_PATH
            bot.STATE_FILE_PATH = os.path.join(directory, "history.json")
            try:
                bot.save_state(state)
                loaded = bot.load_state()
                self.assertTrue(loaded["last_run_at"])
                self.assertEqual(loaded["schema_version"], 2)
                self.assertTrue(os.path.exists(bot.STATE_FILE_PATH))
            finally:
                bot.STATE_FILE_PATH = old_path

    def test_write_report_contains_only_used_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            old_report = bot.REPORT_FILE_PATH
            old_sources = bot.SOURCES_FILE_PATH
            bot.REPORT_FILE_PATH = os.path.join(directory, "latest_threads.txt")
            bot.SOURCES_FILE_PATH = os.path.join(directory, "latest_sources.txt")
            try:
                bot.write_report(
                    "post",
                    [{
                        "category": "gaming",
                        "published": "2026-09-03T00:00:00Z",
                        "source": "Example",
                        "title": "Title",
                        "url": "https://example.com",
                    }],
                )
                with open(bot.SOURCES_FILE_PATH, encoding="utf-8") as handle:
                    self.assertIn("SOURCE 1 | gaming", handle.read())
            finally:
                bot.REPORT_FILE_PATH = old_report
                bot.SOURCES_FILE_PATH = old_sources

    def test_email_uses_utf8(self):
        self.assertEqual(bot.MIMEText("é — ", "plain", "utf-8").get_content_charset(), "utf-8")


if __name__ == "__main__":
    unittest.main()
