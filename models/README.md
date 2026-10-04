# Models

Piper voice files live here but are **not committed** (the `.onnx` is ~64 MB).

Download the voice configured in `config.py`:

```powershell
python scripts/download_model.py
```

This fetches `en_US-john-medium.onnx` and `en_US-john-medium.onnx.json` from the official
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) repository.
Both files must sit side by side in this folder.
