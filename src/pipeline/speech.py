"""Azure AI Speech: text-to-speech and speech-to-text."""
from __future__ import annotations

import tempfile
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk

from config import get_settings


def _speech_config() -> speechsdk.SpeechConfig:
    settings = get_settings()
    config = speechsdk.SpeechConfig(
        subscription=settings.speech_key, region=settings.speech_region)
    config.speech_synthesis_voice_name = settings.tts_voice
    config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
    )
    return config


def synthesize(text: str) -> bytes | None:
    """Return MP3 audio bytes for the given text, or None on failure."""
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=_speech_config(), audio_config=None)
    result = synthesizer.speak_text_async(text).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return bytes(result.audio_data)
    return None


def transcribe(audio_bytes: bytes) -> str | None:
    """Return an en-US transcript for WAV audio bytes, or None on failure."""
    if not audio_bytes:
        return None

    audio_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_file.write(audio_bytes)
            audio_path = Path(audio_file.name)

        config = _speech_config()
        config.speech_recognition_language = "en-US"
        audio_config = speechsdk.audio.AudioConfig(filename=str(audio_path))
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=config, audio_config=audio_config
        )
        result = recognizer.recognize_once()
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            transcript = result.text.strip()
            return transcript or None
        return None
    finally:
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)
