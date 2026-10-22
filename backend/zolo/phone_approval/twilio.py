
"""Twilio voice provider and official webhook signature validation."""

from collections.abc import Mapping

import httpx
from twilio.request_validator import RequestValidator

from zolo.core.config import get_settings


class TwilioProvider:
    """Create outbound Twilio calls and validate Twilio webhooks."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _validate_configuration(self) -> None:
        required = {
            "TWILIO_ACCOUNT_SID": self.settings.twilio_account_sid,
            "TWILIO_AUTH_TOKEN": self.settings.twilio_auth_token,
            "TWILIO_FROM_NUMBER": self.settings.twilio_from_number,
            "PUBLIC_BASE_URL": self.settings.public_base_url,
        }

        missing = [
            name for name, value in required.items()
            if not value or not str(value).strip()
        ]
        if missing:
            raise RuntimeError(
                "Missing Twilio configuration: " + ", ".join(missing)
            )

    def place_call(self, to: str, webhook_url: str, call_id: str) -> str:
        """Place an outbound call and return its Twilio Call SID."""
        self._validate_configuration()

        if not to.startswith("+"):
            raise ValueError("Destination phone number must use E.164 format.")

        base_url = self.settings.public_base_url.rstrip("/")
        account_sid = self.settings.twilio_account_sid

        api_url = (
            f"https://api.twilio.com/2010-04-01/"
            f"Accounts/{account_sid}/Calls.json"
        )

        payload = {
            "To": to,
            "From": self.settings.twilio_from_number,
            "Url": webhook_url,
            "Method": "POST",
            "StatusCallback": f"{base_url}/phone/{call_id}/status",
            "StatusCallbackMethod": "POST",
            "StatusCallbackEvent": [
                "initiated",
                "ringing",
                "answered",
                "completed",
            ],
        }

        with httpx.Client(
            auth=(account_sid, self.settings.twilio_auth_token),
            timeout=15.0,
        ) as client:
            response = client.post(api_url, data=payload)
            response.raise_for_status()
            result = response.json()

        call_sid = result.get("sid")
        if not call_sid:
            raise RuntimeError("Twilio did not return a Call SID.")

        return str(call_sid)

    def validate_signature(
        self,
        url: str,
        params: Mapping[str, str],
        signature: str,
    ) -> bool:
        """Validate X-Twilio-Signature using Twilio's official SDK."""
        token = self.settings.twilio_auth_token
        if not token or not signature or not url:
            return False

        validator = RequestValidator(token)

        try:
            return validator.validate(
                url,
                dict(params),
                signature,
            )
        except (TypeError, ValueError):
            return False
