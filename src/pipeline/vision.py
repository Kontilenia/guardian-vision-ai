"""Vision analysis (GPT-4o): observable facts, self-confidence, critical value."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from azure_clients import get_openai_client
from config import get_settings
from evidence import evidence_from_choice
from schemas import FramingAction, SensitiveContentCategory, VisionResult

_PROMPT = (Path(__file__).parent.parent / "prompts" / "vision.txt").read_text()


def _data_url(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def analyze(question: str, image_bytes: bytes) -> VisionResult:
    client = get_openai_client()
    settings = get_settings()

    response = client.chat.completions.create(
        model=settings.vision_deployment,
        messages=[
            {"role": "system", "content": _PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {
                        "url": _data_url(image_bytes)}},
                ],
            },
        ],
        temperature=0,
        response_format={"type": "json_object"},
        logprobs=True,
    )

    choice = response.choices[0]
    data = json.loads(choice.message.content)
    critical = data.get("critical_value")
    raw_framing_action = data.get("framing_action")
    raw_sensitive_category = data.get("sensitive_content_category")
    try:
        framing_action = FramingAction(
            raw_framing_action) if raw_framing_action else None
    except ValueError:
        framing_action = None
    try:
        sensitive_category = SensitiveContentCategory(
            raw_sensitive_category) if raw_sensitive_category else None
    except ValueError:
        sensitive_category = None
    return VisionResult(
        observations=data.get("observations", ""),
        self_confidence=float(data.get("self_confidence", 0.0)),
        critical_value=None if critical in (
            None, "", "null") else str(critical),
        evidence=evidence_from_choice(choice),
        framing_action=framing_action,
        sensitive_content_category=sensitive_category,
    )
