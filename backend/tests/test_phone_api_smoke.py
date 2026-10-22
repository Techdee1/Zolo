
"""Focused smoke/security tests for Zolo phone-approval endpoints."""

import pytest
from fastapi.testclient import TestClient

from zolo.api.main import create_app


@pytest.fixture(scope="module")
def client():
    # Avoid entering the application's lifespan, which may connect to the DB.
    app = create_app()
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def find_path(client, suffix):
    paths = client.get("/openapi.json").json()["paths"]
    matches = [
        path for path in paths
        if path.endswith(suffix)
    ]
    assert matches, (
        f"Endpoint ending in {suffix!r} is missing. "
        f"Registered paths: {list(paths)}"
    )
    return matches[0]


def test_all_phone_endpoints_are_registered(client):
    expected = [
        "/phone-approval/enrol",
        "/phone/{public_id}/start",
        "/phone/{public_id}/menu",
        "/phone/{public_id}/pin",
        "/phone/{public_id}/status",
    ]

    paths = client.get("/openapi.json").json()["paths"]

    for expected_path in expected:
        assert any(
            path.endswith(expected_path)
            for path in paths
        ), f"Missing endpoint: {expected_path}"


@pytest.mark.parametrize(
    ("suffix", "form_data"),
    [
        ("/phone/{public_id}/start", {}),
        ("/phone/{public_id}/menu", {"Digits": "9"}),
        ("/phone/{public_id}/pin", {"Digits": "1234"}),
        (
            "/phone/{public_id}/status",
            {"CallStatus": "completed"},
        ),
    ],
)
def test_webhooks_reject_invalid_twilio_signatures(
    client, suffix, form_data
):
    path = find_path(client, suffix).replace(
        "{public_id}", "invalid-test-call"
    )

    response = client.post(
        path,
        data=form_data,
        headers={"X-Twilio-Signature": "invalid-signature"},
    )

    assert response.status_code == 403, (
        f"{suffix} should reject an invalid signature; "
        f"got {response.status_code}: {response.text}"
    )


def test_enrol_endpoint_rejects_empty_payload(client):
    path = find_path(client, "/phone-approval/enrol")

    response = client.post(path, json={})

    # Validation or authentication should reject an empty request.
    assert response.status_code in (400, 401, 403, 422), (
        f"Unexpected response: {response.status_code} "
        f"{response.text}"
    )
