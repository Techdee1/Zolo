"""The OpenAPI schema is the contract the frontend generates its types from."""

import json
from pathlib import Path

from zolo.api.export_openapi import schema

COMMITTED = Path(__file__).resolve().parents[2] / "openapi.json"

# The Phase 1 rows of the Backend PRD API table, and nothing from Phase 2 or 3.
PRD_PHASE_1 = {
    ("post", "/auth/mock-login"),
    ("post", "/passkeys/register/options"),
    ("post", "/passkeys/register/verify"),
    ("post", "/agent/requests"),
    ("post", "/requests/claim"),
    ("get", "/requests/{request_id}/readback"),
    ("post", "/requests/{request_id}/challenge"),
    ("post", "/requests/{request_id}/approve"),
    ("post", "/requests/{request_id}/decline"),
    ("get", "/requests/{request_id}"),
    ("get", "/me/activity"),
}
SUPPORT = {("get", "/healthz"), ("get", "/readyz"), ("get", "/voice/audio/{key}.mp3")}
# The Phase 1 demo endpoints (Backend PRD "Demo endpoints": reset, tamper, replay, expire, timeline).
DEMO_PHASE_1 = {
    ("post", "/demo/reset"),
    ("post", "/demo/requests/{request_id}/tamper"),
    ("post", "/demo/requests/{request_id}/replay"),
    ("post", "/demo/requests/{request_id}/expire"),
    ("get", "/demo/requests/{request_id}/timeline"),
}
PHASE_2_3 = [
    "/events",
    "/renew",
    "/voice/turn",
    "/requests/draft",
    "/card-guard",
    "/call/",
    "/me/freeze",
]


def operations() -> set[tuple[str, str]]:
    return {(m, p) for p, item in schema()["paths"].items() for m in item}  # type: ignore[attr-defined]


def test_the_committed_openapi_json_is_current() -> None:
    # CI runs the same comparison; if this fails, regenerate it and the frontend's types:
    #   uv run python -m zolo.api.export_openapi > openapi.json
    assert json.loads(COMMITTED.read_text()) == json.loads(json.dumps(schema())), (
        "openapi.json is stale"
    )


def test_every_phase_1_endpoint_in_the_prd_table_exists_and_nothing_else_does() -> None:
    assert operations() == PRD_PHASE_1 | DEMO_PHASE_1 | SUPPORT


def test_no_phase_2_or_3_endpoint_is_exposed() -> None:
    paths = " ".join(schema()["paths"])  # type: ignore[arg-type]
    for later in PHASE_2_3:
        assert later not in paths, later


def test_the_dev_page_is_not_part_of_the_contract() -> None:
    assert "/dev/passkey-test" not in schema()["paths"]  # type: ignore[operator]


def test_success_statuses_follow_the_prd() -> None:
    paths = schema()["paths"]
    assert "201" in paths["/agent/requests"]["post"]["responses"]  # type: ignore[index]
    assert "201" in paths["/passkeys/register/verify"]["post"]["responses"]  # type: ignore[index]
    for path, method in [("/requests/claim", "post"), ("/requests/{request_id}/approve", "post"),
                         ("/requests/{request_id}/readback", "get"), ("/me/activity", "get")]:  # fmt: skip
        assert "200" in paths[path][method]["responses"], path  # type: ignore[index]


def test_every_prd_error_status_is_documented_as_problem_json() -> None:
    paths = schema()["paths"]

    def statuses(path: str, method: str) -> set[str]:
        return set(paths[path][method]["responses"])  # type: ignore[index]

    assert {"401", "403", "429"} <= statuses("/agent/requests", "post")
    assert {"404", "410"} <= statuses("/requests/claim", "post")
    assert {"401", "409", "410", "422"} <= statuses("/requests/{request_id}/approve", "post")
    assert {"409", "410"} <= statuses("/requests/{request_id}/readback", "get")
    problem_ref = paths["/requests/claim"]["post"]["responses"]["404"]["content"][
        "application/json"
    ]["schema"]["$ref"]  # type: ignore[index]
    assert problem_ref.endswith("/Problem")


def test_the_problem_schema_lists_every_error_code_the_prd_names() -> None:
    codes = set(
        schema()["components"]["schemas"]["Problem"]["properties"]["code"]["$ref"].split("/")[-1:]
    )  # type: ignore[index]
    enum = set(schema()["components"]["schemas"]["ErrorCode"]["enum"])  # type: ignore[index]
    assert codes == {"ErrorCode"}
    assert {"LIMIT_EXCEEDED", "CODE_NOT_FOUND", "REQUEST_EXPIRED", "STATE_CONFLICT", "INTENT_CHANGED",
            "SIGNATURE_INVALID", "ALREADY_USED"} <= enum  # fmt: skip


def test_the_agent_request_response_has_exactly_the_prd_fields() -> None:
    props = schema()["components"]["schemas"]["AgentRequestOut"]["properties"]  # type: ignore[index]
    assert set(props) == {"id", "claim_code", "qr_payload", "expires_at", "payee_name"}


def test_the_readback_response_has_the_prd_fields() -> None:
    props = schema()["components"]["schemas"]["ReadbackOut"]["properties"]  # type: ignore[index]
    assert set(props["lang"]["enum"]) == {"en", "pcm", "yo", "ha", "ig"}
    fallback = props["fallback_from"]["anyOf"]
    assert {"enum": ["yo", "ha", "ig"], "type": "string"} in [
        {k: v for k, v in a.items() if k != "title"} for a in fallback
    ]
    assert set(props) == {
        "text",
        "lang",
        "fallback_from",
        "audio_url",
        "amount_words",
        "payee_name",
        "amount_kobo",
        "expires_at",
    }
