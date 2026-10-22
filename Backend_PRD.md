# Zolo Backend PRD

Oct 21, 2026 · @Akeem Jr Odebiyi

The backend ships in three phases, each a tagged, deployed release that demos end to end on its own, so a later phase can always fall back to the one before.

## Phases and fallbacks

Phase 1 alone is a complete, winning demo; Phases 2 and 3 add depth but are switchable off, so nothing they add can break Phase 1.

|  | Phase 1: Demo MVP | Phase 2: Full demo | Phase 3: Final-ready |
| --- | --- | --- | --- |
| **Goal** | Agent cash-out end to end, secure, on a real phone | Every flow and failure case judges might ask about | Depth for the final pitch and a credible pilot story |
| **Target** | End of sprint Day 1 | End of sprint Day 2 (feature freeze), for the semi-final | Between semi-final (23 Oct) and final (28 Oct) |
| **Tag** | `v0.1-demo-mvp` | `v0.2-demo` | `v0.3-final` |
| **Consent engine** | Create, claim, readback text, challenge, approve, decline, status, expiry, single use, idempotency | Renew request, resume after network drop | Hardening and load test |
| **Passkeys** | Register and approve, one credential per customer | Multiple devices, revoke | Single active device, new-device cap, alerts, freeze |
| **Bank** | Mock name enquiry and transfer | Failure injection (timeouts, rejects) | Adapter interface spec for Zenith integration |
| **AI** | None required. Readback text from templates; pre-rendered audio for demo amounts | Voice drafts, speech-to-text, live voice output in 5 languages (see AI PRD) | Evaluation results, phone-call voice |
| **Risk** | Hard per-payment and daily caps | Full rule set (new payee, cooling-off, velocity) | Tuned rules, coercion check |
| **Card Guard** | No | Behind a flag, if time | Yes |
| **Phone-call approval** | No | No | Africa's Talking voice, keypad approval |
| **Status updates** | Polling | Server-sent events | Same |
| **Demo endpoints** | Tamper, replay, expire, reset | Network drop, cloned-voice draft, bank failure | Same |

### Fallback rules

1. **Two environments.** `stable` runs the last tag that passed its exit checklist; `next` runs the branch being built. We demo from `stable` unless `next` passes the checklist.
2. **Feature flags default off.** Every Phase 2 and 3 feature sits behind a flag; turning flags off returns Phase 1 behaviour.
3. **AI is never on the critical path.** The agent cash-out needs no AI. If speech or the LLM fails, the demo still runs.
4. **Local copy.** The demo laptop runs the same tag with Docker Compose, reachable over a fixed tunnel domain (see Deployment).
5. **Backup video** of the full flow and failure cases recorded at the end of each phase.

## Architecture and module boundaries

One FastAPI service, split into modules with clear interfaces, so the mock bank and the AI can be swapped without touching the consent engine.

| Module | Owns | Depends on |
| --- | --- | --- |
| `consent` | Payment requests, state machine, intent hashing, readback text, approval verification | `passkeys`, `risk`, `bank`, `audit` |
| `passkeys` | WebAuthn registration and assertion verification, credential storage | `audit` |
| `risk` | Limits, rules, Card Guard windows (Phase 2+) | Database only |
| `bank` | `BankAdapter` interface; `MockBankAdapter` for the hackathon | Nothing (external in production) |
| `agents` | Agent accounts, request creation, codes | `bank` (name enquiry), `consent` |
| `voice` | Bridge to the AI service: speech in, draft request out, readback audio | `ai` package (see AI PRD), `consent` |
| `audit` | Append-only event log | Database only |
| `demo` | Failure injection and reset endpoints, flag-gated | All of the above |

**Rules:** the `consent` module is the only code that changes request state or calls `bank.transfer`. The `voice` module can only call `consent.create_draft`. Modules talk through service functions, never each other's tables.

## Data model

PostgreSQL with Alembic migrations; money is always `BIGINT` kobo, and the database enforces what code could get wrong.

```sql
customers        (id uuid pk, display_name, phone, language, created_at)
bank_accounts    (id uuid pk, customer_id fk null, agent_id fk null, account_number char(10),
                  bank_code, verified_name, created_at)
agents           (id uuid pk, account_id fk, business_name, created_at)

payment_requests (id uuid pk, customer_id fk null,           -- null until claimed
                  initiator text check (initiator in ('agent','customer','ai')),
                  payee_account_id fk, payee_verified_name text not null,
                  amount_kobo bigint not null check (amount_kobo > 0),
                  currency char(3) not null default 'NGN',
                  claim_code char(4), nonce bytea not null unique,
                  intent_hash bytea, idempotency_key uuid not null unique,
                  state text not null, channel text default 'app',
                  created_at, expires_at not null, approved_at, settled_at,
                  bank_reference text, failure_reason text)
-- unique partial index: one live claim_code at a time
-- (claim_code) where state in ('CREATED','READ_BACK')

passkey_credentials (id uuid pk, customer_id fk, credential_id bytea unique,
                     public_key bytea, sign_count bigint, transports text[],
                     device_label, created_at, revoked_at)
webauthn_challenges (id uuid pk, request_id fk null, customer_id fk,
                     challenge bytea, purpose text, expires_at, used_at)

risk_limits      (customer_id pk, per_payment_kobo, daily_kobo, new_payee_kobo,
                  call_channel_kobo)
card_guard_windows (id uuid pk, customer_id fk, card_ref, max_amount_kobo,
                    opens_at, closes_at, used_at)          -- Phase 2+
audit_events     (id bigserial pk, request_id null, customer_id null, event text,
                  actor text, at timestamptz, details jsonb)  -- no audio, no PINs
```

Index `payment_requests(customer_id, created_at desc)` for history and `audit_events(request_id)` for the demo timeline.

## Request state machine

Every state change is a single conditional update, so two clicks, two phones or a retry can never approve or pay twice.

| From | Event | To | Guard |
| --- | --- | --- | --- |
| (none) | agent or customer creates | `CREATED` | Payee name enquiry succeeded; amount within hard caps |
| `CREATED` | customer claims and readback is fetched | `READ_BACK` | Not expired; claim code valid; claimer is a registered customer |
| `READ_BACK` | valid signature | `APPROVED` | Not expired; challenge unused; recomputed hash equals signed hash; risk check passes |
| `READ_BACK` | customer declines | `DECLINED` | None |
| `CREATED`, `READ_BACK` | time passes `expires_at` | `EXPIRED` | Applied lazily on read and refused on write |
| `APPROVED` | transfer sent | `SUBMITTED` | Same transaction marks the challenge used |
| `SUBMITTED` | bank confirms | `SETTLED` | Bank reference stored |
| `SUBMITTED` | bank rejects | `FAILED` | Reason stored; no money moved |

### Concurrency and idempotency

- Transitions use `UPDATE ... SET state = :to WHERE id = :id AND state = :from RETURNING *`. Zero rows returned means someone else got there first: return `409 STATE_CONFLICT`.
- Approve runs in one transaction: lock the request row (`SELECT ... FOR UPDATE`), verify, mark the challenge used, move to `APPROVED`, commit. Then submit the transfer.
- The transfer call carries the request's `idempotency_key`. The mock bank (and any real bank) must return the same result for a repeated key, so a retry after a crash or network drop can't double-debit.
- A small reconciler (Phase 2) retries `APPROVED` or `SUBMITTED` requests older than 10 seconds with the same key.
- Client POSTs accept an `Idempotency-Key` header; repeated keys return the stored response.

## Intent hashing and passkey verification

The passkey signs a hash of the exact request, and approval re-computes that hash from the database row, which is how a changed amount is caught.

### Canonical intent (version 1)

```json
{"v":1,"request_id":"<uuid>","customer_id":"<uuid>",
 "payee_account":"0123456789","payee_bank_code":"057",
 "payee_name":"BISI VENTURES","amount_kobo":1500000,"currency":"NGN",
 "nonce":"<base64url 16 bytes>","expires_at":"2026-10-21T10:02:00Z"}
```

- Serialise with keys sorted, no whitespace (`separators=(",", ":")`), UTF-8, integers only for money, UTC timestamps with a `Z` and whole seconds.
- `intent_hash = SHA-256(canonical_bytes)`; store it on the request when the readback is generated.
- The readback text is built from the same row at the same moment, so what is heard and what is hashed come from one read.

### Approval ceremony

1. `POST /requests/{id}/challenge` returns WebAuthn authentication options with `challenge = intent_hash`, `allowCredentials` = the customer's credentials and `userVerification = "required"`. Store a single-use challenge row.
2. The client calls `navigator.credentials.get` and posts the assertion to `POST /requests/{id}/approve`.
3. The server, in one transaction:
   1. loads and locks the request; rejects if expired, not `READ_BACK`, or the challenge is used;
   2. **recomputes** the canonical intent from the current row and checks `SHA-256 == intent_hash` (otherwise `INTENT_CHANGED`);
   3. verifies the assertion with py\_webauthn `verify_authentication_response` (expected challenge = stored `intent_hash`, expected origin and RP ID from config, `require_user_verification=True`);
   4. checks the sign count (accept 0, which many platform passkeys send; reject a decrease from a non-zero value);
   5. runs the risk check, marks the challenge used, moves to `APPROVED`.

**Tamper demo:** the demo endpoint changes `amount_kobo` after the readback. Step 3.2 then fails because the row no longer matches what was signed, and the API returns `INTENT_CHANGED`. Nothing is sent.

### Registration

py\_webauthn `generate_registration_options` with RP name "Zolo", the customer's UUID as user ID, platform authenticator preferred, resident key preferred, `userVerification = "required"`, attestation `none`. Registration requires a logged-in session (mock bank login plus OTP in Phases 1 and 2).

## API specification

The OpenAPI schema FastAPI generates is the contract; the frontend generates its TypeScript types from it, so any breaking change shows up as a type error.

| Phase | Method and path | Purpose | Key responses |
| --- | --- | --- | --- |
| 1 | `POST /auth/mock-login` | Seeded customer or agent login (phone plus fixed OTP) | Session cookie |
| 1 | `POST /passkeys/register/options`, `POST /passkeys/register/verify` | Create passkey | 201 |
| 1 | `POST /agent/requests` | `{amount_kobo}` from logged-in agent; returns `{id, claim_code, qr_payload, expires_at, payee_name}` | 201, 422 `LIMIT_EXCEEDED` |
| 1 | `POST /requests/claim` | `{claim_code}` or QR payload; binds the request to the customer | 200, 404 `CODE_NOT_FOUND`, 410 `REQUEST_EXPIRED` |
| 1 | `GET /requests/{id}/readback?lang=pcm` | `{text, lang, audio_url?, amount_words, payee_name, amount_kobo, expires_at}`; moves to `READ_BACK` | 200 |
| 1 | `POST /requests/{id}/challenge` | WebAuthn options bound to `intent_hash` | 200 |
| 1 | `POST /requests/{id}/approve` | Assertion; returns final or pending state | 200, 409 `STATE_CONFLICT`, 409 `INTENT_CHANGED`, 401 `SIGNATURE_INVALID`, 410 `REQUEST_EXPIRED`, 409 `ALREADY_USED` |
| 1 | `POST /requests/{id}/decline` | Customer declines | 200 |
| 1 | `GET /requests/{id}` | Current state for agent and customer | 200 |
| 1 | `GET /me/activity` | Last 20 payments with readable lines | 200 |
| 2 | `GET /requests/{id}/events` | Server-sent events for state changes | stream |
| 2 | `POST /requests/{id}/renew` | New expiry and nonce for an expiring request ("Ask for more time") | 200 |
| 2 | `POST /voice/turn` | Audio or text in; transcript, reply text and audio, optional `draft_request_id` out (see AI PRD) | 200 |
| 2 | `POST /requests/draft` | Customer transfer by text: `{payee_ref or account+bank, amount_kobo}` | 201 |
| 2 | `POST /card-guard/windows`, `GET /card-guard` | Open a one-payment window (passkey-signed); status | 201, 200 |
| 3 | `POST /call/requests/{id}` | Trigger a phone-call approval | 202 |
| 3 | `POST /me/freeze` | Emergency freeze | 200 |

**Errors** use RFC 9457 problem JSON: `{type, title, status, code, detail}`, where `code` is one of the uppercase codes above. The frontend maps codes to spoken messages; it never shows raw `detail` to customers.

## Mock bank adapter

The mock behaves like a real bank's name enquiry and transfer services, so swapping in a real adapter later changes one class, not the consent engine.

```python
class BankAdapter(Protocol):
    async def name_enquiry(self, account: str, bank_code: str) -> NameEnquiryResult: ...
    async def transfer(self, *, idempotency_key: UUID, from_account: str,
                       to_account: str, to_bank: str, amount_kobo: int,
                       narration: str) -> TransferResult: ...
    async def card_auth(self, *, card_ref: str, amount_kobo: int,
                        merchant: str) -> CardAuthResult: ...      # Phase 2+
```

- **Seeded accounts:** demo customer, two agents ("Bisi Ventures" and "Mama Chi Stores"), a sister on another bank, and one account whose name differs from what the agent claims (for the wrong-recipient demo).
- **Balances** held in a mock ledger table so transfers really reduce the balance and the demo can show it.
- **Idempotent transfers:** a repeated `idempotency_key` returns the original result.
- **Failure injection (Phase 2):** per-call settings for added latency, timeout, or rejection, toggled by demo endpoints. Default: no failures, 300 to 800 ms realistic latency.
- **Card auth (Phase 2+):** checks the customer's open Card Guard window: within amount and unused means approve and mark used; otherwise decline with a reason.

## Risk engine and Card Guard

Rules are plain, testable functions over the request and recent history; each returns allow, pause (needs extra check) or block, with a reason the app can speak.

| Phase | Rule | Default |
| --- | --- | --- |
| 1 | Per-payment cap | ₦100,000 |
| 1 | Daily total cap | ₦200,000 |
| 2 | First payment to a new payee above a threshold pauses for a cooling-off period | Above ₦20,000; 10 minutes (shortened in demo mode) |
| 2 | Velocity: more than 3 approvals in 10 minutes pauses | 3 per 10 min |
| 2 | Late-night large payment pauses with a yes or no check | 23:00 to 05:00, above ₦50,000 |
| 2 | Phone-call channel cap (Phase 3 channel) | ₦20,000 per payment |
| 3 | New device: CBN cap for the first 24 hours | ₦20,000 |
| 3 | Frozen account blocks everything | n/a |

The customer can lower any cap. Values are config, not code, and shown in the demo console.

### Card Guard (Phase 2 behind a flag, Phase 3 required)

- Card is locked by default. Opening a window needs a passkey signature over `{card_ref, max_amount_kobo, closes_at, nonce}`, using the same hashing approach.
- Window: one payment, up to `max_amount_kobo`, closes after 5 minutes or first use.
- `card_auth` approves only within an open, unused window; everything else declines with `CARD_LOCKED`, `OVER_LIMIT` or `WINDOW_USED`.
- Every card attempt, approved or declined, creates an audit event and a spoken alert for the customer.

## Demo endpoints and seed data

Demo endpoints make every failure case repeatable on stage; they exist only when `DEMO_MODE=true` and require a demo token header.

| Phase | Endpoint | What it does |
| --- | --- | --- |
| 1 | `POST /demo/reset` | Re-seeds customers, agents, balances; clears requests |
| 1 | `POST /demo/requests/{id}/tamper` | Changes the amount after the readback (to trigger `INTENT_CHANGED`) |
| 1 | `POST /demo/requests/{id}/replay` | Re-submits the last valid assertion (to trigger `ALREADY_USED`) |
| 1 | `POST /demo/requests/{id}/expire` | Sets `expires_at` to now |
| 1 | `GET /demo/requests/{id}/timeline` | State changes and audit events for the projector |
| 2 | `POST /demo/bank/fail` | Next transfer times out or is rejected (network-drop and resume demo) |
| 2 | `POST /demo/voice/cloned` | Plays a synthetic-voice request: it drafts but can't approve |
| 2 | `POST /demo/card/swap` | Simulates a stolen card used at a POS (Card Guard decline) |

**Seed script** (`python -m zolo.seed`) creates the same named people, accounts and balances every time, so the script and rehearsals never drift.

## Security, privacy and auth

Even as a demo, it handles money logic like production: secrets out of code, least data kept, everything audited.

- **Sessions:** signed, httpOnly, Secure, SameSite=Lax cookies; short-lived (12 hours); separate roles for customer, agent and demo.
- **CORS:** only the frontend origins; credentials allowed only for them.
- **Rate limits:** claim-code attempts (5 per minute per session, to stop code guessing), approve attempts, login.
- **Claim codes:** 4 digits, live for 2 minutes, unique among live requests, locked after 5 wrong tries.
- **Secrets:** environment variables only (`DATABASE_URL`, `SESSION_SECRET`, `RP_ID`, `ORIGIN`, AI keys). Never committed; `.env.example` lists them.
- **Logging:** structured JSON with request IDs; no names, account numbers, amounts or audio in logs (use IDs).
- **Audit:** every state change and security event in `audit_events`; append-only.
- **Headers:** HSTS, no-sniff, frame-deny on the API.
- **Privacy (NDPA):** voice audio is processed and discarded, never stored; transcripts kept only on the draft request, deleted after 24 hours in demo mode.
- **Phase 3:** single active device, new-device alerts, freeze endpoint, dependency audit (`pip-audit`), security checklist review.

## Engineering practice

The consent and passkey code is tested hardest, because a bug there moves money; everything else is tested enough to demo safely.

### Repo layout

```
backend/
  zolo/
    api/          routers per module, dependencies, error handlers
    consent/      models, service, state machine, hashing, readback text
    passkeys/     webauthn service
    risk/         rules, card guard
    bank/         adapter protocol, mock adapter, mock ledger
    agents/       agent service
    voice/        bridge to ai/ (Phase 2)
    audit/        event writer
    demo/         flag-gated endpoints, seed
    core/         config (pydantic-settings), db, logging, security
  migrations/     alembic
  tests/          unit, integration, api
  pyproject.toml  uv, ruff, mypy, pytest
  Dockerfile, docker-compose.yml (api + postgres)
```

### Tooling and workflow

- Python 3.12, FastAPI, SQLAlchemy 2 (async) with asyncpg, Pydantic v2, Alembic, py\_webauthn, uv for dependencies.
- ruff (lint and format) and mypy `--strict` on `consent`, `passkeys`, `risk`, `bank`.
- Conventional commits, short-lived branches, one reviewer per PR; tags per phase.
- CI (GitHub Actions): ruff, mypy, pytest against a Postgres service container, OpenAPI schema export (fails if the schema changes without the frontend types being regenerated).

### Testing

- **Unit:** canonical serialisation (golden fixtures), hash changes when any field changes, state transitions (allowed and refused), each risk rule, Card Guard window logic.
- **Property tests (Hypothesis):** any change to amount, payee or expiry changes the hash; amounts stay integers.
- **Integration:** full approve flow with a software WebAuthn authenticator (generate a test keypair and sign assertions in tests); concurrent double-approve returns one success and one `STATE_CONFLICT`; transfer retry with the same key doesn't double-debit.
- **API:** every failure case in the team brief as a test.
- **Coverage target:** 90% on `consent` and `passkeys`; no target elsewhere.

## Deployment and demo operations

Passkeys are tied to a domain, so the demo must always run on the same domain the passkeys were created on, including the local fallback.

- **Hosting:** API on a container host with HTTPS (e.g. Render, Railway or Fly.io) plus managed Postgres. Frontend on Vercel.
- **Domains:** frontend `app.<our-domain>`, API `api.<our-domain>`. `RP_ID` = `<our-domain>` so passkeys work across both.
- **Passkey domain trap:** a passkey made on the hosted domain will not work on `localhost` or a different tunnel URL. For the local fallback, point the same domain at the laptop (a fixed tunnel such as Cloudflare Tunnel on a subdomain under the same `RP_ID`), or register a separate demo passkey for the fallback domain in advance and test it.
- **Environments:** `stable` (last passed tag, used for demos) and `next` (current work). Promote by redeploying a tag, never by hot-fixing `stable`.
- **Health:** `GET /healthz` (process up) and `GET /readyz` (database reachable, seed present). Check both before going on stage.
- **Before the slot:** run `POST /demo/reset`, run the scripted happy path once, confirm the backup video plays offline.

## Phase exit checklists

A phase is done only when every box is ticked on the deployed `next` environment; then it is tagged and promoted to `stable`.

**Phase 1: Demo MVP**

- [ ] Agent creates ₦15,000 request; customer claims by code on a real phone; readback text correct; passkey approves; agent sees Paid; mock balance moves.
- [ ] Decline, expire, tamper (`INTENT_CHANGED`) and replay (`ALREADY_USED`) all return the right codes and move no money.
- [ ] Concurrent double-approve test passes.
- [ ] Seed and reset work; health checks green; CI green.
- [ ] Tagged `v0.1-demo-mvp`, deployed to `stable`, backup video recorded.

**Phase 2: Full demo**

- [ ] Voice transfer creates a draft through the AI module and reaches the same approve flow.
- [ ] SSE status works; polling still works as fallback.
- [ ] Network-drop demo resumes with no double debit; renew works.
- [ ] Risk rules active with demo-friendly timings.
- [ ] With all Phase 2 flags off, the Phase 1 checklist still passes.
- [ ] Tagged `v0.2-demo`, backup video updated.

**Phase 3: Final-ready**

- [ ] Card Guard: open, pay within limit, decline over limit and second attempt, relock.
- [ ] Phone-call approval works end to end with a real phone.
- [ ] Single active device, new-device cap, freeze.
- [ ] Security checklist and dependency audit done.
- [ ] Bank adapter interface written up for Zenith (what we'd need from them).
- [ ] Tagged `v0.3-final`.
