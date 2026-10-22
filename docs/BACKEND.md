# Backend

FastAPI + SQLAlchemy 2 (async) + Postgres, Python 3.12, `uv` for dependencies, Alembic for migrations.
Start with [`ARCHITECTURE.md`](ARCHITECTURE.md); this page is the practical guide.

## API (the contract is [`backend/openapi.json`](../backend/openapi.json))

| Endpoint | Who | Does |
| --- | --- | --- |
| `POST /auth/mock-login` | anyone (demo) | Fixed-OTP login, sets the session cookie |
| `POST /agent/requests` | agent | Create a request (idempotent with `Idempotency-Key`); returns code, QR payload, expiry |
| `POST /requests/claim` | customer | Link a request by code or QR payload |
| `GET /requests/{id}` | owner | Current state (polled by both screens) |
| `GET /requests/{id}/readback?lang=` | customer | Readback text and `audio_url`; moves the request to `READ_BACK`. `lang` is `en pcm yo ha ig` |
| `POST /requests/{id}/challenge` | customer | WebAuthn options whose challenge is the intent hash |
| `POST /requests/{id}/approve` | customer | Verify the assertion; returns `SETTLED`, `SUBMITTED` or `FAILED` |
| `POST /requests/{id}/decline` | customer | Decline; nothing moves |
| `POST /passkeys/register/options`, `.../verify` | customer | Register a passkey (replaces a previous one) |
| `GET /me/activity` | customer | Last 20 payments |
| `GET /voice/audio/{key}.mp3` | anyone with the key | Readback audio from the cache |
| `GET /healthz`, `/readyz` | anyone | Liveness, readiness |
| `/demo/*` | demo token | reset, tamper, replay, expire, timeline (only when `DEMO_MODE=true`) |

Errors are RFC 9457 problem JSON with an uppercase `code` (`INTENT_CHANGED`, `REQUEST_EXPIRED`, `NO_PASSKEY`,
`LIMIT_EXCEEDED`, `ALREADY_USED`, `RATE_LIMITED`, ...). A readback never returns 422 for Yoruba, Hausa or Igbo:
it falls back to English and sets `fallback_from`.

## Run

```bash
cd backend
docker compose up -d postgres
cp .env.example .env              # SESSION_SECRET (32+ chars); DEMO_MODE=true needs DEMO_TOKEN
uv sync && uv run alembic upgrade head && uv run python -m zolo.seed
uv run uvicorn zolo.api.main:create_app --factory --port 8000
uv run pytest                     # needs Postgres
```

## Configuration (`.env.example` lists all)

Required: `DATABASE_URL` (Postgres; plain `postgres://` is upgraded to asyncpg), `SESSION_SECRET`. Passkeys:
`RP_ID`, `ORIGIN`, `COOKIE_SECURE`, `TRUST_FORWARDED_FOR`. Voice: `AUDIO_PRERENDER_ON_CREATE`,
`AUDIO_PRERENDER_LANGS`, `AUDIO_CACHE_DIR`, `YARNGPT_API_KEY`, `TTS_VOICE_<LANG>`. Demo: `DEMO_MODE`,
`DEMO_TOKEN`. Phase 2 and 3 flags exist and default off.

## Tools (`backend/zolo/tools`)

`render_clips` (build and export the voice clip set), `check_coverage` (the coverage gate),
`real_device` (start everything for a phone test behind a tunnel). `scripts/mutation_sweep.py` runs the
mutation check.
