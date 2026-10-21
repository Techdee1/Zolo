"""How a saved_recipients row becomes the AI package's `SavedRecipient`.

Not wired to anything yet (Phase 2: `DraftService.list_saved_recipients` will query the table
and call this). Kept pure so the mapping is tested now against the real seed data.
"""

from typing import Protocol

from zolo.ai.nlu.recipients import SavedRecipient
from zolo.bank.codes import bank_name


class SavedRecipientRow(Protocol):
    id: object
    display_name: str
    bank_code: str
    account_number: str
    account_name: str


def to_ai_recipient(row: SavedRecipientRow) -> SavedRecipient:
    """display_name is what the customer calls the person ("My sister"); the bank-verified
    account_name is an extra alias, so "Adaeze" matches too. Only the last 4 digits go to the AI."""
    return SavedRecipient(
        id=str(row.id),
        display_name=row.display_name,
        bank=bank_name(row.bank_code),
        last4=row.account_number[-4:],
        aliases=(row.account_name,),
    )
