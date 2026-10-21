# Where the frontend differs from the Frontend PRD

The Frontend PRD was written before the backend existed. Where it disagrees with the backend as
built (Phase 1, `backend/openapi.json`), **the frontend follows the backend**, and the difference is
listed here. Every row says what the PRD asked for, what exists, and what the frontend does.

Living document: add a row whenever a new difference is found or one is resolved.

## 1. Endpoints and behaviour (the backend wins)

| # | PRD says | Backend actually has | Frontend does |
| --- | --- | --- | --- |
| 1 | `GET /requests/{id}/status` | `GET /requests/{id}` | Uses `GET /requests/{id}`. |
| 2 | `POST /passkeys/register` | `POST /passkeys/register/options`, then `POST /passkeys/register/verify` | Two calls, via `@simplewebauthn/browser`. `verify` returns 201. |
| 3 | Live status over server-sent events, polling as fallback | Polling only. SSE is Phase 2. | Polls every 1 s. The `/api` proxy already streams without buffering (tested), so SSE can be added when the backend has it. |
| 4 | `/agent/setup`: agent account setup (P0) | No such endpoint. Agents are seeded, and login is the demo-mode `POST /auth/mock-login`. | No setup screen. Replaced by a simple **demo sign-in chooser** (pick the customer or an agent, enter the fixed code). |
| 5 | `POST /requests/{id}/approve` takes "an assertion" | The body **is** the assertion JSON (`PublicKeyCredential`), no wrapper. | Posts the `@simplewebauthn/browser` result as-is. |
| 6 | "Ask for more time" (`renew`) on the review screen | Not built. `POST /requests/{id}/renew` is Phase 2. | Not shown. Behind a feature flag, off, and only built once the endpoint is in `openapi.json`. |
| 7 | Voice transfer `/send` and `POST /requests/draft` (P0) | Not built. Voice turn and drafts are Phase 2. | Not shown. Behind a feature flag, off, until the endpoint is in `openapi.json`. No disabled "coming soon" controls anywhere. |
| 8 | Demo console: tamper, replay, **drop network**, expire, **cloned-voice draft**, timeline | Only `reset`, `tamper`, `replay`, `expire`, `timeline`. Network drop and cloned voice are Phase 2. | The console shows only those five actions. |
| 9 | Card Guard `/card` (P1) | Not built (Phase 3). | Not shown. Flag off (`NEXT_PUBLIC_FEATURE_CARD_GUARD`). |
| 10 | Readbacks in five languages | The readback endpoint accepts only `en` and `pcm`; anything else is **422**. | The UI is translated into all five languages, but the readback is requested as `pcm` for Pidgin and `en` for everything else. When the customer's language is Yoruba, Hausa or Igbo, a short on-screen note says the spoken readback is in English for now. The frontend never requests an unsupported readback language. |
| 11 | Result states: Paid, Declined, Expired, Changed, Failed | There is a sixth, `SUBMITTED`: the customer approved but the bank call did not finish (for example the network dropped). Phase 1 has no automatic retry, so it can persist. | A calm **"Processing. Don't hand over goods yet."** screen. It never says "Paid", keeps polling, and is announced to screen readers. The agent's view shows the same message. |

## 2. Architecture

| # | PRD says | Decision | Why |
| --- | --- | --- | --- |
| 12 | The frontend calls the API directly (the PRD's `lib/api` calls the backend host) | The browser only talks to the frontend's own origin. `/api/*` is proxied to the backend by a route handler. `BACKEND_URL` is a server-side variable, read at runtime. | The session cookie is first-party (`HttpOnly`, `SameSite=Lax`), there is no CORS, and the CSP says `connect-src 'self'`. A Next rewrite was tried first: it cannot stop Next's gzip middleware from buffering a stream. The handler marks API responses `no-transform` and passes cookies, status, problem+json and aborts through unchanged. All of this is tested. |
| 13 | (not specified) Passkey domain | **The WebAuthn origin and `RP_ID` are now the frontend's domain**, not the API's. Backend settings: `ORIGIN=https://<frontend host>`, `RP_ID=<frontend host>`, and `TRUST_FORWARDED_FOR=true` (requests arrive from the proxy). A passkey made on one domain does not work on another. | Because the browser's origin is the frontend's. |
| 14 | `connect-src` to the API origin | `connect-src 'self'` only, and `media-src 'self' blob:`. Readback audio arrives as `/api/voice/audio/...`. | Follows from 12. |
| 15 | Static shells and server components for fast first paint | Every route renders **per request** (`await connection()`), and `cacheComponents` / `partialPrefetching` are **off**. | A strict nonce-based CSP needs a fresh nonce per response, or the browser blocks every script. And hidden-route state restoration could bring back a stale review screen with an old amount. |
| 16 | "Session in httpOnly cookies" | Same, and the cookie is set by the backend, not by Next. | The backend owns sessions. |

## 3. Implementation details where the PRD and the accessibility standards disagree

| # | PRD says | Frontend does | Why |
| --- | --- | --- | --- |
| 17 | Amounts get an `aria-label` in words | The digits are `aria-hidden` and the words are visually hidden text next to them. | ARIA 1.2 does not allow `aria-label` on a plain `span` or `div`, and axe flags it. The effect for a screen reader user is the same: it hears "fifteen thousand naira". |
| 18 | Approve is "disabled" until the readback has been heard | The button uses `aria-disabled` and stays focusable, with a description saying why. | A natively disabled button is skipped by screen-reader users, who then never learn it exists. |

## 4. Not yet decided

| # | Question | Where it matters |
| --- | --- | --- |
| a | Amount-to-words for Yoruba, Hausa and Igbo. The backend and the AI package only have English number words. | Amounts outside the readback (agent screen, activity list). Plan: English words in every language, as the AI PRD does, until native-reviewed words exist. |
| b | Whether to default to Zolo's voice or the screen reader only (the double-speech default). | Needs blind testers, as the PRD already says. |
