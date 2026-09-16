"""Tier classifier (GPT-5.x Mini): classify a request into Tier 0/1/2."""
from __future__ import annotations

import json
from pathlib import Path

from azure_clients import get_openai_client
from config import get_settings
from evidence import evidence_from_choice
from schemas import Tier, TierResult

_PROMPT = (Path(__file__).parent.parent / "prompts" /
           "tier_classifier.txt").read_text()


def classify(question: str) -> TierResult:
    client = get_openai_client()
    settings = get_settings()

    response = client.chat.completions.create(
        model=settings.text_deployment,
        messages=[
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        logprobs=True,
    )

    choice = response.choices[0]
    data = json.loads(choice.message.content)
    return TierResult(
        tier=Tier(int(data["tier"])),
        rationale=data.get("rationale", ""),
        evidence=evidence_from_choice(choice),
    )
