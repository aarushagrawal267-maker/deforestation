from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
FIXTURES = BACKEND / "tests" / "fixtures"


def pytest_configure(config):
    config.addinivalue_line("markers", "network: needs internet access to public data providers")


@pytest.fixture
def fixture_products() -> list[Path]:
    return sorted(p for p in FIXTURES.glob("obs_*") if p.is_dir())


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Isolated data dir + SQLite database for API tests."""
    monkeypatch.setenv("SYLVA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SYLVA_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.sqlite').as_posix()}")
    from forestwatch.settings import get_settings

    get_settings.cache_clear()
    from app.db.session import reset_engine

    reset_engine()
    yield tmp_path
    reset_engine()
    get_settings.cache_clear()


def pytest_collection_modifyitems(config, items):
    if os.environ.get("SYLVA_RUN_NETWORK") == "1":
        return
    skip = pytest.mark.skip(reason="network test (set SYLVA_RUN_NETWORK=1 to run)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
