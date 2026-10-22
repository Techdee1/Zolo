# Design decisions

Each entry: the decision, why, and what it costs. Newest decisions are not special; the order follows the
build.

## D1. The browser only talks to the web app
**Decision.** The web app proxies `/api/*` to the backend (a streaming route handler). **Why.** One origin
means a first-party `HttpOnly` cookie, no CORS, a CSP of `connect-src 'self'`, and passkeys bound to a single
domain. **Cost.** The passkey RP ID is the *web* domain, so a passkey from a tunnel or localhost does not
carry over. A rewrite was tried first and dropped because Next's gzip middleware buffers streams.

## D2. The passkey signs a hash of the exact payment
**Decision.** The WebAuthn challenge is the SHA-256 of a canonical intent (amount, payee, nonce, expiry...).
**Why.** A signature then covers exactly what was read back; if anything changes the hashes differ and
nothing is sent (`INTENT_CHANGED`). **Cost.** The canonical bytes are frozen (golden fixtures); changing
them needs a version bump.

## D3. One conditional UPDATE per state change
**Decision.** Every transition is `UPDATE ... WHERE state = :from`. **Why.** Double taps, two phones and
retries cannot approve or pay twice; the second caller gets `STATE_CONFLICT`. **Cost.** Callers must treat
conflict as a normal answer.

## D4. SUBMITTED is a first-class state, never "Paid"
**Decision.** If the customer approved but the bank has not confirmed, both screens say "Processing. Don't
hand over goods yet." and keep polling. **Why.** Telling an agent "Paid" early is the costliest possible
error. The PRD had no such state; the backend does.

## D5. Only the consent module may change state or call `transfer`
**Decision.** Enforced by a test that scans imports. **Why.** A bug elsewhere (including the AI package)
cannot move money. **Cost.** More plumbing through the consent service.

## D6. The backend wins over the PRD
**Decision.** Where they disagree the frontend follows the backend and the difference is a row in
[`PRD_DEVIATIONS.md`](PRD_DEVIATIONS.md). **Why.** The contract is the running system, and the log keeps the
disagreement visible instead of buried.

## D7. Typed contract, runtime-checked
**Decision.** TypeScript types are generated from `openapi.json`; Zod schemas validate every response and
must stay equal to the generated types (compile-time assertions); CI fails if types are stale. **Why.** The
screen that states an amount must never render a malformed one. A response that fails validation is refused.

## D8. Money is integer kobo, end to end
**Decision.** No floats anywhere in money paths; a lint rule bans float tools in the formatting code; amounts
are formatted with BigInt. **Why.** Floats and money do not mix, and the amount in words must match the
backend's 700+ checked cases.

## D9. Accessibility is a requirement with tests, not a polish pass
**Decision.** WCAG 2.2 AA; axe must report **zero violations of any impact** in light, dark, reduced motion
and more contrast on every screen; the strict `jsx-a11y` rules are errors; 48px targets; focus to the h1 on
route change. **Specific choices:**
- *Zolo's voice and the screen reader never talk at once:* announcements are held while audio plays, then
  focus moves to the readback. A "screen reader only" mode exists.
- *Approve is `aria-disabled`, not disabled,* so it stays focusable and says why.
- *Amounts:* digits are `aria-hidden` and the words are real text (ARIA forbids a label on a span).
- *No custom PIN pad anywhere.* The only numeric entry is a native `inputmode="numeric"` field for a code
  that is not a secret, and an amount keypad for the agent.

## D10. Strict CSP with per-request nonces, so every route renders per request
**Decision.** `await connection()` in the root layout; `cacheComponents` and `partialPrefetching` off.
**Why.** A nonce must be fresh on each response (a prerendered page has none and its scripts are blocked),
and a hidden-route cache could restore an old review screen with an old amount. **Cost.** No static HTML
caching; the pages are thin.

## D11. Springs, only transform and opacity, interruptible
**Decision.** Motion follows Apple's damping/response model; only `transform` and `opacity` animate; reduced
motion becomes a short fade. Press feedback is instant on pointer-down with a small spring on release.
**Why.** Predictable, cheap on low-end phones, and respectful of vestibular settings.

## D12. Language by cookie, not URL
**Decision.** Five languages with next-intl, chosen by a cookie then `Accept-Language`, no locale in the path.
**Why.** Direct links and the PWA `start_url` stay stable. Strings are in message files, a missing string
falls back to English, and tests check key and placeholder parity.

## D13. Voice is rendered when the request is created, looked up when it is read back
**Decision.** Background render at creation; readback only looks up (plus a short wait for an in-flight
clip); a shipped clip set covers demo amounts. **Why.** Synthesis is too slow for the approval path, yet any
amount should be able to have a voice. Failure degrades to text.

## D14. Demo mode is explicit and guarded
**Decision.** Mock login and `/demo/*` exist only when `DEMO_MODE=true`; `/demo/*` also needs an
`X-Demo-Token` header (header only, wrong tokens are counted and locked out). The operator types the token
into the page; it is never in the JavaScript bundle. **Why.** A stage needs repeatable failures, a public
deployment must not hand them to strangers.

## D15. Landing page is plain HTML
**Decision.** Server component, no client JavaScript of its own, CSS-only scroll reveal, English only,
self-hosted serif for headings. **Why.** It must work with scripts off, load fast (Lighthouse 97 to 98 on
mobile at the time of writing), and make no unsupported claims.
