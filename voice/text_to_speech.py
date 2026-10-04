"""Text-to-speech using Piper (local, neural)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np

import config

logger = logging.getLogger(__name__)

_STRIP = re.compile(r"[*_`#~<>|\\]")


def clean_text(text: str) -> str:
    """Remove markdown-ish symbols that sound odd when read aloud."""
    return re.sub(r"\s+", " ", _STRIP.sub(" ", text)).strip()


def find_voice_files(voice: str) -> tuple[Path, Path] | None:
    """Locate ``<voice>.onnx`` and its JSON config.

    Searches ``config.MODELS_DIR`` and the project root. Also accepts the
    ``<voice>_onnx.json`` name that browsers sometimes produce when saving
    ``<voice>.onnx.json``.
    """
    for folder in (Path(config.MODELS_DIR), Path(config.BASE_DIR)):
        model = folder / f"{voice}.onnx"
        if not model.is_file():
            continue
        for candidate in (folder / f"{voice}.onnx.json", folder / f"{voice}_onnx.json"):
            if candidate.is_file():
                return model, candidate
    return None


class TextToSpeech:
    def __init__(self, silent_mode: bool = False) -> None:
        self.silent_mode = silent_mode
        self.voice = None
        self.sample_rate = 22050
        self._syn_config = None

        if not config.TTS_ENABLED:
            logger.info("TTS disabled in config; replies will be printed only.")
            return
        self._load_voice()

    def _load_voice(self) -> None:
        files = find_voice_files(config.TTS_VOICE)
        if files is None:
            logger.error(
                "Piper voice '%s' not found in %s. Run: python scripts/download_model.py "
                "- NEXA will print replies instead of speaking.",
                config.TTS_VOICE,
                config.MODELS_DIR,
            )
            return

        from piper import PiperVoice, SynthesisConfig

        model_path, config_path = files
        logger.info("Loading Piper voice from %s", model_path)
        self.voice = PiperVoice.load(model_path, config_path=config_path)
        self.sample_rate = self.voice.config.sample_rate
        # length_scale > 1 is slower, so speed 1.08 -> length_scale ~0.926
        self._syn_config = SynthesisConfig(length_scale=1.0 / max(config.TTS_SPEED, 0.1))

    # -- public API ----------------------------------------------------------
    def set_silent_mode(self, enabled: bool) -> None:
        self.silent_mode = bool(enabled)

    def synthesize(self, text: str) -> np.ndarray:
        """Return float32 mono audio for ``text`` (empty array if unavailable)."""
        if self.voice is None:
            return np.zeros(0, dtype=np.float32)
        chunks = [
            chunk.audio_float_array
            for chunk in self.voice.synthesize(text, self._syn_config)
        ]
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

    def speak(self, text: str) -> bool:
        """Speak ``text``. Returns True if audio was actually played."""
        text = clean_text(text or "")
        if not text:
            return False

        print(f"NEXA: {text}")
        if self.silent_mode or self.voice is None:
            return False

        audio = self.synthesize(text)
        if audio.size == 0:
            return False
        self._play(audio, self.sample_rate)
        return True

    def _play(self, audio: np.ndarray, sample_rate: int) -> None:
        import sounddevice as sd

        sd.play(audio, samplerate=sample_rate, device=config.SPEAKER_DEVICE_INDEX)
        sd.wait()

    def cleanup(self) -> None:
        try:
            import sounddevice as sd

            sd.stop()
        except Exception as exc:  # PortAudio missing or device gone
            logger.debug("Audio stop skipped: %s", exc)
        self.voice = None
