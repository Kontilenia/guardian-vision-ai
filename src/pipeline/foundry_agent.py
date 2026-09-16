"""Azure AI Foundry Guardian Agent: provision/resolve the persistent agent and
provide a thread-backed session for traceable orchestration.

The deterministic tier logic lives in the Python stage modules (required for safety
guarantees). This module registers those stages as the agent's tool contracts and
records each run on a Foundry thread so the orchestration is auditable in Foundry.
"""
from __future__ import annotations

from functools import lru_cache

from azure.ai.projects import AIProjectClient

from azure_clients import get_credential
from config import get_settings

_AGENT_INSTRUCTIONS = """You are Guardian Vision AI, a confidence-first accessibility assistant.
Follow the tier workflow strictly:
- Tier 0 Informational: answer directly and state the confidence band.
- Tier 1 Consequential: require a second capture, cross-check the two readings, and only
  confirm the critical value if they agree; offer a human on disagreement.
- Tier 2 Life-safety: describe observable facts only. Never state a conclusion, dose,
  diagnosis, or safety judgement. Refer to a professional and always offer a human.
Never bypass the safety guardrails."""

# Tool contracts describing each pipeline stage the agent orchestrates.
_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "classify_tier",
            "description": "Classify the request into Tier 0/1/2.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "Extract observable facts, self-confidence, and the critical value.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_content_safety",
            "description": "Run input/output content safety guardrails.",
            "parameters": {
                "type": "object",
                "properties": {"stage": {"type": "string", "enum": ["input", "output"]}},
                "required": ["stage"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "score_trust",
            "description": "Compute the composite confidence band.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_policy",
            "description": "Apply the tier rules to produce the final decision.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


@lru_cache(maxsize=1)
def get_project_client() -> AIProjectClient:
    settings = get_settings()
    return AIProjectClient(
        endpoint=settings.foundry_project_endpoint,
        credential=get_credential(),
    )


@lru_cache(maxsize=1)
def ensure_agent() -> str:
    """Create or resolve the persistent Guardian Agent, returning its id."""
    settings = get_settings()
    client = get_project_client()

    if settings.guardian_agent_id:
        return settings.guardian_agent_id

    for agent in client.agents.list_agents():
        if agent.name == settings.guardian_agent_name:
            return agent.id

    created = client.agents.create_agent(
        model=settings.text_deployment,
        name=settings.guardian_agent_name,
        instructions=_AGENT_INSTRUCTIONS,
        tools=_TOOL_DEFINITIONS,
    )
    return created.id


class GuardianAgentSession:
    """A Foundry thread used to record one request's orchestration trace."""

    def __init__(self) -> None:
        self._client = get_project_client()
        self.agent_id = ensure_agent()
        self.thread = self._client.agents.threads.create()

    def record(self, role: str, content: str) -> None:
        try:
            self._client.agents.messages.create(
                thread_id=self.thread.id, role=role, content=content
            )
        except Exception:
            # Tracing must never break the safety pipeline.
            pass
