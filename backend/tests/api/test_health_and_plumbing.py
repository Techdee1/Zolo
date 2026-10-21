import json
import logging

from httpx import AsyncClient

from zolo.api.export_openapi import schema
from zolo.core.logging import JsonFormatter


async def test_healthz_is_ok_without_touching_the_database(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_readyz_reports_not_ready_until_the_seed_exists(client: AsyncClient) -> None:
    r = await client.get("/readyz")
    body = r.json()
    assert body["database"] is True  # the throwaway database is reachable
    assert r.status_code == 503 and body["status"] == "not_ready" and body["seed"] is False


async def test_readyz_is_200_once_the_database_is_seeded(client: AsyncClient, sessionmaker) -> None:  # type: ignore[no-untyped-def]
    from tests import factories as f

    async with sessionmaker() as s:
        await f.agent_with_account(s)
        await s.commit()
    r = await client.get("/readyz")
    assert r.status_code == 200 and r.json() == {"status": "ready", "database": True, "seed": True}


async def test_request_id_is_echoed_or_generated(client: AsyncClient) -> None:
    given = await client.get("/healthz", headers={"X-Request-Id": "abcd1234-req"})
    assert given.headers["x-request-id"] == "abcd1234-req"
    junk = await client.get("/healthz", headers={"X-Request-Id": "bad id with spaces!"})
    assert (
        junk.headers["x-request-id"] != "bad id with spaces!"
        and len(junk.headers["x-request-id"]) == 36
    )


async def test_security_headers_are_present(client: AsyncClient) -> None:
    h = (await client.get("/healthz")).headers
    assert "max-age" in h["strict-transport-security"]
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["cache-control"] == "no-store"


async def test_unknown_route_is_a_problem_json(client: AsyncClient) -> None:
    r = await client.get("/nope")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json() == {
        "type": "https://zolo.app/problems/not-found",
        "title": "Not found", "status": 404, "code": "NOT_FOUND", "detail": "",
    }  # fmt: skip


async def test_cors_allows_only_the_frontend_origin(client: AsyncClient) -> None:
    ok = await client.options(
        "/healthz",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert ok.headers["access-control-allow-credentials"] == "true"
    bad = await client.options(
        "/healthz",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_log_lines_are_json_and_drop_anything_not_allowlisted() -> None:
    rec = logging.LogRecord("zolo.test", logging.INFO, __file__, 1, "request", None, None)
    rec.status = 200
    rec.amount_kobo = 1_500_000  # type: ignore[attr-defined]  # must never reach the log
    rec.payee_name = "BISI VENTURES"  # type: ignore[attr-defined]
    rec.account_number = "0123456789"  # type: ignore[attr-defined]
    line = json.loads(JsonFormatter().format(rec))
    assert line["status"] == 200 and line["msg"] == "request"
    assert not {"amount_kobo", "payee_name", "account_number"} & set(line)
    assert "1500000" not in json.dumps(line) and "BISI" not in json.dumps(line)


async def test_the_access_log_has_route_templates_not_raw_paths(
    client: AsyncClient, caplog: object
) -> None:
    import pytest

    assert isinstance(caplog, pytest.LogCaptureFixture)
    with caplog.at_level(logging.INFO, logger="zolo.access"):
        await client.get("/healthz?secret=1")
    rec = next(r for r in caplog.records if r.name == "zolo.access")
    assert rec.route == "/healthz" and "secret" not in rec.getMessage()  # type: ignore[attr-defined]


def test_openapi_schema_exports_without_a_database() -> None:
    s = schema()
    assert "/healthz" in s["paths"] and "/readyz" in s["paths"]  # type: ignore[operator]
