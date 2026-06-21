"""Shared pytest fixtures for mdview."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mdview.app import create_app
from mdview.config import Settings

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def client() -> TestClient:
    """A TestClient backed by the bundled tests/data structures."""
    return TestClient(create_app(Settings(root=DATA_DIR)))
