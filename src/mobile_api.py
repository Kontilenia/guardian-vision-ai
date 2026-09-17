"""Accessible mobile-style API for live camera and microphone flows."""
from __future__ import annotations

import base64
import sys
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Make src/ and src/pipeline/ importable as flat modules, matching app.py.
_SRC = Path(__file__).parent
sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_SRC / "pipeline"))

import orchestrator  # noqa: E402
import speech  # noqa: E402
from schemas import Decision, FinalResponse, UserRequest  # noqa: E402

_STATIC_DIR = _SRC / "mobile_static"
_PENDING_SESSIONS: dict[str, tuple[str, bytes]] = {}

app = FastAPI(title="Guardian Vision AI Mobile API")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


class TranscriptionResponse(BaseModel):
    transcript: str | None


class AnalyzeResponse(BaseModel):
    session_id: str
    audio_base64: str | None
    spoken_text: str
    text: str
    decision: str
    tier: int
    confidence_band: str
    confidence_score: float
    needs_second_capture: bool
    offer_human: bool
    blocked_reason: str | None = None
    reasons: list[str]
    framing_action: str | None = None


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)) -> TranscriptionResponse:
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="No audio was received.")

    transcript = speech.transcribe(audio_bytes)
    return TranscriptionResponse(transcript=transcript)


@app.delete("/api/sessions/{session_id}")
def cancel_session(session_id: str) -> dict[str, bool]:
    removed = _PENDING_SESSIONS.pop(session_id, None) is not None
    return {"removed": removed}


@app.post("/api/analyze")
async def analyze(
    question: str = Form(...),
    frame: UploadFile = File(...),
    session_id: str | None = Form(default=None),
) -> AnalyzeResponse:
    clean_question = question.strip()
    if not clean_question:
        raise HTTPException(status_code=400, detail="Question is required.")

    frame_bytes = await frame.read()
    if not frame_bytes:
        raise HTTPException(
            status_code=400, detail="Camera frame is required.")

    active_session_id = session_id or str(uuid4())
    pending = _PENDING_SESSIONS.pop(active_session_id, None)

    if pending is None:
        request = UserRequest(question=clean_question, image_bytes=frame_bytes)
    else:
        pending_question, first_frame = pending
        request = UserRequest(
            question=pending_question,
            image_bytes=first_frame,
            second_image_bytes=frame_bytes,
        )

    result = orchestrator.run(request)

    if result.decision.decision is Decision.NEEDS_SECOND_CAPTURE:
        _PENDING_SESSIONS[active_session_id] = (clean_question, frame_bytes)

    return _serialize_result(active_session_id, result)


def _serialize_result(session_id: str, result: FinalResponse) -> AnalyzeResponse:
    audio_base64 = (
        base64.b64encode(result.audio_bytes).decode("ascii")
        if result.audio_bytes
        else None
    )
    return AnalyzeResponse(
        session_id=session_id,
        audio_base64=audio_base64,
        spoken_text=result.spoken_text,
        text=result.spoken_text,
        decision=result.decision.decision.value,
        tier=result.decision.tier.value,
        confidence_band=result.trust.band.value,
        confidence_score=result.trust.score,
        needs_second_capture=result.decision.decision is Decision.NEEDS_SECOND_CAPTURE,
        offer_human=result.decision.offer_human,
        blocked_reason=result.blocked_reason,
        reasons=result.trust.reasons,
        framing_action=result.framing_action.value if result.framing_action else None,
    )
