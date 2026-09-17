"""Typed data models shared across the Guardian Vision pipeline."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Tier(int, Enum):
    INFORMATIONAL = 0
    CONSEQUENTIAL = 1
    LIFE_SAFETY = 2


class ConfidenceBand(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Decision(str, Enum):
    ANSWER = "answer"
    ANSWER_WITH_UNCERTAINTY = "answer_with_uncertainty"
    FACTS_ONLY = "facts_only"
    BLOCKED = "blocked"
    NEEDS_SECOND_CAPTURE = "needs_second_capture"


class FramingAction(str, Enum):
    MOVE_LEFT = "move_left"
    MOVE_RIGHT = "move_right"
    MOVE_CLOSER = "move_closer"
    MOVE_FARTHER = "move_farther"
    HOLD_STEADY = "hold_steady"
    IMPROVE_LIGHTING = "improve_lighting"


class UserRequest(BaseModel):
    question: str
    image_bytes: bytes
    second_image_bytes: Optional[bytes] = None


class ProbabilityEvidence(BaseModel):
    """Token/logprob-derived signal. Availability is explicit and neutral when missing."""

    available: bool = False
    mean_token_probability: Optional[float] = None
    min_token_probability: Optional[float] = None
    note: str = ""


class SafetyResult(BaseModel):
    allowed: bool
    flagged_categories: list[str] = Field(default_factory=list)
    max_severity: int = 0
    raw: dict = Field(default_factory=dict)


class TierResult(BaseModel):
    tier: Tier
    rationale: str
    evidence: ProbabilityEvidence = Field(default_factory=ProbabilityEvidence)


class VisionResult(BaseModel):
    observations: str
    self_confidence: float = Field(ge=0.0, le=1.0)
    critical_value: Optional[str] = None
    evidence: ProbabilityEvidence = Field(default_factory=ProbabilityEvidence)
    framing_action: Optional[FramingAction] = None


class TrustResult(BaseModel):
    band: ConfidenceBand
    score: float = Field(ge=0.0, le=1.0)
    agreement: Optional[bool] = None
    probability_available: bool = False
    reasons: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    decision: Decision
    tier: Tier
    band: ConfidenceBand
    offer_human: bool = False
    response_text: str = ""


class FinalResponse(BaseModel):
    decision: PolicyDecision
    trust: TrustResult
    spoken_text: str
    audio_bytes: Optional[bytes] = None
    blocked_reason: Optional[str] = None
    framing_action: Optional[FramingAction] = None
