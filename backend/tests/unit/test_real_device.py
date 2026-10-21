import pytest

from zolo.core.config import Settings
from zolo.tools.real_device import TUNNEL_URL, build_env, check_host, describe, main


def test_the_env_values_are_exactly_what_the_api_will_read() -> None:
    env = build_env("zolo-demo.trycloudflare.com", demo_token="a-demo-token")
    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        session_secret="s" * 32,
        **{k.lower(): v for k, v in env.items()},  # type: ignore[arg-type]
    )
    assert s.rp_id == "zolo-demo.trycloudflare.com"
    assert s.origins == ["https://zolo-demo.trycloudflare.com"]
    assert s.cors_origin_list == ["https://zolo-demo.trycloudflare.com"]
    assert s.cookie_secure is True and s.demo_mode is True and s.demo_token == "a-demo-token"
    assert s.webauthn_strict_counter is False and s.trust_forwarded_for is True


def test_the_origin_is_https_and_has_no_trailing_slash_or_port() -> None:
    env = build_env("Demo.Example.com")  # case is normalised
    assert env["ORIGIN"] == "https://demo.example.com" and env["RP_ID"] == "demo.example.com"


@pytest.mark.parametrize("bad", [
    "", "localhost", "foo.localhost", "127.0.0.1", "::1", "192.168.1.5", "demo.example.com:8000",
    "https://demo.example.com", "demo.example.com/", "demo example.com", "nodots",
])  # fmt: skip
def test_hosts_that_silently_break_passkeys_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        check_host(bad)


def test_a_generated_token_is_long_enough_for_demo_mode() -> None:
    assert len(build_env("a.example.com")["DEMO_TOKEN"]) >= 8
    assert build_env("a.example.com")["DEMO_TOKEN"] != build_env("a.example.com")["DEMO_TOKEN"]


@pytest.mark.parametrize("line,host", [
    ("2026-10-21 INF |  https://rapid-sunny-dog-123.trycloudflare.com  |", "rapid-sunny-dog-123.trycloudflare.com"),
    ('msg="started tunnel" url=https://ab12-34-56.ngrok-free.app', "ab12-34-56.ngrok-free.app"),
])  # fmt: skip
def test_the_tunnel_url_is_found_in_the_tunnels_output(line: str, host: str) -> None:
    m = TUNNEL_URL.search(line)
    assert m and m.group(0) == f"https://{host}"


def test_unrelated_output_has_no_url() -> None:
    assert (
        TUNNEL_URL.search("INF Starting tunnel connection https://api.cloudflare.com/client")
        is None
    )


def test_print_only_shows_the_values_and_starts_nothing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    def refuse(*a: object, **k: object) -> None:
        raise AssertionError("print-only must not start any process")

    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    assert main(["--host", "demo.example.com", "--print-only"]) == 0
    out = capsys.readouterr().out
    for line in ("RP_ID=demo.example.com", "ORIGIN=https://demo.example.com", "COOKIE_SECURE=true",
                 "DEMO_MODE=true", "WEBAUTHN_STRICT_COUNTER=false", "https://demo.example.com/dev/passkey-test"):  # fmt: skip
        assert line in out
    assert "SESSION_SECRET" not in out  # secrets other than the demo token are never printed


def test_a_bad_host_is_a_clear_error_not_a_stack_trace(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--host", "localhost", "--print-only"]) == 2
    assert "localhost" in capsys.readouterr().err


def test_describe_names_the_two_settings_that_must_match() -> None:
    text = describe(build_env("demo.example.com"))
    assert "RP_ID must equal the host" in text and "ORIGIN must equal the full origin" in text
