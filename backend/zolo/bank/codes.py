"""Mock bank codes and display names.

The names are the ones the AI package recognises (`zolo.ai.nlu.banks`), so a saved recipient's
bank can be matched by voice ("for Opay"). The codes are MOCK values in NIBSS style for the demo;
they are not authoritative. Confirm them against NIBSS before any real integration.
"""

BANKS: dict[str, str] = {
    "044": "Access Bank",
    "033": "UBA",
    "011": "First Bank",
    "050": "Ecobank",
    "058": "GTBank",
    "057": "Zenith Bank",
    "035": "Wema Bank",
    "232": "Sterling Bank",
    "214": "FCMB",
    "070": "Fidelity Bank",
    "032": "Union Bank",
    "076": "Polaris Bank",
    "221": "Stanbic IBTC",
    "100004": "Opay",
    "100033": "Palmpay",
    "50211": "Kuda",
    "50515": "Moniepoint",
}


def bank_name(code: str) -> str:
    return BANKS.get(code, f"Bank {code}")
