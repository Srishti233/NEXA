"""NEXA configuration.

Edit the values below, or create a ``config_local.py`` next to this file to
override any of them on your own machine without touching tracked files
(``config_local.py`` is git-ignored).  Example::

    # config_local.py
    MICROPHONE_DEVICE_INDEX = 1
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- Identity ---------------------------------------------------------------
ASSISTANT_NAME = "NEXA"
ASSISTANT_VERSION = "0.1"

# --- Speech-to-text (faster-whisper) ----------------------------------------
STT_MODEL = "tiny"
STT_LANGUAGE = "en"
STT_TIMEOUT = 10  # max seconds of recording per command
STT_DEVICE = "cpu"
STT_COMPUTE_TYPE = "int8"
STT_NO_SPEECH_TIMEOUT = 5  # give up if nothing is said within this many seconds
STT_SILENCE_DURATION = 1.0  # seconds of silence that end a command
STT_MIN_ENERGY = 0.01  # minimum RMS level counted as speech

# --- Text-to-speech (Piper) -------------------------------------------------
TTS_ENABLED = True
TTS_VOICE = "en_US-john-medium"
TTS_SPEED = 1.08
MODELS_DIR = BASE_DIR / "models"  # the project root is also searched

# --- Audio ------------------------------------------------------------------
MICROPHONE_DEVICE_INDEX = None  # None = system default; list devices with scripts/list_audio_devices.py
SPEAKER_DEVICE_INDEX = None
SAMPLE_RATE = 48000
CHUNK_SIZE = 1280

# --- Behaviour --------------------------------------------------------------
SILENT_MODE = False
DEBUG_MODE = True

# --- Resource monitoring ----------------------------------------------------
RESOURCE_MONITOR = True
MAX_IDLE_RAM_MB = 500
MAX_ACTIVE_RAM_MB = 2000
CPU_THROTTLE_PERCENT = 80

# --- Logging ----------------------------------------------------------------
LOG_FILE = "nexa.log"
LOG_LEVEL = "INFO"
KEEP_LOG_HISTORY = True
MAX_LOG_SIZE_MB = 10

# --- Personality ------------------------------------------------------------
PERSONALITY = {
    "name": "NEXA",
    "tone": "confident, friendly, playful",
    "default_greeting": "Greetings love. I am NEXA. What can I do for you?",
    "error_response": "I didn't catch that. Try again.",
    "application_not_found": "I couldn't find that application.",
    "unknown_command": "I'm not sure how to do that yet.",
    "silent_mode_enabled": "Alright. I'll keep listening, just without the commentary.",
    "silent_mode_disabled": "Finally. I was starting to feel unwanted.",
}

# --- Feature switches -------------------------------------------------------
ENABLE_APPLICATIONS = True
ENABLE_FOLDERS = True
ENABLE_SYSTEM_INFO = True
ENABLE_TIME_DATE = True
ENABLE_CONVERSATION = True

# --- Safety -----------------------------------------------------------------
ALLOW_SHELL_COMMANDS = False
ALLOW_ADMIN_COMMANDS = False
ALLOW_DESTRUCTIVE_COMMANDS = False  # enables confirmed shutdown / restart
CONFIRMATION_TIMEOUT = 30  # seconds a pending confirmation stays valid

# --- Allow-lists ------------------------------------------------------------
# NEXA only ever launches targets listed here; spoken text is never executed.
# Format: "spoken name": ("launch target", ("extra", "aliases"))
APPLICATIONS = {
    "chrome": ("chrome", ("google chrome",)),
    "edge": ("msedge", ("microsoft edge",)),
    "firefox": ("firefox", ()),
    "pycharm": ("pycharm64.exe", ("py charm",)),
    "vs code": ("code", ("vscode", "visual studio code", "v s code")),
    "file explorer": ("explorer", ("explorer", "files", "file manager")),
    "notepad": ("notepad", ("note pad",)),
    "calculator": ("calc", ("calc",)),
    "task manager": ("taskmgr", ()),
    "command prompt": ("cmd", ("cmd",)),
    "paint": ("mspaint", ()),
    "spotify": ("spotify", ()),
    "discord": ("discord", ()),
}

WEBSITES = {
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com",
}

_HOME = Path.home()
FOLDERS = {
    "downloads": _HOME / "Downloads",
    "documents": _HOME / "Documents",
    "desktop": _HOME / "Desktop",
    "pictures": _HOME / "Pictures",
    "music": _HOME / "Music",
    "videos": _HOME / "Videos",
}

SETTINGS_PAGES = {
    "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth",
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "battery": "ms-settings:batterysaver",
    "update": "ms-settings:windowsupdate",
    "privacy": "ms-settings:privacy",
    "apps": "ms-settings:appsfeatures",
    "settings": "ms-settings:",
}

# --- Local overrides --------------------------------------------------------
try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
