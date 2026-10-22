# Frontend

Next.js 16 (App Router), React 19, TypeScript strict, Tailwind 4, next-intl, motion. pnpm. See
[`ARCHITECTURE.md`](ARCHITECTURE.md) for how it fits together and [`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md)
for why.

## Screens

| Route | For | Notes |
| --- | --- | --- |
| `/` | everyone | Landing page: what Zolo is, how it works, what keeps it safe, "Try the demo" |
| `/signin` | demo | Pick the customer or an agent (the backend has seeded agents and a fixed-code login) |
| `/home` | customer | Pay an agent, last payments, passkey status, language |
| `/pay/code` | customer | 4-digit code in a native numeric field, submits on the fourth digit |
| `/requests/[id]` | customer | **Review and approve**: hero amount, readback, voice-first with a screen-reader mode, passkey approval |
| `/requests/[id]/result` | customer | One outcome per screen: Paid, Processing, Declined, Expired, Changed, Failed |
| `/setup/passkey` | customer | Explains a passkey, handles cancel, already registered and no screen lock |
| `/agent`, `/agent/requests/[id]` | agent | Amount keypad; code and QR; live status |
| `/demo` | operator | Reset, tamper, replay, expire, timeline (flagged; token typed in) |

## Design system

Tokens (`styles/tokens.css`) are the source of truth: colour (light and dark), type scale in rem, spacing,
radius, materials, depth, motion. Every text pair is contrast-tested in both themes. The red is used for the
single primary action per screen and never alone. Motion follows springs with damping 1.0 by default, animates
only transform and opacity, and becomes a fade under reduced motion; translucent chrome becomes solid under
reduced transparency and more contrast.

## Conventions

- No text in components: strings are in `messages/<locale>.json` by key (`useT()`).
- Money is integer kobo; `AmountDisplay` and `SaidText` give digits for the eye and words for the ear.
- One polite live region and one assertive region; `useHoldAnnouncements()` pauses them while Zolo speaks.
- API access only through `lib/api/endpoints.ts`; every response is Zod-validated.
- `eslint` (strict jsx-a11y as errors), `prettier`, `tsc` strict, conventional commits.

## Run and test

```bash
cd frontend
pnpm install
cp .env.example .env.local        # BACKEND_URL defaults to http://localhost:8000
pnpm dev
pnpm check                        # types, lint, format, unit tests
pnpm build:e2e && pnpm e2e        # end to end + axe, against a fake backend
pnpm e2e:real                     # against the real backend (needs Postgres)
```

Direct links that work on their own: `/signin`, `/home`, `/agent`, `/demo`. The PWA manifest's `start_url` is
`/home`.
