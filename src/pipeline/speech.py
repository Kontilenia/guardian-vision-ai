"""Azure AI Speech: text-to-speech (STT is a stretch goal, included as a helper)."""
from __future__ import annotations

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
    """Optional STT helper for the stretch goal."""
    stream = speechsdk.audio.PushAudioInputStream()
    stream.write(audio_bytes)
    stream.close()
    audio_config = speechsdk.audio.AudioConfig(stream=stream)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=_speech_config(), audio_config=audio_config
    )
    result = recognizer.recognize_once()
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return result.text
    return None
