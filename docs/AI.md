# AI in Zolo: what it does, what it may never do, and how it is kept honest

The full engineering record is [`AI_IMPLEMENTATION.md`](AI_IMPLEMENTATION.md). This page is the summary an
auditor or a new engineer needs.

## Where AI is used

| Use | Provider | Status |
| --- | --- | --- |
| **Text to speech** for the readback ("who is asking, how much") and fixed status lines, in five languages | YarnGPT (hosted) | **Live in the demo.** Rendered in the background, cached as mp3 by a hash of (provider, language, voice, exact words) |
| **Speech to text** for a spoken payment request | Spitch (hosted) | Built and tested with fakes and synthetic clips; **off by default** (`STT_LIVE_ENABLED=false`) and not exposed over HTTP in Phase 1 |
| **Understanding** a spoken request ("send 15k to Tunde") | Deterministic grammar, fuzzy recipient matching. **No language model** | Built and tested; Phase 2 surface |

There is deliberately **no generative model anywhere on the payment path**.

## The boundary: the AI proposes, the consent engine and the customer decide

1. The AI package has two reads (`get_balance`, `list_saved_recipients`) and **one write: `create_draft`**,
   which can only create a DRAFT request. There is no approve, execute, cancel or limit-changing method in it.
2. **The AI never writes the words a customer approves.** The readback is a fixed, versioned template
   (`backend/zolo/ai/readbacks/*.txt`) filled from the stored request row. The audio is a rendering of that
   exact sentence, never a paraphrase.
3. **Voice is never an identity check.** Approval needs a passkey signature over the payment's hash. A
   voice, a transcript or a "yes" can never approve a payment.
4. **Any failure degrades to the keypad or to plain text.** Any exception in a voice turn ends in
   `handoff_keypad`; a missing key, a rate limit or a provider outage yields the text readback and the
   screen reader reads it. A bug cannot produce a payment.
5. The AI never asks for or hears a PIN, card number or OTP.

## Safety properties that are enforced in code, not just stated

- **Uncertainty is surfaced, not guessed.** Confusable amounts (`15,000` vs `50,000`, "k" vs "hundred") and
  sound-only name matches are never confident: the customer is asked to choose, at most three times, then
  handed to the keypad.
- **No transcripts, replies or customer audio are logged or stored.** Logs carry ids, timings, actions and
  reason codes only. The audio cache holds only Zolo's own synthesised sentences, named by hash, so the
  directory contains no readable payment details.
- **Cost control.** Each sentence is rendered once, ever. Rendering is on a background thread with a
  timeout; a failed line is not retried for 60 seconds; agents are limited to 10 requests a minute, which
  caps spend. The clip tool stops immediately on a quota error and waits out rate limits.
- **Language fallback instead of mispronunciation.** Yoruba, Hausa and Igbo readbacks are returned in
  that language only when a recording of the exact sentence exists; otherwise the English readback comes
  back with `fallback_from` set, and the app says so. A screen reader never reads those languages aloud.
- **The audio path is out of the approval path.** Live synthesis takes 3 to 7 seconds, so it never blocks
  an approval; the customer simply gets text if a clip is late.

## Languages and the clip set

English, Pidgin, Yoruba, Hausa and Igbo. The readback endpoint accepts all five. A set of mono 40 kbps mp3
clips ships in `backend/audio_seed/` (110 of a planned 162 at the time of writing; the rest wait on the
provider's rate limit) so the demo amounts have a voice even on a host with no persistent disk. Rebuild
with `python -m zolo.tools.render_clips` (see [`DEPLOY.md`](DEPLOY.md)). Voices: `idera` primary for all
languages, `jude` as a backup for English and Pidgin; chosen from the provider's descriptions, not yet
judged by listeners.

## Known gaps (stated plainly)

- **Data retention at Spitch and YarnGPT is unconfirmed.** Do not claim "no retention" to customers or
  judges until it is confirmed in writing. The product copy makes no privacy claim beyond what the system
  does.
- Pidgin wording has not been natively reviewed. Yoruba, Hausa and Igbo wording was reported approved by
  native speakers (2026-10-22). The Yoruba, Hausa and Igbo readback templates carry no tone marks.
- Real-speech accuracy is unmeasured (no speech test set), and voice quality has not been judged by native
  listeners. Voice turns have not been run end to end with a real microphone.

## How AI was used to build this repository

The code was written with an AI coding assistant working under a human owner who set requirements, reviewed
results and made every product decision. What kept that safe: a written brief and PRDs; tests written
alongside every change (and mutation checks that plant bugs to see whether tests notice); CI that must stay
green; and a deviations log that records every place the build departs from the PRDs. Generated clients are
checked against the backend's OpenAPI contract in CI.
