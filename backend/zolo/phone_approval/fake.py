class FakeVoiceProvider:
    def __init__(self):
        self.calls = []

    def place_call(self, to: str, webhook_url: str, call_id: str) -> str:
        simulated_sid = f"CA_FAKE_{len(self.calls)+1}"
        self.calls.append({"to": to, "webhook_url": webhook_url, "call_id": call_id, "sid": simulated_sid})
        return simulated_sid

    def validate_signature(self, url: str, params: dict, signature: str) -> bool:
        return True