# Zolo AI and Speech: Implementation Record

Living document. Updated as each phase lands. Source of truth for what the AI package does today is the code in `backend/zolo/ai/`; the requirements are in [AI_PRD.md](../AI_PRD.md). Where this record and the PRD disagree, this record says what was actually built and why.

**Last updated:** 2026-10-21 · **Branch:** `ai-phase-1` · **Tests:** 383 passing (offline) · **Type check:** mypy strict clean · **Lint:** ruff clean

## 1. Status

| Phase | State | Notes |
| --- | --- | --- |
| 1. Voice MVP (no language model) | **Built and tested** | Not yet wired into the backend: the backend's Phase 1 (consent engine, passkeys, mock bank, HTTP API) exists on branch `backend-phase-1` but does not implement `DraftService` yet (that is backend Phase 2; see section 7). |
| 2. Smart agent (LLM, tools) | Not started | Behind `AI_AGENT_ENABLED`, default off. `agent/` and `eval/` do not exist yet. |
| 3. Final-ready | Not started | Native-speaker review of Pidgin, Yoruba, Hausa, Igbo wording; phone-call prompts. |

### Phase 1 exit checklist

| Box | Result | Caveat |
| --- | --- | --- |
| Parser and number-to-words pass every table row and confusable pair | Pass | |
| Spitch transcribes a clip in each language | Pass | Tested on synthetic YarnGPT clips, not real speakers. |
| YarnGPT readbacks in 5 languages, demo lines pre-rendered | Pass | 67 clips cached. Nobody has listened to them; non-English wording is unreviewed. |
| `voice_turn()` handles "send X to Y" and "check balance" with the grammar only | Pass | Tested with fakes. Not run end to end with real microphone audio. |
| With all AI providers off, typed and keypad flow still works | Pass for the AI side | The typed form and keypad belong to the app and backend, which do not exist yet. |

## 2. The boundary

The AI proposes; the consent engine and the customer decide.

- The AI has **two reads and one write**: `get_balance`, `list_saved_recipients`, and `create_draft` (a DRAFT request only). There is no approve, execute, cancel or limit-changing method anywhere in the package.
- The AI never writes the readback a customer approves against. Readbacks are fixed templates filled from the stored request.
- Voice is never an identity check. The AI never asks for or hears a PIN, card number or OTP.
- Transcripts, replies and audio are **never logged**. Logs carry conversation ids, timings, actions and error codes only. Customer audio is never stored (the audio cache holds only our own synthesised replies).

## 3. How a voice turn works

`VoiceService.voice_turn(customer_id, lang, conversation_id, audio | text | selected_option)` in [service.py](../backend/zolo/ai/service.py) is the single entry point. It returns the PRD response shape:

```json
{"conversation_id": "...", "transcript": "...", "reply_text": "...", "reply_audio_url": "... or null",
 "action": "ask | draft | answer | handoff_keypad", "draft_request_id": "... or null", "options": []}
```

Order of work inside a turn:

1. **Input.** A tapped option, typed text (only if `ALLOW_TEXT_INPUT`), or audio. Audio is converted by ffmpeg to 16 kHz mono wav, then sent to Spitch with the customer's recipient names, bank names and money words as `special_words`.
2. **Uncertainty check.** A turn is *uncertain* if the transcript is empty, has under 2 words (fresh requests only; one-word answers to our own question are fine), or the amount is confusable or low confidence.
3. **Understanding.** Deterministic grammar ([grammar.py](../backend/zolo/ai/nlu/grammar.py)) finds the intent (send, balance, unknown), amount, recipient phrase, bank and any account number. English and Pidgin phrasing.
4. **Recipient.** Fuzzy match against saved recipients. Match, ambiguous (top two offered), or none.
5. **Decision.**
   - Amount and recipient both resolved and not uncertain: `create_draft`, return `draft`.
   - Something missing or ambiguous: `ask` with tappable options.
   - Uncertain: **ask once, then `handoff_keypad`**. Three clarifying questions per conversation at most.
   - Balance: `answer`.
   - A typed account number: `handoff_keypad` (new recipients are typed so the name enquiry sees exact digits).
6. **Reply.** Fixed reply text from `readbacks/replies.json`, voiced from cache (see section 6).

Any exception ends in `handoff_keypad`. A bug can never produce a draft.

### Fallback ladder as built

| Component | Primary | Fallback 1 | Fallback 2 |
| --- | --- | --- | --- |
| Understanding | (LLM agent, Phase 2) | Deterministic grammar | `handoff_keypad` (form) |
| Speech to text | Spitch | (Intron/YarnGPT `/asr`, Phase 2) | Typed text or keypad |
| Amount | Parser, flagged if confusable | Ask once | Keypad |
| Voice output | Cached audio | Background render, text now | Screen reader / on-device speech (English) |

Every STT call has a 5-second hard timeout. A circuit breaker switches STT off for 60 seconds after 3 failures in a row. An STT failure asks the customer to repeat once, then hands off.

## 4. Amounts and names

### Amount parser ([amount.py](../backend/zolo/ai/nlu/amount.py))

- Returns integer **kobo**, a confidence (`high` or `low`), a `confusable` flag and the span. Returns `None` rather than guess.
- Handles `15k`, `15,000`, `fifteen thousand`, digit by digit (`one five zero zero zero`), `1.5m`, `half a million`, `a thousand`, and more. Kobo, amounts below ₦1 and fractional naira are rejected. Phone and account numbers are not amounts. Two different amounts in one utterance give `None`; the same amount said twice is accepted.
- **Confusable is decided by value.** If the English words for the amount contain a teen or "ty" word (thirteen to nineteen, thirty to ninety), it is confusable, whether it arrived as words, digits or `k`. So `15,000`, `15k` and `fifteen thousand` are all flagged, as are `50,000` and `250,000`. A bare "X hundred" or a spelled "X k" is also flagged (k versus hundred cannot be heard in text).
- **Yoruba** ([yoruba.py](../backend/zolo/ai/nlu/yoruba.py)): common amounts up to 500,000 (tens, hundreds, thousands, ọ̀kẹ́, joined by *àti* or *ó lé*). Used only when no English number words are found. Anything unclear returns no amount. **Unreviewed by a native speaker.**
- Hausa and Igbo number words are not implemented (Phase 3). Spitch returns Igbo and Pidgin amounts as digits, which the parser handles.

### Recipient matching ([recipients.py](../backend/zolo/ai/nlu/recipients.py))

- Fuzzy by word, with aliases (`my sister`), bank words (`for opay`) and diacritics stripped. Words of 3 letters or fewer must match exactly.
- Handles speech-to-text mangles: letter-by-letter spellings (`b c` becomes `bc`, which sounds like `Bisi`), consonant-skeleton matches (`busy`, `Bisi`, `Bose` share `bs`), and split or merged words (`chi nedu`).
- **A match that rests on sound alone is never confident.** It returns `ambiguous` so the customer confirms. Ambiguity offers the **top two** options.
- A bank word that disagrees with the only name match is treated as ambiguous.

Measured on [mangled_names.json](../backend/tests/ai/data/mangled_names.json) (58 cases, 13 saved recipients; only 6 rows are real Spitch output, 52 are hand-written, so these are rates on this set, not on customers):

| Outcome | Cases |
| --- | --- |
| Confident and correct | 41 |
| Asked, right person in the top two | 10 |
| Miss ("mama she stores") | 1 |
| Wrong confident match | **0** |
| False hit on an unsaved name | **0** |
| Unsaved names correctly rejected | 6 of 6 |

Re-run with `python -m zolo.ai.tools.name_match_report`.

## 5. Speech to text ([stt/](../backend/zolo/ai/stt/))

Verified against the docs and the installed SDK, not the PRD's assumptions:

| PRD assumed | Reality |
| --- | --- |
| webm/opus accepted | Spitch takes mp3, wav, m4a, ogg only, max 25 MB. Everything is converted server-side. |
| Confidence returned | **No confidence.** `Transcript.confidence` is always `None`. We do not invent one; uncertainty comes from the parser and rules above. |
| Pidgin model | None. Pidgin uses the English model (`en`). |
| Audio retention | **Unconfirmed.** The SDK sends `X-Data-Retention: True` by default; we send `False`, but have not verified Spitch honours it. |

- ffmpeg emits raw PCM and we wrap a proper wav header (piped wav headers claim a 37-hour length). Clips are capped at 15 seconds. Dev and CI use the bundled `imageio-ffmpeg` binary; **production needs ffmpeg installed** (no Dockerfile exists yet).
- Live smoke test (5 calls, synthetic clips): 1.1–1.7 seconds per call, all five languages work. Observed quirks: names are mangled (`Bisi` became `bc`, `busy`, `b c`); Yoruba amounts come back as Yoruba words; Pidgin and Igbo amounts as digits; Hausa digits as `1,5 sifiri sifiri sifiri`.
- `STT_LIVE_ENABLED` defaults to **false** to protect credits. Tests use `FakeSTT` only. Calls per day are counted (count only) in `var/stt_calls.json`.

## 6. Voice output ([tts/](../backend/zolo/ai/tts/))

- YarnGPT, hosted API only. Job flow: `POST /api/v1/tts` (with `Idempotency-Key`), poll `GET /api/v1/status/{job_id}`, download the signed link **without** our API key. Pidgin text is sent with `target_language: "en"` (no Pidgin code exists).
- **Live synthesis takes 3 to 7 seconds** per short line, far over the PRD's 2-second budget. So replies are served from a **byte cache** keyed by hash of (provider, lang, voice, text); the text itself is not stored.
- **Readback fallback chain** ([readback.py](../backend/zolo/ai/tts/readback.py)): cached audio returns at once; otherwise the text returns immediately and a background render fills the cache. One render per line at a time; a failed line is not retried for 60 seconds. English responses carry `device_speech_after_s` (2.0 while rendering, 0.0 if nothing is rendering) so the client can use on-device speech; other languages get text for the screen reader.
- YarnGPT rejects very short text (`INPUT_TOO_SHORT`), so short phrases were lengthened.
- Provider is configurable per language (`TTS_PROVIDER_<LANG>`), voice per language (`TTS_VOICE_<LANG>`, default `idera`, YarnGPT's own default; **no one has judged which voice is most natural**).
- Retention of synthesised audio is **not stated** by YarnGPT's docs.

### Readbacks

Fixed templates in [readbacks/](../backend/zolo/ai/readbacks/) (`en`, `pcm`, `yo`, `ha`, `ig`), versioned, filled from the stored request. The PRD's example is reproduced exactly: *"Bisi Ventures dey ask for fifteen thousand naira. One five, zero zero zero. You wan approve?"* Words and digits come from the same amount.

Pre-rendered content: the demo script, every static reply, and extra scenarios (`scenarios.json`). 67 clips are cached.

## 7. Backend contract ([contracts.py](../backend/zolo/ai/contracts.py))

The backend implements this Protocol and passes it to `VoiceService`:

```python
class DraftService(Protocol):
    def create_draft(self, customer_id: str, recipient_ref: str, amount_kobo: int) -> str: ...
    def get_balance(self, customer_id: str) -> int: ...                       # kobo
    def list_saved_recipients(self, customer_id: str) -> list[SavedRecipient]: ...
```

- `create_draft` stores a DRAFT and returns the request id; the AI never sees the stored record. The backend must validate `recipient_ref` and `amount_kobo` itself.
- `SavedRecipient(id, display_name, bank, last4, aliases)`. No full account numbers.
- `zolo.ai.fakes.FakeBackend` is the in-memory version used in tests.
- **The signature was designed by the AI team without reading the backend spec; the backend should confirm or change it.**

**Backend status (branch `backend-phase-1`, as of 2026-10-21):**
- The backend reuses this package's readback templates and number-to-words (`render_readback`), so the words on screen, the words in the pre-rendered audio and the words in the signed intent come from one place. It looks readback audio up in this package's cache; for that to hit, the bank's capitals are title-cased ("BISI VENTURES" becomes "Bisi Ventures"). Verified against the real pre-rendered clips for the demo amounts.
- A `saved_recipients` table and a tested mapper to this package's `SavedRecipient` exist (`zolo/voice/recipients.py`); nothing is wired to a `DraftService` yet.
- **Known mismatch to resolve in backend Phase 2:** `create_draft(recipient_ref, ...)` takes a saved-recipient id, but a payment request's payee must be a `bank_accounts` row. Creating a draft from a saved recipient therefore has to run a name enquiry and upsert an outside bank account first.

## 8. Configuration

Keys come from environment variables only. See [.env.example](../backend/.env.example).

| Variable | Default | Purpose |
| --- | --- | --- |
| `SPITCH_API_KEY`, `YARNGPT_API_KEY` | none | Provider keys. Never committed. |
| `STT_LIVE_ENABLED` | false | Allow real Spitch calls. On only in the demo environment. |
| `TTS_LIVE_ENABLED` | false | Allow live YarnGPT renders (otherwise cache only). |
| `ALLOW_TEXT_INPUT` | false | Dev: typed text in place of audio. |
| `AI_AGENT_ENABLED` | false | Phase 2. Nothing reads it yet. |
| `TTS_PROVIDER_<LANG>`, `TTS_VOICE_<LANG>` | yarngpt, idera | Per-language provider and voice. |
| `AUDIO_CACHE_DIR`, `STT_CALL_COUNT_FILE` | `var/audio`, `var/stt_calls.json` | Local state, gitignored. |

## 9. Package map

```
backend/zolo/ai/
  types.py  config.py  contracts.py  fakes.py  resilience.py  usage.py
  service.py            voice_turn(): the only entry point
  replies.py  demo_script.py
  nlu/       amount.py  words.py  yoruba.py  recipients.py  banks.py  grammar.py
  stt/       base.py  spitch.py  audio.py  fake.py
  tts/       base.py  yarngpt.py  cache.py  readback.py  factory.py  fake.py
  readbacks/ en|pcm|yo|ha|ig.txt  replies.json  demo_script.json  scenarios.json
  tools/     prerender_demo  prerender_scenarios  pidgin_listening_test  stt_smoke  name_match_report
backend/tests/ai/   (383 tests; fakes only, never calls a provider)
```

### Tools (manual; some cost credits)

| Command | Costs credits | Purpose |
| --- | --- | --- |
| `python -m zolo.ai.tools.prerender_demo [--dry-run]` | YarnGPT | Render all demo and reply lines; skips cached. |
| `python -m zolo.ai.tools.prerender_scenarios [--dry-run]` | YarnGPT | Render extra demo variants; skips cached. |
| `python -m zolo.ai.tools.pidgin_listening_test` | YarnGPT | Pidgin readbacks as mp3 for a native-speaker listening test. **Not yet run.** |
| `python -m zolo.ai.tools.stt_smoke --live` | Spitch | One call per language on cached clips; transcripts cached. |
| `python -m zolo.ai.tools.name_match_report` | None | Score recipient matching. |

## 10. Decision log

| Decision | Why |
| --- | --- |
| Spitch confidence is `None` | The API returns none; inventing one would fake certainty. |
| Uncertain means ask once, then keypad | A wrong amount is the most expensive mistake; the keypad is exact. |
| Confusable by value, not by spelling | Speech engines often return digits (`15,000`), which bypass a words-only rule. |
| Typed text follows the same confusable rule as speech | The dev text path should behave like the real one. |
| One-word answers to our own question are not uncertain | Otherwise "5000" after "How much?" would always bounce. |
| Sound-alike recipient matches ask, never assume | "Busayo" must not silently become "Bisi". |
| Cache holds bytes, not URLs | Provider links expire in about an hour. |
| Replies never block on live synthesis | It takes 3 to 7 seconds. |
| New recipients (typed account number) go to the keypad | Name enquiry needs exact digits; not built in Phase 1. |

## 11. Known gaps and risks

- **Wording is unreviewed.** Pidgin (from the PRD), Yoruba, Hausa and Igbo text in `readbacks/` and `replies.json` needs native speakers before it is used with customers. Yoruba, Hausa and Igbo templates are machine-written drafts, not for the demo.
- **Yoruba numerals** are from published tables, not reviewed. Hausa and Igbo number words and non-English grammar verbs are not implemented.
- **Voice choice, Pidgin quality and audio quality** are unjudged by any listener.
- **Data retention** for Spitch and YarnGPT is unconfirmed. Do not claim "no retention" to customers, judges or in the NDPA notice until confirmed in writing.
- **Real-speech accuracy is unmeasured.** The name set is mostly hand-written; no speech test set (about 250 clips) exists yet.
- **No end-to-end run** with real microphone audio and a real backend.
- **No Dockerfile**, so ffmpeg is not installed anywhere but the dev bundle.
- **Backend timeouts:** STT and TTS have 5-second limits; calls into `DraftService` do not. The backend owns those.
- Both provider API keys were pasted into a chat session. Rotate them after the hackathon.

## 12. Credits log

| Date | Provider | What | Calls |
| --- | --- | --- | --- |
| 2026-10-21 | YarnGPT | One latency probe; first demo pre-render (35 lines, 2 rejected as too short); re-render of the changed and new reply lines (20); scenario pre-render (14) | about 70 |
| 2026-10-21 | YarnGPT | `GET /voices` (read only) | 1 |
| 2026-10-21 | Spitch | Live smoke test, one per language | 5 |

Add a row whenever credits are spent.

## 13. Changelog

| Date | Change |
| --- | --- |
| 2026-10-21 | **Phase 1 built.** Package, interfaces and fakes; amount parser and number-to-words; recipient matching; grammar; Spitch STT with ffmpeg conversion; YarnGPT TTS with byte cache and pre-render tools; `voice_turn()`. 206 tests. |
| 2026-10-21 | **Backend integration notes.** Backend Phase 1 built separately (see `backend/README.md`); readback text and audio keys verified against it. No AI code changed. |
| 2026-10-21 | **Phase 1 follow-ups.** Confusable by value (words and digits). `DraftService` backend contract and `FakeBackend`. Readback fallback chain and scenario pre-render. Yoruba numerals. Phonetic recipient matching with a 58-case set. Committed on `ai-phase-1` in 7 commits. 383 tests. |

## 14. Next

1. Backend implements `DraftService` and wires `POST /voice/turn` and `GET /voice/audio/{key}.mp3`.
2. Native-speaker review: Pidgin listening test first, then Yoruba, Hausa and Igbo wording.
3. Confirm Spitch and YarnGPT retention terms in writing.
4. Record the speech test set and measure real amount and recipient accuracy.
5. Phase 2: agent loop behind `AI_AGENT_ENABLED` (parser and agent must agree or the turn asks or goes to keypad), YarnGPT `/asr` as a second STT engine, injection tests, eval script.
