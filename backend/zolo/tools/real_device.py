"""Start the API behind a public HTTPS tunnel so a real phone can register and use a passkey.

    python -m zolo.tools.real_device                      # starts a cloudflared quick tunnel
    python -m zolo.tools.real_device --host my.example.com  # you already run a tunnel or domain
    python -m zolo.tools.real_device --host my.example.com --print-only

It prints the exact RP_ID, origin and environment values, migrates and seeds the database,
then runs the API with those values. See docs/REAL_DEVICE_TEST.md. Untested on a phone until
someone runs it: do not claim otherwise.
"""

import argparse
import ipaddress
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

TUNNEL_URL = re.compile(
    r"https://[a-z0-9-]+\.(?:trycloudflare\.com|ngrok-free\.app|ngrok\.app|ngrok\.io|ngrok\.dev)"
)


def check_host(host: str) -> str:
    """A passkey needs a registrable domain: no scheme, port, path, IP address or localhost."""
    host = host.strip().lower()
    if not host or "/" in host or ":" in host or " " in host:
        raise ValueError(
            "give the bare host name only, e.g. demo.example.com (no https://, port or path)"
        )
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("an IP address cannot be an RP ID: passkeys need a domain name")
    if host == "localhost" or host.endswith(".localhost") or "." not in host:
        raise ValueError(
            "use the public tunnel host, not localhost: a localhost passkey will not work there"
        )
    return host


def build_env(host: str, demo_token: str | None = None) -> dict[str, str]:
    host = check_host(host)
    origin = f"https://{host}"
    return {
        "RP_ID": host,
        "ORIGIN": origin,
        "CORS_ORIGINS": origin,
        "COOKIE_SECURE": "true",
        "DEMO_MODE": "true",
        "DEMO_TOKEN": demo_token or secrets.token_urlsafe(12),
        # Platform passkeys may repeat a counter; the demo tolerates that (with a warning).
        "WEBAUTHN_STRICT_COUNTER": "false",
        # Behind a tunnel every request comes from the tunnel: use X-Forwarded-For for rate limits.
        "TRUST_FORWARDED_FOR": "true",
    }


def describe(env: dict[str, str]) -> str:
    lines = ["Set these (the script does it for you when it starts the API):", ""]
    lines += [f"  {key}={value}" for key, value in env.items()]
    lines += [
        "",
        f"  Page to open on the phone:  {env['ORIGIN']}/dev/passkey-test",
        f"  RP_ID must equal the host the phone sees:  {env['RP_ID']}",
        f"  ORIGIN must equal the full origin, exactly:  {env['ORIGIN']}",
    ]
    return "\n".join(lines)


def _start_tunnel(kind: str, port: int) -> tuple[subprocess.Popen[str], str]:
    if shutil.which(kind) is None:
        raise SystemExit(f"{kind} is not installed (see docs/REAL_DEVICE_TEST.md), or pass --host")
    cmd = {
        "cloudflared": [
            "cloudflared",
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://localhost:{port}",
        ],
        "ngrok": ["ngrok", "http", str(port), "--log", "stdout"],
    }[kind]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.monotonic() + 60
    assert proc.stdout is not None
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        match = TUNNEL_URL.search(line)
        if match:
            return proc, urlparse(match.group(0)).hostname or ""
        if proc.poll() is not None:
            break
    proc.terminate()
    raise SystemExit("could not read a tunnel URL from the tunnel's output within 60 seconds")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--host", help="public host of a tunnel/domain you already run")
    ap.add_argument("--tunnel", choices=["cloudflared", "ngrok"], default="cloudflared")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--print-only", action="store_true", help="show the values and exit")
    args = ap.parse_args(argv)

    tunnel: subprocess.Popen[str] | None = None
    try:
        host = args.host
        if host is None:
            if args.print_only:
                raise SystemExit("--print-only needs --host (it will not start a tunnel)")
            tunnel, host = _start_tunnel(args.tunnel, args.port)
        env = build_env(host)
        print(describe(env))
        if args.print_only:
            return 0
        full_env = {**os.environ, **env}
        full_env.setdefault("SESSION_SECRET", secrets.token_urlsafe(32))
        python = sys.executable
        subprocess.run([python, "-m", "alembic", "upgrade", "head"], env=full_env, check=True)
        subprocess.run([python, "-m", "zolo.seed"], env=full_env, check=True)
        print(
            f"\nStarting the API on port {args.port}. "
            f"Open {env['ORIGIN']}/dev/passkey-test on the phone."
        )
        subprocess.run(
            [python, "-m", "uvicorn", "zolo.api.main:create_app", "--factory",
             "--port", str(args.port),
             "--proxy-headers", "--forwarded-allow-ips", "*"],
            env=full_env, check=False,
        )  # fmt: skip
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if tunnel is not None:
            tunnel.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
