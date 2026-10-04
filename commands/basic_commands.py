"""Intent matching and safe command execution.

``CommandIntentHandler.handle_command(text)`` returns ``(command_type, response)``.

Safety model: spoken text is only ever *matched* against the allow-lists in
``config.py``; it is never passed to a shell or executed.  Launch targets come
exclusively from config.  Sensitive actions (lock, shutdown, restart) need a
spoken confirmation, and shutdown/restart are off unless
``ALLOW_DESTRUCTIVE_COMMANDS`` is enabled.
"""

from __future__ import annotations

import logging
import os
import random
import re
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import psutil

import config

logger = logging.getLogger(__name__)

UNKNOWN = "__UNKNOWN__"
IS_WINDOWS = sys.platform == "win32"

_WAKE_PREFIX = re.compile(r"^(?:(?:hey|ok|okay)\s+nexa\b|nexa\b)[\s,]*")
_POLITE_PREFIX = re.compile(
    r"^(?:(?:please|can you|could you|would you|will you|i want you to|i need you to)\s+)+"
)
_POLITE_SUFFIX = re.compile(r"\s+(?:please|for me)$")
# Strong verbs mean "launch something"; weak verbs fall through to other intents.
_STRONG_OPEN_VERBS = ("open", "launch", "start", "run")
_WEAK_OPEN_VERBS = ("show me", "show", "go to")
_YES = {"yes", "yeah", "yep", "confirm", "confirmed", "do it", "go ahead", "sure", "proceed"}
_NO = {"no", "nope", "cancel", "stop", "never mind", "nevermind", "abort", "dont"}


# --------------------------------------------------------------------------- #
# Platform actions (isolated so tests can replace them)
# --------------------------------------------------------------------------- #
def _require_windows() -> None:
    if not IS_WINDOWS:
        raise OSError("This action is only supported on Windows.")


def launch_app(target: str) -> None:
    """Start an allow-listed application via the Windows shell."""
    _require_windows()
    subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)  # noqa: S603,S607


def open_path(path: Path) -> None:
    _require_windows()
    os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606


def open_uri(uri: str) -> None:
    if uri.startswith("ms-settings:"):
        _require_windows()
        os.startfile(uri)  # type: ignore[attr-defined]  # noqa: S606
    else:
        webbrowser.open(uri)


def send_hotkey(combo: str) -> None:
    import keyboard

    keyboard.send(combo)


def run_system(args: list[str]) -> None:
    _require_windows()
    subprocess.Popen(args, shell=False)  # noqa: S603


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def normalize(text: str) -> str:
    """Lowercase, drop punctuation and filler words ("hey nexa, please ...")."""
    text = text.lower().replace("'", "")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("wi fi", "wifi")
    text = _WAKE_PREFIX.sub("", text)
    text = _POLITE_PREFIX.sub("", text)
    return _POLITE_SUFFIX.sub("", text).strip()


def has_word(text: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"


def _gb(n_bytes: float) -> str:
    return f"{n_bytes / 1024**3:.1f}"


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #
class CommandIntentHandler:
    def __init__(self) -> None:
        self._pending: tuple[str, float] | None = None  # (action, expires_at)
        self._jokes = (
            "Why do programmers prefer dark mode? Because light attracts bugs.",
            "I told my computer I needed a break. It said no problem, it'll go to sleep.",
            "There are ten kinds of people: those who understand binary, and those who don't.",
        )

    # -- entry point ---------------------------------------------------------
    def handle_command(self, text: str) -> tuple[str, str]:
        raw = (text or "").strip()
        cmd = normalize(raw)
        logger.info("Command: %r -> %r", raw, cmd)
        if not cmd:
            if "nexa" in raw.lower():
                return "conversation", "I'm here. What do you need?"
            return UNKNOWN, config.PERSONALITY["unknown_command"]

        for handler in (
            self._handle_confirmation,
            self._handle_silent_mode,
            self._handle_open,
            self._handle_power,
            self._handle_system_info,
            self._handle_time_date,
            self._handle_help,
            self._handle_conversation,
        ):
            result = handler(cmd)
            if result is not None:
                return result

        return UNKNOWN, config.PERSONALITY["unknown_command"]

    # -- confirmation flow ---------------------------------------------------
    def _ask_confirmation(self, action: str, question: str) -> tuple[str, str]:
        self._pending = (action, time.monotonic() + config.CONFIRMATION_TIMEOUT)
        return "confirmation_required", f"{question} Press Insert and say yes to confirm."

    def _handle_confirmation(self, cmd: str) -> tuple[str, str] | None:
        if self._pending is None:
            return None
        action, expires_at = self._pending
        self._pending = None
        if time.monotonic() > expires_at:
            return None  # stale; treat the new text as a normal command
        if cmd in _YES:
            return self._execute_confirmed(action)
        if cmd in _NO:
            return "confirmation_cancelled", "Okay, cancelled."
        return None

    def _execute_confirmed(self, action: str) -> tuple[str, str]:
        try:
            if action == "lock":
                _require_windows()
                import ctypes

                ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
                return "lock", "Locking your computer."
            if action == "shutdown":
                run_system(["shutdown", "/s", "/t", "10"])
                return "shutdown", "Shutting down in ten seconds."
            if action == "restart":
                run_system(["shutdown", "/r", "/t", "10"])
                return "restart", "Restarting in ten seconds."
        except OSError as exc:
            logger.error("Confirmed action %s failed: %s", action, exc)
            return "error", "I couldn't do that on this system."
        return UNKNOWN, config.PERSONALITY["unknown_command"]

    # -- silent mode ---------------------------------------------------------
    def _handle_silent_mode(self, cmd: str) -> tuple[str, str] | None:
        disable = (
            "disable silent mode", "turn off silent mode", "silent mode off",
            "exit silent mode", "stop silent mode", "unmute", "speak again",
            "start talking", "talk to me", "you can talk",
        )
        enable = (
            "silent mode", "enable silent mode", "turn on silent mode", "be quiet",
            "stop talking", "mute", "shut up", "quiet mode",
        )
        if any(p in cmd for p in disable):
            return "silent_mode", config.PERSONALITY["silent_mode_disabled"]
        if cmd in enable or any(p in cmd for p in enable if " " in p):
            return "silent_mode", "ENABLE"
        return None

    # -- open <thing> --------------------------------------------------------
    def _extract_target(self, cmd: str) -> tuple[bool, str] | None:
        """Return (is_strong_verb, target) if ``cmd`` starts with an open-style verb."""
        for strong, verbs in ((True, _STRONG_OPEN_VERBS), (False, _WEAK_OPEN_VERBS)):
            for verb in verbs:
                if cmd == verb:
                    return strong, ""
                if cmd.startswith(verb + " "):
                    target = cmd[len(verb) + 1:]
                    return strong, re.sub(r"^(?:the|my|a|an)\s+", "", target).strip()
        return None

    def _handle_open(self, cmd: str) -> tuple[str, str] | None:
        parsed = self._extract_target(cmd)
        if parsed is None:
            return None
        strong, target = parsed
        not_found = ("open_application", config.PERSONALITY["application_not_found"])
        if not target:
            return not_found if strong else None

        if "search" in target:
            return self._press("windows+s", "search_bar", "Opening search.")

        # Settings pages: "settings", "wifi settings", "bluetooth", "windows update", ...
        pages = [k for k in config.SETTINGS_PAGES if k != "settings"]
        page = next((k for k in pages if has_word(target, k, k + "s")), None)
        if "setting" in target or page:
            if page:
                return self._open_uri(
                    config.SETTINGS_PAGES[page], "open_settings", f"Opening {page} settings."
                )
            return self._open_uri(
                config.SETTINGS_PAGES["settings"], "open_settings", "Opening Settings."
            )

        if config.ENABLE_FOLDERS:
            for name, path in config.FOLDERS.items():
                if has_word(target, name, name.rstrip("s")):
                    return self._open_folder(name, Path(path))

        if config.ENABLE_APPLICATIONS:
            app = self._match_app(target)
            if app:
                return self._open_app(*app)
            for name, url in config.WEBSITES.items():
                if has_word(target, name):
                    return self._open_uri(url, "open_website", f"Opening {name}.")

        return not_found if strong else None

    def _match_app(self, target: str) -> tuple[str, str] | None:
        """Return (spoken name, launch target) for the best allow-list match."""
        best: tuple[int, str, str] | None = None
        for name, (launch, aliases) in config.APPLICATIONS.items():
            for phrase in (name, *aliases):
                if has_word(target, phrase) and (best is None or len(phrase) > best[0]):
                    best = (len(phrase), name, launch)
        return (best[1], best[2]) if best else None

    def _open_app(self, name: str, launch: str) -> tuple[str, str]:
        try:
            launch_app(launch)
            return "open_application", f"Opening {name}."
        except OSError as exc:
            logger.error("Could not launch %s: %s", name, exc)
            return "open_application", config.PERSONALITY["application_not_found"]

    def _open_folder(self, name: str, path: Path) -> tuple[str, str]:
        try:
            open_path(path)
            return "open_folder", f"Opening {name}."
        except OSError as exc:
            logger.error("Could not open folder %s: %s", path, exc)
            return "open_folder", f"I couldn't open {name}."

    def _open_uri(self, uri: str, kind: str, reply: str) -> tuple[str, str]:
        try:
            open_uri(uri)
            return kind, reply
        except OSError as exc:
            logger.error("Could not open %s: %s", uri, exc)
            return kind, "I couldn't open that."

    def _press(self, combo: str, kind: str, reply: str) -> tuple[str, str]:
        try:
            send_hotkey(combo)
            return kind, reply
        except Exception as exc:  # keyboard raises various errors per platform
            logger.error("Hotkey %s failed: %s", combo, exc)
            return kind, "I couldn't do that."

    # -- lock / shutdown / restart ------------------------------------------
    def _handle_power(self, cmd: str) -> tuple[str, str] | None:
        if has_word(cmd, "lock") and has_word(cmd, "computer", "pc", "screen", "laptop", "it"):
            return self._ask_confirmation("lock", "Do you want me to lock your computer?")
        if cmd in ("lock", "lock it"):
            return self._ask_confirmation("lock", "Do you want me to lock your computer?")

        wants_shutdown = has_word(cmd, "shutdown", "shut") and not has_word(cmd, "up")
        wants_restart = has_word(cmd, "restart", "reboot")
        if wants_shutdown or wants_restart:
            if not config.ALLOW_DESTRUCTIVE_COMMANDS:
                return "blocked", "Power commands are disabled in my settings."
            action = "restart" if wants_restart else "shutdown"
            return self._ask_confirmation(action, f"Are you sure you want to {action}?")
        return None

    # -- system information --------------------------------------------------
    def _handle_system_info(self, cmd: str) -> tuple[str, str] | None:
        if not config.ENABLE_SYSTEM_INFO:
            return None
        if has_word(cmd, "ram", "memory"):
            m = psutil.virtual_memory()
            return "system_info", (
                f"You're using {m.percent:.0f} percent of your RAM, "
                f"{_gb(m.used)} of {_gb(m.total)} gigabytes."
            )
        if has_word(cmd, "cpu", "processor"):
            return "system_info", f"CPU usage is {psutil.cpu_percent(interval=0.5):.0f} percent."
        if has_word(cmd, "storage", "disk", "drive", "space", "hard drive"):
            d = psutil.disk_usage(Path.home().anchor or "/")
            return "system_info", (
                f"You have {_gb(d.free)} gigabytes free out of {_gb(d.total)}, "
                f"{d.percent:.0f} percent used."
            )
        if has_word(cmd, "battery", "charge", "charging"):
            b = psutil.sensors_battery()
            if b is None:
                return "system_info", "I can't find a battery. This looks like a desktop."
            state = "plugged in" if b.power_plugged else "on battery"
            return "system_info", f"Battery is at {b.percent:.0f} percent and {state}."
        if has_word(cmd, "network", "wifi", "internet", "connection", "online"):
            return "system_info", self._network_status()
        if has_word(cmd, "system") and has_word(cmd, "status", "info", "information", "usage"):
            m = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.5)
            return "system_info", (
                f"CPU is at {cpu:.0f} percent and RAM is at {m.percent:.0f} percent."
            )
        return None

    @staticmethod
    def _network_status() -> str:
        stats = psutil.net_if_stats()
        active = [n for n, s in stats.items() if s.isup and not n.lower().startswith(("lo", "loopback"))]
        if not active:
            return "You don't appear to be connected to any network."
        wifi = [n for n in active if "wi" in n.lower() and "fi" in n.lower()]
        kind = "Wi-Fi" if wifi else "a network adapter"
        return f"You're connected through {kind}."

    # -- time and date -------------------------------------------------------
    def _handle_time_date(self, cmd: str) -> tuple[str, str] | None:
        if not config.ENABLE_TIME_DATE:
            return None
        now = datetime.now()
        if has_word(cmd, "time"):
            return "time_date", f"It's {now.strftime('%I:%M %p').lstrip('0')}."
        if has_word(cmd, "date", "today", "day"):
            if has_word(cmd, "day") and not has_word(cmd, "date"):
                return "time_date", f"It's {now.strftime('%A')}."
            return "time_date", f"Today is {now.strftime('%A')}, {now.strftime('%B')} {_ordinal(now.day)}."
        return None

    # -- help ----------------------------------------------------------------
    def _handle_help(self, cmd: str) -> tuple[str, str] | None:
        if has_word(cmd, "help") or "what can you do" in cmd or "what do you do" in cmd:
            return "help", (
                "I can open apps, websites, folders and Windows settings, "
                "tell you your CPU, RAM, storage and battery status, "
                "give you the time and date, and chat a little. "
                "Try saying, open Chrome, or, what is my RAM usage."
            )
        return None

    # -- conversation --------------------------------------------------------
    def _handle_conversation(self, cmd: str) -> tuple[str, str] | None:
        if not config.ENABLE_CONVERSATION:
            return None
        if re.fullmatch(r"(?:hello|hi|hey)(?: nexa)?", cmd):
            return "conversation", "Hello there. What can I do for you?"
        if "how are you" in cmd:
            return "conversation", "Running smoothly and feeling quite confident, thanks for asking."
        if "who are you" in cmd or "your name" in cmd or "what are you" in cmd:
            return "conversation", (
                f"I'm {config.ASSISTANT_NAME}, your local voice assistant. "
                "Everything I do stays on this computer."
            )
        if "version" in cmd:
            return "conversation", f"I'm {config.ASSISTANT_NAME} version {config.ASSISTANT_VERSION}."
        if has_word(cmd, "thanks", "thank"):
            return "conversation", "Anytime."
        if "joke" in cmd:
            return "conversation", random.choice(self._jokes)  # noqa: S311
        if has_word(cmd, "goodbye", "bye"):
            return "conversation", "Goodbye. I'll be here when you press Insert."
        return None
