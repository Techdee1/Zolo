"""What the AI package needs from the backend. The backend implements `DraftService`.

The AI can read (balance, saved recipients) and make exactly one write: create a DRAFT request.
There is deliberately no approve, execute, cancel or limit-changing method here, so nothing the
AI does can move money. The consent engine owns the stored request and the readback.
"""

from typing import Protocol

from zolo.ai.nlu.recipients import SavedRecipient


class DraftService(Protocol):
    def create_draft(self, customer_id: str, recipient_ref: str, amount_kobo: int) -> str:
        """Store a DRAFT payment request and return its request id.

        `recipient_ref` is the id of one of the customer's saved recipients (as returned by
        `list_saved_recipients`); `amount_kobo` is a positive integer in kobo. Implementations
        should reject anything else. The AI gets back only the id, never the stored record.
        """
        ...

    def get_balance(self, customer_id: str) -> int:
        """The customer's available balance in kobo (read only)."""
        ...

    def list_saved_recipients(self, customer_id: str) -> list[SavedRecipient]:
        """The customer's saved recipients (read only): display names, never account numbers."""
        ...
