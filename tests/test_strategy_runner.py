import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import content_engine
import strategy_runner


class StrategyRunnerTests(unittest.TestCase):
    def test_strategy_contains_20_slots_for_four_weeks(self):
        self.assertEqual(len(strategy_runner.STRATEGY_POSTS), 20)

    def test_strategy_mix_matches_observed_content_direction(self):
        counts = {}
        for recipe in strategy_runner.STRATEGY_POSTS:
            counts[recipe[0]] = counts.get(recipe[0], 0) + 1
        self.assertEqual(counts, strategy_runner.STRATEGY_MIX)
        self.assertEqual(counts["builder_experience"], 8)
        self.assertEqual(counts["humor"], 4)
        self.assertEqual(counts["opinion_observation"], 4)
        self.assertEqual(counts["question"], 2)
        self.assertEqual(counts["news_explainer"], 1)
        self.assertEqual(counts["gaming"], 1)

    def test_strategy_kind_maps_to_explicit_post_type(self):
        self.assertEqual(strategy_runner.POST_TYPE_BY_STRATEGY["builder_experience"], "EXPERIENCE")
        self.assertEqual(strategy_runner.POST_TYPE_BY_STRATEGY["question"], "ENGAGEMENT_QUESTION")
        self.assertEqual(strategy_runner.POST_TYPE_BY_STRATEGY["opinion_observation"], "OPINION")
        self.assertEqual(strategy_runner.POST_TYPE_BY_STRATEGY["news_explainer"], "EXPLANATION")
        self.assertEqual(strategy_runner.POST_TYPE_BY_STRATEGY["gaming"], "ENGAGEMENT_QUESTION")

    def test_engagement_patterns_are_distinct_for_question_slots(self):
        self.assertNotEqual(
            strategy_runner._engagement_pattern("question", "What are you actually building with AI right now?"),
            strategy_runner._engagement_pattern("question", "What AI tool genuinely earns a place in your daily workflow?"),
        )

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

    def test_topic_and_editorial_brief_are_separate(self):
        recipe = strategy_runner.STRATEGY_POSTS[1]
        article = {"title": "Source story", "description": "Source facts."}
        relatable = ("passwords", "People reuse passwords even when they work in tech")
        topic = strategy_runner._topic_from_slot(recipe, article)
        brief = strategy_runner._editorial_brief_from_slot(recipe, relatable)
        self.assertEqual(topic, "Source story. Source facts.")
        self.assertNotIn("Format:", topic)
        self.assertNotIn("Hook direction:", topic)
        self.assertNotIn("Relatable context:", topic)
        self.assertIn("Format:", brief)
        self.assertIn("Hook direction:", brief)
        self.assertIn("Relatable context:", brief)
        self.assertIn("Creator-safety rule", brief)
        self.assertIn("never invent hardware", brief)

    def test_editorial_brief_requires_compact_punchy_threads_copy(self):
        recipe = strategy_runner.STRATEGY_POSTS[2]
        brief = strategy_runner._editorial_brief_from_slot(recipe, None)
        self.assertIn("fast-scrolling feed", brief)
        self.assertIn("3-7 short lines", brief)
        self.assertIn("remove setup, repetition, filler, and essay-style context", brief)
        self.assertIn("End with the strongest line in the post", brief)
        self.assertIn("should hit harder than the opening", brief)
        self.assertIn("Do not use a generic call to action", brief)

    def test_builder_brief_requires_source_supported_first_person(self):
        recipe = next(item for item in strategy_runner.STRATEGY_POSTS if item[0] == "builder_experience")
        brief = strategy_runner._editorial_brief_from_slot(recipe, None)
        self.assertIn("Use first person only when the supplied material or configured creator context supports it", brief)
        self.assertIn("never invent hardware, spending, actions, or results", brief)

    def test_editorial_brief_is_not_sent_to_fact_prompt(self):
        topic = "Source story. Source facts."
        brief = "Format: question. Editorial instruction: ask for experience. Relatable context: passwords."
        fact_prompt = content_engine.build_fact_prompt(topic, [{"title": "Source story", "description": "Source facts.", "url": "https://example.com"}])
        angle_prompt = content_engine.build_angle_prompt(topic, {"claims": []}, [{"title": "Source story"}], editorial_brief=brief)
        self.assertIn("Source story. Source facts.", fact_prompt)
        self.assertNotIn("Relatable context: passwords", fact_prompt)
        self.assertIn("Relatable context: passwords", angle_prompt)
        self.assertIn("NOT factual evidence", angle_prompt)

    def test_record_performance_normalizes_metrics(self):
        state = {}
        row = strategy_runner.record_performance(state, {
            "post_id": "p1", "date": "2026-09-11", "topic": "AI", "angle": "economic",
            "idea_score": 90, "quality_score": 85, "final_score": 88, "views": 1000,
            "likes": 50, "replies": 20, "reposts": 10, "quotes": 5, "follows": 10,
        })
        self.assertEqual(row["normalized"]["reply_rate"], 0.02)
        self.assertEqual(len(state["performance_history"]), 1)

    def test_run_pipeline_retries_semantic_fact_validation_failure(self):
        first_error = content_engine.PipelineError("Unknown factual status: ''")
        expected = {"decision": "PUBLISH"}
        with patch.object(strategy_runner, "evaluate_topic", side_effect=[first_error, expected]) as evaluator:
            result = strategy_runner._run_pipeline("Topic", {"title": "Story"}, "Format: opinion.")
        self.assertEqual(result, expected)
        self.assertEqual(evaluator.call_count, 2)
        retry_brief = evaluator.call_args_list[1].kwargs["editorial_brief"]
        self.assertIn("VALIDATION RETRY", retry_brief)
        self.assertIn("Never leave status blank", retry_brief)
        self.assertIsNone(evaluator.call_args_list[0].kwargs["post_type"])

    def test_run_pipeline_retries_empty_provider_output(self):
        first_error = RuntimeError("OpenRouter returned empty content")
        expected = {"decision": "PUBLISH"}
        with patch.object(strategy_runner, "evaluate_topic", side_effect=[first_error, expected]) as evaluator:
            result = strategy_runner._run_pipeline("Topic", {"title": "Story"}, "Format: opinion.")
        self.assertEqual(result, expected)
        self.assertEqual(evaluator.call_count, 2)
        retry_brief = evaluator.call_args_list[1].kwargs["editorial_brief"]
        self.assertIn("PROVIDER OUTPUT RETRY", retry_brief)
        self.assertIn("no usable text", retry_brief)

    def test_run_pipeline_uses_plain_openrouter_on_empty_provider_retry(self):
        expected = {"decision": "PUBLISH"}
        captured = []

        def fake_evaluate(topic, sources, chat, editorial_brief="", post_type=None):
            captured.append(chat)
            if len(captured) == 1:
                raise RuntimeError("OpenRouter returned empty content")
            return expected

        with patch.object(strategy_runner, "evaluate_topic", side_effect=fake_evaluate):
            result = strategy_runner._run_pipeline("Topic", {"title": "Story"})
        self.assertEqual(result, expected)
        self.assertIs(captured[0]._provider, strategy_runner.bot.openrouter_chat_json)
        self.assertIs(captured[1]._provider, strategy_runner._retry_openrouter_chat)

    def test_retryable_provider_error_includes_no_choices(self):
        error = RuntimeError("OpenRouter returned no choices: unknown error")
        self.assertTrue(strategy_runner._is_retryable_provider_error(error))

    def test_angle_retry_brief_demands_material_diversity(self):
        error = content_engine.PipelineError("Angles are repetitive; need at least 8 materially distinct angles")
        brief = strategy_runner._retry_brief("Format: news_opinion.", error)
        self.assertIn("ANGLE DIVERSITY RETRY", brief)
        self.assertIn("at least 10 angles", brief)
        self.assertIn("at least 8 different allowed angle types", brief)
        self.assertIn("materially different core_claims", brief)

    def test_run_pipeline_does_not_mask_original_validation_failure_when_retry_hits_provider_error(self):
        first_error = content_engine.PipelineError("Angles are repetitive; need at least 8 materially distinct angles")
        provider_error = RuntimeError("OpenRouter HTTP 429: rate limit")
        with patch.object(strategy_runner, "evaluate_topic", side_effect=[first_error, provider_error]) as evaluator:
            with self.assertRaises(content_engine.PipelineError) as raised:
                strategy_runner._run_pipeline("Topic", {"title": "Story"}, "Format: opinion.")
        self.assertIn("Angles are repetitive", str(raised.exception))
        self.assertIn("retry failed", str(raised.exception))
        self.assertIn("rate limit", str(raised.exception))
        self.assertEqual(evaluator.call_count, 2)

    def test_recoverable_idea_reject_retries_once_and_can_publish(self):
        rejected = {
            "decision": "REJECT",
            "post_type": "EXPERIENCE",
            "fact_confidence": 1.0,
            "fact_gate": "Fact claims passed the minimum evidence gate.",
            "angles": [{"core_claim": "Best idea", "idea_score": 76.5, "idea_decision": "REWORK"}],
        }
        published = {"decision": "PUBLISH"}
        with patch.object(strategy_runner, "evaluate_topic", side_effect=[rejected, published]) as evaluator:
            result = strategy_runner._run_pipeline("Topic", {"title": "Story"}, "Format: builder_experience.", post_type="EXPERIENCE")
        self.assertEqual(result, published)
        self.assertEqual(evaluator.call_count, 2)
        retry_brief = evaluator.call_args_list[1].kwargs["editorial_brief"]
        self.assertIn("IDEA GATE RETRY", retry_brief)
        self.assertIn("weighted idea score >= 80", retry_brief)
        self.assertEqual(evaluator.call_args_list[0].kwargs["post_type"], "EXPERIENCE")
        self.assertNotIn("fact_result_override", evaluator.call_args_list[0].kwargs)
        self.assertNotIn("fact_result_override", evaluator.call_args_list[1].kwargs)

    def test_decision_retry_reuses_original_fact_result(self):
        rejected = {
            "decision": "REJECT",
            "post_type": "EXPERIENCE",
            "fact_status": {
                "claims": [{
                    "claim": "Source claim",
                    "status": "VERIFIED",
                    "evidence": "Source evidence",
                    "confidence": 9,
                    "central": True,
                }]
            },
            "fact_confidence": 0.9,
            "fact_gate": "Fact claims passed the minimum evidence gate.",
            "angles": [{"core_claim": "Best idea", "idea_score": 76.5, "idea_decision": "REWORK"}],
        }
        published = {"decision": "PUBLISH"}
        with patch.object(strategy_runner, "evaluate_topic", side_effect=[rejected, published]) as evaluator:
            result = strategy_runner._run_pipeline(
                "Topic", {"title": "Story"}, "Format: builder_experience.", post_type="EXPERIENCE"
            )
        self.assertEqual(result, published)
        self.assertEqual(
            evaluator.call_args_list[1].kwargs["fact_result_override"],
            rejected["fact_status"],
        )

    def test_repeated_idea_reject_preserves_exploitable_reason(self):
        rejected = {
            "decision": "REJECT",
            "fact_confidence": 1.0,
            "fact_gate": "Fact claims passed the minimum evidence gate.",
            "angles": [
                {"core_claim": "Best idea", "idea_score": 76.5, "idea_decision": "REWORK"},
                {"core_claim": "Other idea", "idea_score": 61.0, "idea_decision": "REJECT"},
            ],
        }
        with patch.object(strategy_runner, "evaluate_topic", side_effect=[rejected, rejected]) as evaluator:
            result = strategy_runner._run_pipeline("Topic", {"title": "Story"}, "Format: builder_experience.")
        self.assertEqual(evaluator.call_count, 2)
        self.assertEqual(result["decision"], "REJECT")
        self.assertEqual(result["stage"], "idea_selection")
        self.assertTrue(result["recoverable"])
        self.assertIn("best_idea_score=76.5/100", result["rejection_reason"])
        self.assertIn("scroll_stop, originality, and debate_potential", result["rejection_reason"])

    def test_provider_wrapper_logs_without_prompt_or_response_content(self):
        secret = "super-secret-api-key"
        output = io.StringIO()
        provider = lambda prompt: '{"ok": true}'
        wrapped = strategy_runner._instrument_provider(provider, attempt=1)
        with redirect_stdout(output):
            result = wrapped(f"Fact-check source using {secret}")
        logs = output.getvalue()
        self.assertEqual(result, '{"ok": true}')
        self.assertIn("provider_request", logs)
        self.assertIn("provider_response", logs)
        self.assertNotIn(secret, logs)
        self.assertNotIn('{"ok": true}', logs)

    def test_generate_strategy_threads_reject_error_includes_reason_and_stage(self):
        rejected = {
            "decision": "REJECT",
            "fact_confidence": 1.0,
            "fact_gate": "Fact claims passed the minimum evidence gate.",
            "angles": [{"core_claim": "Best idea", "idea_score": 76.5, "idea_decision": "REWORK"}],
        }
        with patch.object(strategy_runner, "_run_pipeline", return_value=rejected):
            with patch.object(strategy_runner, "PIPELINE_REPORT_PATH", "/tmp/thread-bot-evaluation.txt"):
                with self.assertRaisesRegex(RuntimeError, r"Content pipeline decision: REJECT stage=idea_selection reason=.*best_idea_score=76\.5/100"):
                    strategy_runner.generate_strategy_threads(
                        [{"category": "technology", "title": "AI story", "description": "AI tool for developers."}],
                        {"strategy_cursor": 2},
                    )

    def test_generate_strategy_threads_runs_typed_pipeline_and_tracks_state(self):
        articles = [{
            "category": "gaming",
            "title": "A current gaming story",
            "description": "A useful summary.",
            "published": "2026-09-11T10:00:00Z",
            "url": "https://example.com/story",
        }]
        state = {
            "strategy_cursor": 16,
            "recent_post_titles": [],
            "recent_relatable_topic_tags": [],
            "recent_post_types": [],
            "recent_engagement_patterns": [],
        }
        idea_weights = content_engine.POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["idea_weights"]
        quality_weights = content_engine.POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["quality_weights"]
        angles = []
        for index, angle_type in enumerate(content_engine.ANGLE_TYPES[:8]):
            angles.append({
                "angle": angle_type,
                "core_claim": f"Distinct question idea {index}",
                "why_it_matters": "Specific consequence",
                "target_reaction": "A reader shares a concrete experience",
                "supporting_facts": [],
                "potential_counterargument": "Some readers may disagree",
                "scores": {key: 9 for key in idea_weights},
            })
        responses = [
            json.dumps({"claims": [{"claim": "The story happened", "status": "VERIFIED", "evidence": "A useful summary.", "confidence": 9, "central": True}]}),
            json.dumps({"angles": angles}),
            json.dumps({
                "draft": "What game would you want an AI-powered NPC to actually remember you in?",
                "quality": {key: 9 for key in quality_weights},
                "stress": {
                    "scroll_answer": "It invites a specific scenario.",
                    "reply_example": "A reader can name a game.",
                    "counterargument": "",
                    "generic": False,
                    "quotable_line": "",
                    "type_checks": {key: True for key in content_engine.POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["stress_checks"]},
                },
                "claims": [],
            }),
        ]
        with patch.object(strategy_runner.bot, "openrouter_chat", side_effect=responses):
            with patch.object(strategy_runner, "PIPELINE_REPORT_PATH", "/tmp/thread-bot-evaluation.txt"):
                content, posts = strategy_runner.generate_strategy_threads(articles, state)
        self.assertIn("AI-powered NPC", content)
        self.assertEqual(posts[0]["decision"], "PUBLISH")
        self.assertEqual(posts[0]["post_type"], "ENGAGEMENT_QUESTION")
        self.assertEqual(posts[0]["engagement_pattern"], "PROJECT_SHARE")
        self.assertGreaterEqual(posts[0]["idea_score"], 90)
        self.assertEqual(state["strategy_cursor"], 17)
        self.assertEqual(state["recent_post_types"][-1], "ENGAGEMENT_QUESTION")
        self.assertEqual(state["recent_engagement_patterns"][-1], "PROJECT_SHARE")
        self.assertEqual(state["strategy_mix"], strategy_runner.STRATEGY_MIX)

    def test_provider_stage_recognizes_every_pipeline_prompt(self):
        sources = [{"title": "Story", "description": "Facts", "url": "https://example.com/a"}]
        angle = {"angle": "contrarian", "core_claim": "claim"}
        self.assertEqual(strategy_runner._provider_stage(content_engine.build_fact_prompt("t", sources)), "fact_check")
        self.assertEqual(strategy_runner._provider_stage(content_engine.build_angle_prompt("t", {"claims": []}, sources, "", "OPINION")), "angles")
        self.assertEqual(strategy_runner._provider_stage(content_engine.build_draft_prompt(angle, {"claims": []}, sources, "", "OPINION")), "draft")

    def test_diagnose_confident_contradiction_is_unrecoverable_fact_check_reject(self):
        diagnosed = strategy_runner._diagnose_result({
            "decision": "REJECT", "fact_confidence": 0.9, "angles": [],
            "fact_gate": "Central or material claim is contradicted by the supplied evidence.",
        })
        self.assertEqual(diagnosed["stage"], "fact_check")
        self.assertFalse(diagnosed["recoverable"])

    def test_retry_brief_for_stress_failure_does_not_blame_json_contract(self):
        brief = strategy_runner._retry_brief("BRIEF", "Stress test failed: scroll, replyability.", "ENGAGEMENT_QUESTION")
        self.assertIn("STRESS TEST RETRY", brief)
        self.assertIn("scroll, replyability", brief)
        self.assertNotIn("JSON/data contract", brief)

    def _published(self):
        return {
            "decision": "PUBLISH", "top_pick": {"core_claim": "claim", "idea_score": 90.0}, "draft": "body",
            "quality_score": 90.0, "final_score": 90.0, "fact_confidence": 0.9,
        }

    def _articles(self):
        return [
            {"category": "technology", "title": "University exam result announced today", "description": "Scorecards", "url": "https://example.com/0"},
            {"category": "technology", "title": "Open source AI coding tool adds local model support", "description": "Developers run an AI model", "url": "https://example.com/1"},
            {"category": "gaming", "title": "Studio confirms a new game release date", "description": "Gaming news", "url": "https://example.com/2"},
        ]

    def test_strategy_post_source_marker_points_to_selected_article(self):
        import bot
        articles = self._articles()
        state = {"strategy_cursor": 0, "recent_relatable_topic_tags": []}
        with patch.object(strategy_runner, "_run_pipeline", return_value=self._published()), \
             patch.object(strategy_runner, "_write_pipeline_report"), redirect_stdout(io.StringIO()):
            _, posts = strategy_runner.generate_strategy_threads(articles, state)
        self.assertEqual(posts[0]["source"], "NEWS 2")
        self.assertEqual(bot.used_articles_from_posts(posts, articles)[0]["url"], "https://example.com/1")

    def test_strategy_records_relatable_topic_tag_for_rotation(self):
        state = {"strategy_cursor": 8, "recent_relatable_topic_tags": []}
        expected = strategy_runner._fresh_topic(state)[0]
        with patch.object(strategy_runner, "_run_pipeline", return_value=self._published()), \
             patch.object(strategy_runner, "_write_pipeline_report"), redirect_stdout(io.StringIO()):
            strategy_runner.generate_strategy_threads(self._articles(), state)
        self.assertEqual(state["recent_relatable_topic_tags"], [expected])
        self.assertNotEqual(strategy_runner._fresh_topic(state)[0], expected)

    def test_fresh_topic_reuses_least_recent_topic_when_all_were_used(self):
        topics = strategy_runner.bot.RELATABLE_TOPICS
        state = {"recent_relatable_topic_tags": [item[0] for item in topics]}
        self.assertEqual(strategy_runner._fresh_topic(state), topics[0])
        state = {"recent_relatable_topic_tags": [item[0] for item in reversed(topics)]}
        self.assertEqual(strategy_runner._fresh_topic(state), topics[-1])

    def test_pipeline_report_creates_missing_state_directory(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "missing", "report.txt")
            with patch.object(strategy_runner, "PIPELINE_REPORT_PATH", path):
                strategy_runner._write_pipeline_report({"decision": "REJECT", "topic": "t"})
            self.assertTrue(os.path.exists(path))

    def test_pipeline_report_labels_successful_run_with_final_decision_stage(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "report.txt")
            with patch.object(strategy_runner, "PIPELINE_REPORT_PATH", path):
                strategy_runner._write_pipeline_report({"decision": "PUBLISH", "topic": "t"})
            with open(path, encoding="utf-8") as handle:
                self.assertIn("STAGE: final_decision", handle.read())


if __name__ == "__main__":
    unittest.main()
