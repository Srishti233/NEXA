import pytest

import config
from commands.basic_commands import UNKNOWN, normalize


@pytest.mark.parametrize(
    "spoken, expected",
    [
        ("Hey NEXA, please open Chrome!", "open chrome"),
        ("Nexa what's the time?", "whats the time"),
        ("Can you open Wi-Fi settings please", "open wifi settings"),
        ("  OPEN   notepad ", "open notepad"),
    ],
)
def test_normalize(spoken, expected):
    assert normalize(spoken) == expected


@pytest.mark.parametrize(
    "spoken, target",
    [
        ("Open Chrome", "chrome"),
        ("open google chrome", "chrome"),
        ("Open PyCharm", "pycharm64.exe"),
        ("open VS Code", "code"),
        ("open visual studio code", "code"),
        ("Open File Explorer", "explorer"),
        ("launch notepad", "notepad"),
    ],
)
def test_open_application(handler, actions, spoken, target):
    kind, reply = handler.handle_command(spoken)
    assert kind == "open_application"
    assert actions == [("app", target)]
    assert reply.startswith("Opening")


def test_open_unknown_application(handler, actions):
    kind, reply = handler.handle_command("open flux capacitor")
    assert kind == "open_application"
    assert reply == config.PERSONALITY["application_not_found"]
    assert actions == []


def test_open_settings(handler, actions):
    assert handler.handle_command("Open Settings")[0] == "open_settings"
    assert actions == [("uri", "ms-settings:")]


def test_open_specific_settings(handler, actions):
    handler.handle_command("open bluetooth settings")
    assert actions == [("uri", "ms-settings:bluetooth")]


def test_open_search_bar(handler, actions):
    kind, _ = handler.handle_command("Open the search bar")
    assert kind == "search_bar"
    assert actions == [("hotkey", "windows+s")]


def test_open_folder(handler, actions):
    kind, _ = handler.handle_command("open my downloads")
    assert kind == "open_folder"
    assert actions == [("path", "Downloads")]


def test_open_website(handler, actions):
    kind, _ = handler.handle_command("open youtube")
    assert kind == "open_website"
    assert actions == [("uri", "https://www.youtube.com")]


def test_weak_verb_falls_through_to_system_info(handler, actions):
    kind, reply = handler.handle_command("show me my cpu usage")
    assert kind == "system_info"
    assert "CPU" in reply
    assert actions == []


@pytest.mark.parametrize(
    "spoken, word",
    [
        ("What is my RAM usage?", "RAM"),
        ("what is my cpu usage", "CPU"),
        ("What is my storage?", "free"),
    ],
)
def test_system_info(handler, spoken, word):
    kind, reply = handler.handle_command(spoken)
    assert kind == "system_info"
    assert word in reply


@pytest.mark.parametrize("spoken", ["What time is it?", "what's the time"])
def test_time(handler, spoken):
    kind, reply = handler.handle_command(spoken)
    assert kind == "time_date"
    assert reply.startswith("It's") and ("AM" in reply or "PM" in reply)


@pytest.mark.parametrize("spoken", ["what's the date", "what is today's date"])
def test_date(handler, spoken):
    kind, reply = handler.handle_command(spoken)
    assert kind == "time_date"
    assert reply.startswith("Today is")


def test_help(handler):
    assert handler.handle_command("What can you do?")[0] == "help"


@pytest.mark.parametrize("spoken", ["silent mode", "be quiet", "enable silent mode"])
def test_silent_mode_enable(handler, spoken):
    assert handler.handle_command(spoken) == ("silent_mode", "ENABLE")


@pytest.mark.parametrize("spoken", ["disable silent mode", "unmute", "speak again"])
def test_silent_mode_disable(handler, spoken):
    kind, reply = handler.handle_command(spoken)
    assert kind == "silent_mode"
    assert reply == config.PERSONALITY["silent_mode_disabled"]


@pytest.mark.parametrize("spoken", ["hello", "hey nexa", "hi"])
def test_greeting(handler, spoken):
    assert handler.handle_command(spoken)[0] == "conversation"


@pytest.mark.parametrize("spoken", ["", "   ", "blah blah", "sing opera"])
def test_unknown(handler, spoken):
    kind, reply = handler.handle_command(spoken)
    assert kind == UNKNOWN
    assert reply == config.PERSONALITY["unknown_command"]


# ---- safety --------------------------------------------------------------- #
def test_shell_text_is_never_executed(handler, actions):
    handler.handle_command("open chrome && del /s /q C:\\")
    assert all(call[0] != "system" for call in actions)
    handler.handle_command("run rm -rf slash")
    assert actions[-1][0] != "system"


def test_shutdown_blocked_by_default(handler, actions):
    kind, reply = handler.handle_command("shut down the computer")
    assert kind == "blocked"
    assert "disabled" in reply
    assert actions == []


def test_shutdown_needs_confirmation_when_enabled(handler, actions, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_DESTRUCTIVE_COMMANDS", True)
    kind, _ = handler.handle_command("restart the computer")
    assert kind == "confirmation_required"
    assert actions == []  # nothing happens until confirmed

    kind, _ = handler.handle_command("yes")
    assert kind == "restart"
    assert actions == [("system", ("shutdown", "/r", "/t", "10"))]


def test_confirmation_can_be_cancelled(handler, actions, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_DESTRUCTIVE_COMMANDS", True)
    handler.handle_command("shutdown")
    assert handler.handle_command("no")[0] == "confirmation_cancelled"
    assert handler.handle_command("yes")[0] == UNKNOWN  # nothing pending any more
    assert actions == []


def test_confirmation_expires(handler, actions, monkeypatch):
    import commands.basic_commands as bc

    monkeypatch.setattr(config, "ALLOW_DESTRUCTIVE_COMMANDS", True)
    handler.handle_command("shutdown")
    real = bc.time.monotonic()
    monkeypatch.setattr(bc.time, "monotonic", lambda: real + config.CONFIRMATION_TIMEOUT + 5)
    assert handler.handle_command("yes")[0] == UNKNOWN
    assert actions == []


def test_unrelated_command_clears_pending(handler, actions, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_DESTRUCTIVE_COMMANDS", True)
    handler.handle_command("shutdown")
    handler.handle_command("what time is it")
    assert handler.handle_command("yes")[0] == UNKNOWN
    assert actions == []


def test_lock_requires_confirmation(handler, actions):
    kind, _ = handler.handle_command("lock my computer")
    assert kind == "confirmation_required"
    assert actions == []


def test_disabled_feature_flags(handler, monkeypatch):
    monkeypatch.setattr(config, "ENABLE_SYSTEM_INFO", False)
    assert handler.handle_command("what is my ram usage")[0] == UNKNOWN
    monkeypatch.setattr(config, "ENABLE_TIME_DATE", False)
    assert handler.handle_command("what time is it")[0] == UNKNOWN
