from __future__ import annotations

import pytest

from config import Settings
from runtime import build_runtime


@pytest.fixture
def runtime(tmp_path):
    value = build_runtime(Settings(api_key=None, steam_id=None, mock=True, history_db_path=str(tmp_path / "steam-history.sqlite3")))
    yield value
    value.close()
