# Real-device passkey test

**Status: not yet run on a phone.** Everything below is the procedure and what the server is built to show. The API's passkey logic is tested with a software authenticator; whether a real phone's fingerprint or face prompt works end to end through a public HTTPS tunnel is exactly what this test finds out. Fill in the results table at the bottom, and only then say it works.

## Why this test exists

A passkey is bound to a web domain. It only works on the exact domain it was created on, over HTTPS. A passkey made on `localhost` will not work on a tunnel address, and a tunnel address that changes makes yesterday's passkey useless. The PRD calls this the "passkey domain trap". This test proves, on your own phone, that the domain settings are right before the demo depends on them.

## Through the frontend (the real app, not the test page)

The frontend proxies `/api` to the backend, so the passkey's origin and RP ID are the **frontend's**
domain, not the API's. To try the real screens on a phone:

1. Start the backend with `RP_ID=<frontend host>`, `ORIGIN=https://<frontend host>`,
   `CORS_ORIGINS=` the same origin, `COOKIE_SECURE=true`, `TRUST_FORWARDED_FOR=true`, `DEMO_MODE=true`.
2. Start the frontend with `BACKEND_URL=<where the API listens>` and `NEXT_PUBLIC_FEATURE_DEMO=true`,
   and put the HTTPS tunnel (or domain) in front of the **frontend**, not the API.
3. On the phone: open `/signin`, sign in as the customer, tap **Passkey** on the home screen, then
   set one up. On the laptop: sign in as the agent at `/agent`, ask for ₦15,000. On the phone:
   **Pay an agent**, type the code, listen, **Approve**.

The same journeys run automatically against the real backend with a software authenticator:
`cd frontend && pnpm build:e2e && pnpm e2e:real` (needs Docker for Postgres). That proves the wiring;
it does not prove a real phone's fingerprint or face prompt. That is still the table at the bottom.

## What you need

- Your phone, with a screen lock set and fingerprint or face unlock enabled. Android with Chrome, or iPhone with Safari, both on a current version. Open the page in the real browser, not inside another app's built-in browser (WhatsApp, Instagram and similar often break passkeys).
- A laptop on the same project, with the database running (`docker compose up -d postgres` in `backend/`) and `backend/.env` holding `DATABASE_URL` and `SESSION_SECRET`.
- A public HTTPS address that reaches the laptop. Easiest is a Cloudflare quick tunnel: install `cloudflared` (check Cloudflare's current download page for your system). The helper script below can start it for you. You can also use a tunnel or domain you already run.

## Steps

All commands run from the `backend/` folder.

1. **Start everything.** Either let the script start a tunnel and the API:

   ```
   uv run python -m zolo.tools.real_device
   ```

   or, if you already have a public host (for example `demo.example.com`):

   ```
   uv run python -m zolo.tools.real_device --host demo.example.com
   ```

   It prints the exact values it sets, migrates and seeds the database, then runs the API. Look at the printed block:

   | Value | Must be |
   | --- | --- |
   | `RP_ID` | the host name only, e.g. `abc-def.trycloudflare.com` |
   | `ORIGIN` | `https://` plus that host, no trailing slash, no port |
   | `COOKIE_SECURE` | `true` |
   | `DEMO_MODE` | `true` (this is what turns on mock login and the test page) |

   To only see the values without starting anything: add `--print-only --host <your host>`.

2. **Open the test page on the phone:** `https://<your host>/dev/passkey-test`. The top of the page shows `origin` and `host (must equal RP_ID)`. Check they match what the script printed.

3. **Log in as the customer.** Leave the phone number `+2348011111111` and code `123456`, tap **Log in**. The log at the bottom should show `POST /auth/mock-login -> 200`.

4. **Create a passkey.** Tap **Create passkey on this phone**. Your phone shows its own fingerprint, face or screen-lock prompt. Approve it. Expect `POST /passkeys/register/options -> 200` then `POST /passkeys/register/verify -> 201`.

5. **On the laptop, log in as the agent.** Open the same page in a normal browser tab, set the phone number to `+2348022222222` (Bisi Ventures), code `123456`, **Log in**, set the amount to `15000`, tap **Create request**. The page prints a 4-digit code. (You can use the phone for this too in a second tab, but two devices makes it feel real.)

6. **On the phone, claim it.** Type the 4-digit code, tap **Claim by code**, then **Read it back**. You should see and hear: *Bisi Ventures dey ask for fifteen thousand naira. One five, zero zero zero. You wan approve?* The request must not be older than 2 minutes, or you will get `REQUEST_EXPIRED`; create a new one.

7. **Approve.** Tap **Approve with passkey**. The phone prompts for your fingerprint, face or screen lock. Approve. Expect the log to show `challenge -> 200`, then `approve -> 200` with `"state": "SETTLED"`.

8. **On the laptop, check the agent side.** Tap **Check status**: it should show `SETTLED`. In the database the customer's mock balance drops by ₦15,000.

9. **Try the failures on purpose** (they should all be refused, and nothing should move):
   - Create another request, claim and read it back, then tap **Decline**: state `DECLINED`.
   - Create another request, claim it, wait 2 minutes, tap **Read it back**: `REQUEST_EXPIRED`.
   - Cancel the fingerprint prompt at step 7: the page shows a `NotAllowedError`; the request stays `READ_BACK` and you can try again within the 2 minutes.

10. **Stop the API and tunnel with Ctrl-C.** A quick tunnel gets a new address every time. Next run you must create a new passkey (step 4; the old one is replaced automatically).

## When it fails: what you see, and what the server logs

The API writes one JSON line per event to the terminal. To watch only the passkey problems, pipe the output through:

```
... | grep -E 'signature_invalid|registration_failed|counter_not_increased'
```

The server logs a **reason code only** (never the payload), and the phone only ever sees a generic error. These are the lines the code writes.

| What went wrong | What you see on the phone | What the API log shows | Fix |
| --- | --- | --- | --- |
| **Page opened over `http://`** (not https) | "This browser has no WebAuthn (is the page on https?)". Browsers only expose passkeys on https or localhost. | Nothing from passkeys. If you logged in, later calls show `"status":401` on `/passkeys/register/options` because the Secure cookie is dropped over http. | Use the `https://` tunnel address. |
| **`RP_ID` is not the page's host** (a typo, or a different domain) | The browser refuses before asking you: a `SecurityError`, wording like "the relying party ID is not a registrable domain suffix of, nor equal to, the current domain". The log in the page shows `ERROR: SecurityError`. | Only `POST /passkeys/register/options -> 200` (`"route":"/passkeys/register/options","status":200`). No `/register/verify` request follows. | Set `RP_ID` to exactly the host in the page's header line. |
| **`ORIGIN` does not match** (http vs https, a trailing slash, a port, a different subdomain) | The phone prompt works, then the page shows `400 PASSKEY_REGISTRATION_FAILED` (registering) or `401 SIGNATURE_INVALID` (approving). | `"event":"registration_failed","code":"wrong_origin"` or `"event":"signature_invalid","code":"wrong_origin"`. | Set `ORIGIN` to the exact origin shown in the page's header line. |
| **Passkey made on `localhost` (or another host), used on the tunnel** | At step 7 the phone shows no passkey to use, or the page shows `NotAllowedError`. | Only `POST /requests/<id>/challenge -> 200`. No `/approve` request follows. | Create the passkey (step 4) on the same host you approve on. |
| **Tunnel restarted, so the host changed** | Same as the row above: the old passkey belongs to the old address. | Same: a challenge request, then no approve. | Repeat step 4 on the new address. The server replaces the old passkey. |
| **Assertion's RP ID hash does not match `RP_ID`** (rare: a client that is not a normal browser) | `401 SIGNATURE_INVALID`. | `"code":"wrong_rp"`. | Check `RP_ID` was not changed between registering and approving. |
| **No fingerprint, face or screen lock on the phone**, or user verification refused | The phone cannot offer a prompt, or the page shows `NotAllowedError`. If the authenticator signs without verifying you: `401 SIGNATURE_INVALID`. | If it reaches the server: `"code":"uv_missing"`. | Turn on a screen lock and biometrics. |
| **The wrong person's passkey, or a revoked one** | `401 SIGNATURE_INVALID`. | `"code":"revoked_or_foreign_passkey"`. | Register again as the customer you are logged in as. |
| **Signature counter went backwards, or repeated while strict** | `401 SIGNATURE_INVALID`. | `"code":"stale_counter"`. With `WEBAUTHN_STRICT_COUNTER=false` an equal, non-zero count is allowed and you see `"event":"counter_not_increased","code":"equal_counter"` as a warning instead. | Normal on the helper script (strict is off). In strict mode a repeated count means a possibly cloned authenticator. |
| **Browser blocks the cookie** (private mode, strict settings, in-app browser) | After login every call says `401 UNAUTHENTICATED`. | `"status":401` on each protected route, no passkey lines. | Use the normal Chrome or Safari window, not private mode. |
| **Everyone shares one rate-limit bucket** (all requests appear to come from the tunnel) | Login or claim suddenly `429 RATE_LIMITED`. | `"status":429`. | The helper script sets `TRUST_FORWARDED_FOR=true` so limits use the real address. If you start the API yourself behind a tunnel, set it too. |

A failure that shows only in the **page log and not at all in the API log** (the `SecurityError` and `NotAllowedError` cases) is a browser-side refusal, before anything reaches the server. A failure with a `code` in the **API log** reached the server and was rejected there.

## What I have not verified

- That any of this works on a real phone, in Chrome or Safari. No one has run it.
- The `cloudflared` and `ngrok` output parsing is tested against sample lines, not against the live programs.
- The browser wording quoted above (`SecurityError`, `NotAllowedError`, the "relying party ID" text) is from memory of how browsers typically behave; the exact text varies by browser and version.
- Behaviour with iCloud Keychain or Google Password Manager turned off, or with a hardware security key instead of the phone's own passkey.
- Anything about the real frontend: this page is a plain test tool served by the API, not the product UI.

## Results (fill this in)

| Step | Device and browser | Result | Notes |
| --- | --- | --- | --- |
| 4. Register a passkey | | | |
| 7. Approve ₦15,000 | | | |
| 9. Decline / expire / cancel prompt | | | |
