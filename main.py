"""NEXA - a lightweight, local-first voice assistant for Windows.

Flow: INSERT key -> speech-to-text -> command routing -> action -> voice reply.
"""

from __future__ import annotations

import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import keyboard
import psutil

from commands import CommandIntentHandler
from config import (
    ASSISTANT_NAME,
    ASSISTANT_VERSION,
    BASE_DIR,
    DEBUG_MODE,
    KEEP_LOG_HISTORY,
    LOG_FILE,
    LOG_LEVEL,
    MAX_ACTIVE_RAM_MB,
    MAX_IDLE_RAM_MB,
    MAX_LOG_SIZE_MB,
    PERSONALITY,
    RESOURCE_MONITOR,
    SILENT_MODE,
)
from voice import SpeechToText, TextToSpeech

UNKNOWN = "__UNKNOWN__"
DEFAULT_UNKNOWN = "I'm not sure how to do that yet."


def setup_logging() -> logging.Logger:
    root = logging.getLogger()
    if root.handlers:
        return logging.getLogger(__name__)

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    root.setLevel(level)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)

    log_path = Path(LOG_FILE)
    if not log_path.is_absolute():
        log_path = BASE_DIR / log_path
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=int(MAX_LOG_SIZE_MB * 1024 * 1024),
        backupCount=3 if KEEP_LOG_HISTORY else 1,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    root.addHandler(console)
    root.addHandler(file_handler)
    return logging.getLogger(__name__)


class NEXA:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.name = ASSISTANT_NAME
        self.version = ASSISTANT_VERSION
        self.silent_mode = SILENT_MODE
        self.running = False

        self.speech_to_text: SpeechToText | None = None
        self.text_to_speech: TextToSpeech | None = None
        self.command_handler: CommandIntentHandler | None = None

    # ------------------------------------------------------------------ setup
    def initialize(self) -> bool:
        try:
            self.logger.info("=" * 60)
            self.logger.info("%s v%s initializing...", self.name, self.version)
            self.logger.info("=" * 60)

            self.logger.info("Initializing speech-to-text engine...")
            self.speech_to_text = SpeechToText()

            self.logger.info("Initializing text-to-speech engine...")
            self.text_to_speech = TextToSpeech(silent_mode=self.silent_mode)

            self.logger.info("Initializing command handler...")
            self.command_handler = CommandIntentHandler()

            self.logger.info("%s initialization complete.", self.name)
            self.logger.info("Silent mode: %s", self.silent_mode)
            self.logger.info("Debug mode: %s", DEBUG_MODE)
            self.logger.info("Resource monitoring: %s", RESOURCE_MONITOR)
            return True
        except Exception as exc:
            self.logger.exception("NEXA initialization failed: %s", exc)
            self.shutdown()
            return False

    # ----------------------------------------------------------------- output
    def speak(self, text: str) -> bool:
        if self.text_to_speech is None or text is None:
            return False
        text = str(text).strip()
        if not text or text == "_":
            return False
        try:
            return self.text_to_speech.speak(text)
        except Exception as exc:
            self.logger.error("TTS error: %s", exc)
            return False

    # ------------------------------------------------------------------ input
    def wait_for_activation(self) -> bool:
        try:
            print()
            print("\U0001F47B NEXA is waiting...")
            print("Press INSERT to wake NEXA")
            print("Press Ctrl+C to stop")
            self.logger.info("Waiting for INSERT key...")

            keyboard.wait("insert")
            # Wait for key release so one press triggers exactly one activation.
            while keyboard.is_pressed("insert"):
                time.sleep(0.05)

            self.logger.info("[WAKE] INSERT key pressed.")
            print()
            print("\U0001F47B NEXA activated!")
            return True
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.logger.error("Keyboard activation error: %s", exc)
            time.sleep(1)  # avoid a hot loop if the keyboard hook keeps failing
            return False

    def listen_for_command(self) -> str:
        if self.speech_to_text is None:
            return ""
        try:
            print()
            print("\U0001F3A4 Listening...")
            command = self.speech_to_text.transcribe_command()
            return str(command).strip() if command else ""
        except Exception as exc:
            self.logger.error("Speech recognition error: %s", exc)
            return ""

    # ---------------------------------------------------------------- routing
    def process_command(self, command_text: str) -> tuple[str, str]:
        if self.command_handler is None:
            return "error", "My command system isn't ready yet."

        unknown_text = PERSONALITY.get("unknown_command", DEFAULT_UNKNOWN)

        try:
            result = self.command_handler.handle_command(command_text)

            if isinstance(result, (tuple, list)) and result:
                command_type = result[0]
                response = result[1] if len(result) > 1 else unknown_text
            else:
                command_type, response = UNKNOWN, unknown_text

            command_type = str(command_type or "").strip() or UNKNOWN
            response = "" if response is None else str(response).strip()

            # A bare "_" is a placeholder, never a real reply.
            if response == "_":
                command_type, response = UNKNOWN, unknown_text

            if command_type == "silent_mode":
                return self._apply_silent_mode(command_type, response)

            if command_type == UNKNOWN:
                self.logger.info("[ACTION] unknown_command")
                response = response or unknown_text

            return command_type, response

        except Exception as exc:
            self.logger.exception("Command processing error: %s", exc)
            return "error", PERSONALITY.get("error_response", "I encountered an error.")

    def _apply_silent_mode(self, command_type: str, response: str) -> tuple[str, str]:
        enable = response == "ENABLE"
        self.silent_mode = enable
        if self.text_to_speech:
            self.text_to_speech.set_silent_mode(enable)
        self.logger.info("Silent mode %s.", "enabled" if enable else "disabled")

        if enable:
            # Nothing is spoken in silent mode, so show the acknowledgement instead.
            print(f"NEXA: {PERSONALITY.get('silent_mode_enabled', 'Silent mode on.')}")
            return command_type, ""
        return command_type, response

    # ------------------------------------------------------------- monitoring
    def _log_resource_usage(self, state: str) -> None:
        if not RESOURCE_MONITOR:
            return
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            cpu_percent = process.cpu_percent(interval=0.05)
            self.logger.debug("[%s] RAM: %.1f MB | CPU: %.1f%%", state, memory_mb, cpu_percent)

            limit = MAX_IDLE_RAM_MB if state == "IDLE" else MAX_ACTIVE_RAM_MB
            if memory_mb > limit:
                self.logger.warning(
                    "[%s] RAM %.0f MB is above the configured limit of %d MB.",
                    state,
                    memory_mb,
                    limit,
                )
        except Exception as exc:
            self.logger.debug("Could not read resource usage: %s", exc)

    def _return_to_idle(self) -> None:
        self._log_resource_usage("IDLE")
        self.logger.info("Returning to idle state...")

    # ------------------------------------------------------------------- loop
    def run(self) -> None:
        self.running = True
        self.logger.info("%s is ready.", self.name)
        self._log_resource_usage("IDLE")

        try:
            while self.running:
                if not self.wait_for_activation():
                    continue

                self.logger.info("[WAKE] NEXA activated by INSERT.")
                self._log_resource_usage("ACTIVE")

                self.speak(PERSONALITY.get("default_greeting", "Yes?"))

                command_text = self.listen_for_command()
                if not command_text:
                    self.speak(PERSONALITY.get("error_response", "I didn't catch that. Try again."))
                    self._return_to_idle()
                    continue

                self.logger.info("[STT] User said: %s", command_text)
                print(f"\U0001F5E3\uFE0F You said: {command_text}")

                command_type, response = self.process_command(command_text)
                self.logger.info("[ACTION] %s", command_type)

                if response:
                    self.speak(response)

                self._return_to_idle()

        except KeyboardInterrupt:
            self.logger.info("%s interrupted by user.", self.name)
            self.shutdown()
        except Exception as exc:
            self.logger.exception("Runtime error: %s", exc)
            self.shutdown()

    # --------------------------------------------------------------- shutdown
    def shutdown(self) -> None:
        self.logger.info("Shutting down %s...", self.name)
        self.running = False

        for label, component in (
            ("TTS", self.text_to_speech),
            ("STT", self.speech_to_text),
        ):
            try:
                if component:
                    component.cleanup()
            except Exception as exc:
                self.logger.warning("%s cleanup error: %s", label, exc)

        self.logger.info("%s shutdown complete.", self.name)


def main() -> None:
    # Emoji in the console banner would crash a cp1252 Windows console otherwise.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    logger = setup_logging()
    nexa = NEXA()

    if not nexa.initialize():
        logger.error("Failed to initialize %s.", nexa.name)
        sys.exit(1)

    try:
        nexa.run()
    except Exception as exc:
        logger.exception("Fatal NEXA error: %s", exc)
        nexa.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
