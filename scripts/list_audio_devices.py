"""Print audio devices so you can set MICROPHONE_DEVICE_INDEX / SPEAKER_DEVICE_INDEX."""

import sounddevice as sd

default_in, default_out = sd.default.device
print(f"{'idx':>3}  {'in':>2} {'out':>3}  {'rate':>6}  name")
for index, dev in enumerate(sd.query_devices()):
    marks = []
    if index == default_in:
        marks.append("default input")
    if index == default_out:
        marks.append("default output")
    print(
        f"{index:>3}  {dev['max_input_channels']:>2} {dev['max_output_channels']:>3}  "
        f"{int(dev['default_samplerate']):>6}  {dev['name']}  {'<- ' + ', '.join(marks) if marks else ''}"
    )
print("\nPut the index of your microphone in config_local.py, e.g.  MICROPHONE_DEVICE_INDEX = 1")
