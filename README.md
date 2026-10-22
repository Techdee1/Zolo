# Zolo

**Anyone can propose a payment. Only you can approve it.**

Zolo is a consent layer for Zenith Bank, built for blind and low-vision customers who pay at an agent
or a POS. The customer *hears* who is asking and how much, then approves with their own passkey
(fingerprint, face or screen lock). Nothing is sent unless they approve, a request expires after
2 minutes, and a voice on its own can never approve a payment.

Built for Zecathon 6.0, Track 7.

> **This is a demo.** Login is a fixed code, the bank is a mock, and there is a demo console for the
> stage. It is not connected to real accounts.

## What is here

| Folder | What |
| --- | --- |
| [`backend/`](backend/README.md) | The API (FastAPI, Postgres): the consent state machine, passkeys (WebAuthn), the mock bank, readback text and audio, the demo console |
| [`frontend/`](frontend/README.md) | The web app (Next.js): the landing page, the customer and agent screens, five languages, the PWA manifest |
| [`deploy/`](deploy/) | Docker Compose and Caddy for one machine |
| [`render.yaml`](render.yaml) | A Render Blueprint: database, private API, public web app |
| [`docs/`](docs/) | Guides and records (below) |

The requirements are in [`Backend_PRD.md`](Backend_PRD.md), [`Frontend_PRD.md`](Frontend_PRD.md),
[`AI_PRD.md`](AI_PRD.md) and [`Engineering_Brief.md`](Engineering_Brief.md). Where the frontend differs
from the PRD (because the backend as built wins), [`docs/PRD_DEVIATIONS.md`](docs/PRD_DEVIATIONS.md)
lists every difference.

## How it works

1. **The agent asks.** They type an amount; the backend asks the bank to verify the payee's name and
   returns a 4-digit code and a QR code.
2. **The customer hears it.** They enter the code. The backend builds the readback sentence ("Bisi
   Ventures is asking for fifteen thousand naira...") and, when a clip exists, its audio. The amount
   is also on screen in very large type, and the screen is built for TalkBack and VoiceOver.
3. **The customer approves.** The browser's own passkey prompt signs the request's intent hash. If the
   amount changed after they heard it, the backend refuses (`INTENT_CHANGED`) and nothing is sent.
4. **The agent sees Paid** and gives the cash. If the bank has not confirmed yet, both screens say
   "Processing. Don't hand over goods yet."

The browser only ever talks to the web app, which proxies `/api/*` to the backend. That is why
passkeys are bound to the web app's address.

## Run it locally

You need Docker (for Postgres), [`uv`](https://docs.astral.sh/uv/) and Node 24 with pnpm.

```bash
# the API
cd backend
docker compose up -d postgres
cp .env.example .env            # set SESSION_SECRET, and DEMO_MODE=true with a DEMO_TOKEN
uv sync && uv run alembic upgrade head && uv run python -m zolo.seed
uv run uvicorn zolo.api.main:create_app --factory --port 8000

# the web app, in another terminal
cd frontend
pnpm install
cp .env.example .env.local      # BACKEND_URL defaults to http://localhost:8000
pnpm dev                        # http://localhost:3000
```

Open `http://localhost:3000`, tap "Try the demo", and sign in as the agent in one window and the
customer in another. Direct links that work on their own: `/signin`, `/home`, `/agent`, and `/demo`
(the demo console, when `NEXT_PUBLIC_FEATURE_DEMO=true`).

## Tests

| What | Command | Notes |
| --- | --- | --- |
| Backend | `cd backend && uv run pytest` | Needs Postgres. Coverage gate: 90% on `consent` and `passkeys` |
| Frontend: types, lint, unit | `cd frontend && pnpm check` | Includes the strict accessibility lint rules |
| Frontend: end to end and axe | `pnpm build:e2e && pnpm e2e` | Against a fake backend, in light, dark and reduced motion |
| Frontend: against the real backend | `pnpm e2e:real` | Postgres and real WebAuthn verification, with a software authenticator |

CI runs all of these on every push, and also builds the two Docker images.

## Deploy

- **Render (the quick way):** [`docs/DEPLOY.md`](docs/DEPLOY.md), "On Render". New > Blueprint, pick
  this repo and `main`.
- **Your own machine:** the same guide, with `deploy/compose.yml`.

The guide also explains how the voice works once deployed: which languages, how any amount gets a
clip, and where the clips are stored.

## Guides and records

| File | What |
| --- | --- |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Deploying, and how the readback audio works |
| [`docs/REAL_DEVICE_TEST.md`](docs/REAL_DEVICE_TEST.md) | Testing passkeys on a real phone, and the results so far |
| [`docs/PRD_DEVIATIONS.md`](docs/PRD_DEVIATIONS.md) | Every place the frontend follows the backend instead of the PRD |
| [`docs/TRANSLATION_REVIEW.md`](docs/TRANSLATION_REVIEW.md) | The translations to be checked by native speakers, safety sentences first |
| [`docs/AI_IMPLEMENTATION.md`](docs/AI_IMPLEMENTATION.md) | The speech and language package |

## Status and known limits

- **Languages:** the screens are in English, Pidgin, Yoruba, Hausa and Igbo. The Pidgin, Yoruba, Hausa
  and Igbo translations are **drafts** that no native speaker has checked yet. The backend can speak
  the readback in English and Pidgin only, so Yoruba, Hausa and Igbo customers hear English (with a
  note saying so).
- **Real phone:** the passkey flow has been run once on a real phone through a tunnel and worked. The
  failure cases were tested too. It has **not** yet been recorded with TalkBack or VoiceOver for a
  full payment, so whether the voice and the screen reader ever talk over each other is unverified.
- **Voice:** a clip is rendered in the background when an agent creates a request (this spends
  text-to-speech credits). If it is late or the provider fails, the screen reader reads the text.
- **Not built:** QR scanning from the customer's camera (the agent's screen shows the QR; the customer
  types the code), a service worker (the manifest and icons exist, offline use does not), voice
  transfer, "ask for more time", and Card Guard. Those are Phase 2 and 3 and the frontend only builds
  them when the backend endpoint exists.
- **One open mismatch:** the backend returns the payee's name in two cases ("Bisi Ventures" on the
  readback, "BISI VENTURES" elsewhere). The frontend shows what each call returns.

## Conventions

Conventional commits (`feat(frontend): ...`, `fix: ...`, plus `a11y:`). Keys and `.env` files are never
committed. The API contract is [`backend/openapi.json`](backend/openapi.json); the frontend generates
its types from it and CI fails if they drift.
