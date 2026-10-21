# Zolo Frontend PRD

Oct 20, 2026 · @Akeem Jr Odebiyi

This PRD defines the Zolo customer app and agent page: an accessible, Apple-quality PWA in a Zenith-inspired palette, built for blind and low-vision users first.

## Overview

We are building two web surfaces on one codebase: a **customer app** where a blind customer hears a payment request and approves it with a passkey, and an **agent page** where a POS agent creates that request.

- **Product rule the UI must express:** anyone can propose a payment; only the account holder approves it. The approve moment is the centre of the product, so it gets the most design and engineering care.
- **Primary flow:** Pay by transfer (agent creates request, customer claims by code, hears readback, approves, both see the result).
- **Secondary:** voice transfer, Card Guard unlock, and a demo console for judges.
- **Quality bar:** feels like an Apple first-party app (calm, precise, physical motion), reads as Zenith (red, graphite, white), and works fully with TalkBack and VoiceOver with the screen off.

**Done means:** a blind tester completes an agent cash-out alone on a low-cost Android phone with TalkBack, catches a wrong amount, and the flow passes automated accessibility checks with zero serious violations.

Related: the Zolo Engineering Team Brief (flows, states, API, security).

## Users and contexts

| User | Context | What the UI must do |
| --- | --- | --- |
| Blind customer | Screen reader on, phone held close, noisy POS stand, often one hand busy | Everything reachable by swipe navigation and double-tap; spoken readback; nothing depends on seeing the screen |
| Low-vision customer | Large text setting, high contrast, bright sunlight | Huge amounts, strong contrast, works at 200% text size |
| Elderly or low-literacy customer | Unfamiliar with apps, prefers voice in Pidgin or Yoruba | Few choices per screen, plain words, voice first |
| POS agent | Busy stand, sighted, mid-range Android, wants speed | Big keypad, one tap to request, clear "Paid" state |
| Judges and audience | Watching a projector mirror of the phone | Clear visual states, readable from a distance, failure cases visible |

## Scope

One Next.js app with three route groups; P0 screens must ship, P1 only after P0 passes acceptance.

| Route | Screen | Surface | Priority |
| --- | --- | --- | --- |
| `/welcome` | Welcome and language choice | Customer | P0 |
| `/setup/link` | Link account (mock bank login and OTP) | Customer | P0 |
| `/setup/passkey` | Create passkey and screen-lock guidance | Customer | P0 |
| `/` | Home: "Pay an agent", "Send money", recent activity | Customer | P0 |
| `/pay/code` | Enter or scan agent code | Customer | P0 |
| `/requests/[id]` | **Review and approve** (readback, approve, decline) | Customer | P0 |
| `/requests/[id]/result` | Result: paid, declined, expired, changed, failed | Customer | P0 |
| `/send` | Voice transfer (talk to Zolo, confirm draft) | Customer | P0 |
| `/activity` | Spoken history of payments | Customer | P1 |
| `/settings` | Language, voice, earpiece mode, limits, freeze | Customer | P1 |
| `/card` | Card Guard: status and "open my card" | Customer | P1 |
| `/agent/setup` | Agent account setup | Agent | P0 |
| `/agent` | New request: amount keypad | Agent | P0 |
| `/agent/requests/[id]` | Code and QR, live waiting, paid or declined | Agent | P0 |
| `/demo` | Demo console: tamper, replay, network drop, state timeline | Demo | P0 |

## Screen requirements

Each screen lists what it shows and the checks it must pass; the review screen is the one we polish hardest.

### Review and approve (`/requests/[id]`) · P0

**Shows:** who is asking (bank-verified name, with a "Verified by bank" badge), the amount as the largest element on screen (e.g. ₦15,000, with the words "fifteen thousand naira" under it), the bank, time left, and two actions: **Approve** and **Decline**.

- [ ] On arrival, Zolo's voice reads the request once from the server's `readback` text and audio; screen-reader focus lands on the readback heading after the audio ends (see Accessibility for the double-speech rule).
- [ ] **Approve** stays disabled until the readback has played or been read by the screen reader at least once.
- [ ] Approve triggers the platform passkey prompt with the challenge from `POST /requests/{id}/challenge`. No custom PIN pad.
- [ ] Decline is one tap, no confirmation dialog, and is announced ("Declined. Nothing was sent.").
- [ ] "Hear again" button replays the readback; "Ask for more time" renews an expiring request.
- [ ] Time left is announced at 60 and 15 seconds, politely, not every second.
- [ ] The displayed and spoken amount and name come only from the API response, never from local input.
- [ ] Amounts are formatted from kobo integers; no floating-point maths anywhere.

### Result (`/requests/[id]/result`) · P0

- [ ] One state per screen: Paid, Declined, Expired, Changed after you heard it, Failed.
- [ ] Each has an icon, a one-line spoken message, and a single next action ("Done" or "Try again").
- [ ] Paid uses the success colour and a subtle completion motion; Changed and Failed use the critical colour plus icon and text, never colour alone.

### Pay an agent (`/pay/code`) · P0

- [ ] Large 4-digit code entry using the system numeric keyboard (`inputmode="numeric"`), auto-submits on the 4th digit.
- [ ] "Scan QR instead" opens the camera with spoken guidance; code entry stays the default.
- [ ] Invalid or expired code gives a spoken, specific error.

### Voice transfer (`/send`) · P0

- [ ] One large press-to-talk button (hold or tap to toggle; both supported), with a clear listening state.
- [ ] Zolo's reply is shown as text and spoken; clarifying questions offer tappable answers (e.g. the two Tundes).
- [ ] When the server returns a draft request, navigate to the same Review and approve screen. There is no second approve UI.
- [ ] If amount confidence is low, show a numeric keypad for the amount only.

### Setup passkey (`/setup/passkey`) · P0

- [ ] Explains in two short sentences what a passkey is and that Zolo never asks for a PIN.
- [ ] Tells the customer to set their own screen lock privately, with earphones in.
- [ ] Handles: no platform authenticator, user cancels, already registered.

### Home (`/`) · P0

- [ ] Two primary actions as large tiles: "Pay an agent" and "Send money". Card Guard tile appears when enabled (P1).
- [ ] Last three payments, each one line, spoken naturally ("Fifteen thousand naira to Bisi Ventures, today").

### Agent new request (`/agent`) · P0

- [ ] Full-screen amount keypad, quick chips (₦5,000, ₦10,000, ₦20,000), and a "Request" button.
- [ ] Shows the agent's verified business name at the top so they know what the customer will hear.

### Agent waiting (`/agent/requests/[id]`) · P0

- [ ] 4-digit code in very large type plus QR; a "Read code aloud" hint.
- [ ] Live status (polling or server-sent events): Waiting, Paid, Declined, Expired. Paid shows a full-screen green confirmation with amount and time.
- [ ] Copy makes it clear the agent must wait for "Paid" before giving cash.

### Demo console (`/demo`) · P0

- [ ] Buttons for each failure case (tamper amount, replay approval, drop network, expire now, cloned-voice draft).
- [ ] A live state timeline for the current request (CREATED to SETTLED) readable on a projector.
- [ ] Hidden from the customer app navigation; behind a feature flag.

### Card Guard (`/card`) · P1

- [ ] Status announced first: "Your card is locked."
- [ ] "Open my card" by voice or amount keypad, then the same passkey approval; shows a time-left ring while open and announces relock.

## Brand and visual design

The look is Zenith's red, graphite and white with Apple-level restraint: mostly white and graphite, red reserved for the one action that matters on each screen.

### Principles

- **One red thing per screen.** Red marks the primary action or the brand mark, never decoration. On the review screen that is **Approve**.
- **The amount is the hero.** Biggest, heaviest element; tabular figures; nothing competes with it.
- **Calm, not empty.** Generous space, clear grouping by proximity, specific labels ("Approve ₦15,000", not "Continue").
- **Never colour alone.** Every state also has an icon and words.

### Colour tokens

These are Zenith-inspired values, not official brand codes. Swap in exact values if the organisers share brand assets. All text pairs below meet WCAG AA; re-check any new pair.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--color-brand` | #D7191E | #D7191E | Primary button fill, brand mark (white text on it: about 5.2:1) |
| `--color-brand-pressed` | #B3141A | #B3141A | Pressed primary |
| `--color-brand-text` | #D7191E | #FF5A5F | Red text and icons on page background |
| `--color-graphite` | #3A3A3C | #3A3A3C | Brand secondary surfaces (agent header, chips) |
| `--color-bg` | #FFFFFF | #000000 | Page background |
| `--color-bg-grouped` | #F5F5F7 | #111113 | Grouped sections, cards |
| `--color-bg-elevated` | #FFFFFF | #1C1C1E | Sheets, popovers |
| `--color-text` | #1C1C1E | #F5F5F7 | Primary text |
| `--color-text-secondary` | #6E6E73 | #A1A1A6 | Secondary text (meets 4.5:1 on both page and grouped backgrounds) |
| `--color-separator` | rgba(60,60,67,0.18) | rgba(84,84,88,0.6) | Hairlines |
| `--color-success` | #137333 | #32D74B | Paid, verified |
| `--color-warning` | #A15C00 | #FFB340 | Expiring, check this |
| `--color-critical` | #B3141A | #FF5A5F | Changed, failed (always with icon and text) |
| `--color-focus` | #1C1C1E | #FFFFFF | 3px focus ring with 2px offset |

**Brand use:** show the Zolo wordmark with a small "for Zenith Bank" line. Do not use the Zenith logo unless the organisers provide official assets for it.

### Typography

System font first (`-apple-system, BlinkMacSystemFont, "SF Pro Text", Roboto, "Segoe UI", sans-serif`) with `font-optical-sizing: auto`. All sizes in `rem` so they follow the user's text-size setting.

| Style | Size | Weight | Line height | Tracking | Use |
| --- | --- | --- | --- | --- | --- |
| Amount | 3.5rem | 700 | 1.05 | -0.02em | The amount on review and result screens, tabular figures |
| Code | 3rem | 600 | 1.1 | 0.08em | Agent's 4-digit code |
| Title | 1.75rem | 600 | 1.15 | -0.01em | Screen titles |
| Headline | 1.25rem | 600 | 1.25 | 0 | Payee name, section titles |
| Body | 1.0625rem | 400 | 1.47 | 0 | Default text |
| Secondary | 0.9375rem | 400 | 1.4 | 0 | Supporting text |
| Caption | 0.8125rem | 500 | 1.35 | 0.01em | Badges only; nothing smaller |

### Layout, shape and materials

- **Spacing:** 0.25rem steps (4, 8, 12, 16, 24, 32, 48, 64 px). Screen side padding 1.25rem.
- **Targets:** at least 48px; primary buttons 3.5rem tall, full width, at the bottom within thumb reach.
- **Radius:** 12px controls, 20px cards, 28px sheets.
- **Materials:** the top bar and bottom action area are translucent (`backdrop-filter: blur(20px) saturate(180%)` over about 72% opaque background). The amount card and buttons are always solid. Fall back to solid backgrounds under `prefers-reduced-transparency` and `prefers-contrast: more`.
- **Icons:** one line-icon set (e.g. Lucide) at 24px, stroke 1.75, always paired with a text label.
- **Layout:** single column, max width 30rem centred; the agent page may use the full width for its keypad.

## Motion and feedback

Motion follows the apple-design Claude Code skill (emilkowalski/skills, `skills/apple-design`): physical, interruptible, and never in the way of a screen-reader user.

- **Install and use the skill** in Claude Code for all UI work; when this PRD and the skill differ, accessibility in this PRD wins.
- **Instant response:** feedback on pointer-down (buttons scale to about 0.97 on press), commit on release, cancel by dragging away. No artificial delays or debounces on the input path.
- **Springs, not keyframes,** for anything that moves: critically damped by default (damping 1.0, response about 0.4s); sheets about 0.8 damping, 0.3s response. Animate only `transform` and `opacity`.
- **Interruptible:** never lock input during a transition; animate from the current on-screen value.
- **Spatial consistency:** a sheet leaves the way it came; popovers grow from their trigger.
- **Meaningful moments only:** the approve-to-paid transition gets a short completion motion and a vibration (`navigator.vibrate` on Android, where available). Errors get a single short shake of the amount card plus haptic. Nothing loops.
- **Sound:** none by default apart from Zolo's voice, so we never talk over the screen reader.

**Reduced motion** (`prefers-reduced-motion: reduce`): replace slides and springs with short opacity fades, no shake, no overshoot. Test every screen with it on.

## Accessibility requirements

Accessibility is the product, not a polish pass: a screen that fails these is not done, however good it looks.

**Standards:** WCAG 2.2 AA; tested with TalkBack (Android Chrome) and VoiceOver (iOS Safari) on real devices.

### Screen readers

- Semantic HTML first (`button`, `h1` to `h3`, `main`, `nav`, lists); ARIA only where HTML can't express it.
- One `h1` per screen; on route change, move focus to it and update `document.title`.
- Every control has a specific accessible name ("Approve fifteen thousand naira to Bisi Ventures"), never "button".
- Amounts get an `aria-label` in words ("fifteen thousand naira") because screen readers mangle "₦15,000".
- Status changes (Paid, Declined, Expired, waiting) are announced through one shared polite live region; errors through an assertive one.
- The QR code and decorative images are hidden from screen readers; the 4-digit code is announced digit by digit.

### Double-speech rule

Zolo's own voice and the user's screen reader must never talk at the same time.

1. **Default ("Zolo voice"):** play the readback audio first, then move focus to the readback heading after the audio ends. The readback region is not a live region.
2. **"Screen reader only" setting:** no audio; focus moves straight to the readback heading.
3. Validate the default with blind testers before demo day; switch the default if testers prefer screen reader only.

### Input, time and vision

- Every action works with a single tap; no swipe or path gestures required.
- Targets at least 48px with 8px between them.
- No time limit without a way to extend ("Ask for more time").
- Works at 200% text size and 320px width without loss of content or horizontal scrolling.
- Contrast at least 4.5:1 for text and 3:1 for controls and focus rings in both themes.
- Respect `prefers-reduced-motion`, `prefers-reduced-transparency`, `prefers-contrast` and dark mode.
- Camera (QR) and microphone (voice) are always optional, with a keypad or text alternative.

### Checks before merge

- [ ] axe-core in Playwright reports zero serious or critical violations on every P0 route.
- [ ] Keyboard-only run-through of the P0 flow (also catches switch-access issues).
- [ ] Manual TalkBack run-through on a low-cost Android phone for any change to a P0 screen.

## Content, voice and languages

Words are short, specific and spoken-first: if it sounds wrong read aloud, rewrite it.

- **Languages:** English, Pidgin, Yoruba, Hausa and Igbo for all UI strings. English is the source; translations reviewed by a native speaker before demo.
- **Spoken readbacks** come from the API in the chosen language; the frontend never builds readback sentences itself.
- **Tone:** warm and direct. Say what happened and what to do next. No blame ("The amount changed after you heard it. Nothing was sent.").
- **Numbers:** amounts in digits on screen and words for screen readers; dates as "today", "yesterday", then "14 Oct".
- **Never ask for a PIN or card number** anywhere in the app copy.
- **Strings** live in message files by key (`review.approve`, `result.changed`), with no hard-coded text in components.

| Key | English | Pidgin |
| --- | --- | --- |
| `review.heading` | Bisi Ventures is asking for ₦15,000 | Bisi Ventures dey ask for ₦15,000 |
| `review.approve` | Approve ₦15,000 | Approve ₦15,000 |
| `review.decline` | Decline | No, decline am |
| `result.paid` | Paid. You sent ₦15,000 to Bisi Ventures. | E don pay. You don send ₦15,000 to Bisi Ventures. |
| `result.changed` | This payment changed after you heard it. Nothing was sent. | This payment change after you hear am. We no send anything. |
| `agent.waitForPaid` | Give cash only after you see Paid. | Give cash only when you see Paid. |

Pidgin lines are drafts; have a fluent speaker review them.

## Technical architecture

A typed Next.js PWA talks only to the Zolo FastAPI backend; it holds no secrets and never decides amounts, names or approvals itself.

| Concern | Choice | Why |
| --- | --- | --- |
| Framework | Next.js (App Router, current stable), React, TypeScript `strict` | Routing, server components for static shells, easy HTTPS deploys |
| Styling | Tailwind CSS with the colour and type tokens as CSS variables | Tokens in one place; light and dark from the same classes |
| Accessible primitives | Native HTML first; React Aria Components for dialogs and complex widgets | Tested screen-reader behaviour |
| Motion | `motion` (Framer Motion) springs | Interruptible, velocity-aware springs as the skill asks |
| Server state | TanStack Query; status via server-sent events, polling fallback every 1s | Live "Paid" without manual refresh |
| Validation | Zod schemas for every API response | Never render unvalidated money data |
| Passkeys | `@simplewebauthn/browser` (server uses py\_webauthn) | Standard WebAuthn ceremonies |
| i18n | next-intl message files | Five languages, keyed strings |
| QR | `qrcode.react` to show; BarcodeDetector with a ZXing fallback to scan | Works on Android Chrome and iOS Safari |
| Audio | `HTMLAudioElement` for readbacks; `MediaRecorder` to capture speech and send to the backend | Speech keys stay on the server |
| PWA | Web app manifest plus Serwist service worker (app shell only, never cache API responses) | Installable, fast reloads |
| Mocks | MSW (Mock Service Worker) with fixtures for every state | Frontend can build before the backend is ready |

### Folder structure

```
app/
  (customer)/            welcome, setup, home, pay, requests, send, activity, settings, card
  agent/                 setup, new request, request status
  demo/                  demo console (feature-flagged)
components/
  ui/                    Button, AmountDisplay, Sheet, Badge, Keypad, LiveRegion
  review/                ReadbackCard, ApproveBar, TimeLeft
lib/
  api/                   typed client + Zod schemas
  webauthn/              register and approve helpers
  audio/                 readback player, recorder, double-speech guard
  format/                kobo to naira, amount to words
messages/                en, pcm, yo, ha, ig
styles/tokens.css        colour, type, spacing, radius, motion tokens
tests/                   unit, e2e (Playwright), a11y
```

### API contract used by the frontend

| Call | Used on |
| --- | --- |
| `POST /agent/requests` | Agent new request |
| `GET /requests/{id}/status` (and SSE stream) | Agent waiting, result screens |
| `POST /requests/claim` | Pay an agent (code or QR) |
| `GET /requests/{id}/readback` | Review and approve (text, language, audio URL) |
| `POST /requests/{id}/challenge` then `POST /requests/{id}/approve` | Approve |
| `POST /requests/{id}/decline` | Decline |
| `POST /requests/draft` (voice turn) | Voice transfer; exact shape to agree with backend |
| `POST /passkeys/register` | Setup passkey |
| `POST /card-guard/windows` | Card Guard (P1) |
| Demo endpoints (tamper, replay, expire) | Demo console |

All money values arrive as integer kobo plus a currency code. Schemas live in `lib/api` and are shared with MSW fixtures so mocks and reality can't drift.

## Engineering practice

Main is always deployable, every change is reviewed, and every P0 screen is covered by an automated accessibility test.

### Workflow

- pnpm, Node LTS, ESLint (with `jsx-a11y`) and Prettier; no lint warnings on main.
- Short-lived branches, conventional commits (`feat:`, `fix:`, `a11y:`), small pull requests reviewed by one teammate.
- PR template includes: screenshots in light and dark, TalkBack checked (yes or no), reduced motion checked.
- Preview deploy for every PR over HTTPS so passkeys work on real phones.
- Feature flags via environment variables: `NEXT_PUBLIC_FEATURE_CARD_GUARD`, `NEXT_PUBLIC_FEATURE_DEMO`.

### CI (GitHub Actions, on every PR)

1. Type check (`tsc --noEmit`)
2. Lint
3. Unit tests (Vitest and Testing Library)
4. End-to-end tests (Playwright) against MSW mocks, with axe-core on every P0 route
5. Production build and bundle size check

### Testing

- **Unit:** kobo formatting, amount to words in all five languages, double-speech guard, status reducer.
- **Component:** review screen states (loading, ready, expiring, approving, error) and accessible names.
- **End to end:** full Pay by transfer flow with Chromium's virtual WebAuthn authenticator; every failure case from the team brief.
- **Manual:** TalkBack on a low-cost Android phone and VoiceOver on an iPhone before each milestone.

### Performance budgets

- First-load JavaScript for the review route at most 170 KB gzipped.
- Largest Contentful Paint under 2.5s on a mid-range Android over 4G.
- Readback audio starts within 1s of the screen appearing (preload as soon as the request is claimed).
- System fonts only, so no web font loading.

### Security and privacy

- No API keys or secrets in the client; speech and bank calls go through the backend.
- Session in httpOnly, Secure, SameSite cookies; nothing sensitive in localStorage.
- Strict Content Security Policy; HTTPS only.
- Never trust or send amounts from the client for execution; the client only sends request IDs and signatures.
- No analytics or logging of names, amounts or audio.

## Milestones

The frontend tracks the team build plan, building against MSW mocks until the backend endpoints land.

| When | Deliverable | Exit check |
| --- | --- | --- |
| Before the sprint | Repo, CI, tokens, UI kit (Button, AmountDisplay, Keypad, LiveRegion, Sheet), MSW fixtures, HTTPS preview | Storybook-style kitchen-sink page passes axe; dark mode works |
| Day 1 | Agent new request and waiting screens; Pay an agent; Review and approve against mocks | Mocked happy path end to end with virtual authenticator |
| Day 2 morning | Wire to real backend; passkey setup; result screens; voice transfer | Real phone: agent request to Paid with TalkBack on |
| Day 2 afternoon | Demo console; failure states; translations in. **Feature freeze.** | All failure cases demoable; axe clean |
| Day 2 stretch | Card Guard screen | Lock, open, relock announced correctly |
| Day 3 | Fixes from blind-tester session; polish motion; projector check | Tester completes cash-out unaided |

## Out of scope and open questions

**Out of scope:** native apps, phone-call (IVR) screens, onboarding KYC, naira note recognition, delegate approval, offline payments.

- [ ] Agree the voice-turn endpoint shape with the backend owner.
- [ ] Confirm the readback API returns audio in all five languages, and its latency.
- [ ] Blind testers to choose the double-speech default (Zolo voice vs screen reader only).
- [ ] Get official Zenith colours from the organisers, if available, and swap tokens.
- [ ] Native speakers to review Pidgin, Yoruba, Hausa and Igbo strings.
- [ ] Confirm the demo phones (one low-cost Android, one iPhone) and mirroring setup.
