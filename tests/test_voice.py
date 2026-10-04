"""Pure-logic tests for the voice package (no audio hardware or models needed)."""

import numpy as np
import pytest

pytest.importorskip("numpy")

from voice.speech_to_text import WHISPER_RATE, resample_to_whisper, rms  # noqa: E402
from voice.text_to_speech import clean_text, find_voice_files  # noqa: E402


def test_resample_48k_to_16k_length():
    audio = np.random.default_rng(0).standard_normal(48000).astype(np.float32)
    out = resample_to_whisper(audio, 48000)
    assert out.dtype == np.float32
    assert out.size == WHISPER_RATE


def test_resample_44k_to_16k_length():
    out = resample_to_whisper(np.zeros(44100, dtype=np.float32), 44100)
    assert out.size == WHISPER_RATE


def test_resample_noop_at_16k():
    audio = np.ones(100, dtype=np.float32)
    assert resample_to_whisper(audio, 16000) is audio or np.array_equal(
        resample_to_whisper(audio, 16000), audio
    )


def test_rms():
    assert rms(np.zeros(10, dtype=np.float32)) == 0.0
    assert rms(np.ones(10, dtype=np.float32)) == pytest.approx(1.0)
    assert rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_clean_text():
    assert clean_text("**Hello**   _world_ #1") == "Hello world 1"


def test_find_voice_files_accepts_misnamed_json(tmp_path, monkeypatch):
    import config

    (tmp_path / "v.onnx").write_bytes(b"x")
    (tmp_path / "v_onnx.json").write_text("{}")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path / "nowhere")
    model, cfg = find_voice_files("v")
    assert model.name == "v.onnx" and cfg.name == "v_onnx.json"


def test_find_voice_files_missing(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    assert find_voice_files("nope") is None
