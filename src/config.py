"""Central configuration loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


@dataclass(frozen=True)
class Settings:
    # Foundry
    foundry_project_endpoint: str
    guardian_agent_id: str
    guardian_agent_name: str
    credential_mode: str

    # Foundry model inference
    openai_api_key: str
    vision_deployment: str
    text_deployment: str

    # Speech
    speech_key: str
    speech_region: str
    tts_voice: str

    # Trust thresholds
    trust_high_threshold: float = 0.75
    trust_low_threshold: float = 0.45

    @property
    def use_key_auth(self) -> bool:
        return self.credential_mode.lower() == "key"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        foundry_project_endpoint=_get("FOUNDRY_PROJECT_ENDPOINT"),
        guardian_agent_id=_get("GUARDIAN_AGENT_ID"),
        guardian_agent_name=_get(
            "GUARDIAN_AGENT_NAME", "guardian-vision-agent"),
        credential_mode=_get("AZURE_CREDENTIAL_MODE", "default"),
        openai_api_key=_get("AZURE_OPENAI_API_KEY"),
        vision_deployment=_get("VISION_DEPLOYMENT", "gpt-4o"),
        text_deployment=_get("TEXT_DEPLOYMENT", "gpt-5-mini"),
        speech_key=_get("SPEECH_KEY"),
        speech_region=_get("SPEECH_REGION"),
        tts_voice=_get("TTS_VOICE", "en-US-JennyNeural"),
        trust_high_threshold=float(_get("TRUST_HIGH_THRESHOLD", "0.75")),
        trust_low_threshold=float(_get("TRUST_LOW_THRESHOLD", "0.45")),
    )
