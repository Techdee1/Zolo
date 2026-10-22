"""The named demo people, accounts and recipients. Fixed ids, so the script, the rehearsals and a
passkey registered on the demo phone always refer to the same people (reset never changes them).

Pure data: `python -m zolo.seed` (step 3) writes it. All names are fictional.
"""

import uuid
from dataclasses import dataclass

_NS = uuid.UUID("5a0f0000-0000-4000-8000-5a0f00000000")


def _id(name: str) -> uuid.UUID:
    return uuid.uuid5(_NS, name)


@dataclass(frozen=True)
class SeedCustomer:
    id: uuid.UUID
    display_name: str
    phone: str
    language: str


@dataclass(frozen=True)
class SeedAgent:
    id: uuid.UUID
    account_id: uuid.UUID
    business_name: str
    phone: str


@dataclass(frozen=True)
class SeedAccount:
    id: uuid.UUID
    account_number: str
    bank_code: str
    verified_name: str
    balance_kobo: int
    customer_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None


@dataclass(frozen=True)
class SeedRecipient:
    id: uuid.UUID
    customer_id: uuid.UUID
    display_name: str
    bank_code: str
    account_number: str
    account_name: str


NAIRA = 100

# The demo customer (a Pidgin speaker) and her account.
AMAKA = SeedCustomer(_id("customer:amaka"), "Amaka Obi", "+2348011111111", "pcm")

_BISI_ACC, _MAMA_ACC = _id("account:bisi"), _id("account:mama-chi")
BISI = SeedAgent(_id("agent:bisi"), _BISI_ACC, "Bisi Ventures", "+2348022222222")
MAMA_CHI = SeedAgent(_id("agent:mama-chi"), _MAMA_ACC, "Mama Chi Stores", "+2348033333333")

ACCOUNTS: tuple[SeedAccount, ...] = (
    SeedAccount(
        _id("account:amaka"),
        "2000000001",
        "057",
        "AMAKA OBI",
        250_000 * NAIRA,
        customer_id=AMAKA.id,
    ),
    SeedAccount(_BISI_ACC, "0123456789", "057", "BISI VENTURES", 500_000 * NAIRA, agent_id=BISI.id),
    SeedAccount(
        _MAMA_ACC, "0234567890", "057", "MAMA CHI STORES", 500_000 * NAIRA, agent_id=MAMA_CHI.id
    ),
    # Outside accounts (no owner in Zolo): the customer's sister and two Tundes on other banks.
    SeedAccount(_id("account:adaeze"), "0345678901", "044", "ADAEZE OKAFOR", 80_000 * NAIRA),
    SeedAccount(
        _id("account:tunde-bakare"), "8023456789", "100004", "TUNDE BAKARE", 40_000 * NAIRA
    ),
    SeedAccount(_id("account:tunde-adeyemi"), "0456789012", "058", "TUNDE ADEYEMI", 60_000 * NAIRA),
    # The wrong-recipient demo: an agent claims to be Bisi Ventures but this account is not.
    SeedAccount(_id("account:okonkwo"), "0567890123", "057", "OKONKWO PETER", 10_000 * NAIRA),
)

# Amaka's saved recipients. Two people called Tunde on different banks make the voice
# disambiguation case ("Which Tunde: Opay or GTBank?") work.
RECIPIENTS: tuple[SeedRecipient, ...] = (
    SeedRecipient(
        _id("rcp:tunde-bakare"), AMAKA.id, "Tunde Bakare", "100004", "8023456789", "TUNDE BAKARE"
    ),
    SeedRecipient(
        _id("rcp:tunde-adeyemi"), AMAKA.id, "Tunde Adeyemi", "058", "0456789012", "TUNDE ADEYEMI"
    ),
    SeedRecipient(_id("rcp:sister"), AMAKA.id, "My sister", "044", "0345678901", "ADAEZE OKAFOR"),
    SeedRecipient(
        _id("rcp:mama-chi"), AMAKA.id, "Mama Chi Stores", "057", "0234567890", "MAMA CHI STORES"
    ),
)

WRONG_RECIPIENT_ACCOUNT = ACCOUNTS[-1]
