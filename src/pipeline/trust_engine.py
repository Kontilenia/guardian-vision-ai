"""Trust Engine: composite confidence band from multiple signals.

Signals combined:
- vision self-reported confidence
- Tier 1 cross-capture agreement on the critical value
- token-probability evidence (only when the deployment exposes it)
- safety results

Missing probability metadata is neutral and recorded explicitly; it never lowers the band.
"""
from __future__ import annotations

from config import get_settings
from schemas import (
    ConfidenceBand,
    ProbabilityEvidence,
    TrustResult,
    VisionResult,
)


def _normalize(value: str | None) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def values_agree(first: str | None, second: str | None) -> bool:
    return bool(first) and _normalize(first) == _normalize(second)


def compute(
    vision: VisionResult,
    *,
    agreement: bool | None = None,
    extra_evidence: ProbabilityEvidence | None = None,
) -> TrustResult:
    settings = get_settings()
    reasons: list[str] = []

    score = vision.self_confidence
    reasons.append(f"vision self-confidence={vision.self_confidence:.2f}")

    probability_available = False
    for evidence in (vision.evidence, extra_evidence):
        if evidence and evidence.available and evidence.mean_token_probability is not None:
            probability_available = True
            # Blend model self-report with observed token probability.
            score = 0.6 * score + 0.4 * evidence.mean_token_probability
            reasons.append(
                f"token prob mean={evidence.mean_token_probability:.2f}")
    if not probability_available:
        reasons.append("token probability unavailable (neutral)")

    if agreement is True:
        score = min(1.0, score + 0.15)
        reasons.append("second capture agrees")
    elif agreement is False:
        score = min(score, settings.trust_low_threshold - 0.01)
        reasons.append("second capture disagrees")

    if score >= settings.trust_high_threshold:
        band = ConfidenceBand.HIGH
    elif score >= settings.trust_low_threshold:
        band = ConfidenceBand.MEDIUM
    else:
        band = ConfidenceBand.LOW

    return TrustResult(
        band=band,
        score=round(score, 3),
        agreement=agreement,
        probability_available=probability_available,
        reasons=reasons,
    )
