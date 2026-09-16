"""Guardian Vision AI — Streamlit app.

Upload a photo, type a question, and hear a confidence-first voice reply. Tier 1
(consequential) requests use two explicit image slots to cross-check the reading.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make src/ and src/pipeline/ importable as flat modules.
_SRC = Path(__file__).parent
sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_SRC / "pipeline"))

import streamlit as st  # noqa: E402

import orchestrator  # noqa: E402
from schemas import ConfidenceBand, Decision, UserRequest  # noqa: E402

_BAND_ICON = {
    ConfidenceBand.HIGH: "🟢 High confidence",
    ConfidenceBand.MEDIUM: "🟡 Medium confidence",
    ConfidenceBand.LOW: "🔴 Low confidence",
}

st.set_page_config(page_title="Guardian Vision AI", page_icon="🦮")
st.title("Guardian Vision AI")
st.caption(
    "A confidence-first accessibility assistant. Every answer is checked before it's spoken.")


def _reset() -> None:
    for key in ("first_image", "pending_question", "awaiting_second"):
        st.session_state.pop(key, None)


def _render_result(result) -> None:
    st.subheader("Response")
    st.write(result.spoken_text)

    st.markdown(
        f"**{_BAND_ICON[result.trust.band]}**  ·  score `{result.trust.score}`")
    if not result.trust.probability_available:
        st.caption(
            "Token-probability signal unavailable for this deployment (treated as neutral).")
    if result.decision.offer_human:
        st.info("A human helper can be connected for this request.")
    if result.blocked_reason:
        st.warning(f"Held back by safety guardrails: {result.blocked_reason}")

    with st.expander("Why this confidence?"):
        for reason in result.trust.reasons:
            st.write(f"- {reason}")

    if result.audio_bytes:
        st.audio(result.audio_bytes, format="audio/mp3")


# --- Tier 1 second-capture flow ---
if st.session_state.get("awaiting_second"):
    st.info("This is a consequential request. Please provide a second photo of the same thing.")
    st.write(f"**Question:** {st.session_state['pending_question']}")
    second = st.file_uploader("Second photo", type=[
                              "jpg", "jpeg", "png"], key="second_upload")
    col1, col2 = st.columns(2)
    if col1.button("Compare readings", disabled=second is None):
        request = UserRequest(
            question=st.session_state["pending_question"],
            image_bytes=st.session_state["first_image"],
            second_image_bytes=second.getvalue(),
        )
        with st.spinner("Cross-checking both photos..."):
            result = orchestrator.run(request)
        _render_result(result)
        _reset()
    if col2.button("Start over"):
        _reset()
        st.rerun()

# --- Initial request flow ---
else:
    question = st.text_input(
        "Your question", placeholder="e.g. What color is this shirt?")
    photo = st.file_uploader(
        "Photo", type=["jpg", "jpeg", "png"], key="first_upload")

    if st.button("Ask Guardian", disabled=not question or photo is None):
        request = UserRequest(question=question, image_bytes=photo.getvalue())
        with st.spinner("Thinking safely..."):
            result = orchestrator.run(request)

        if result.decision.decision is Decision.NEEDS_SECOND_CAPTURE:
            st.session_state["first_image"] = photo.getvalue()
            st.session_state["pending_question"] = question
            st.session_state["awaiting_second"] = True
            st.rerun()
        else:
            _render_result(result)
