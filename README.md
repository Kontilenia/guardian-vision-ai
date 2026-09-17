# Guardian Vision AI

Empowering accessibility through trusted visual intelligence.

Guardian Vision AI is a confidence-first accessibility assistant for visually impaired
users. A user uploads a photo and asks a question by voice or text; every answer is evaluated
before it is spoken. When confidence is high, the user gets immediate voice guidance. When
confidence is low, the system explains the uncertainty and proposes safer alternatives.
Guardrails block inappropriate, illegal, medical, or unsafe requests.

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
| Azure AI Speech | Speech-to-text input and text-to-speech output |
| Azure AI Content Safety on the Foundry account | Input and output guardrails |

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

## Accessible mobile mock

The mobile app is an audio-first browser experience with an accessible visual control
panel. Choose Voice or Text before pressing Start. Voice mode requests camera and
microphone access; Text mode requests only camera access. The required Start action also
unlocks browser audio for status speech and feedback tones.

In Voice mode, a tone confirms when listening begins. The app waits for the speaker to
finish, pauses recording, captures the picture, and immediately confirms the capture with
a shutter tone, optional vibration, visible status, and the spoken phrase "Picture
captured. Thinking." It never records while speaking a status message or answer. Text mode
uses the same capture and analysis path without listening to the microphone.

Stop ends recording and playback, closes camera and microphone tracks, ignores unfinished
requests, and clears pending second-capture state. Repeat answer replays the latest answer,
and Take picture again preserves the question while replacing its image. Consequential
questions that require a second view wait for the user to activate Take another picture;
the app does not capture another view silently on a timer.

Local darkness and blur checks are advisory. A user can retake the picture or choose Use
this picture, so a heuristic cannot block access. Model-provided framing guidance is
limited to fixed camera adjustments and is not navigation or obstacle-avoidance advice.
Speak status messages can be turned off to avoid duplicate speech when using a screen
reader; live-region status updates remain available.

Run it locally:

```bash
uvicorn src.mobile_api:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` for local development. For a container or hosted app link,
serve the same FastAPI app over HTTPS; browsers only allow camera and microphone access
from secure contexts, except for localhost. A self-signed certificate is enough for local
testing, but a trusted certificate or HTTPS reverse proxy is recommended for demos.

Vibration is an optional enhancement and is not supported by every browser, notably iOS
Safari. Validate permissions, audio routing, speech, and assistive technology on physical
Android and iOS devices over HTTPS; desktop device simulation cannot verify those paths.

Example HTTPS development command:

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes
uvicorn src.mobile_api:app --host 0.0.0.0 --port 8443 --ssl-keyfile=key.pem --ssl-certfile=cert.pem
```

Authentication uses `DefaultAzureCredential` by default. Grant that identity the
`Cognitive Services User` role on the Foundry resource. For local key authentication, set
`AZURE_CREDENTIAL_MODE=key`; `AZURE_OPENAI_API_KEY` is then used as the Foundry account key
for both model and Content Safety calls. No separate Content Safety resource, endpoint, or
key is required. Model deployment names are configurable via `.env`.

## Responsible AI notes

- Confidence blends the model's self-report, Tier 1 cross-capture agreement, and token
  probabilities when the deployment exposes them. Missing probability data is treated as
  neutral, never as low confidence.
- Tier 2 responses are strictly observational and always offer a human.
- Content Safety runs on both the incoming request (text + image) and the outgoing reply.
