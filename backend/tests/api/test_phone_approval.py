
"""Focused tests for phone approval API behavior."""

import pytest
from zolo.phone_approval.twilio import TwilioProvider


@pytest.mark.asyncio
async def test_enrol_rejects_weak_pin(customer, api, monkeypatch):
    """A weak PIN must never be accepted for enrolment."""
    monkeypatch.setattr(api.state.settings, "feature_phone_call", True)

    response = await customer.post(
        "/phone-approval/enrol",
        json={
            "phone_number": "+2348012345678",
            "pin": "1234",
            "language": "en",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_enrol_accepts_valid_details(customer, api, monkeypatch):
    """A valid phone number and strong numeric PIN should enrol."""
    monkeypatch.setattr(api.state.settings, "feature_phone_call", True)

    response = await customer.post(
        "/phone-approval/enrol",
        json={
            "phone_number": "+2348012345678",
            "pin": "9274",
            "language": "en",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_enrol_rejects_invalid_phone_format(customer, api, monkeypatch):
    """Phone numbers must use international E.164 format."""
    monkeypatch.setattr(api.state.settings, "feature_phone_call", True)

    response = await customer.post(
        "/phone-approval/enrol",
        json={
            "phone_number": "08012345678",
            "pin": "9274",
            "language": "en",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_status_webhook_unknown_call_returns_404(
    anonymous, api, monkeypatch
):
    """A correctly authenticated webhook must not invent a call."""
    monkeypatch.setattr(api.state.settings, "feature_phone_call", True)
    monkeypatch.setattr(
        TwilioProvider,
        "validate_signature",
        lambda self, url, params, signature: True,
    )

    response = await anonymous.post(
        "/phone/unknown-test-call/status",
        data={"CallStatus": "completed"},
        headers={"X-Twilio-Signature": "test-signature"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_menu_webhook_unknown_call_returns_404(
    anonymous, api, monkeypatch
):
    """Menu handling must reject an unknown call identifier."""
    monkeypatch.setattr(api.state.settings, "feature_phone_call", True)
    monkeypatch.setattr(
        TwilioProvider,
        "validate_signature",
        lambda self, url, params, signature: True,
    )

    response = await anonymous.post(
        "/phone/unknown-test-call/menu",
        data={"Digits": "1"},
        headers={"X-Twilio-Signature": "test-signature"},
    )

    assert response.status_code == 404
