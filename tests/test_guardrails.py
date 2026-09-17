from schemas import (
    ConfidenceBand,
    Decision,
    ProbabilityEvidence,
    SafetyResult,
    SensitiveContentCategory,
    Tier,
    TierResult,
    TrustResult,
    UserRequest,
    VisionResult,
)
import policy_engine
import orchestrator
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(SRC / "pipeline"))


def safe_result() -> SafetyResult:
    return SafetyResult(allowed=True)


def vision_result(
    sensitive_category: SensitiveContentCategory | None = None,
) -> VisionResult:
    return VisionResult(
        observations="generic observation",
        self_confidence=0.9,
        evidence=ProbabilityEvidence(),
        sensitive_content_category=sensitive_category,
    )


class GuardrailTests(unittest.TestCase):
    @patch.object(orchestrator, "_trace")
    @patch.object(orchestrator.vision, "analyze")
    @patch.object(orchestrator.tier_classifier, "classify")
    @patch.object(orchestrator.content_safety, "check_image", return_value=safe_result())
    @patch.object(orchestrator.content_safety, "check_text", return_value=safe_result())
    def test_sensitive_first_capture_is_blocked(
        self, _check_text, _check_image, classify, analyze, trace
    ):
        trace.return_value.record.return_value = None
        classify.return_value = TierResult(
            tier=Tier.INFORMATIONAL, rationale="informational"
        )
        analyze.return_value = vision_result(
            SensitiveContentCategory.IDENTITY_DOCUMENT)

        result = orchestrator.run(
            UserRequest(question="Read this", image_bytes=b"image"),
            synthesize_audio=False,
        )

        self.assertEqual(result.decision.decision, Decision.BLOCKED)
        self.assertEqual(result.blocked_reason,
                         "sensitive_content: identity_document")
        self.assertNotIn("generic observation", result.spoken_text)

    @patch.object(orchestrator, "_trace")
    @patch.object(orchestrator.vision, "analyze")
    @patch.object(orchestrator.tier_classifier, "classify")
    @patch.object(orchestrator.content_safety, "check_image", return_value=safe_result())
    @patch.object(orchestrator.content_safety, "check_text", return_value=safe_result())
    def test_sensitive_second_capture_is_blocked(
        self, _check_text, _check_image, classify, analyze, trace
    ):
        trace.return_value.record.return_value = None
        classify.return_value = TierResult(
            tier=Tier.CONSEQUENTIAL, rationale="consequential"
        )
        analyze.side_effect = [
            vision_result(),
            vision_result(SensitiveContentCategory.FINANCIAL_DOCUMENT),
        ]

        result = orchestrator.run(
            UserRequest(
                question="Read this",
                image_bytes=b"first",
                second_image_bytes=b"second",
            ),
            synthesize_audio=False,
        )

        self.assertEqual(result.decision.decision, Decision.BLOCKED)
        self.assertEqual(result.blocked_reason,
                         "sensitive_content: financial_document")

    def test_medical_advice_is_refused(self):
        decision = policy_engine.decide(
            TierResult(
                tier=Tier.LIFE_SAFETY,
                rationale="medical judgement",
                medical_advice_requested=True,
            ),
            vision_result(),
            TrustResult(band=ConfidenceBand.HIGH, score=0.9),
            has_second_capture=False,
        )

        self.assertEqual(decision.decision, Decision.BLOCKED)
        self.assertTrue(decision.offer_human)
        self.assertEqual(
            decision.response_text,
            "I can read the printed instructions, but I cannot recommend dosage or "
            "provide medical advice. Please consult a pharmacist, doctor, or official "
            "medication guidance.",
        )

    def test_tier_one_requests_second_capture_for_safety_before_answering(self):
        decision = policy_engine.decide(
            TierResult(tier=Tier.CONSEQUENTIAL, rationale="consequential"),
            vision_result(),
            TrustResult(band=ConfidenceBand.MEDIUM, score=0.6),
            has_second_capture=False,
        )

        self.assertEqual(decision.decision, Decision.NEEDS_SECOND_CAPTURE)
        self.assertIn("For your safety", decision.response_text)
        self.assertIn("before I can answer", decision.response_text)


if __name__ == "__main__":
    unittest.main()
