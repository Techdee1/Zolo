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

| 19 | Demo console needs "drop network" and "cloned-voice draft" | See row 8. | Built: reset, tamper, replay, expire, timeline. |
| 20 | (not specified) How the demo console authenticates | Every `/demo/*` call needs an `X-Demo-Token` header (the backend's `DEMO_TOKEN`). | The operator **types the token into the page**; it lives in that tab's memory only. It is never in the bundle (a secret in `NEXT_PUBLIC_*` would ship to every visitor). The page itself is off unless `NEXT_PUBLIC_FEATURE_DEMO=true`. |
| 21 | Agent waiting screen shows the code and QR from a status call | `GET /requests/{id}` does not return the claim code or QR payload; only `POST /agent/requests` does, once. | The code is kept in `sessionStorage` (this tab only) when the request is made. If the agent reloads in a new tab, the screen says the code is no longer there and offers "New request". It never invents a code. |
| 22 | Pay an agent: "Scan QR instead" opens the camera (P0) | The API accepts `qr_payload`, and the agent screen shows a QR. | **Scanning is not built yet**; code entry is the default the PRD asks for. The agent's QR is shown. Camera scanning needs real-device testing, so it is left open rather than shipped untested. |
| 23 | Home has two tiles: Pay an agent, Send money | Voice transfer is Phase 2 (row 7). | One tile. No disabled "coming soon" control. |
| 24 | Review: "Ask for more time" | `renew` is Phase 2 (row 6). | Not shown. Time left is announced at 60 s, 15 s and 0. |
| 25 | Recent payments are "spoken naturally" ("Fifteen thousand naira to Bisi Ventures, today") | The API gives a `line` such as `Paid ₦15,000 to Bisi Ventures` with no date. | The line is shown as-is for the eye. Screen readers get a sentence built from the amount and payee fields, in words, plus "today / yesterday / 14 Oct" from `created_at`. |
| 26 | Result "Changed after you heard it" is a state | It is not a request state. The request stays `READ_BACK`; `INTENT_CHANGED` (409) comes back from readback, challenge or approve. | The screen that gets that error opens the result page with `?r=changed`. The query only chooses the words; nothing else trusts it. |
| 27 | Approval outcome is final in the response | `approve` can return `SUBMITTED` (bank call did not finish). Also, a connection that drops *after* the approval was sent leaves the outcome unknown. | `SUBMITTED` shows Processing (row 11). A dropped connection never says "failed": the result page asks the server what happened. |
| 28 | Setup passkey: status "set up or not" | There is no "list my passkeys" call. | The status is remembered on this phone (`localStorage`) when setup succeeds, and cleared if the API answers `NO_PASSKEY`. It only chooses the wording ("Set up" or "Replace") and shows an explainer on the review screen; it never blocks Approve. |
| 29 | Frame: phone-sized column | (not specified) | On screens 40rem and wider the app is a 30rem frame centred on a backdrop; on phones it fills the screen. Agent screens carry a faint cool tint and an "Agent" pill; customer screens a "Customer" pill. |
| 30 | `/` is the customer home | `/` is the landing page; the customer home moved to `/home`. | The landing page is the first thing a stranger sees. The installed app skips it: the manifest's `start_url` is `/home`. |
| 31 | PWA manifest, service worker (P1) | Manifest and icons exist; **no service worker yet**. | Enough for "Add to home screen" metadata; offline support is not built. The icons are a plain "Z" tile made for this project (not the Zenith logo). |
| 32 | System fonts only | One serif (Instrument Serif, one weight) for the landing page's big headings, self-hosted through `next/font`. | Requested for the landing page. The app screens stay on the system font, and the landing page makes no third-party request at runtime. |
| 33 | Passkey status: "Replace" for someone who has one | The backend sends the existing passkey in `excludeCredentials`, so a phone that already has it cannot register a second (the browser refuses). Only another phone can replace it. | Once this phone has a passkey the home row is just a status, with no action. A same-phone retry says "This phone already has your passkey." |
| 34 | The payee's name is the same everywhere | `GET /requests/{id}/readback` gives `payee_name` as `Bisi Ventures`; `GET /requests/{id}` and the approve response give the bank's `BISI VENTURES`. | **Open, for the backend:** the review screen shows and the voice says "Bisi Ventures", the result and activity screens show "BISI VENTURES". The frontend shows what each call returns and does not re-case names. |

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
