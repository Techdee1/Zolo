
"""Audio clip keys and URL helpers for phone approval."""

CALL_CLIP_KEYS = [
    "call_intro",
    "call_menu",
    "call_pin",
    "call_wrong_pin",
    "call_locked",
    "call_privacy",
    "call_bye",
    "changed",
]


def get_call_clip_url(clip_key: str, language: str) -> str:
    """Return the URL path for a phone-approval audio clip."""
    if clip_key not in CALL_CLIP_KEYS:
        raise ValueError(f"Unknown phone audio clip: {clip_key}")

    return f"/voice/audio/{language}_{clip_key}.mp3"
