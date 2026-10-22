
"""Safe TwiML generation helpers for Zolo phone approval."""

from xml.etree import ElementTree as ET


def _response() -> ET.Element:
    """Create a Twilio Response document."""
    return ET.Element("Response")


def _play(parent: ET.Element, audio_url: str) -> None:
    """Append an audio playback instruction."""
    if not audio_url or not audio_url.strip():
        raise ValueError("Audio URL must not be empty.")

    ET.SubElement(parent, "Play").text = audio_url


def _gather(
    parent: ET.Element,
    action_url: str,
    num_digits: int,
    timeout: int = 10,
) -> None:
    """Append a keypad-input instruction."""
    if not action_url or not action_url.strip():
        raise ValueError("Gather action URL must not be empty.")

    if num_digits < 1 or num_digits > 20:
        raise ValueError("num_digits must be between 1 and 20.")

    if timeout < 1 or timeout > 60:
        raise ValueError("timeout must be between 1 and 60 seconds.")

    gather = ET.SubElement(
        parent,
        "Gather",
        {
            "numDigits": str(num_digits),
            "action": action_url,
            "method": "POST",
            "timeout": str(timeout),
            "actionOnEmptyResult": "true",
        },
    )

    # Twilio needs an instruction inside Gather. The caller can speak
    # the prompt or play audio here if desired; the current flow plays
    # the prompt before opening Gather.


def render_twiml(xml_content: str) -> str:
    """Wrap a trusted TwiML fragment in a Response document.

    Kept for compatibility with any existing callers. Prefer the
    structured helper functions below for new code.
    """
    if not isinstance(xml_content, str):
        raise TypeError("xml_content must be a string.")

    # Parse the fragment instead of interpolating it into XML.
    fragment_root = ET.fromstring(f"<Fragment>{xml_content}</Fragment>")
    response = _response()

    for child in list(fragment_root):
        response.append(child)

    return ET.tostring(
        response,
        encoding="unicode",
        xml_declaration=True,
    )


def twiml_gather_menu(
    action_url: str,
    audio_url: str,
    menu_audio_url: str,
) -> str:
    """Play the approval summary and menu, then collect one keypad digit."""
    response = _response()

    _play(response, audio_url)
    _play(response, menu_audio_url)
    _gather(response, action_url, num_digits=1)

    return ET.tostring(
        response,
        encoding="unicode",
        xml_declaration=True,
    )


def twiml_gather_pin(
    action_url: str,
    privacy_audio_url: str,
    pin_audio_url: str,
) -> str:
    """Play the PIN privacy notice and prompt, then collect four digits."""
    response = _response()

    _play(response, privacy_audio_url)
    _play(response, pin_audio_url)
    _gather(response, action_url, num_digits=4)

    return ET.tostring(
        response,
        encoding="unicode",
        xml_declaration=True,
    )


def twiml_play_and_hangup(audio_url: str) -> str:
    """Play a final message and end the call."""
    response = _response()

    _play(response, audio_url)
    ET.SubElement(response, "Hangup")

    return ET.tostring(
        response,
        encoding="unicode",
        xml_declaration=True,
    )
