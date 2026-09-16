"""Content Safety guardrails for input (text + image) and output (text)."""
from __future__ import annotations

from azure.ai.contentsafety.models import (
    AnalyzeImageOptions,
    AnalyzeTextOptions,
    ImageData,
)
from azure.core.exceptions import HttpResponseError

from azure_clients import get_content_safety_client
from schemas import SafetyResult

# Severity at or above this level blocks the request/response.
_BLOCK_SEVERITY = 4


def _summarize(categories_analysis) -> tuple[list[str], int]:
    flagged: list[str] = []
    max_severity = 0
    for item in categories_analysis:
        severity = item.severity or 0
        max_severity = max(max_severity, severity)
        if severity >= _BLOCK_SEVERITY:
            flagged.append(str(item.category))
    return flagged, max_severity


def check_text(text: str) -> SafetyResult:
    client = get_content_safety_client()
    try:
        result = client.analyze_text(AnalyzeTextOptions(text=text))
    except HttpResponseError as exc:
        return SafetyResult(allowed=False, flagged_categories=["service_error"], raw={"error": str(exc)})

    flagged, max_severity = _summarize(result.categories_analysis)
    return SafetyResult(allowed=not flagged, flagged_categories=flagged, max_severity=max_severity)


def check_image(image_bytes: bytes) -> SafetyResult:
    client = get_content_safety_client()
    try:
        result = client.analyze_image(
            AnalyzeImageOptions(image=ImageData(content=image_bytes))
        )
    except HttpResponseError as exc:
        return SafetyResult(allowed=False, flagged_categories=["service_error"], raw={"error": str(exc)})

    flagged, max_severity = _summarize(result.categories_analysis)
    return SafetyResult(allowed=not flagged, flagged_categories=flagged, max_severity=max_severity)
