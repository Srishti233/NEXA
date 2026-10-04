"""Download the Piper voice configured in config.TTS_VOICE into ./models.

    python scripts/download_model.py            # voice from config.py
    python scripts/download_model.py en_US-amy-medium

Uses only the standard library. Voices come from the official
https://huggingface.co/rhasspy/piper-voices repository (MIT licensed).
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def voice_url_prefix(voice: str) -> str:
    """'en_US-john-medium' -> '<base>/en/en_US/john/medium/en_US-john-medium'."""
    try:
        lang, name, quality = voice.split("-", 2)
        family = lang.split("_")[0]
    except ValueError:
        raise SystemExit(
            f"Unrecognised voice name '{voice}'. Expected something like en_US-john-medium."
        ) from None
    return f"{BASE_URL}/{family}/{lang}/{name}/{quality}/{voice}"


def download(url: str, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"already present: {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    print(f"downloading {dest.name} ...")
    try:
        with urllib.request.urlopen(url, timeout=30) as response, part.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while block := response.read(1 << 20):
                out.write(block)
                done += len(block)
                if total:
                    print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
            print()
    except (urllib.error.URLError, TimeoutError) as exc:
        part.unlink(missing_ok=True)
        raise SystemExit(f"Download failed: {exc}\n  URL: {url}") from exc
    part.replace(dest)


def main() -> None:
    import config

    voice = sys.argv[1] if len(sys.argv) > 1 else config.TTS_VOICE
    prefix = voice_url_prefix(voice)
    models_dir = Path(config.MODELS_DIR)
    download(f"{prefix}.onnx", models_dir / f"{voice}.onnx")
    download(f"{prefix}.onnx.json", models_dir / f"{voice}.onnx.json")
    print(f"\nDone. Voice '{voice}' is ready in {models_dir}")
    if voice != config.TTS_VOICE:
        print(f"Set TTS_VOICE = \"{voice}\" in config.py (or config_local.py) to use it.")


if __name__ == "__main__":
    main()
