# Handoff: where Zolo stands and how we got here

Written 2026-10-22 for the next person or agent. Read this first, then `README.md`.
Everything described here is committed on `main` and `frontend-phase-1` (same commit) unless it says otherwise.

## What Zolo is

A consent layer for Zenith Bank (Zecathon 6.0, Track 7) for blind and low-vision customers paying at an
agent or POS: the customer **hears** who is asking and how much, then approves with a **passkey**.
Nothing is sent without approval, requests expire after 2 minutes, voice alone can never approve.
It is a **demo**: mock login (fixed code), mock bank, a demo console. Not for real money.

## The pieces

| Path | What |
| --- | --- |
| `backend/` | FastAPI + Postgres. Consent state machine, WebAuthn, mock bank, readback text and audio, demo endpoints. Contract: `backend/openapi.json` (the frontend generates its types from it; CI fails if stale) |
| `frontend/` | Next.js 16 app: landing page (`/`), customer app (`/home`, `/pay/code`, `/requests/[id]`, `/setup/passkey`), agent (`/agent`), demo console (`/demo`), five languages |
| `deploy/`, `render.yaml`, `render.free.yaml` | Compose + Caddy for one machine; Render Blueprints (paid and free) |
| `docs/` | `DEPLOY.md`, `REAL_DEVICE_TEST.md`, `PRD_DEVIATIONS.md`, `AI_IMPLEMENTATION.md`, this file |
| PRDs at the root | `Backend_PRD.md`, `Frontend_PRD.md`, `AI_PRD.md`, `Engineering_Brief.md` |

## Rules we work by

- **Backend wins over the PRD.** Every difference is a row in `docs/PRD_DEVIATIONS.md`. Add a row for any new one.
- **Accessibility is the product.** WCAG 2.2 AA, 48px targets, focus to the h1 on route change, amounts spoken in words, one polite live region, Zolo's voice and the screen reader never talk at once, Approve disabled until the readback is heard, no custom PIN pads, never ask for a PIN or card number. axe must report **zero violations** in light, dark and reduced motion.
- **Money is integer kobo end to end.** No floats (a lint rule enforces it in `frontend/lib/format/`).
- **Red is only the primary button and tiny accents.** Never colour alone.
- **Strict CSP** (nonce, `connect-src 'self'`); every route renders per request (`await connection()`).
- **Commits:** conventional (`feat(frontend): ...`, `fix: ...`, plus `a11y:`), with only the author's name (no co-author or tool attribution lines, the owner's standing rule). Keys and `.env` files are never committed.
- Report honestly: say what was tested and what was not.

## How it was built (the seven steps, all done)

1. Scaffold (Next, Tailwind, TS strict, ESLint with strict jsx-a11y, Vitest, Playwright + axe, CI).
2. Design tokens (`frontend/styles/tokens.css`, tested for contrast).
3. UI kit + `/kitchen-sink` (Button, AmountDisplay, Keypad, Badge, TimeLeft, Sheet, LiveRegion).
4. Typed API client: generated types + Zod schemas that must stay equal to them (`lib/api/`), one fake backend (`frontend/tests/fakes/fake-backend.ts`) used by MSW and the e2e server.
5. P0 screens, then a polish pass (Apple-style: hero amount, sticky translucent action bar, role tint, demo menu).
6. Passkeys against the **real backend** with Chromium's virtual authenticator (`pnpm e2e:real`), and once on a **real phone** through a tunnel (worked; see `docs/REAL_DEVICE_TEST.md`).
7. Five languages with next-intl (en, pcm, yo, ha, ig), cookie + Accept-Language, no locale in the URL.

Later additions: landing page + PWA manifest (`start_url=/home`), voice for any amount, deployment files,
readbacks in yo/ha/ig with English fallback, the clip set.

## The voice, in one paragraph

The backend builds the readback sentence and serves audio by `GET /voice/audio/{key}.mp3`, where the key is
a hash of provider, language, voice and exact words. The readback endpoint **only looks clips up**
(rendering takes 3 to 7 s). With `AUDIO_PRERENDER_ON_CREATE=true` the backend renders English and Pidgin in
the background when an agent creates a request (`AUDIO_PRERENDER_LANGS` adds more). `?lang=` accepts
`en|pcm|yo|ha|ig`; yo/ha/ig come back in that language only if the exact clip exists, otherwise the English
readback with `fallback_from` set (never an error). The frontend shows "spoken request is in English for
now" only when `fallback_from` is set. A clip set is shipped in `backend/audio_seed/` and copied onto the
audio disk at container start. Details: `docs/DEPLOY.md`.

## State right now

- **Tests (last run):** backend 950 passed (coverage gate 90% on `consent` and `passkeys` met); frontend unit 378; e2e 165 passed 2 skipped; real-backend e2e 10; CI green on `main`.
- **Clip set: 110 of 162 shipped** (en 53, pcm 48, yo 3, ha 3, ig 3). 52 are missing because YarnGPT returned `tts_RATE_LIMITED` after 55 clips and had not cleared 40+ minutes later. To finish, from `backend/`:
  `uv run python -m zolo.tools.render_clips` (resumes, waits out rate limits, stops on quota), then
  `uv run python -m zolo.tools.render_clips --export audio_seed`, commit, push. `--dry-run` shows counts and voices.
- **Voices:** `idera` primary for all five languages, `jude` backup for en and pcm (switch with `TTS_VOICE_EN=jude`, `TTS_VOICE_PCM=jude`). Chosen from descriptions only; nobody has listened.

## Not done / open (in rough priority order)

1. **Deploy.** Nothing is deployed. `render.yaml` (paid: private API + disk) and `render.free.yaml` (free: sleeps, no disk) exist and are validated but **never run on Render**. Steps in `docs/DEPLOY.md`. Passkeys are bound to the web app's public address, so set `RP_ID`, `ORIGIN`, `CORS_ORIGINS` to it, then redo the phone run on that address.
2. **Finish the 52 clips** (above).
3. **TalkBack / VoiceOver:** one TalkBack pass was done informally; nobody checked whether Zolo's voice and the screen reader ever talk over each other, or where focus lands after the audio. The "heard" gate in screen-reader-only mode is a 2-second guess (`frontend/lib/use-readback-voice.ts`).
4. **Pidgin has not been natively reviewed.** Yoruba, Hausa and Igbo wording (UI and readback templates) was reported approved by native speakers on 2026-10-22; the yo/ha/ig readback templates have no tone marks, so voice pronunciation may suffer.
5. **Fixed status clips** (paid, declined, expired, processing) are rendered but **nothing plays them** (no endpoint). "Approved" and "request intro" have no approved yo/ha/ig wording.
6. Not built: QR scanning from the customer's camera, a service worker (manifest and icons exist), the 170 KB bundle-size measurement, voice transfer, "ask for more time", Card Guard (Phase 2/3: build behind flags only when the endpoint exists in `openapi.json`).
7. The owner said to ignore: the photo credit on `street.jpg` and the payee name case difference ("Bisi Ventures" on the readback, "BISI VENTURES" elsewhere).

## Run it

Backend: `cd backend && docker compose up -d postgres && uv sync && uv run alembic upgrade head && uv run python -m zolo.seed && uv run uvicorn zolo.api.main:create_app --factory --port 8000` (needs `.env`: `SESSION_SECRET` 32+ chars, `DEMO_MODE=true`, `DEMO_TOKEN`). Frontend: `cd frontend && pnpm install && pnpm dev`. Secrets live in `backend/.env` (gitignored; holds the YarnGPT and Spitch keys) and `deploy/.env` (gitignored).

Tests: `cd backend && uv run pytest`; `cd frontend && pnpm check`; `pnpm build:e2e && pnpm e2e`; `pnpm e2e:real` (needs Postgres; uses its own `zolo_e2e` database and ports 3300/3301).

Fake backend for UI work: `pnpm exec tsx tests/e2e/fake-api.ts` (port 3101) with `BACKEND_URL=http://localhost:3101`. Controls: `POST /__fake/outcome/SUBMITTED`, `/__fake/settle/<id>`, `/__fake/audio/on`, `/__fake/native/on`, `/__fake/reset`.

Real phone: Cloudflare quick tunnel to the frontend (`cloudflared tunnel --url http://localhost:3300`), restart the backend with `RP_ID=<host>`, `ORIGIN=https://<host>`, `COOKIE_SECURE=true`, `TRUST_FORWARDED_FOR=true`. See `docs/REAL_DEVICE_TEST.md`.

## Gotchas that cost time

- **`pkill -f` / `ps | grep` of a pattern that appears in your own command kills your own shell** (exit 144). Use a script file, or `grep "[p]attern"`.
- **`next start` caches the `public/` file list at startup:** a file added later returns 404 until restart. A stale `next dev` server also serves stale CSS: use the production build for screenshots.
- **Containers cannot reach each other on Codespaces' Docker network** (TCP times out). `deploy/compose.yml` is fine on a normal server; in Codespaces test images with `--network host`.
- **Playwright treats `aria-disabled` as disabled:** use `click({ force: true })` to test an inactive Approve. A live region duplicates text in the DOM: scope text assertions to `main`.
- **axe reads colours mid-animation as low contrast:** wait for settle-in animations before scanning (see `flow.spec.ts`).
- **pnpm blocks install scripts** (`ERR_PNPM_IGNORED_BUILDS` in CI): every new dependency with a build script needs an entry in `frontend/pnpm-workspace.yaml` `allowBuilds`.
- **Next.js here is a newer version than most training data:** read `frontend/node_modules/next/dist/docs/` before relying on memory (see `frontend/AGENTS.md`).
- **Postgres in Codespaces can stop:** `cd backend && docker compose up -d postgres` before running backend tests (otherwise hundreds of errors, not failures).
- **YarnGPT:** no balance endpoint; `QUOTA_EXCEEDED` means credits, `RATE_LIMITED` means too fast or an hourly cap.
- The conversation history for this work is in the Claude Code transcript under `~/.claude/projects/-workspaces-Zolo/` (lost if the Codespace is deleted); this file and `PRD_DEVIATIONS.md` are the durable record.
