"""Policy Engine: apply Tier 0/1/2 rules to trust + vision to produce a decision."""
from __future__ import annotations

from schemas import (
    ConfidenceBand,
    Decision,
    PolicyDecision,
    Tier,
    TierResult,
    TrustResult,
    VisionResult,
)

_BAND_PHRASE = {
    ConfidenceBand.HIGH: "I'm confident about this.",
    ConfidenceBand.MEDIUM: "I'm fairly sure, but not certain.",
    ConfidenceBand.LOW: "I'm not confident about this.",
}


def decide(
    tier_result: TierResult,
    vision: VisionResult,
    trust: TrustResult,
    *,
    has_second_capture: bool,
) -> PolicyDecision:
    tier = tier_result.tier

    if tier is Tier.INFORMATIONAL:
        return _tier0(tier, vision, trust)
    if tier is Tier.CONSEQUENTIAL:
        return _tier1(tier, vision, trust, has_second_capture)
    return _tier2(tier_result, vision, trust)


def _tier0(tier: Tier, vision: VisionResult, trust: TrustResult) -> PolicyDecision:
    text = f"{vision.observations} {_BAND_PHRASE[trust.band]}"
    return PolicyDecision(
        decision=Decision.ANSWER,
        tier=tier,
        band=trust.band,
        offer_human=False,
        response_text=text.strip(),
    )


def _tier1(
    tier: Tier, vision: VisionResult, trust: TrustResult, has_second_capture: bool
) -> PolicyDecision:
    if not has_second_capture:
        return PolicyDecision(
            decision=Decision.NEEDS_SECOND_CAPTURE,
            tier=tier,
            band=trust.band,
            offer_human=False,
            response_text=(
                "For your safety, I need a second photo before I can answer. Please take "
                "another photo of the same thing so I can compare the two readings."
            ),
        )

    if trust.agreement is False:
        return PolicyDecision(
            decision=Decision.ANSWER_WITH_UNCERTAINTY,
            tier=tier,
            band=ConfidenceBand.LOW,
            offer_human=True,
            response_text=(
                "The two photos did not agree on the important detail, so I can't confirm it. "
                "I saw: "
                f"{vision.observations} Would you like me to connect you with a human helper?"
            ),
        )

    value = vision.critical_value or "the value"
    return PolicyDecision(
        decision=Decision.ANSWER,
        tier=tier,
        band=trust.band,
        offer_human=trust.band is ConfidenceBand.LOW,
        response_text=(
            f"Both photos agree. I read {value}. {_BAND_PHRASE[trust.band]} "
            f"What was visible: {vision.observations}"
        ),
    )


def _tier2(
    tier_result: TierResult, vision: VisionResult, trust: TrustResult
) -> PolicyDecision:
    if tier_result.medical_advice_requested:
        return PolicyDecision(
            decision=Decision.BLOCKED,
            tier=tier_result.tier,
            band=trust.band,
            offer_human=True,
            response_text=(
                "I can read the printed instructions, but I cannot recommend dosage or "
                "provide medical advice. Please consult a pharmacist, doctor, or official "
                "medication guidance."
            ),
        )

    # Life-safety: observable facts only, never a conclusion/dose/diagnosis. Always offer a human.
    return PolicyDecision(
        decision=Decision.FACTS_ONLY,
        tier=tier_result.tier,
        band=trust.band,
        offer_human=True,
        response_text=(
            "This could affect your safety, so I will only describe what I can see and won't "
            "make a judgement. "
            f"{vision.observations} "
            "Please confirm with a qualified professional. Would you like me to connect you "
            "with a human helper?"
        ),
    )
