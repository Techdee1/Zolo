"""In-memory fakes for tests and local runs. The real backend implements DraftService."""

from zolo.ai.nlu.recipients import SavedRecipient


class FakeBackend:
    """In-memory `DraftService`. Records every draft so tests can assert on them."""

    def __init__(
        self, recipients: list[SavedRecipient] | None = None, balance_kobo: int = 2_500_000
    ) -> None:
        self.recipients = recipients or []
        self.balance_kobo = balance_kobo
        self.drafts: list[tuple[str, str, int]] = []  # (customer_id, recipient_ref, amount_kobo)
        self.fail_with: Exception | None = None

    def create_draft(self, customer_id: str, recipient_ref: str, amount_kobo: int) -> str:
        if self.fail_with:
            raise self.fail_with
        if amount_kobo <= 0 or recipient_ref not in {r.id for r in self.recipients}:
            raise ValueError("invalid draft")  # a real backend must refuse these too
        self.drafts.append((customer_id, recipient_ref, amount_kobo))
        return f"req_{len(self.drafts)}"

    def get_balance(self, customer_id: str) -> int:
        return self.balance_kobo

    def list_saved_recipients(self, customer_id: str) -> list[SavedRecipient]:
        return list(self.recipients)
