import math
import unittest
from unittest.mock import Mock

from content_engine import (
    ANGLE_TYPES,
    IDEA_WEIGHTS,
    QUALITY_WEIGHTS,
    extract_json,
    factuality_gate,
    final_decision,
    final_score,
    idea_decision,
    idea_score,
    normalized_metrics,
    performance_row,
    run_llm_json,
    stress_test,
    validate_angles,
    weighted_score,
)


class ContentEngineTests(unittest.TestCase):
    def test_weights_match_product_spec(self):
        self.assertEqual(sum(IDEA_WEIGHTS.values()), 100)
        self.assertEqual(sum(QUALITY_WEIGHTS.values()), 100)
        self.assertEqual(IDEA_WEIGHTS["scroll_stop"], 20)
        self.assertEqual(QUALITY_WEIGHTS["factual_accuracy"], 20)

    def test_weighted_score_scales_to_100(self):
        values = {key: 10 for key in IDEA_WEIGHTS}
        self.assertEqual(weighted_score(values, IDEA_WEIGHTS), 100.0)
        values["originality"] = 0
        self.assertEqual(weighted_score(values, IDEA_WEIGHTS), 85.0)

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
            "status": "UNVERIFIED",
            "confidence": 5,
            "evidence": "No supporting source",
            "central": True,
        }])
        self.assertFalse(ok)

    def test_factuality_gate_rejects_factual_claim_without_evidence(self):
        ok, _, reason = factuality_gate([{
            "status": "VERIFIED",
            "confidence": 9,
            "central": True,
        }])
        self.assertFalse(ok)
        self.assertIn("evidence", reason.lower())

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
            claims=[{"status": "VERIFIED", "evidence": "Source text", "confidence": 9}],
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
            claims=[{"status": "VERIFIED", "evidence": "Source text", "confidence": 9}],
        )
        self.assertFalse(result["genericity"])
        self.assertFalse(result["all_pass"])

    def test_stress_test_accepts_opinion_without_evidence(self):
        result = stress_test(
            "draft",
            scroll_answer="A concrete reason",
            reply_example="A plausible reply",
            counterargument="A reasonable counterargument",
            generic=False,
            quotable_line="A quote",
            claims=[{"status": "OPINION", "confidence": 9}],
        )
        self.assertTrue(result["claim_integrity"])
        self.assertTrue(result["all_pass"])

    def test_stress_test_rejects_missing_evidence_for_factual_claim(self):
        result = stress_test(
            "draft",
            scroll_answer="A concrete reason",
            reply_example="A plausible reply",
            counterargument="A reasonable counterargument",
            generic=False,
            quotable_line="A quote",
            claims=[{"status": "VERIFIED", "confidence": 9}],
        )
        self.assertFalse(result["claim_integrity"])
        self.assertFalse(result["all_pass"])

    def test_stress_test_rejects_contradicted_claim(self):
        result = stress_test(
            "draft",
            scroll_answer="A concrete reason",
            reply_example="A plausible reply",
            counterargument="A reasonable counterargument",
            generic=False,
            quotable_line="A quote",
            claims=[{"status": "CONTRADICTED", "evidence": "Source disagrees", "confidence": 9}],
        )
        self.assertFalse(result["claim_integrity"])
        self.assertFalse(result["all_pass"])

    def test_validate_angles_requires_allowed_distinct_types(self):
        valid = []
        for index, angle_type in enumerate(ANGLE_TYPES[:8]):
            valid.append({
                "angle": angle_type,
                "core_claim": f"claim {index}",
                "why_it_matters": "matter",
                "target_reaction": "reaction",
                "supporting_facts": ["fact"],
                "potential_counterargument": "counter",
            })
        self.assertEqual(len(validate_angles(valid)), 8)
        repeated_types = [
            dict(valid[index], angle="contrarian", core_claim=f"other claim {index}")
            for index in range(8)
        ]
        with self.assertRaises(ValueError) as raised:
            validate_angles(repeated_types)
        self.assertEqual(getattr(raised.exception, "stage", None), "angles")
        self.assertEqual(getattr(raised.exception, "code", None), "INSUFFICIENT_DIVERSITY")

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

    def test_performance_metrics_are_normalized(self):
        row = performance_row({
            "post_id": "p1",
            "date": "2026-09-11",
            "topic": "AI",
            "angle": "economic",
            "idea_score": 88,
            "quality_score": 84,
            "final_score": 86,
            "views": 1000,
            "likes": 100,
            "replies": 20,
            "reposts": 30,
            "quotes": 10,
            "follows": 15,
        })
        metrics = normalized_metrics(row)
        self.assertEqual(metrics["like_rate"], 0.1)
        self.assertEqual(metrics["reply_rate"], 0.02)
        self.assertEqual(metrics["repost_rate"], 0.03)
        self.assertEqual(metrics["follow_conversion"], 0.015)
        self.assertEqual(metrics["engagement_rate"], 0.16)

    def test_performance_row_rejects_fractional_and_boolean_metrics(self):
        base = {
            "post_id": "p1",
            "date": "2026-09-11",
            "topic": "AI",
            "angle": "economic",
            "idea_score": 88,
            "quality_score": 84,
            "final_score": 86,
        }
        with self.assertRaises(ValueError):
            performance_row({**base, "views": 1.5})
        with self.assertRaises(ValueError):
            performance_row({**base, "likes": True})

    def test_follow_conversion_is_zero_without_views(self):
        row = performance_row({
            "post_id": "p1",
            "date": "2026-09-11",
            "topic": "AI",
            "angle": "economic",
            "idea_score": 88,
            "quality_score": 84,
            "final_score": 86,
            "impressions": 100,
            "follows": 10,
        })
        self.assertEqual(normalized_metrics(row)["follow_conversion"], 0.0)


if __name__ == "__main__":
    unittest.main()
