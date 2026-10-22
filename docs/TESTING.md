# Testing strategy

Numbers are from the last full run at the time of writing; CI is the source of truth.

## Backend (`backend/tests`, pytest, real Postgres): about 950 tests

| Layer | What it proves |
| --- | --- |
| Golden fixtures | The canonical intent bytes and SHA-256 never change (strings typed by hand, hashed with `sha256sum`) |
| Properties | Any change to amount, payee or expiry changes the hash; only a true integer is ever an amount |
| State table | The transition table is exactly the PRD's; every action in every state gives the expected outcome and moves money only where it should |
| Ceremony | A **software WebAuthn authenticator** (a real P-256 key) drives registration and approval, including tamper, replay, expiry, counters, caps and races |
| Failure cases | All twelve cases from the brief; a test fails if one is missing |
| Random storms | Seeded sequences of hundreds of mixed operations; money is conserved, nothing is paid twice, finished requests never change |
| HTTP | Every endpoint, role, limit and error code; the **OpenAPI contract is pinned** and CI fails if `openapi.json` is stale |
| Audio and language | On-create rendering, late and failing providers, language fallback, clip compression, the clip set |
| Mutation sweep | `scripts/mutation_sweep.py` plants one deliberate bug at a time in the security-critical code and lists any that no test notices |

Coverage gate: **90% on `consent` and `passkeys`** (`python -m zolo.tools.check_coverage`); currently above it.

## Frontend (`frontend/tests`)

| Suite | Count | What it proves |
| --- | --- | --- |
| Unit (Vitest, Testing Library, MSW) | ~380 | Kit components, tokens (contrast of every text pair in both themes), money and words (checked against 717 backend-generated cases), every screen against one **shared fake backend**, all five languages (key and placeholder parity), the landing page rendered with no JavaScript, the manifest |
| End to end (Playwright, Chromium, production build) | ~165 | Full journeys with Chromium's virtual authenticator, **axe with zero violations of any impact** in light, dark, reduced motion and more contrast on every screen, the strict CSP (no violations, nothing leaves the origin), the `/api` proxy (cookies, streaming, path tricks), 320px at 200% text, keyboard use, press feedback, language switching |
| Real-backend e2e (`pnpm e2e:real`) | 10 | The same passkey journeys against the **real API and Postgres**: registration, approval, NO_PASSKEY, cancel, tamper, replay, expiry, decline, contract |
| Lighthouse (mobile, simulated 4G) | manual | Landing page performance 97 to 98, accessibility 100, best practices 96, SEO 100 |

## Practices that keep the tests honest

- **Mutation checks:** when a test is written for a behaviour, the behaviour is broken on purpose once to
  confirm the test fails.
- **Drift alarms:** Zod schemas versus generated types fail the type-check if they disagree; CSS tokens versus
  the JavaScript spring constants are compared in a unit test.
- **Real device:** the passkey flow has been run once on a real phone through a tunnel
  ([`REAL_DEVICE_TEST.md`](REAL_DEVICE_TEST.md)). A full TalkBack/VoiceOver pass is still open.

## CI (`.github/workflows`)

`ci.yml`: backend (ruff, mypy, pytest with coverage gate, OpenAPI export check) and an images job (both Docker
images build, Caddy and Render Blueprints validate). `frontend.yml`: API types match `openapi.json`, type
check, lint (strict `jsx-a11y`), format, unit, production build, e2e with axe, and the real-backend job against a
Postgres service.

## Run it

```bash
make test            # backend + frontend unit
cd backend && uv run pytest
cd frontend && pnpm check && pnpm build:e2e && pnpm e2e && pnpm e2e:real
```
