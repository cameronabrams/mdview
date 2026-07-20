"""Shared pytest fixtures for mdview."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mdview.app import create_app
from mdview.config import Settings

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def client(tmp_path) -> TestClient:
    """A TestClient backed by the bundled tests/data structures.

    The processing cache is isolated to a per-test tmp dir so prepare tests never
    touch (or evict) the real shared cache.
    """
    settings = Settings(root=DATA_DIR, cache_dir=tmp_path / "cache")
    return TestClient(create_app(settings))
