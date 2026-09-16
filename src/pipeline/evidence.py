"""Extract token-probability evidence from Azure OpenAI responses when available.

Availability is explicit: when a deployment does not return logprobs the evidence is
marked unavailable and treated as neutral by the Trust Engine (never as low confidence).
"""
from __future__ import annotations

import math

from schemas import ProbabilityEvidence


def evidence_from_choice(choice) -> ProbabilityEvidence:
    logprobs = getattr(choice, "logprobs", None)
    content = getattr(logprobs, "content", None) if logprobs else None
    if not content:
        return ProbabilityEvidence(available=False, note="logprobs not returned by deployment")

    probs: list[float] = []
    for token in content:
        lp = getattr(token, "logprob", None)
        if lp is None:
            continue
        probs.append(math.exp(lp))

    if not probs:
        return ProbabilityEvidence(available=False, note="no token logprobs present")

    return ProbabilityEvidence(
        available=True,
        mean_token_probability=sum(probs) / len(probs),
        min_token_probability=min(probs),
        note=f"derived from {len(probs)} tokens",
    )
