"""Speech-to-text using faster-whisper with a simple energy-based recorder."""

from __future__ import annotations

import logging
import time

import numpy as np

import config

logger = logging.getLogger(__name__)

WHISPER_RATE = 16000
_PRE_ROLL_SECONDS = 0.3
_CALIBRATION_SECONDS = 0.3
_NOISE_MARGIN = 3.0
_IGNORED_TEXT = {"", "you", "thank you.", "thanks for watching!", "[blank_audio]"}


def resample_to_whisper(audio: np.ndarray, source_rate: int) -> np.ndarray:
    """Convert mono float32 audio to 16 kHz, which Whisper expects."""
    audio = np.asarray(audio, dtype=np.float32)
    if source_rate == WHISPER_RATE or audio.size == 0:
        return audio
    if source_rate % WHISPER_RATE == 0:
        factor = source_rate // WHISPER_RATE
        usable = (audio.size // factor) * factor
        return audio[:usable].reshape(-1, factor).mean(axis=1).astype(np.float32)
    target_len = int(round(audio.size * WHISPER_RATE / source_rate))
    positions = np.linspace(0, audio.size - 1, num=target_len)
    return np.interp(positions, np.arange(audio.size), audio).astype(np.float32)


def rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0


class SpeechToText:
    """Records one spoken command and transcribes it locally."""

    def __init__(self) -> None:
        from faster_whisper import WhisperModel  # heavy import, keep lazy

        logger.info(
            "Loading Whisper model '%s' (%s, %s)...",
            config.STT_MODEL,
            config.STT_DEVICE,
            config.STT_COMPUTE_TYPE,
        )
        self.model = WhisperModel(
            config.STT_MODEL,
            device=config.STT_DEVICE,
            compute_type=config.STT_COMPUTE_TYPE,
        )
        self.sample_rate = int(config.SAMPLE_RATE)
        self.chunk_size = int(config.CHUNK_SIZE)

    # -- recording -----------------------------------------------------------
    def record_utterance(self) -> np.ndarray | None:
        """Record until the speaker stops. Returns mono float32 audio or None."""
        import sounddevice as sd

        chunk_seconds = self.chunk_size / self.sample_rate
        silence_limit = max(1, int(config.STT_SILENCE_DURATION / chunk_seconds))
        pre_roll_chunks = max(1, int(_PRE_ROLL_SECONDS / chunk_seconds))
        calibration_chunks = max(1, int(_CALIBRATION_SECONDS / chunk_seconds))

        pre_roll: list[np.ndarray] = []
        recorded: list[np.ndarray] = []
        noise_levels: list[float] = []
        threshold = float(config.STT_MIN_ENERGY)
        speaking = False
        silent_chunks = 0
        started = time.monotonic()
        speech_started_at = 0.0

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.chunk_size,
            device=config.MICROPHONE_DEVICE_INDEX,
        ) as stream:
            while True:
                data, overflowed = stream.read(self.chunk_size)
                if overflowed:
                    logger.debug("Audio input overflow")
                chunk = data[:, 0].copy()
                level = rms(chunk)
                now = time.monotonic()

                # Learn the room's noise floor from the first few chunks.
                if len(noise_levels) < calibration_chunks:
                    noise_levels.append(level)
                    pre_roll.append(chunk)
                    if len(noise_levels) == calibration_chunks:
                        threshold = max(threshold, float(np.mean(noise_levels)) * _NOISE_MARGIN)
                        logger.debug("Speech threshold: %.4f", threshold)
                    continue

                if not speaking:
                    pre_roll.append(chunk)
                    pre_roll = pre_roll[-pre_roll_chunks:]
                    if level >= threshold:
                        speaking = True
                        speech_started_at = now
                        recorded.extend(pre_roll)
                    elif now - started > config.STT_NO_SPEECH_TIMEOUT:
                        logger.info("No speech detected.")
                        return None
                    continue

                recorded.append(chunk)
                silent_chunks = silent_chunks + 1 if level < threshold else 0
                if silent_chunks >= silence_limit:
                    break
                if now - speech_started_at > config.STT_TIMEOUT:
                    logger.info("Recording time limit reached.")
                    break

        return np.concatenate(recorded) if recorded else None

    # -- transcription -------------------------------------------------------
    def transcribe(self, audio: np.ndarray) -> str:
        audio16k = resample_to_whisper(audio, self.sample_rate)
        if audio16k.size < WHISPER_RATE // 4:  # shorter than 0.25 s
            return ""
        segments, _info = self.model.transcribe(
            audio16k,
            language=config.STT_LANGUAGE,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return "" if text.lower() in _IGNORED_TEXT else text

    def transcribe_command(self) -> str:
        """Listen for one command and return its text ('' if nothing was heard)."""
        audio = self.record_utterance()
        if audio is None:
            return ""
        return self.transcribe(audio)

    def cleanup(self) -> None:
        self.model = None
