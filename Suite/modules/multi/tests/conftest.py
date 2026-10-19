import pytest


@pytest.fixture(autouse=True)
def _console_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTI_CONSOLE_FILE", str(tmp_path / "console" / "multi.jsonl"))
