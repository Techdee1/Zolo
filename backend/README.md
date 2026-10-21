# Zolo backend: AI and speech package (`zolo/ai`)

Phase 1 (Voice MVP): no language model. The AI only proposes: its single write is
`create_draft`, and it never approves, executes, or writes the readback a customer approves.

## API (Phase 1)

The HTTP API is the contract in `openapi.json` (regenerate with
`uv run python -m zolo.api.export_openapi > openapi.json`; CI fails if it is stale and the
frontend generates its types from it). Errors are RFC 9457 problem JSON with an uppercase `code`.

- **Sessions:** a signed, `HttpOnly`, `SameSite=Lax` cookie (12 hours). Customers and agents log in
  with `POST /auth/mock-login` (phone plus the fixed OTP). That route and `/dev/passkey-test`
  exist **only when `DEMO_MODE=true`** (which also needs a `DEMO_TOKEN` of 8+ characters).
- **Rate limits** (in memory, one process): login, request creation, claim (5 a minute, and 5
  wrong codes lock the customer for 5 minutes), challenge and approve. `429` carries `Retry-After`.
- **Passkeys:** `WEBAUTHN_STRICT_COUNTER` (default `true`) refuses a repeated non-zero counter;
  `false` is for the demo and logs a warning. A counter that goes backwards is always refused.
  A bad signature is always a bare `SIGNATURE_INVALID`; the reason is logged server-side only.
- **Real phone:** see `../docs/REAL_DEVICE_TEST.md` (not yet run on a phone).

## Demo console (`DEMO_MODE=true` only)

Five endpoints make every failure repeatable on stage. They are mounted only in demo mode, each
needs the `X-Demo-Token` header (header only; ten wrong tokens lock the caller out for 5 minutes),
and they go through the consent service, never straight to a table:

| Endpoint | Does |
| --- | --- |
| `POST /demo/reset` | Re-seeds people, accounts and balances; clears requests, audit and transfers. **Keeps registered passkeys.** |
| `POST /demo/requests/{id}/tamper` | Changes the amount after the readback (default ₦51,000): approval then returns `INTENT_CHANGED`. |
| `POST /demo/requests/{id}/replay` | Re-sends the last accepted approval: `409 ALREADY_USED`, no second payment. |
| `POST /demo/requests/{id}/expire` | Sets `expires_at` to now; the next action gets `410 REQUEST_EXPIRED`. |
| `GET /demo/requests/{id}/timeline` | Audit events in order, for the projector (includes internal reason codes, so demo only). |

Phase 2 demo endpoints (bank failure, cloned voice, card swap) are not built.

## Run

```
python3 -m venv .venv && .venv/bin/pip install httpx spitch imageio-ffmpeg pytest mypy ruff
# (packaging via pip install -e is not set up yet; run from this directory)
cp .env.example .env        # then fill SPITCH_API_KEY and YARNGPT_API_KEY (never commit .env)
.venv/bin/pytest            # offline: fakes only, never calls Spitch or YarnGPT
.venv/bin/mypy zolo
```

Production images need `ffmpeg` installed; locally the bundled `imageio-ffmpeg` binary is used.

## Tools (cost credits, run by hand)

- `python -m zolo.ai.tools.prerender_demo [--dry-run]`: render every demo/reply line into the audio cache (YarnGPT). Skips cached lines.
- `python -m zolo.ai.tools.pidgin_listening_test [--voices idera,jude]`: Pidgin readbacks as mp3 in `var/listening/` for a native-speaker listening test.
- `python -m zolo.ai.tools.stt_smoke --live`: one Spitch call per language on cached clips; transcripts cached in `var/stt_cache.json`.

## Flags (see `.env.example`)

`STT_LIVE_ENABLED` (default false), `TTS_LIVE_ENABLED`, `ALLOW_TEXT_INPUT` (dev: typed text skips STT),
`AI_AGENT_ENABLED` (Phase 2, not built), `TTS_PROVIDER_<LANG>`, `TTS_VOICE_<LANG>`.

## Data handling: unconfirmed

- **Spitch** audio retention terms are **not confirmed**. The SDK sends `X-Data-Retention: True` by default; we send `False`, but we have not verified that Spitch honours it.
- **YarnGPT** retention of synthesised audio is **not stated** in its docs. Text sent to it is readback text (payee name and amount).
- Do not claim "no retention" to customers, judges or the NDPA notice until both are confirmed in writing.
- This package never logs transcripts, replies or audio, and never stores audio. The audio cache holds only synthesised readbacks, named by hash.

## Backend contract (`zolo/ai/contracts.py`)

The backend implements the `DraftService` Protocol and passes it to `VoiceService`. It is the only
way the AI touches the system: two reads and one write, and no approve, execute, cancel or
limit-changing method exists.

```python
class DraftService(Protocol):
    def create_draft(self, customer_id: str, recipient_ref: str, amount_kobo: int) -> str: ...
    def get_balance(self, customer_id: str) -> int: ...  # kobo
    def list_saved_recipients(self, customer_id: str) -> list[SavedRecipient]: ...
```

- `create_draft` stores a DRAFT request and returns its request id. `recipient_ref` is the id of a
  saved recipient; `amount_kobo` is a positive integer. Reject anything else (the AI validates, but
  the backend must not rely on it). The AI never sees the stored record.
- `list_saved_recipients` returns `SavedRecipient(id, display_name, bank, last4, aliases)`. Never
  full account numbers.
- `zolo.ai.fakes.FakeBackend` is an in-memory implementation for tests and local runs.

```python
VoiceService(stt, RoutingTTS(settings), settings, backend)  # then .voice_turn(...)
```

## Readback audio (`zolo/ai/tts/readback.py`)

Live YarnGPT takes 4-7 seconds, so `ReadbackService.get(text, lang)` never waits for it:
cached audio returns `status="ready"` with `audio_url`; otherwise it returns the text at once
(`status="rendering"`) and renders in the background to fill the cache (one render per line at a
time; a failed line is not retried for 60 seconds). English responses carry
`device_speech_after_s` (2.0 while rendering, 0.0 if no render is running) telling the client to
speak the text with on-device speech if audio is not ready; other languages get text for the
screen reader. Serve `/voice/audio/{key}.mp3` from `AudioCache.get`.

## Other notes

- Amounts are confusable **by value**: 15,000 and 50,000 are flagged in words and in digits.
- Yoruba amounts (`nlu/yoruba.py`): common forms up to 500,000, unreviewed by a native speaker.
- Recipient matching copes with letter-by-letter and sound-alike transcripts; a match that rests on
  sound alone is returned as "ambiguous" (confirm), never as a confident match. Score it with
  `python -m zolo.ai.tools.name_match_report`.
- `python -m zolo.ai.tools.prerender_scenarios` renders extra demo variants from `readbacks/scenarios.json`.

## Known gaps

- Pidgin, Yoruba, Hausa and Igbo wording (`readbacks/*.txt`, `replies.json`) is unreviewed and must be checked by native speakers.
- Yoruba/Hausa/Igbo grammar verbs and number words are not implemented (Phase 3). Spitch returns Yoruba amounts in Yoruba words, which the parser deliberately does not read.
