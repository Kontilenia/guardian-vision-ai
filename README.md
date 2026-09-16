# Guardian Vision AI

Empowering accessibility through trusted visual intelligence.

Guardian Vision AI is a confidence-first accessibility assistant for visually impaired
users. A user uploads a photo and asks a question; every answer is evaluated before it is
spoken. When confidence is high, the user gets immediate voice guidance. When confidence is
low, the system explains the uncertainty and proposes safer alternatives. Guardrails block
inappropriate, illegal, medical, or unsafe requests.

## Safety tiers

| Tier | Meaning | Behaviour |
| ---- | ------- | --------- |
| 0 — Informational | Wrong answer is a mild inconvenience the user can detect | Answer directly, state the confidence band |
| 1 — Consequential | Wrong answer is costly and hard to detect | Require a second photo, cross-check the readings, answer only if they agree, offer a human on disagreement |
| 2 — Life-safety | Wrong answer can cause injury or worse | Describe observable facts only; never conclude, dose, or diagnose; refer to a professional and always offer a human |

## Pipeline

```
Input guardrail → Tier classify → GPT-4o vision → (Tier 1: second capture + cross-check)
→ Trust engine (confidence band) → Policy engine (tier rules) → Output guardrail → TTS
```

## Azure services

| Service | Role |
| ------- | ---- |
| Azure AI Foundry | Guardian Agent orchestration + traceability |
| GPT-4o | Vision understanding |
| GPT-5.x Mini | Tier classification + text safeguards |
| Azure AI Speech | Text-to-speech (speech-to-text optional) |
| Azure AI Content Safety | Input and output guardrails |

## Project layout

```
src/
  app.py                     Streamlit UI
  config.py                  Environment-driven settings
  requirements.txt
  .env.example
  prompts/                   System prompts for tier + vision
  pipeline/
    schemas.py               Typed data models
    azure_clients.py         Azure client factories
    evidence.py              Token-probability evidence extraction
    tier_classifier.py       GPT-5.x Mini tier classification
    vision.py                GPT-4o image analysis
    content_safety.py        Input/output guardrails
    trust_engine.py          Composite confidence band
    policy_engine.py         Tier 0/1/2 rules
    speech.py                Text-to-speech (and optional STT)
    foundry_agent.py         Persistent Foundry Agent + thread tracing
    orchestrator.py          End-to-end flow
```

## Setup

```bash
pip install -r src/requirements.txt
cp src/.env.example src/.env   # then fill in your Azure endpoints and keys
streamlit run src/app.py
```

Authentication uses `DefaultAzureCredential` by default (set `AZURE_CREDENTIAL_MODE=key`
to use API keys for Azure OpenAI). Model deployment names are configurable via `.env`.

## Responsible AI notes

- Confidence blends the model's self-report, Tier 1 cross-capture agreement, and token
  probabilities when the deployment exposes them. Missing probability data is treated as
  neutral, never as low confidence.
- Tier 2 responses are strictly observational and always offer a human.
- Content Safety runs on both the incoming request (text + image) and the outgoing reply.
