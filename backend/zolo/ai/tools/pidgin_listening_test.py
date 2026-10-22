"""Render a few Pidgin readback lines so a native speaker can judge them before we lock wording.

    python -m zolo.ai.tools.pidgin_listening_test [--voices idera,jude]

Writes mp3 files and a README.txt to var/listening/ (gitignored). Uses live YarnGPT credits:
4 lines x the number of voices.
"""

import argparse
from pathlib import Path

from zolo.ai.config import Settings, load_dotenv
from zolo.ai.readbacks import render_readback
from zolo.ai.tts.yarngpt import YarnGPTRenderer

CASES = [
    ("Bisi Ventures", 1_500_000),
    ("Bisi Ventures", 5_100_000),
    ("Mama Chi Stores", 1_850_000),
    ("Tunde Bakare", 250_000),
]
OUT = Path("var/listening")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voices", help="comma separated voice ids; default is the configured one")
    args = ap.parse_args()
    load_dotenv()
    settings = Settings.from_env()
    voices = args.voices.split(",") if args.voices else [settings.tts_voice_for("pcm")]

    OUT.mkdir(parents=True, exist_ok=True)
    renderer, notes = YarnGPTRenderer(), []
    for voice in voices:
        for i, (payee, kobo) in enumerate(CASES, 1):
            text = render_readback("pcm", payee, kobo)
            path = OUT / f"pcm_{voice}_{i}.mp3"
            path.write_bytes(renderer.render(text, "pcm", voice, 30.0).data)
            notes.append(f"{path.name}\t{text}")
            print("wrote", path)
    (OUT / "README.txt").write_text(
        "Pidgin listening test. Does it sound natural? Are numbers clear? Note the best voice.\n\n"
        + "\n".join(notes)
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
