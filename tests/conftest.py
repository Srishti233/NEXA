import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def actions(monkeypatch):
    """Replace every OS-touching action with a recorder."""
    import commands.basic_commands as bc

    calls: list[tuple] = []
    monkeypatch.setattr(bc, "launch_app", lambda t: calls.append(("app", t)))
    monkeypatch.setattr(bc, "open_path", lambda p: calls.append(("path", Path(p).name)))
    monkeypatch.setattr(bc, "open_uri", lambda u: calls.append(("uri", u)))
    monkeypatch.setattr(bc, "send_hotkey", lambda c: calls.append(("hotkey", c)))
    monkeypatch.setattr(bc, "run_system", lambda a: calls.append(("system", tuple(a))))
    return calls


@pytest.fixture
def handler(actions):
    from commands import CommandIntentHandler

    return CommandIntentHandler()
