from typing import Protocol

class VoiceProvider(Protocol):
    def place_call(self, to: str, webhook_url: str, call_id: str) -> str:
        ...
    def validate_signature(self, url: str, params: dict, signature: str) -> bool:
        ...