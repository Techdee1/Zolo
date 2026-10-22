# Security

Zolo is a **demo** for a hackathon: mock login, a mock bank, a demo console. Do not connect it to real
accounts. This page describes the controls that exist, how to report a problem, and what is not covered.

## Reporting a vulnerability

Please do not open a public issue. Email the maintainers (see the repository's contact details) with steps to
reproduce. We will acknowledge within a few days. Never include real credentials or personal data.

## Controls in the system

**Payments**
- Approval requires a **WebAuthn passkey signature over the SHA-256 of the exact payment** (amount, payee,
  nonce, expiry). If anything changed after the readback, the hashes differ and nothing is sent.
- Every state change is a single conditional `UPDATE`; no double approval or double payment is possible, and
  random-operation storm tests assert that money is conserved and nothing is paid twice.
- Only the consent module may change request state or call the bank's `transfer` (a test enforces it).
- Requests expire after 2 minutes; per-payment and daily caps apply; `Idempotency-Key` makes creation safe to
  retry.
- A bad signature always returns a bare `SIGNATURE_INVALID`; the reason is logged server-side as a code only.
  A signature counter that goes backwards is always refused.

**Sessions and abuse**
- Sessions are a signed `HttpOnly`, `SameSite=Lax` cookie (12 hours; `Secure` in production). No tokens or
  secrets are ever in client code; `NEXT_PUBLIC_*` values are public by construction.
- Rate limits on login, request creation, claim (5 wrong codes lock the customer for 5 minutes), challenge and
  approve, with `Retry-After`. The limiter is in memory (one process); a shared store is needed for several
  workers.
- Errors are RFC 9457 problem JSON with a code; 5xx responses from the proxy never leak backend text.

**Browser**
- Strict, nonce-based **Content Security Policy** (no `unsafe-inline` or `unsafe-eval` for scripts,
  `connect-src 'self'`, no third-party requests; a test fails if anything leaves the origin).
- HSTS, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Opener-Policy: same-origin`, and a restrictive `Permissions-Policy`.
- The `/api` proxy rejects path tricks (`..`, slashes, empty segments), passes cookies unchanged and never
  buffers responses.
- The app never asks for a PIN, card number or OTP, and has no custom PIN pad.

**Data**
- Logs carry ids, timings and reason codes. They never carry payment details in prose, readback words,
  transcripts or audio. The audio cache stores only Zolo's own synthesised sentences, named by hash.
- Secrets live in environment variables (`backend/.env`, `deploy/.env`, Render's environment); both `.env`
  files are gitignored and examples contain no values.

**Phone-call approval (optional, `FEATURE_PHONE_CALL`, off by default)**
- A lower-assurance channel: a four digit Zolo PIN typed on a call, after the readback, never a voice alone.
  Capped at ₦20,000 per payment, one PIN try per call, locked after 3 wrong tries, slowed after a number
  change. Only the consent module can approve; the PIN is a salted hash and never appears in logs or the
  audit trail. In this build the call is simulated in the app. Details: `docs/PRD_DEVIATIONS.md`.

**Demo mode**
- Mock login and `/demo/*` exist only when `DEMO_MODE=true`. `/demo/*` needs an `X-Demo-Token` header; ten
  wrong tokens lock the caller out for 5 minutes. The token is typed by the operator and never bundled.

## Not covered (be aware)

- It is a demo: the bank is a mock and login is a fixed code. A production system needs real authentication,
  a real bank integration, a shared rate-limit store, monitoring and a penetration test.
- **Data retention at the speech providers (YarnGPT, Spitch) is unconfirmed.** Make no "no retention" claim.
- Dependencies are pinned by lockfiles; there is no automated vulnerability scanning in CI yet.
- Passkeys are verified with the `webauthn` library; this project has not had an independent security review.
