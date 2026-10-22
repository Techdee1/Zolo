"""Do the tests notice a bug? Plant one deliberate bug at a time, in a THROWAWAY COPY of the
code, run the tests, and report any bug that no test catches ("survivors").

    uv run python scripts/mutation_sweep.py            # all mutations
    uv run python scripts/mutation_sweep.py M06 M22    # just these

It uses its own database (zolo_mutation, created on demand in the same Postgres), so it can run
while you run the normal test suite. The real source tree is never modified.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAST_FIRST = [
    "tests/unit",
    "tests/integration/test_schema.py",
    "tests/integration/test_consent_engine.py",
    "tests/integration/test_passkeys.py",
    "tests/integration/test_state_matrix.py",
    "tests/integration/test_mock_bank.py",
    "tests/api",
]


@dataclass(frozen=True)
class Mutation:
    id: str
    what: str  # the bug, in words
    file: str
    anchor: str  # a unique piece of text just before the line to change
    old: str
    new: str


M = Mutation
MUTATIONS: list[Mutation] = [
    # --- who may touch a request
    M(
        "M01",
        "anyone can hear someone else's readback",
        "zolo/consent/service.py",
        "async def get_readback(",
        "if row.customer_id != customer_id:",
        "if False:",
    ),
    M(
        "M02",
        "anyone can decline someone else's request",
        "zolo/consent/service.py",
        "async def decline(",
        "if row.customer_id != customer_id:",
        "if False:",
    ),
    M(
        "M03",
        "anyone can get a challenge for someone else's request",
        "zolo/consent/service.py",
        "async def issue_challenge(",
        "if row.customer_id != customer_id:",
        "if False:",
    ),
    M(
        "M04",
        "anyone can approve someone else's request",
        "zolo/consent/service.py",
        "async def _approve(",
        "if seen.customer_id != customer_id:",
        "if False:",
    ),
    M(
        "M05",
        "a second customer can claim an already-claimed code",
        "zolo/consent/service.py",
        "async def claim(",
        "elif row.customer_id != customer_id:",
        "elif False:",
    ),
    M(
        "M06",
        "another agent can read an agent's request",
        "zolo/consent/service.py",
        "async def _visible(",
        "ok = payee is not None and payee.agent_id == viewer.id",
        "ok = True",
    ),
    # --- time
    M(
        "M07",
        "a request is not expired exactly at its deadline",
        "zolo/consent/service.py",
        "async def _expire_if_due(",
        "row.expires_at > now",
        "row.expires_at >= now",
    ),
    M(
        "M08",
        "approval allowed exactly at the deadline",
        "zolo/consent/service.py",
        "async def _approve(",
        "if row.expires_at <= now:",
        "if row.expires_at < now:",
    ),
    M(
        "M09",
        "the approval move forgets to check expiry",
        "zolo/consent/service.py",
        "moved = await apply_transition(\n            session, row.id, State.READ_BACK, State.APPROVED,",
        "PaymentRequest.expires_at > now,\n                PaymentRequest.intent_hash == digest,",
        "PaymentRequest.intent_hash == digest,",
    ),
    M(
        "M10",
        "the approval move forgets to check the hash",
        "zolo/consent/service.py",
        "moved = await apply_transition(\n            session, row.id, State.READ_BACK, State.APPROVED,",
        "PaymentRequest.intent_hash == digest,",
        "PaymentRequest.id.is_not(None),",
    ),
    M(
        "M11",
        "declining forgets the expiry guard",
        "zolo/consent/service.py",
        "async def decline(",
        "guards=[PaymentRequest.customer_id == customer_id, PaymentRequest.expires_at > now],",
        "guards=[PaymentRequest.customer_id == customer_id],",
    ),
    # --- money rules
    M(
        "M12",
        "the risk check is skipped at approval",
        "zolo/consent/service.py",
        "async def _approve(",
        "if not decision.allowed:",
        "if False:",
    ),
    M(
        "M13",
        "settled payments do not count toward the daily cap",
        "zolo/consent/service.py",
        "SIGNED_STATES = (",
        "State.APPROVED.value, State.SUBMITTED.value, State.SETTLED.value",
        "State.APPROVED.value, State.SUBMITTED.value",
    ),
    M(
        "M14",
        "no per-payment cap when an agent creates a request",
        "zolo/consent/service.py",
        "async def create_agent_request(",
        "if not check_per_payment(amount_kobo, global_limits(self.settings)).allowed:",
        "if False:",
    ),
    M(
        "M15",
        "amounts with kobo are accepted",
        "zolo/consent/service.py",
        "async def create_agent_request(",
        " or amount_kobo % 100 != 0",
        "",
    ),
    M(
        "M16",
        "a customer can raise their own cap above the hard cap",
        "zolo/risk/service.py",
        "return Limits(",
        "min(row.per_payment_kobo, hard.per_payment_kobo), min(row.daily_kobo, hard.daily_kobo)",
        "row.per_payment_kobo, row.daily_kobo",
    ),
    M(
        "M17",
        "daily cap is exclusive instead of inclusive",
        "zolo/risk/rules.py",
        "def check_daily(",
        "> limits.daily_kobo",
        ">= limits.daily_kobo",
    ),
    M(
        "M18",
        "per-payment cap is exclusive instead of inclusive",
        "zolo/risk/rules.py",
        "def check_per_payment(",
        "> limits.per_payment_kobo",
        ">= limits.per_payment_kobo",
    ),
    M(
        "M19",
        "a retried transfer uses a NEW idempotency key (double debit)",
        "zolo/consent/service.py",
        "result = await self.bank.transfer(",
        "idempotency_key=row.idempotency_key,",
        "idempotency_key=uuid.uuid4(),",
    ),
    M(
        "M20",
        "the bank lets an account overdraw by exactly its balance",
        "zolo/bank/mock.py",
        "async def _move(",
        "if rows[source].balance_kobo < amount_kobo:",
        "if rows[source].balance_kobo < amount_kobo - 1:",
    ),
    # --- passkeys and challenges
    M(
        "M21",
        "someone else's passkey is accepted",
        "zolo/passkeys/service.py",
        "async def verify_assertion(",
        "PasskeyCredential.customer_id == customer_id,",
        "PasskeyCredential.id.is_not(None),",
    ),
    M(
        "M22",
        "a revoked passkey is still accepted",
        "zolo/passkeys/service.py",
        "async def verify_assertion(",
        "PasskeyCredential.revoked_at.is_(None),",
        "PasskeyCredential.id.is_not(None),",
    ),
    M(
        "M23",
        "an expired challenge is still accepted",
        "zolo/passkeys/service.py",
        "async def current_challenge(",
        "WebAuthnChallenge.expires_at > self.clock(),",
        "WebAuthnChallenge.id.is_not(None),",
    ),
    M(
        "M24",
        "a challenge can be spent twice",
        "zolo/passkeys/service.py",
        "async def consume_challenge(",
        "WebAuthnChallenge.id == challenge_id, WebAuthnChallenge.used_at.is_(None)",
        "WebAuthnChallenge.id == challenge_id",
    ),
    M(
        "M25",
        "a passkey can be REGISTERED without user verification",
        "zolo/passkeys/service.py",
        "async def verify_registration(",
        "require_user_verification=True,",
        "require_user_verification=False,",
    ),
    M(
        "M26",
        "an approval is accepted without user verification",
        "zolo/passkeys/service.py",
        "async def verify_assertion(",
        "require_user_verification=True,",
        "require_user_verification=False,",
    ),
    M(
        "M27",
        "registering again does not revoke the old passkey",
        "zolo/passkeys/service.py",
        "async def verify_registration(",
        "old.revoked_at = now",
        "pass",
    ),
    M(
        "M28",
        "a backwards signature counter is accepted",
        "zolo/passkeys/service.py",
        "def _check_counter(",
        'raise _reject("stale_counter")',
        "return",
    ),
    M(
        "M29",
        "an equal counter is always allowed, even when strict",
        "zolo/passkeys/service.py",
        "def _check_counter(",
        "if new == stored and not self.settings.webauthn_strict_counter:",
        "if new == stored:",
    ),
    M(
        "M30",
        "a registration challenge can be used twice in a race",
        "zolo/passkeys/service.py",
        "async def verify_registration(",
        "WebAuthnChallenge.id == challenge.id, WebAuthnChallenge.used_at.is_(None)",
        "WebAuthnChallenge.id == challenge.id",
    ),
    M(
        "M31",
        "the signature check is skipped entirely",
        "zolo/passkeys/service.py",
        "async def verify_assertion(",
        "verified = verify_authentication_response(",
        "verified = SimpleNamespace(new_sign_count=1) if True else verify_authentication_response(",
    ),
    # --- rate limits and sessions
    M(
        "M32",
        "rate limit allows one attempt too many",
        "zolo/core/ratelimit.py",
        "def check(",
        "if len(hits) >= limit:",
        "if len(hits) > limit:",
    ),
    M(
        "M33",
        "the lock needs one failure too many",
        "zolo/core/ratelimit.py",
        "def fail(",
        ">= max_failures",
        "> max_failures",
    ),
    M(
        "M34",
        "a correct-but-expired code counts as a wrong try",
        "zolo/api/routes_requests.py",
        "except ApiError as exc:",
        "if exc.code is ErrorCode.CODE_NOT_FOUND:",
        "if True:",
    ),
    M(
        "M35",
        "wrong claim codes never lock anyone out",
        "zolo/api/routes_requests.py",
        "except ApiError as exc:",
        "if exc.code is ErrorCode.CODE_NOT_FOUND:",
        "if False:",
    ),
    M(
        "M36",
        "the claim lock is ignored",
        "zolo/api/routes_requests.py",
        "async def claim(",
        'limiter.assert_unlocked("claim", key)',
        "pass",
    ),
    M(
        "M37",
        "the claim per-minute limit is ignored",
        "zolo/api/routes_requests.py",
        "async def claim(",
        'limiter.check("claim", key, settings.claim_attempts_per_minute)',
        "pass",
    ),
    M(
        "M38",
        "approve attempts are not rate limited",
        "zolo/api/routes_requests.py",
        "async def approve(",
        "services.settings.approve_attempts_per_minute",
        "10**9",
    ),
    M(
        "M39",
        "challenge requests are not rate limited",
        "zolo/api/routes_requests.py",
        "async def challenge(",
        "services.settings.challenge_attempts_per_minute",
        "10**9",
    ),
    M(
        "M40",
        "creating requests is not rate limited",
        "zolo/api/routes_agent.py",
        "async def create_request(",
        "services.settings.create_requests_per_minute",
        "10**9",
    ),
    M(
        "M41",
        "login is not rate limited",
        "zolo/api/routes_auth.py",
        "async def mock_login(",
        "limit = settings.login_attempts_per_minute",
        "limit = 10**9",
    ),
    M(
        "M42",
        "any login code is accepted",
        "zolo/api/routes_auth.py",
        "async def mock_login(",
        "code_ok = hmac.compare_digest(body.otp.encode(), settings.mock_otp.encode())",
        "code_ok = True",
    ),
    M(
        "M43",
        "the session cookie is readable by scripts",
        "zolo/api/routes_auth.py",
        "response.set_cookie(",
        "httponly=True,",
        "httponly=False,",
    ),
    M(
        "M44",
        "the session cookie is sent cross-site",
        "zolo/api/routes_auth.py",
        "response.set_cookie(",
        'samesite="lax",',
        'samesite="none",',
    ),
    M(
        "M45",
        "sessions never expire",
        "zolo/core/security.py",
        "def loads(",
        "max_age=self.max_age",
        "max_age=10**9",
    ),
    # --- contract and privacy
    M(
        "M46",
        "money accepts floats and strings",
        "zolo/api/schemas.py",
        "class AgentRequestIn",
        "amount_kobo: StrictInt = Field(",
        "amount_kobo: int = Field(",
    ),
    M(
        "M47",
        "unsupported readback languages are accepted",
        "zolo/consent/readback.py",
        "def readback_lang(",
        "return next((lang for lang in READBACK_LANGS if lang == value), None)",
        "return value  # type: ignore[return-value]",
    ),
    M(
        "M48",
        "the audit trail accepts personal data",
        "zolo/audit/service.py",
        "def _check(",
        "if unknown:",
        "if False:",
    ),
    M(
        "M49",
        "logs include every field, not just the allowlist",
        "zolo/core/logging.py",
        "class JsonFormatter",
        "for key in ALLOWED_FIELDS:",
        "for key in list(record.__dict__):",
    ),
    M(
        "M50",
        "canonical intent keys are not sorted",
        "zolo/consent/intent.py",
        "def canonical_bytes(",
        "sort_keys=True",
        "sort_keys=False",
    ),
    M(
        "M51",
        "the intent keeps sub-second noise in the expiry",
        "zolo/consent/intent.py",
        "def _timestamp(",
        ".replace(microsecond=0)",
        "",
    ),
    M(
        "M52",
        "the activity feed is not limited to 20",
        "zolo/consent/service.py",
        "async def activity(",
        ".limit(limit)",
        "",
    ),
    M(
        "M53",
        "the demo gate stops checking the token",
        "zolo/api/deps.py",
        "def require_demo(",
        "if not x_demo_token or not hmac.compare_digest(given, settings.demo_token.encode()):",
        "if False:",
    ),
    M(
        "M54",
        "reset deletes the demo phone's passkey",
        "zolo/demo/seed.py",
        "_STATE_TABLES =",
        '"webauthn_challenges,',
        '"passkey_credentials, webauthn_challenges,',
    ),
    M(
        "M55",
        "a replayed approval is reported as a generic conflict",
        "zolo/consent/service.py",
        "async def _approve(",
        "if arrived_after_approval and await self.passkeys.challenge_was_used(session, row.id):",
        "if False:",
    ),
]


def prepare() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="zolo-mutation-"))
    shutil.copytree(
        ROOT, tmp / "backend",
        ignore=shutil.ignore_patterns(
            ".venv", "var", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
            ".coverage", "htmlcov", ".env", "coverage.json",
        ),
    )  # fmt: skip
    return tmp / "backend"


def _env() -> dict[str, str]:
    base = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://zolo:zolo@localhost:5432/zolo_test"
    )
    return {**os.environ, "TEST_DATABASE_URL": base.rsplit("/", 1)[0] + "/zolo_mutation"}


def run_tests(workdir: Path) -> tuple[bool, str, float]:
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "--no-header", *FAST_FIRST],
        cwd=workdir, capture_output=True, text=True, timeout=900, env=_env(),
    )  # fmt: skip
    tail = proc.stdout.strip().splitlines()
    failed = next((ln for ln in tail if ln.startswith("FAILED") or ln.startswith("ERROR")), "")
    return proc.returncode == 0, failed.replace("FAILED ", "")[:140], time.monotonic() - started


def apply(workdir: Path, m: Mutation) -> bool:
    path = workdir / m.file
    text = path.read_text()
    start = text.find(m.anchor)
    if start < 0 or text.count(m.anchor) != 1 and m.anchor.startswith("async def"):
        pass
    if start < 0:
        return False
    at = text.find(m.old, start)
    if at < 0:
        return False
    text = text[:at] + m.new + text[at + len(m.old) :]
    if "SimpleNamespace" in m.new and "from types import SimpleNamespace" not in text:
        text = "from types import SimpleNamespace\n" + text
    path.write_text(text)
    return True


def main(ids: list[str]) -> int:
    chosen = [m for m in MUTATIONS if not ids or m.id in ids]
    work = prepare()
    print(f"working copy: {work}\n")
    ok, failed, secs = run_tests(work)
    print(f"baseline (no bug planted): {'PASS' if ok else 'FAIL ' + failed} in {secs:.0f}s")
    if not ok:
        print("the unmodified code must pass first; fix that before trusting any result")
        return 2
    results = []
    for m in chosen:
        original = (work / m.file).read_text()
        if not apply(work, m):
            results.append({"id": m.id, "result": "NOT APPLIED", "what": m.what})
            print(f"{m.id} NOT APPLIED   {m.what}")
            continue
        ok, failed, secs = run_tests(work)
        (work / m.file).write_text(original)
        verdict = "SURVIVED" if ok else "killed"
        results.append(
            {
                "id": m.id,
                "result": verdict,
                "what": m.what,
                "caught_by": failed,
                "seconds": round(secs),
            }
        )
        print(
            f"{m.id} {verdict:9} {secs:4.0f}s  {m.what}"
            + (f"\n        caught by: {failed}" if failed else ""),
            flush=True,
        )
    summary = {
        r: sum(1 for x in results if x["result"] == r)
        for r in ("killed", "SURVIVED", "NOT APPLIED")
    }
    print(f"\n{summary}")
    (ROOT / "var").mkdir(exist_ok=True)
    (ROOT / "var" / "mutation_report.json").write_text(json.dumps(results, indent=1))
    shutil.rmtree(work.parent, ignore_errors=True)
    return 1 if summary["SURVIVED"] or summary["NOT APPLIED"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
