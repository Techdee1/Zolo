"""voice_turn(): the only entry point the backend calls.

The AI proposes. The only write it can make is `create_draft`, which stores a DRAFT request and
returns its id. There is no approve, execute or change tool, and the readback the customer approves
against comes from the consent engine's stored record, not from here.

Phase 1 is deterministic: grammar plus parser, no language model. Every external call has a
5-second timeout; failures drop down the PRD's fallback ladder, ending in `handoff_keypad`.
Transcripts, replies and audio are never logged or stored: logs carry ids, timings, actions and
error codes only.
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

from zolo.ai.config import Settings
from zolo.ai.contracts import DraftService
from zolo.ai.nlu.amount import parse_amount
from zolo.ai.nlu.grammar import parse_utterance
from zolo.ai.nlu.recipients import MAX_OPTIONS, MatchResult, SavedRecipient, find_recipients
from zolo.ai.nlu.words import balance_words
from zolo.ai.replies import reply_text
from zolo.ai.resilience import CircuitBreaker
from zolo.ai.stt.base import SpeechToText
from zolo.ai.tts.factory import RoutingTTS
from zolo.ai.tts.readback import ReadbackService
from zolo.ai.types import LANGS, Lang, ProviderError

log = logging.getLogger("zolo.ai.voice")

Action = Literal["ask", "draft", "answer", "handoff_keypad"]
INTENT_OPTIONS = [
    {"label": "Send money", "value": "intent:send"},
    {"label": "Check balance", "value": "intent:balance"},
]
MAX_ASKS = 3  # clarifying questions per conversation, then keypad
MONEY_SAY = ("k", "naira", "thousand", "hundred", "million")
T = TypeVar("T")
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="zolo-ai")


@dataclass(frozen=True)
class VoiceResponse:
    conversation_id: str
    transcript: str
    reply_text: str
    reply_audio_url: str | None
    action: Action
    draft_request_id: str | None = None
    options: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """The POST /voice/turn response shape from the PRD."""
        return {
            "conversation_id": self.conversation_id,
            "transcript": self.transcript,
            "reply_text": self.reply_text,
            "reply_audio_url": self.reply_audio_url,
            "action": self.action,
            "draft_request_id": self.draft_request_id,
            "options": self.options,
        }


@dataclass
class _Conversation:
    """Slots and counters only. No transcripts, replies or audio."""

    intent: str | None = None
    amount_kobo: int | None = None
    recipient_id: str | None = None
    offered: dict[str, str] = field(default_factory=dict)  # option value -> "recipient" | "intent"
    pending_options: list[dict[str, str]] = field(default_factory=list)  # ambiguous recipients
    recipient_tried: bool = False
    asks: int = 0
    uncertain: int = 0
    stt_failures: int = 0
    touched: float = field(default_factory=time.monotonic)


class _Store:
    TTL_S = 600.0

    def __init__(self) -> None:
        self._d: dict[str, _Conversation] = {}
        self._lock = threading.Lock()

    def get(self, conversation_id: str | None) -> tuple[str, _Conversation]:
        with self._lock:
            now = time.monotonic()
            for k in [k for k, c in self._d.items() if now - c.touched > self.TTL_S]:
                del self._d[k]
            cid = conversation_id if conversation_id in self._d else (conversation_id or "")
            if cid not in self._d:
                cid = uuid.uuid4().hex
                self._d[cid] = _Conversation()
            conv = self._d[cid]
            conv.touched = now
            return cid, conv

    def drop(self, cid: str) -> None:
        with self._lock:
            self._d.pop(cid, None)


def _within(seconds: float, fn: Callable[[], T], code: str) -> T:
    """Run fn with a hard timeout; a hung provider cannot hold the turn."""
    fut = _pool.submit(fn)
    try:
        return fut.result(timeout=seconds)
    except FutureTimeout:
        raise ProviderError(code) from None


class VoiceService:
    def __init__(
        self,
        stt: SpeechToText,
        tts: RoutingTTS,
        settings: Settings,
        backend: DraftService,
        stt_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.stt, self.tts, self.settings = stt, tts, settings
        self.readbacks = ReadbackService(tts)
        self.backend = backend
        self.stt_breaker = stt_breaker or CircuitBreaker()
        self._store = _Store()

    # ------------------------------------------------------------------ entry point

    def voice_turn(
        self,
        customer_id: str,
        lang: str,
        conversation_id: str | None = None,
        audio: bytes | None = None,
        mime: str = "audio/webm",
        text: str | None = None,
        selected_option: str | None = None,
    ) -> VoiceResponse:
        t0 = time.monotonic()
        language: Lang = lang if lang in LANGS else "en"
        cid, conv = self._store.get(conversation_id)
        code = ""
        try:
            resp = self._turn(customer_id, language, cid, conv, audio, mime, text, selected_option)
        except ProviderError as exc:
            code = exc.code
            resp = self._respond(cid, "", "handoff_type", language, "handoff_keypad")
        except Exception:  # a bug must end in a safe state, never a draft
            code = "internal_error"
            resp = self._respond(cid, "", "handoff_form", language, "handoff_keypad")
        if resp.action in ("draft", "handoff_keypad"):
            self._store.drop(cid)
        log.info(
            "voice_turn conv=%s action=%s ms=%d err=%s",
            cid, resp.action, (time.monotonic() - t0) * 1000, code,
        )  # fmt: skip
        return resp

    # ------------------------------------------------------------------ the turn

    def _turn(
        self, customer_id: str, lang: Lang, cid: str, conv: _Conversation,
        audio: bytes | None, mime: str, text: str | None, selected_option: str | None,
    ) -> VoiceResponse:  # fmt: skip
        saved = self.backend.list_saved_recipients(customer_id)
        speech = False
        transcript = ""

        if selected_option is not None:
            return self._apply_option(customer_id, lang, cid, conv, saved, selected_option)

        if text is not None:
            if not self.settings.allow_text_input:
                return self._respond(cid, "", "unavailable", lang, "handoff_keypad")
            transcript = text.strip()
        elif audio is not None:
            if self.stt_breaker.is_open:
                return self._respond(cid, "", "handoff_type", lang, "handoff_keypad")
            heard = self._listen(audio, mime, lang, saved)
            if heard is None:
                return self._stt_failed(cid, conv, lang)
            transcript, speech = heard, True
            conv.stt_failures = 0
        else:
            return self._ask_or_handoff(cid, conv, lang, "", "ask_intent", INTENT_OPTIONS)

        # A fresh request needs at least two words; a one-word answer to our question is fine.
        if speech and len(transcript.split()) < (1 if conv.intent == "send" and transcript else 2):
            return self._uncertain(cid, conv, lang, transcript, "repeat")

        parsed = parse_utterance(transcript)
        if parsed.intent == "balance":
            return self._answer_balance(customer_id, lang, cid, transcript)

        if parsed.intent == "send":
            conv.intent = "send"
            if parsed.amount is not None and parsed.amount.kobo is not None:
                if parsed.amount.confusable or parsed.amount.confidence == "low":
                    conv.amount_kobo = None
                    return self._uncertain(cid, conv, lang, transcript, "ask_amount_again")
                conv.amount_kobo = parsed.amount.kobo
            if (
                parsed.account_number
            ):  # new recipients are typed so the name enquiry sees exact digits
                return self._respond(cid, transcript, "handoff_recipient", lang, "handoff_keypad")
            if parsed.recipient_phrase:
                self._set_recipient(conv, find_recipients(parsed.recipient_phrase, saved))
        elif conv.intent == "send":
            # A reply to our question: fill whichever slot is still empty.
            if conv.amount_kobo is None:
                a = parse_amount(transcript)
                if a.kobo is not None:
                    if a.confusable or a.confidence == "low":
                        return self._uncertain(cid, conv, lang, transcript, "ask_amount_again")
                    conv.amount_kobo = a.kobo
            if conv.recipient_id is None and transcript:
                self._set_recipient(conv, find_recipients(transcript, saved))
        else:
            return self._ask_or_handoff(cid, conv, lang, transcript, "ask_intent", INTENT_OPTIONS)

        return self._continue_send(customer_id, lang, cid, conv, saved, transcript)

    # ------------------------------------------------------------------ steps

    def _listen(
        self, audio: bytes, mime: str, lang: Lang, saved: list[SavedRecipient]
    ) -> str | None:
        words = [r.display_name for r in saved] + [r.bank for r in saved]
        try:
            t = _within(
                self.settings.request_timeout_s,
                lambda: self.stt.transcribe(audio, mime, lang, words),
                "stt_timeout",
            )
        except ProviderError as exc:
            if exc.code != "stt_disabled":
                self.stt_breaker.record_failure()
            log.info("stt failed err=%s", exc.code)
            return None
        self.stt_breaker.record_success()
        return t.text.strip() or None

    def _stt_failed(self, cid: str, conv: _Conversation, lang: Lang) -> VoiceResponse:
        conv.stt_failures += 1
        if conv.stt_failures >= 2 or self.stt_breaker.is_open:
            return self._respond(cid, "", "handoff_type", lang, "handoff_keypad")
        return self._ask_or_handoff(cid, conv, lang, "", "repeat")

    def _uncertain(
        self, cid: str, conv: _Conversation, lang: Lang, transcript: str, key: str
    ) -> VoiceResponse:
        """Uncertain: ask once, then hand off to the keypad."""
        if conv.uncertain >= 1:
            handoff = "handoff_amount" if key == "ask_amount_again" else "handoff_type"
            return self._respond(cid, transcript, handoff, lang, "handoff_keypad")
        conv.uncertain += 1
        return self._ask_or_handoff(cid, conv, lang, transcript, key)

    def _ask_or_handoff(
        self, cid: str, conv: _Conversation, lang: Lang, transcript: str, key: str,
        options: list[dict[str, str]] | None = None,
    ) -> VoiceResponse:  # fmt: skip
        if conv.asks >= MAX_ASKS:
            return self._respond(cid, transcript, "handoff_form", lang, "handoff_keypad")
        conv.asks += 1
        opts = options or []
        # Remember what we offered: only these answers are accepted back.
        conv.offered = {o["value"]: "intent" if o["value"].startswith("intent:") else "recipient"
                        for o in opts}  # fmt: skip
        return self._respond(cid, transcript, key, lang, "ask", options=opts)

    def _set_recipient(self, conv: _Conversation, result: MatchResult) -> None:
        conv.recipient_tried = True
        conv.recipient_id, conv.pending_options = None, []
        if result.status == "match" and result.recipient is not None:
            conv.recipient_id = result.recipient.id
        elif result.status == "ambiguous":
            conv.pending_options = result.options()

    def _continue_send(
        self, customer_id: str, lang: Lang, cid: str, conv: _Conversation,
        saved: list[SavedRecipient], transcript: str,
    ) -> VoiceResponse:  # fmt: skip
        if conv.recipient_id is None and conv.pending_options:
            options, conv.pending_options = conv.pending_options, []
            return self._ask_or_handoff(cid, conv, lang, transcript, "which_one", options)
        if conv.amount_kobo is None:
            return self._ask_or_handoff(cid, conv, lang, transcript, "ask_amount")
        if conv.recipient_id is None:
            if not saved:
                return self._respond(cid, transcript, "handoff_recipient", lang, "handoff_keypad")
            known = [{"label": f"{r.display_name}, {r.bank}", "value": r.id} for r in saved]
            key = "not_found" if conv.recipient_tried else "ask_recipient"
            return self._ask_or_handoff(cid, conv, lang, transcript, key, known[:MAX_OPTIONS])
        if conv.recipient_id not in {r.id for r in saved}:
            return self._respond(cid, transcript, "handoff_recipient", lang, "handoff_keypad")
        request_id = self.backend.create_draft(customer_id, conv.recipient_id, conv.amount_kobo)
        return self._respond(
            cid, transcript, "read_back", lang, "draft", draft_request_id=request_id
        )

    def _apply_option(
        self, customer_id: str, lang: Lang, cid: str, conv: _Conversation,
        saved: list[SavedRecipient], value: str,
    ) -> VoiceResponse:  # fmt: skip
        meaning = conv.offered.get(value)
        if meaning is None:  # only answers we offered are accepted
            return self._ask_or_handoff(cid, conv, lang, "", "ask_intent", INTENT_OPTIONS)
        conv.offered = {}
        if value == "intent:balance":
            return self._answer_balance(customer_id, lang, cid, "")
        conv.intent = "send"
        if meaning == "recipient":
            conv.recipient_id, conv.recipient_tried = value, True
        return self._continue_send(customer_id, lang, cid, conv, saved, "")

    def _answer_balance(
        self, customer_id: str, lang: Lang, cid: str, transcript: str
    ) -> VoiceResponse:
        kobo = self.backend.get_balance(customer_id)
        return self._respond(
            cid, transcript, "balance", lang, "answer", amount=balance_words(kobo)
        )  # fmt: skip

    # ------------------------------------------------------------------ output

    def _respond(
        self, cid: str, transcript: str, key: str, lang: Lang, action: Action,
        options: list[dict[str, str]] | None = None, draft_request_id: str | None = None,
        **fmt: str,
    ) -> VoiceResponse:  # fmt: skip
        text = reply_text(key, lang, **fmt)
        # Cached audio if we have it; otherwise text now and a background render for next time.
        url = self.readbacks.get(text, lang, wait_s=self.settings.reply_audio_wait_s).audio_url
        return VoiceResponse(cid, transcript, text, url, action, draft_request_id, options or [])
