import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "RULES_FILE", tmp_path / "rules.json")
    monkeypatch.setattr(config, "DB_FILE", tmp_path / "t.db")
    return tmp_path
