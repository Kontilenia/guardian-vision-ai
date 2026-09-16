"""Guardian orchestrator: runs the confidence-first pipeline stage by stage.

Order: input guardrail -> tier classify -> vision -> (Tier 1 second capture + cross-check)
-> trust -> policy -> output guardrail -> TTS. Each stage is recorded on a Foundry thread
for traceability when the agent/project is configured.
"""
from __future__ import annotations

import content_safety
import policy_engine
import speech
import tier_classifier
import trust_engine
import vision
from schemas import (
    ConfidenceBand,
    Decision,
    FinalResponse,
    PolicyDecision,
    Tier,
    TrustResult,
    UserRequest,
)


def _blocked(reason: str, spoken: str) -> FinalResponse:
    decision = PolicyDecision(
        decision=Decision.BLOCKED,
        tier=Tier.INFORMATIONAL,
        band=ConfidenceBand.LOW,
        offer_human=True,
        response_text=spoken,
    )
    trust = TrustResult(band=ConfidenceBand.LOW, score=0.0, reasons=[reason])
    return FinalResponse(
        decision=decision,
        trust=trust,
        spoken_text=spoken,
        audio_bytes=speech.synthesize(spoken),
        blocked_reason=reason,
    )


def _trace():
    """Return a Foundry session for tracing, or a no-op if unavailable."""
    try:
        from foundry_agent import GuardianAgentSession

        return GuardianAgentSession()
    except Exception:
        class _NoOp:
            def record(self, *args, **kwargs) -> None:
                ...

        return _NoOp()


def run(request: UserRequest, *, synthesize_audio: bool = True) -> FinalResponse:
    session = _trace()
    session.record("user", request.question)

    # 1. Input guardrails.
    text_safety = content_safety.check_text(request.question)
    image_safety = content_safety.check_image(request.image_bytes)
    if not text_safety.allowed or not image_safety.allowed:
        reason = "input_guardrail: " + ", ".join(
            text_safety.flagged_categories + image_safety.flagged_categories
        )
        session.record("assistant", reason)
        return _blocked(
            reason,
            "I can't help with this request. If you're in danger, please contact local emergency services.",
        )

    # 2. Tier classification.
    tier_result = tier_classifier.classify(request.question)
    session.record("assistant", f"tier={tier_result.tier.value}: {tier_result.rationale}")

    # 3. Vision on the first capture.
    first = vision.analyze(request.question, request.image_bytes)
    session.record("assistant", f"vision1: {first.observations}")

    # 4. Tier 1 second-capture branch.
    agreement: bool | None = None
    has_second = request.second_image_bytes is not None
    active_vision = first

    if tier_result.tier is Tier.CONSEQUENTIAL:
        if not has_second:
            trust = trust_engine.compute(first, agreement=None)
            decision = policy_engine.decide(
                tier_result, first, trust, has_second_capture=False
            )
            session.record("assistant", "requesting second capture")
            spoken = _compose_spoken(decision)
            return FinalResponse(
                decision=decision,
                trust=trust,
                spoken_text=spoken,
                audio_bytes=speech.synthesize(spoken) if synthesize_audio else None,
            )

        second = vision.analyze(request.question, request.second_image_bytes)
        session.record("assistant", f"vision2: {second.observations}")
        agreement = trust_engine.values_agree(first.critical_value, second.critical_value)
        active_vision = first if agreement else second

    # 5. Trust engine.
    trust = trust_engine.compute(active_vision, agreement=agreement)
    session.record("assistant", f"trust band={trust.band.value} score={trust.score}")

    # 6. Policy engine.
    decision = policy_engine.decide(
        tier_result, active_vision, trust, has_second_capture=has_second
    )

    # 7. Output guardrail on the generated reply.
    spoken = _compose_spoken(decision)
    output_safety = content_safety.check_text(spoken)
    if not output_safety.allowed:
        reason = "output_guardrail: " + ", ".join(output_safety.flagged_categories)
        session.record("assistant", reason)
        return _blocked(
            reason,
            "I generated a response but held it back for safety. Let me connect you with a human helper.",
        )

    session.record("assistant", spoken)

    # 8. Text-to-speech.
    audio = speech.synthesize(spoken) if synthesize_audio else None
    return FinalResponse(decision=decision, trust=trust, spoken_text=spoken, audio_bytes=audio)


def _compose_spoken(decision: PolicyDecision) -> str:
    return decision.response_text.strip()
