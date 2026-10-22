# Zolo frontend

The customer app and agent page for Zolo, a consent layer for Zenith Bank: anyone can ask for a
payment, only the account holder approves it, after hearing it. One Next.js app, built for blind
and low-vision users first. Requirements are in [`Frontend_PRD.md`](../Frontend_PRD.md); the API it
talks to is [`backend/openapi.json`](../backend/openapi.json).

> **Status: steps 1 to 5 of 7** (scaffold, design tokens, UI kit, typed API client, P0 screens).
> Passkeys work end to end in Chromium against a fake backend; the real backend and a real phone are
> step 6. The five languages are step 7 (English only now).

## Run it

```bash
pnpm install
cp .env.example .env.local     # optional; the defaults point at http://localhost:8000
pnpm dev                       # http://localhost:3000
```

| Command            | What it does                                                                   |
| ------------------ | ------------------------------------------------------------------------------ |
| `pnpm check`       | typecheck, lint, format check and unit tests (run before every push)           |
| `pnpm typecheck`   | `tsc --noEmit`, TypeScript strict plus extra strictness flags                  |
| `pnpm lint`        | ESLint with the **strict** `jsx-a11y` set; every rule is an error              |
| `pnpm test`        | Vitest and Testing Library                                                     |
| `pnpm build`       | production build                                                               |
| `pnpm e2e:install` | one-off: Chromium and its system libraries (needs sudo on Linux)               |
| `pnpm e2e`         | Playwright plus axe-core against the **production build** (`pnpm build` first) |

## Decisions worth knowing

- **Every route renders per request** (`await connection()` in the root layout). The Content
  Security Policy uses a fresh nonce for each response, and a statically prerendered page has no
  nonce on its scripts, so the browser would block all of them and the app would never become
  interactive. An end-to-end test proves the app hydrates under the CSP. The cost is no static
  caching of the HTML; the pages are thin shells over client data, so this is acceptable.
- **`cacheComponents` and `partialPrefetching` are off.** With them on, Next keeps visited routes
  alive and restores their state on back-navigation. For a payment app that risks showing an old
  review screen with an old amount. Money screens always refetch.
- **Strict CSP** ([`proxy.ts`](proxy.ts)): scripts need the nonce, no `unsafe-inline` or
  `unsafe-eval` in production, network and audio only to this origin and the API.
  `style-src-attr 'unsafe-inline'` allows style _attributes_ only (React and animation libraries
  set them); style elements still need the nonce.
- **Only Chromium is tested end to end**, because its virtual WebAuthn authenticator is what lets
  us test passkeys without a phone. Real-device checks (TalkBack, VoiceOver) are manual.
- **Accessibility gates are stricter than the PRD:** axe must report zero violations of _any_
  impact, not only serious ones, in light, dark, and reduced-motion with more contrast.
- **System fonts only.** No web fonts, no third-party requests (a test checks nothing leaves the
  origin).

## Conventions

- **Conventional commits**, with `a11y:` as an extra type: `feat(review): ...`, `fix: ...`,
  `a11y: ...`. CI checks the PR title (squash-merge uses it).
- **PRs** use the template: screenshots in light and dark, TalkBack checked, reduced motion checked.
- Feature flags are environment variables (`NEXT_PUBLIC_FEATURE_*`, see `.env.example`). Nothing in
  `NEXT_PUBLIC_*` is secret, by construction.

## Where things are

| Path                          | What                                                                                                                                                                                                                         |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/`                        | Screens: `/signin` (demo chooser), `/` (home), `/pay/code`, `/requests/[id]` (review and approve), `/requests/[id]/result`, `/setup/passkey`, `/agent`, `/agent/requests/[id]`, `/demo` (flagged), `/kitchen-sink` (flagged) |
| `components/ui/`              | The kit: Button, AmountDisplay, Keypad, Badge, TimeLeft, Sheet, LiveRegion                                                                                                                                                   |
| `lib/api/`                    | `client.ts` (one fetch, two checks), `schemas.ts` (Zod, checked against the generated types), `endpoints.ts` (one function per call)                                                                                         |
| `messages/en.json`            | Every word on screen, by key. No text lives in components                                                                                                                                                                    |
| `tests/fakes/fake-backend.ts` | A faithful copy of the Phase 1 API as one pure function. MSW (unit tests) and the e2e server both use it                                                                                                                     |

## Not built yet

Real-backend passkey runs and real-phone checks (6), the other four languages (7), QR scanning
(camera, needs a real device), the PWA manifest and service worker, and the bundle-size budget check
(170 KB gzipped for the review route). The list of differences from the PRD is
[`docs/PRD_DEVIATIONS.md`](../docs/PRD_DEVIATIONS.md).
