# Zolo: Engineering Team Brief

Oct 20, 2026 · @Akeem Jr Odebiyi

Zolo is a voice-first consent layer for Zenith (Zecathon 6.0, Track 7) built on one rule: anyone can propose a payment, only the account holder can approve it.

## Summary

We are building a consent layer that lets blind and low-vision customers pay and withdraw cash without handing their card, PIN or phone to anyone.

- **Core rule:** anyone (the customer, a POS agent, a shop) can propose a payment. Only the account holder approves it, after hearing the exact amount and the bank-verified recipient name.
- **Approval:** a passkey on the customer's own phone (fingerprint, face or screen lock), cryptographically tied to that one request. Voice can propose, never approve.
- **Three ways in:**
  1. **Pay by transfer (primary):** the agent or shop creates the request; the customer listens and approves; a normal transfer moves the money. No card, no PIN.
  2. **Card Guard (secondary):** the card stays locked until the customer unlocks it by voice for one payment up to a set amount. A stolen card and PIN are useless.
  3. **Phone-call approval (fallback):** for feature phones or no data, the bank calls the customer, reads the request and they approve with a PIN on their own keypad.
- **Languages:** Pidgin, Yoruba, Hausa, Igbo and English.
- **Hackathon scope:** Pay by transfer end to end against a mocked bank, plus the failure cases. Card Guard and the phone call only if time allows.

## Problem

Blind and visually impaired Nigerians routinely hand their card and PIN to agents, strangers or relatives because the channels around them assume sight.

| Channel | What goes wrong |
| --- | --- |
| Touchscreen POS | No buttons or audio, so the customer says the PIN aloud or lets the agent enter it. |
| ATMs | Audio guidance is rarely working, so customers ask bystanders or guards for help. |
| Bank apps | Unlabelled buttons, custom PIN pads screen readers can't read, and selfie checks that assume sight. |
| USSD | Sessions time out before a screen reader finishes reading the menu. |
| Branches | Some customers report being refused cards or asked to sign indemnity forms. |

- **The harm is real:** a visually impaired widow in Anambra lost over ₦2 million after an ATM "helper" took her PIN and swapped her card.
- **The regulator is asking:** in September 2026 the CBN Governor said about 40 million Nigerians live with disabilities and the financial system has not innovated for them. Estimates vary widely (about 5.1 million adults in one NBS-based figure), so always say whose number it is.
- **What already works:** some apps (e.g. OPay) can be used with TalkBack by a confident user. Our gap is the agent's stand and the card, not "blind people can't use phones".

## Goals and non-goals

The build succeeds if a blind tester can complete an agent cash-out alone, catch a wrong amount, and nothing moves that they didn't hear and sign.

**Goals**

- A blind or low-vision user completes an agent cash-out and a voice transfer without help.
- The card and PIN never leave the customer's hands in Pay by transfer.
- Money moves only for a request the customer heard and signed. Any change voids the approval.
- Every failure case in this brief is demoed and handled safely.
- Readbacks work in Pidgin, Yoruba, Hausa, Igbo and English.

**Non-goals for the hackathon**

- Real integration with Zenith systems. We use a mock bank service and say so.
- Holding live card payments open while the customer approves. Card Guard uses a stored rule instead.
- Delegate approval (anyone other than the account holder approving).
- Onboarding, KYC and liveness checks.
- Naira note recognition, sign language and switch access (roadmap).

## User flows

All three flows share the same core: a stored request, a spoken readback from that record, and a signed approval.

### Setup (once)

1. Customer opens Zolo (directly or via ZiVA) with TalkBack or VoiceOver, links their Zenith account through the bank's own login and OTP.
2. Customer creates a passkey and sets their own screen lock privately (earphones in). Fingerprint or face preferred where the phone has it.
3. Customer picks a language and sets daily limits. Card Guard is opt-in.
4. Agent (once): opens the Zolo Agent web page, enters their account number. Zolo checks the name with the bank and saves it.

### Flow A: Pay by transfer at an agent (primary)

1. Customer says, "I want fifteen thousand cash." Card stays in their pocket.
2. Agent types ₦15,000 on the Zolo Agent page. **Server** creates and stores the request: amount, bank-verified agent name and account, unique ID, nonce, 2-minute expiry.
3. Page shows a 4-digit code and a QR. Agent reads the code aloud; customer says or types it (or scans the QR).
4. Zolo reads from the stored record: *"Bisi Ventures dey ask for fifteen thousand naira. One five, zero zero zero. You wan approve?"*
5. Customer declines (nothing moves) or approves with their passkey. **Server** verifies the signature, expiry and single use.
6. Bank sends a normal transfer built from the stored record only.
7. Customer hears the confirmation; agent sees "Paid ₦15,000" on their page plus their bank alert, then hands over the cash.

**Without the Agent page:** agent says their account number and bank; customer says it to Zolo (or picks a saved recipient); Zolo reads back the bank-verified name; customer says the amount, hears it back and approves.

**Voice transfer:** customer says *"Send 15k to my sister for Opay."* The AI finds the recipient and asks if unsure, then the same readback and approval.

### Flow B: Card Guard (secondary)

1. Card is locked by default. Every POS and ATM payment is declined.
2. Customer says *"Open my card for twenty thousand naira."* Zolo reads it back; customer approves with their passkey.
3. For a few minutes the card allows **one** payment up to ₦20,000.
4. Card is used normally. The PIN is still entered at the terminal (physical keypad if available). When the payment reaches the bank, it checks the stored rule instantly: within limit approved, above limit or second attempt declined.
5. Card relocks after one payment or when time runs out. Customer hears *"Your card don pay eighteen thousand five hundred to Mama Chi Stores."*

Card Guard does not hide the PIN. It makes a leaked PIN useless.

### Flow C: Phone-call approval (feature phone or no data)

1. Agent enters the amount and the customer's phone number on the Agent page.
2. Bank calls the registered number and reads the request in the customer's language: *"Press 1 to approve, 2 to reject."*
3. Customer presses 1 and enters their Zolo PIN on their own keypad. PIN is never spoken.
4. Transfer goes through; the call ends with a spoken confirmation and an SMS follows.

Phone-call approvals get lower limits than passkey approvals.

## Architecture

The consent engine is the only path to money: entry points can create requests, but only a verified signature lets the bank adapter execute.

&#91;embedded content: Zolo architecture · 3 entry points, 1 API, 3 services\]

In the hackathon the bank adapter is a mock that behaves like name enquiry, transfer and a card rule check. In production it calls the bank's own services. The AI agent has read tools (balance, saved recipients, name enquiry) and one write tool: create a draft request. It cannot approve or execute.

## Payment request lifecycle

A request only moves forward through these states, and the server refuses any out-of-order transition.

| State | Entered when | Next states |
| --- | --- | --- |
| `CREATED` | Agent, customer or AI agent drafts the request; name enquiry done | `READ_BACK`, `EXPIRED` |
| `READ_BACK` | Readback generated from the stored record and played | `APPROVED`, `DECLINED`, `EXPIRED` |
| `APPROVED` | Valid passkey signature (or phone-call PIN) received within the window | `SUBMITTED` |
| `SUBMITTED` | Transfer sent to the bank adapter with the request's idempotency key | `SETTLED`, `FAILED` |
| `SETTLED` | Bank confirms; both sides notified | (final) |
| `DECLINED` / `EXPIRED` / `FAILED` | Customer says no, 2 minutes pass, or the bank rejects | (final) |

### Data model (core tables)

- **payment\_request:** id, customer\_id, initiator (agent / customer / ai), payee\_account, payee\_bank, payee\_verified\_name, amount\_kobo, currency, nonce, idempotency\_key, intent\_hash, state, created\_at, expires\_at, approved\_at, channel (app / call).
- **passkey\_credential:** id, customer\_id, credential\_id, public\_key, sign\_count, device\_label, created\_at, revoked\_at.
- **card\_guard\_window:** id, customer\_id, card\_ref, max\_amount\_kobo, opens\_at, closes\_at, used (bool).
- **risk\_limit:** customer\_id, daily\_cap, per\_payment\_cap, new\_payee\_cap, call\_channel\_cap.
- **audit\_event:** id, request\_id, event, actor, timestamp, details (no raw voice).
- **agent:** id, account, bank, verified\_name, created\_at.

Amounts are stored in kobo as integers. `intent_hash` = SHA-256 over a canonical serialisation of the request fields that matter (payee, amount, nonce, expiry, request id).

### API endpoints

| Method and path | Purpose |
| --- | --- |
| `POST /agent/requests` | Agent creates a cash-out or payment request; returns code and QR |
| `POST /requests/claim` | Customer links to a request by code or QR |
| `POST /requests/draft` | Customer or AI agent drafts a transfer from voice |
| `GET /requests/{id}/readback` | Readback text and audio built from the stored record |
| `POST /requests/{id}/challenge` | Returns the WebAuthn challenge (derived from `intent_hash`) |
| `POST /requests/{id}/approve` | Verifies the passkey assertion; moves to `APPROVED` and submits |
| `POST /requests/{id}/decline` | Customer rejects |
| `GET /requests/{id}/status` | Status for agent page and customer app |
| `POST /card-guard/windows` | Opens a one-payment card window (passkey-signed) |
| `POST /mock-bank/card-auth` | Mock card payment checked against the open window |
| `POST /passkeys/register` | Registers a passkey after bank login and OTP |

## Security design

What the customer hears is exactly what they sign, and the server only executes what was signed.

### The consent chain

1. **Server creates the request.** Amount, bank-verified payee name, unique ID, nonce and a 2-minute expiry are stored before anything is read out.
2. **Readback comes from the stored record,** never from speech recognition, the AI agent or the phone.
3. **Challenge = hash of the request.** The WebAuthn challenge is derived from `intent_hash`, so the signature covers that exact amount and payee. This follows the logic of PSD2 dynamic linking.
4. **One use, one window.** A request accepts one valid signature within 2 minutes. Replays and second approvals are rejected.
5. **Execute from the stored record.** The transfer is built from the database row, never from fields the phone sends. An idempotency key stops double debits on retry.
6. **Voice never approves.** Speech only drafts. A cloned voice can propose, not pay.

### Device and account controls

- **Passkey registration** only after bank login plus OTP to the registered SIM. A new device triggers alerts on every channel and the CBN new-device limit (₦20,000 for the first 24 hours).
- **One active device** per customer. Recovery goes through branch or video KYC, never voice or chat alone.
- **Setup guidance:** customer sets their own screen lock privately; Zolo prefers fingerprint or face.
- **Emergency freeze** from any phone through the bank line or ZiVA.

### Risk rules

- Per-payment and daily caps set by the customer.
- New-payee cap and a cooling-off period before a large first payment.
- Unusual patterns (late night, rapid payments, new device) pause the request and trigger a call.
- Phone-call approvals have lower caps than passkey approvals; SIM-swap check before calling where available.
- **Card Guard:** locked by default; one payment per window; amount cap; auto-relock; daily count cap; stays locked if the phone is unreachable.

### Threat model

| Threat | Example | Control | Remaining risk |
| --- | --- | --- | --- |
| Spoofing | Cloned voice; helper knows the PIN | Voice is not a factor; device-bound passkey; Card Guard | Unlocked phone plus known screen lock |
| Tampering | Amount or payee changed after readback | Signature bound to `intent_hash`; execute from stored record | Malware controlling both audio and screen (rare) |
| Repudiation | "I never approved that" | Signed requests with time, device and readback text logged | Coerced but genuine approval |
| Information disclosure | PIN or balance overheard | Earpiece mode; passkey instead of PIN; voice not stored | Shoulder-surfing a phone-call PIN |
| Denial of service | Locked out by network or failures | Idempotent resume; phone-call fallback; branch recovery | Long network outages |
| Elevation of privilege | Helper gains standing control | No delegate approval; recovery needs bank identity checks | Long-term coercion at home |

### Data protection

HTTPS everywhere, encryption at rest, audit log of every state change, NDPA-compliant consent. Voice audio is processed and discarded, never stored.

## Failure handling

Every failure ends in a safe state: nothing moves unless the customer heard and signed it.

| # | Situation | Expected behaviour | Demo it? |
| --- | --- | --- | --- |
| 1 | Misheard amount ("fifteen" vs "fifty", low confidence) | Switch to keypad entry for the amount; nothing signed until confirmed | Yes |
| 2 | Wrong recipient (verified name doesn't match) | Customer says no; request declined | Yes |
| 3 | Amount changed after readback | Signature check fails; customer told "This payment changed after you heard it. Nothing was sent." | Yes |
| 4 | Replay of an old approval | Rejected as already used | Yes |
| 5 | Network drops during approval | Resume by idempotency key; no double debit; final status spoken | Yes |
| 6 | Fingerprint fails 3 times | Fall back to screen lock; then lock with a cooling-off period | If time |
| 7 | Cloned voice | Can draft only; no approval without passkey | Yes |
| 8 | Large first payment to a new payee at night | Cooling-off, private yes/no check, call to customer | If time |
| 9 | Noisy environment | Two retries, then offer text or keypad | Yes |
| 10 | Swapped card used with stolen PIN | Card Guard declines: card locked | If Card Guard built |
| 11 | Agent keys more than the unlocked amount | Card Guard declines: over limit | If Card Guard built |
| 12 | Request not approved in 2 minutes | Expires; agent creates a new one | Yes |

## Accessibility requirements

We build to WCAG 2.2 AA and test every screen with TalkBack and VoiceOver before it counts as done.

- Every control has a meaningful label; no "button, button".
- No time limits the user can't extend (the 2-minute request window is announced and can be renewed).
- No path or swipe gestures required; every action works with a single tap.
- Touch targets at least 48dp; high-contrast, large text for low-vision users.
- Amounts read in words and digits; account numbers read in groups.
- Earpiece or earphone mode for private readbacks.
- Passkey approval uses the phone's own prompt, which works with screen readers.
- Voice in Pidgin, Yoruba, Hausa, Igbo and English; English numerals understood mid-sentence.
- Any spoken step can also be done by typing or keypad.

## Tech stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Backend | FastAPI (Python), PostgreSQL | Pydantic models; SQLAlchemy or SQLModel; Alembic migrations |
| Passkeys | WebAuthn/FIDO2 (py\_webauthn on server, browser WebAuthn API on client) | Needs HTTPS and a stable domain |
| Front end | PWA (React or Next.js) | Customer app and Agent page; WCAG 2.2 AA |
| Speech to text | Spitch (Yoruba, Hausa, Igbo, English); Pidgin via English model plus naira grammar | Intron as alternative; N-ATLAS benchmarked only |
| Voice output | YarnGPT | Pidgin, Yoruba, Hausa, Igbo, English; pre-cache readback templates |
| AI agent | LLM with tool calling | Read tools plus one "draft request" tool; no execute tool |
| Amount parsing | Custom naira grammar | "15k", "fifteen thousand", Pidgin forms; confusable-pair guard |
| Phone call (stretch) | Africa's Talking voice API | Keypad (DTMF) approval |
| Bank rails | Mock bank adapter | Name enquiry, transfer, card rule; same interface as production |
| Hosting | Cloud host with HTTPS (e.g. Render, Railway or Vercel plus managed Postgres) | Local fallback server for the venue |

## Testing and validation

We prove it works with automated tests for the money logic and real blind testers for the experience.

- **Unit tests (must pass before demo):** state machine transitions, `intent_hash` canonicalisation, signature verification, expiry, single use, idempotency, risk rules, Card Guard window logic, naira amount parser.
- **Failure suite:** every row in Failure handling as a scripted, repeatable test and a demo button.
- **Speech test set:** about 50 real banking phrases per language (Pidgin, Yoruba, Hausa, Igbo, English), recorded by different speakers. Measure errors on the amount and payee only, and report the real numbers.
- **User testing:** 3 to 5 blind or low-vision testers. Measure unaided completion, time per cash-out, errors caught and whether anyone needed help.
- **Baseline comparison:** the same testers do the same ₦15,000 agent cash-out with a normal app and TalkBack, then with Zolo. One slide with both results.
- **Device check:** run the full flow on a low-cost Android phone with TalkBack and on an iPhone with VoiceOver.
- **Venue check:** test the demo on the venue network and on the local fallback server.

## Build plan

Pay by transfer end to end with the failure suite is the must-have; everything else is cut first if time runs short.

| When | Work | Priority |
| --- | --- | --- |
| Before the sprint | Repo, CI, HTTPS deploy; Spitch and YarnGPT access; speech test set; book blind testers | P0 |
| Day 1 | Consent engine: request model, state machine, `intent_hash`, passkey register and approve, idempotency; mock bank adapter (name enquiry, transfer) | P0 |
| Day 2 morning | Customer app and Agent page: claim by code, readback, approve, status; voice transfer via AI agent | P0 |
| Day 2 afternoon | Risk rules; failure suite as buttons; amount parser and keypad fallback. **Feature freeze at end of day.** | P0 |
| Day 2 stretch | Card Guard window and mock card payment | P1 |
| Day 3 morning | Blind-tester session; fix the top issues; record backup video | P0 |
| Day 3 afternoon | Rehearse demo and Q\&A; venue test | P0 |
| Only if ahead | Phone-call approval via Africa's Talking | P2 |

**Cut order if behind:** phone call, then Card Guard (keep as slide and Q&A answer), then extra languages in the live demo (keep Pidgin and English live, others recorded).

## Team roles

Each area has one owner who decides and reviews; fill in names below.

| Area | Owns | Owner |
| --- | --- | --- |
| Backend and security | Consent engine, passkeys, state machine, risk rules, mock bank, tests | \[Name\] |
| Front end and accessibility | Customer app, Agent page, TalkBack and VoiceOver testing | \[Name\] |
| Speech and AI | Spitch, YarnGPT, AI agent tools, amount parser, speech test set | \[Name\] |
| Product, demo and pitch | User testing, demo script, deck, Q&A, backup video | Akeem |

**Working rules:** main branch always deployable; small pull requests reviewed by one other person; no direct pushes to main after the feature freeze; secrets in environment variables, never in the repo.

## Demo plan

The moment judges should remember: a blind tester catches a wrong amount at a POS stand and still gets their cash, without touching a card or PIN.

### Script (about 3 minutes)

1. **Open (20s):** the Anambra widow story and the core rule.
2. **Fraud caught (60s):** the "agent" keys ₦51,000 under a different name. Zolo says in Pidgin what is being asked. Tester declines.
3. **Honest payment (40s):** agent corrects to ₦15,000. Tester approves with fingerprint; agent page shows "Paid"; cash handed over.
4. **Try to break it (30s):** invite a judge to tamper with the amount after the readback, or replay the approval. Signature check fails on screen.
5. **Card Guard (20s, if built):** swapped card with the stolen PIN is declined because it's locked.
6. **Close (10s):** results from the blind-tester session and the baseline comparison.

### Setup

- Real phone over HTTPS (passkeys need it), TalkBack or VoiceOver on.
- Mirror to the projector: scrcpy over USB for Android (`scrcpy --stay-awake`), HDMI adapter or AirPlay for iPhone.
- The fingerprint prompt may show black when mirrored, so a second camera on a small tripod films the tester's hands.
- Do Not Disturb on, screen timeout off, brightness up, spare cables and adapters.
- Local fallback server and a pre-recorded backup video of the full flow and failure cases.
- One teammate drives the demo; one speaks; nobody improvises the script.

## Hard questions from judges

Everyone on the team gives these same answers.

**How is this different from a normal transfer in an accessible app like OPay?** An accessible app lets a skilled screen-reader user send money. At an agent's stand they still have to get and type a 10-digit account number, pick a bank and enter a PIN, often with the agent offering to "help" by taking the phone. With Zolo the agent types, the customer only listens and approves with a fingerprint, and the phone never leaves their hand.

**Do you hold card payments open while the customer approves?** No. Card payments have short timeouts, so Card Guard uses a stored rule the bank checks instantly: the customer unlocks one payment up to an amount beforehand.

**Doesn't Card Guard still expose the PIN?** Yes, the PIN is still entered at the terminal. Pay by transfer is the private route. Card Guard makes a leaked PIN useless because the card is locked except for the one payment the customer approved.

**What if someone steals the phone?** Locked phone: nothing can be approved. Unlocked phone with a known screen lock: they can act within the customer's limits, as with any banking app, but caps, cooling-off periods and alerts limit the damage and the customer can freeze everything from any phone. We reduce that risk; we don't claim to remove it.

**What about feature phones or no data?** The bank calls the customer, reads the request in their language, and they approve with a PIN on their own keypad. Phone-call approvals get lower limits. India's UPI 123PAY uses the same model.

**Can a cloned voice move money?** No. Voice only drafts requests. Approval needs the passkey on the customer's phone.

**Does this work with Zenith today?** In the hackathon we use a mock that behaves like name enquiry, transfer and card controls. In production Zolo sits in front of the bank's existing services and channels such as ZiVA. We have not built a live integration and don't claim one.

**How accurate is the speech recognition?** We measured it on our own test set: \[fill in results\]. Speech only drafts; amounts are confirmed in words and digits and switch to keypad when confidence is low.

## Risks and open questions

| Risk | Impact | Mitigation |
| --- | --- | --- |
| No live Zenith access | Feasibility questioned | Mock with the same interface; say so openly |
| Speech accuracy unproven in our languages | Wrong drafts, slow demo | Own test set; keypad fallback; readback from bank data |
| Testers not available | Weak evidence | Book now; teammate under a blindfold as last resort, stated honestly |
| Venue network fails | Demo breaks | Local fallback server; backup video |
| Passkey prompt invisible when mirrored | Judges miss the key moment | Second camera on the tester's hands |
| Scope creep | Nothing finished | Feature freeze end of Day 2; cut order agreed |
| Coercion at home | Genuine but forced approvals | Cooling-off and checks reduce it; we don't claim to solve it |

**Open questions**

- [ ] Confirm Spitch and YarnGPT access and rate limits for the sprint.
- [ ] Confirm blind testers and dates.
- [ ] Agree team name and fill in owners.
- [ ] Decide React or Next.js for the PWA.
- [ ] Confirm the exact CBN new-device rule wording before quoting it on a slide.

## Roadmap

- **Pilot (8 to 12 weeks):** about 50 blind and low-vision customers through associations for the blind and 10 POS agents, capped limits. Measure unaided completion, errors caught, time per transaction, speech accuracy per language and fraud incidents. Target: zero unauthorised debits.
- **Phone-call approval** for feature phones, if not built in the sprint.
- **Relative proposes, holder approves:** a family member can start a payment; only the account holder approves it.
- **Direct agent requests** through NIBSS Request-to-Pay once it is available to consumers.
- **Other needs:** text-first flows for deaf users, switch access for motor impairments, naira note recognition.
- **Other banks and fintechs:** offer the same consent layer as an SDK.

## Sources

- [Nairametrics, 25 Sept 2026: CBN identifies 40 million Nigerians with disabilities as untapped fintech market](https://nairametrics.com/2026/09/25/cbn-identifies-40-million-nigerians-with-disabilities-as-untapped-fintech-market/)
- [Vanguard, Jan 2026: How failures in payment pillars, infrastructure lock out people with disabilities](https://www.vanguardngr.com/2026/01/how-failures-in-payment-pillars-infrastructure-lock-out-people-with-disabilities/)
- [Vanguard, Sept 2024: Trapped in digital dark](https://www.vanguardngr.com/2024/09/trapped-in-digital-dark-how-nigerias-financial-system-fails-persons-with-disabilities/)
- [BusinessDay: Locked out, Nigeria's 5.1m people with disabilities and banking barriers](https://businessday.ng/opinion/article/locked-out-nigerias-5-1m-people-with-disabilities-and-banking-barriers/)
- [Nairametrics, Mar 2026: CBN sets ₦20,000 limit for new mobile banking app activations](https://nairametrics.com/2026/03/13/cbn-sets-n20000-transaction-limit-for-new-mobile-banking-app-activations/)
- [EBA Q&A on PSD2 dynamic linking (RTS Article 5)](https://eba.europa.eu/single-rule-book-qa/qna/view/publicId/2019_4556)
- [UPI 123PAY (Digital India)](https://www.digitalindia.gov.in/initiative/upi-123pay/)
- [Spitch documentation](https://docs.spitch.app/)
- Anambra widow ATM card-swap case: Ripples Nigeria report (confirm the link before using it on a slide).
