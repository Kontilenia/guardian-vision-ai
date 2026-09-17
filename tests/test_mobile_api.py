from schemas import (
    ConfidenceBand,
    Decision,
    FinalResponse,
    FramingAction,
    PolicyDecision,
    Tier,
    TrustResult,
)
import mobile_api
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


class FakeUpload:
    def __init__(self, content: bytes):
        self.content = content

    async def read(self) -> bytes:
        return self.content


def make_result(decision: Decision, framing_action=None) -> FinalResponse:
    policy = PolicyDecision(
        decision=decision,
        tier=Tier.CONSEQUENTIAL,
        band=ConfidenceBand.MEDIUM,
        response_text="Take another picture.",
    )
    trust = TrustResult(band=ConfidenceBand.MEDIUM, score=0.6)
    return FinalResponse(
        decision=policy,
        trust=trust,
        spoken_text=policy.response_text,
        framing_action=framing_action,
    )


class MobileApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        mobile_api._PENDING_SESSIONS.clear()

    def tearDown(self):
        mobile_api._PENDING_SESSIONS.clear()

    def test_serializes_constrained_framing_action(self):
        response = mobile_api._serialize_result(
            "session-1",
            make_result(Decision.ANSWER, FramingAction.MOVE_LEFT),
        )

        self.assertEqual(response.framing_action, "move_left")

    async def test_second_capture_reuses_stored_question_and_first_frame(self):
        first_result = make_result(Decision.NEEDS_SECOND_CAPTURE)
        final_result = make_result(Decision.ANSWER)

        with patch.object(
            mobile_api.orchestrator,
            "run",
            side_effect=[first_result, final_result],
        ) as run:
            first_response = await mobile_api.analyze(
                question="What does the label say?",
                frame=FakeUpload(b"first-frame"),
                session_id="session-2",
            )
            second_response = await mobile_api.analyze(
                question="ignored on second capture",
                frame=FakeUpload(b"second-frame"),
                session_id="session-2",
            )

        self.assertTrue(first_response.needs_second_capture)
        self.assertFalse(second_response.needs_second_capture)
        first_request = run.call_args_list[0].args[0]
        second_request = run.call_args_list[1].args[0]
        self.assertEqual(first_request.image_bytes, b"first-frame")
        self.assertEqual(second_request.question, "What does the label say?")
        self.assertEqual(second_request.image_bytes, b"first-frame")
        self.assertEqual(second_request.second_image_bytes, b"second-frame")
        self.assertNotIn("session-2", mobile_api._PENDING_SESSIONS)

    def test_cancel_session_is_idempotent(self):
        mobile_api._PENDING_SESSIONS["session-3"] = ("question", b"frame")

        self.assertEqual(mobile_api.cancel_session(
            "session-3"), {"removed": True})
        self.assertEqual(mobile_api.cancel_session(
            "session-3"), {"removed": False})


if __name__ == "__main__":
    unittest.main()
