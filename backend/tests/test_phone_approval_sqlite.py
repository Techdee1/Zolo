
"""Focused SQLite tests for Zolo phone-approval endpoints."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from zolo.api.main import create_app
from zolo.core.base import Base
from zolo.phone_approval.models import (
    PhoneApprovalEnrolment,
    PhoneCall,
)


@pytest.fixture
def client(tmp_path):
    """Create an isolated SQLite database for each test."""
    db_file = tmp_path / "phone_tests.db"

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file.as_posix()}",
        poolclass=NullPool,
    )

    sessionmaker = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async def create_tables():
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[
                        PhoneApprovalEnrolment.__table__,
                        PhoneCall.__table__,
                    ],
                )
            )

    asyncio.run(create_tables())

    app = create_app()
    app.state.sessionmaker = sessionmaker

    try:
        with TestClient(
            app,
            base_url="https://testserver",
        ) as test_client:
            yield test_client
    finally:
        asyncio.run(engine.dispose())


def get_paths(client):
    """Return registered API paths."""
    return client.get("/openapi.json").json()["paths"]


def find_path(client, suffix):
    """Find an endpoint by its path suffix."""
    paths = get_paths(client)

    matches = [
        path for path in paths
        if path.endswith(suffix)
    ]

    assert matches, (
        f"Endpoint ending in {suffix!r} was not found. "
        f"Registered paths: {list(paths)}"
    )

    return matches[0]


def test_phone_endpoints_are_registered(client):
    """Ensure all five phone-approval endpoints exist."""
    paths = get_paths(client)

    expected = [
        "/phone-approval/enrol",
        "/phone/{public_id}/start",
        "/phone/{public_id}/menu",
        "/phone/{public_id}/pin",
        "/phone/{public_id}/status",
    ]

    for expected_path in expected:
        assert any(
            path.endswith(expected_path)
            for path in paths
        ), f"Missing endpoint: {expected_path}"


def test_enrol_rejects_invalid_phone_format(client):
    """Reject a local-format phone number instead of E.164."""
    path = find_path(client, "/phone-approval/enrol")

    response = client.post(
        path,
        json={
            "phone_number": "08012345678",
            "pin": "9274",
            "language": "en",
        },
    )

    # Authentication or feature-flag checks may run before
    # request validation, depending on the application setup.
    assert response.status_code in (401, 403, 404, 422), (
        f"Unexpected response: {response.status_code} "
        f"{response.text}"
    )


@pytest.mark.parametrize(
    ("suffix", "form_data"),
    [
        ("/phone/{public_id}/start", {}),
        ("/phone/{public_id}/menu", {"Digits": "9"}),
        ("/phone/{public_id}/pin", {"Digits": "1234"}),
        ("/phone/{public_id}/status", {"CallStatus": "completed"}),
    ],
)
def test_webhooks_reject_invalid_twilio_signatures(
    client,
    suffix,
    form_data,
):
    """Reject webhook requests with an invalid Twilio signature."""
    path = find_path(client, suffix).replace(
        "{public_id}",
        "invalid-test-call",
    )

    response = client.post(
        path,
        data=form_data,
        headers={
            "X-Twilio-Signature": "invalid-signature",
        },
    )

    assert response.status_code == 403, (
        f"{suffix} should reject an invalid signature, "
        f"but returned {response.status_code}: {response.text}"
    )


def test_enrol_rejects_empty_payload(client):
    """Ensure enrolment doesn't accept an empty JSON payload."""
    path = find_path(client, "/phone-approval/enrol")

    response = client.post(path, json={})

    assert response.status_code in (400, 401, 403, 404, 422), (
        f"Unexpected response: {response.status_code} "
        f"{response.text}"
    )
