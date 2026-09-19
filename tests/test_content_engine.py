import math
import json
import unittest
from unittest.mock import Mock

from content_engine import (
    ANGLE_TYPES,
    IDEA_WEIGHTS,
    POST_TYPE_CONTRACTS,
    POST_TYPES,
    QUALITY_WEIGHTS,
    build_angle_prompt,
    build_draft_prompt,
    extract_json,
    factuality_gate,
    final_decision,
    final_score,
    idea_decision,
    idea_score,
    idea_score_for_type,
    normalized_metrics,
    performance_row,
    quality_score_for_type,
    run_llm_json,
    stress_test,
    validate_angle_result,
    validate_draft_result,
    validate_stress_payload,
    weighted_score,
    evaluate_topic,
)


class ContentEngineTests(unittest.TestCase):
    def test_weights_match_product_spec(self):
        self.assertEqual(sum(IDEA_WEIGHTS.values()), 100)
        self.assertEqual(sum(QUALITY_WEIGHTS.values()), 100)
        self.assertEqual(IDEA_WEIGHTS["scroll_stop"], 20)
        self.assertEqual(QUALITY_WEIGHTS["factual_accuracy"], 20)

    def test_all_post_type_contracts_are_complete_and_weighted(self):
        self.assertEqual(set(POST_TYPE_CONTRACTS), set(POST_TYPES))
        for post_type, contract in POST_TYPE_CONTRACTS.items():
            self.assertEqual(sum(contract["idea_weights"].values()), 100, post_type)
            self.assertEqual(sum(contract["quality_weights"].values()), 100, post_type)
            self.assertTrue(set(contract["hard_idea_dimensions"]) <= set(contract["idea_weights"]))
            self.assertTrue(contract["stress_checks"])

    def test_weighted_score_scales_to_100(self):
        values = {key: 10 for key in IDEA_WEIGHTS}
        self.assertEqual(weighted_score(values, IDEA_WEIGHTS), 100.0)
        values["originality"] = 0
        self.assertEqual(weighted_score(values, IDEA_WEIGHTS), 85.0)

    def test_type_specific_scoring_uses_different_rubrics(self):
        opinion = {key: 10 for key in POST_TYPE_CONTRACTS["OPINION"]["idea_weights"]}
        question = {key: 10 for key in POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["idea_weights"]}
        opinion["argument_strength"] = 0
        question["replyability"] = 0
        self.assertNotEqual(
            idea_score_for_type("OPINION", opinion),
            idea_score_for_type("ENGAGEMENT_QUESTION", question),
        )

    def test_unknown_post_type_is_rejected(self):
        with self.assertRaises(ValueError):
            idea_score_for_type("BLOG_POST", {})
        with self.assertRaises(ValueError):
            quality_score_for_type("BLOG_POST", {})

    def test_idea_decision_enforces_hard_dimensions(self):
        values = {key: 10 for key in IDEA_WEIGHTS}
        values["originality"] = 6
        self.assertEqual(idea_decision(95, values, 1.0), "REWORK")
        self.assertEqual(idea_decision(65, values, 1.0), "REJECT")

    def test_score_boundaries_reject_non_finite_values(self):
        values = {key: 10 for key in IDEA_WEIGHTS}
        with self.assertRaises(ValueError):
            idea_decision(math.nan, values, 1.0)
        with self.assertRaises(ValueError):
            final_score(math.inf, 90, 0.9, True)
        with self.assertRaises(ValueError):
            final_decision(90, -1, 0.9, {"all_pass": True})

    def test_factuality_gate_rejects_contradicted_claim(self):
        ok, confidence, reason = factuality_gate([{
            "claim": "Source says X",
            "status": "CONTRADICTED",
            "confidence": 10,
            "evidence": "Source disagrees",
            "central": True,
        }])
        self.assertFalse(ok)
        self.assertLessEqual(confidence, 1)
        self.assertIn("contradicted", reason.lower())

    def test_factuality_gate_rejects_unverified_central_claim(self):
        ok, _, _ = factuality_gate([{
            "claim": "Unknown claim",
            "status": "UNVERIFIED",
            "confidence": 5,
            "evidence": "No supporting source",
            "central": True,
        }])
        self.assertFalse(ok)

    def test_factuality_gate_rejects_factual_claim_without_evidence(self):
        ok, _, reason = factuality_gate([{
            "claim": "Claim",
            "status": "VERIFIED",
            "confidence": 9,
            "central": True,
        }])
        self.assertFalse(ok)
        self.assertIn("evidence", reason.lower())

    def test_factuality_confidence_ignores_opinion_and_prediction_confidence(self):
        claims = [
            {"claim": "Verified claim", "status": "VERIFIED", "confidence": 9, "evidence": "Source", "central": True},
            {"claim": "My view", "status": "OPINION", "confidence": 0, "evidence": "", "central": False},
            {"claim": "My forecast", "status": "PREDICTION", "confidence": 0, "evidence": "", "central": False},
        ]
        ok, confidence, _ = factuality_gate(claims)
        self.assertTrue(ok)
        self.assertEqual(confidence, 0.9)

    def test_claim_free_content_has_safe_fact_confidence(self):
        ok, confidence, reason = factuality_gate([])
        self.assertTrue(ok)
        self.assertEqual(confidence, 1.0)
        self.assertIn("No factual claims", reason)

    def test_final_score_is_gated_by_facts_and_stress(self):
        self.assertEqual(final_score(95, 90, 0.69, True), 0.0)
        self.assertEqual(final_score(95, 90, 0.9, False), 0.0)
        self.assertEqual(final_score(90, 80, 0.9, True), 85.5)

    def test_final_decision_has_publish_rewrite_reject(self):
        passing = {"all_pass": True}
        self.assertEqual(final_decision(90, 85, 0.9, passing), "PUBLISH")
        self.assertEqual(final_decision(82, 85, 0.9, passing), "REWRITE")
        self.assertEqual(final_decision(90, 85, 0.6, passing), "REJECT")
        self.assertEqual(final_decision(90, 85, 0.9, {"all_pass": False}), "REWRITE")

    def test_stress_test_requires_a_nonempty_draft(self):
        result = stress_test(
            "",
            scroll_answer="A concrete reason",
            reply_example="A plausible reply",
            counterargument="A reasonable counterargument",
            generic=False,
            quotable_line="A quote",
            claims=[{"claim": "x", "status": "VERIFIED", "evidence": "Source text", "confidence": 9}],
        )
        self.assertFalse(result["draft_present"])
        self.assertFalse(result["all_pass"])

    def test_stress_test_catches_generic_posts_and_missing_claim_evidence(self):
        result = stress_test(
            "draft",
            scroll_answer="A concrete reason",
            reply_example="A plausible reply",
            counterargument="A reasonable counterargument",
            generic=True,
            quotable_line="A quote",
            claims=[{"claim": "x", "status": "VERIFIED", "evidence": "Source text", "confidence": 9}],
        )
        self.assertFalse(result["genericity"])
        self.assertFalse(result["all_pass"])

    def test_claim_free_engagement_question_can_pass_without_counterargument(self):
        checks = {key: True for key in POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["stress_checks"]}
        result = stress_test(
            "What tool changed your workflow most?",
            scroll_answer="The question is easy to answer from lived experience.",
            reply_example="I would answer with one concrete tool.",
            counterargument="",
            generic=False,
            quotable_line="",
            claims=[],
            post_type="ENGAGEMENT_QUESTION",
            type_checks=checks,
        )
        self.assertTrue(result["claim_integrity"])
        self.assertTrue(result["all_pass"])

    def test_generic_yes_no_question_fails_type_stress(self):
        checks = {key: True for key in POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["stress_checks"]}
        checks["specificity"] = False
        result = stress_test(
            "Do you like AI?",
            scroll_answer="It invites a quick answer.",
            reply_example="Yes.",
            counterargument="",
            generic=False,
            quotable_line="",
            claims=[],
            post_type="ENGAGEMENT_QUESTION",
            type_checks=checks,
        )
        self.assertFalse(result["type_checks"]["specificity"])
        self.assertFalse(result["all_pass"])

    def test_stress_test_allows_labeled_opinion_and_prediction_without_evidence(self):
        for status in ("OPINION", "PREDICTION"):
            with self.subTest(status=status):
                result = stress_test(
                    "draft",
                    scroll_answer="A concrete reason",
                    reply_example="A plausible reply",
                    counterargument="",
                    generic=False,
                    quotable_line="",
                    claims=[{"claim": "x", "status": status, "evidence": "", "confidence": 0}],
                    post_type="ENGAGEMENT_QUESTION",
                    type_checks={key: True for key in POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["stress_checks"]},
                )
                self.assertTrue(result["claim_integrity"])

    def test_stress_test_rejects_unsupported_claim_status(self):
        result = stress_test(
            "draft",
            scroll_answer="A concrete reason",
            reply_example="A plausible reply",
            counterargument="A reasonable counterargument",
            generic=False,
            quotable_line="A quote",
            claims=[{"claim": "x", "status": "CONTRADICTED", "evidence": "Source text", "confidence": 9}],
        )
        self.assertFalse(result["claim_integrity"])
        self.assertFalse(result["all_pass"])

    def test_extract_json_accepts_surrounding_prose(self):
        payload = extract_json("Here is the requested JSON:\n{\"claims\": []}\nDone.")
        self.assertEqual(payload, {"claims": []})

    def test_run_llm_json_retries_and_requires_object_payload(self):
        responder = Mock(side_effect=["[1, 2, 3]", "Here: {\"claims\": []}"])
        payload = run_llm_json(responder, "fact check")
        self.assertEqual(payload, {"claims": []})
        self.assertEqual(responder.call_count, 2)

    def test_run_llm_json_rejects_repeated_non_object_payloads(self):
        responder = Mock(side_effect=["[]", "null"])
        with self.assertRaises(ValueError):
            run_llm_json(responder, "fact check")
        self.assertEqual(responder.call_count, 2)

    def test_validate_angles_rejects_unknown_angle_type(self):
        angle = {
            "angle": "made_up_type",
            "core_claim": "Distinct",
            "why_it_matters": "Reason",
            "target_reaction": "Reaction",
            "supporting_facts": ["Fact"],
            "potential_counterargument": "Counter",
            "scores": {key: 8 for key in IDEA_WEIGHTS},
        }
        angles = [dict(angle, core_claim=f"Distinct {index}") for index in range(8)]
        with self.assertRaisesRegex(ValueError, "Unknown angle type"):
            validate_angle_result({"angles": angles})

    def test_validate_draft_requires_claims_and_typed_stress(self):
        checks = {key: True for key in POST_TYPE_CONTRACTS["OPINION"]["stress_checks"]}
        valid = {
            "draft": "A specific opinion.",
            "quality": {key: 8 for key in POST_TYPE_CONTRACTS["OPINION"]["quality_weights"]},
            "stress": {
                "scroll_answer": "The position is clear.",
                "reply_example": "A reader could disagree.",
                "counterargument": "A fair counterargument exists.",
                "generic": False,
                "quotable_line": "The point is specific.",
                "type_checks": checks,
            },
            "claims": [{
                "claim": "A fact",
                "status": "VERIFIED",
                "evidence": "Source",
                "confidence": 9,
                "central": True,
            }],
        }
        result = validate_draft_result(valid, "OPINION")
        self.assertEqual(result["draft"], "A specific opinion.")
        with self.assertRaises(ValueError):
            validate_draft_result({key: value for key, value in valid.items() if key != "claims"}, "OPINION")

    def test_validate_stress_rejects_non_boolean_type_check(self):
        checks = {key: True for key in POST_TYPE_CONTRACTS["OPINION"]["stress_checks"]}
        checks["position_clarity"] = "yes"
        stress = {
            "scroll_answer": "x",
            "reply_example": "x",
            "counterargument": "x",
            "generic": False,
            "quotable_line": "x",
            "type_checks": checks,
        }
        with self.assertRaises(ValueError):
            validate_stress_payload(stress, "OPINION")

    def test_typed_prompt_contains_fixed_type_and_dimensions(self):
        prompt = build_angle_prompt("Topic", {"claims": []}, [], post_type="OPINION")
        self.assertIn("POST TYPE IS FIXED BY THE ORCHESTRATOR: OPINION", prompt)
        self.assertIn("argument_strength", prompt)
        self.assertNotIn("scroll_stop", prompt)

        draft_prompt = build_draft_prompt({}, {"claims": []}, [], post_type="ENGAGEMENT_QUESTION")
        self.assertIn("Post type: ENGAGEMENT_QUESTION", draft_prompt)
        self.assertIn("replyability", draft_prompt)
        self.assertIn("type_checks", draft_prompt)

    def test_typed_claim_free_question_pipeline_can_publish(self):
        angle_scores = {key: 9 for key in POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["idea_weights"]}
        quality_scores = {key: 9 for key in POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["quality_weights"]}
        checks = {key: True for key in POST_TYPE_CONTRACTS["ENGAGEMENT_QUESTION"]["stress_checks"]}
        angles = [{
            "angle": ANGLE_TYPES[index],
            "core_claim": f"Question idea {index}",
            "why_it_matters": "It creates a concrete conversation.",
            "target_reaction": "A reader shares a specific experience.",
            "supporting_facts": [],
            "potential_counterargument": "Some readers may differ.",
            "scores": angle_scores,
        } for index in range(8)]
        responses = [
            json.dumps({"claims": []}),
            json.dumps({"angles": angles}),
            json.dumps({
                "draft": "What AI tool actually changed the way you work?",
                "quality": quality_scores,
                "stress": {
                    "scroll_answer": "It asks for a concrete experience.",
                    "reply_example": "A reader can name one tool.",
                    "counterargument": "",
                    "generic": False,
                    "quotable_line": "",
                    "type_checks": checks,
                },
                "claims": [],
            }),
        ]
        result = evaluate_topic(
            "A source topic",
            [{"title": "Source", "description": "Context", "url": "https://example.com"}],
            Mock(side_effect=responses),
            post_type="ENGAGEMENT_QUESTION",
        )
        self.assertEqual(result["post_type"], "ENGAGEMENT_QUESTION")
        self.assertEqual(result["fact_confidence"], 1.0)
        self.assertEqual(result["decision"], "PUBLISH")

    def test_performance_metrics_are_normalized(self):
        row = performance_row({
            "post_id": "p1", "date": "2026-09-11", "topic": "AI", "angle": "economic",
            "idea_score": 88, "quality_score": 84, "final_score": 86,
            "views": 1000, "likes": 100, "replies": 20, "reposts": 30, "quotes": 10, "follows": 15,
        })
        metrics = normalized_metrics(row)
        self.assertEqual(metrics["like_rate"], 0.1)
        self.assertEqual(metrics["reply_rate"], 0.02)
        self.assertEqual(metrics["repost_rate"], 0.03)
        self.assertEqual(metrics["follow_conversion"], 0.015)
        self.assertEqual(metrics["engagement_rate"], 0.16)

    def test_performance_row_rejects_fractional_and_boolean_metrics(self):
        base = {"post_id": "p1", "date": "2026-09-11", "topic": "AI", "angle": "economic", "idea_score": 88, "quality_score": 84, "final_score": 86}
        with self.assertRaises(ValueError):
            performance_row({**base, "views": 1.5})
        with self.assertRaises(ValueError):
            performance_row({**base, "likes": True})

    def test_follow_conversion_is_zero_without_views(self):
        row = performance_row({
            "post_id": "p1", "date": "2026-09-11", "topic": "AI", "angle": "economic",
            "idea_score": 88, "quality_score": 84, "final_score": 86, "impressions": 100, "follows": 10,
        })
        self.assertEqual(normalized_metrics(row)["follow_conversion"], 0.0)


if __name__ == "__main__":
    unittest.main()
