"""Processing-cache eviction, stats/clear, size parsing, and the cache endpoints."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mdview.app import create_app
from mdview.config import Settings, parse_size
from mdview.process import cache_stats, clear_cache, evict

DATA_DIR = Path(__file__).parent / "data"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("5G", 5 * 1024**3),
        ("500M", 500 * 1024**2),
        ("2K", 2048),
        ("2048", 2048),
        ("1.5G", int(1.5 * 1024**3)),
        ("10GB", 10 * 1024**3),
        ("0", None),
        ("", None),
        ("none", None),
        ("unlimited", None),
        (None, None),
    ],
)
def test_parse_size(text, expected):
    assert parse_size(text) == expected


def test_parse_size_rejects_garbage():
    with pytest.raises(ValueError):
        parse_size("banana")


def _entry(cache_dir, name, nbytes, mtime):
    """Create a fake cache entry dir with one file and a set mtime."""
    d = cache_dir / name
    d.mkdir(parents=True)
    (d / "traj.dcd").write_bytes(b"x" * nbytes)
    os.utime(d, (mtime, mtime))
    return d


def test_evict_removes_least_recently_used(tmp_path):
    cache = tmp_path / "cache"
    a = _entry(cache, "a" * 64, 1000, mtime=100)  # oldest
    b = _entry(cache, "b" * 64, 1000, mtime=200)
    c = _entry(cache, "c" * 64, 1000, mtime=300)  # newest
    freed = evict(cache, max_bytes=2500)  # 3000 total -> drop oldest to fit
    assert freed == 1000
    assert not a.exists()
    assert b.exists() and c.exists()


def test_evict_never_removes_protected_entry(tmp_path):
    cache = tmp_path / "cache"
    old = _entry(cache, "a" * 64, 1000, mtime=100)   # oldest, but protected
    new = _entry(cache, "b" * 64, 1000, mtime=300)
    # Cap forces one removal; protecting the oldest makes eviction take the newer.
    freed = evict(cache, max_bytes=1500, protect="a" * 64)
    assert freed == 1000
    assert old.exists()
    assert not new.exists()


def test_evict_noop_when_unlimited_or_under_cap(tmp_path):
    cache = tmp_path / "cache"
    _entry(cache, "a" * 64, 1000, mtime=100)
    assert evict(cache, max_bytes=None) == 0
    assert evict(cache, max_bytes=0) == 0
    assert evict(cache, max_bytes=10_000) == 0


def test_cache_stats_and_clear(tmp_path):
    cache = tmp_path / "cache"
    _entry(cache, "a" * 64, 1000, mtime=100)
    _entry(cache, "b" * 64, 2000, mtime=200)
    stats = cache_stats(cache, max_bytes=5000)
    assert stats["entries"] == 2
    assert stats["bytes"] == 3000
    assert stats["max_bytes"] == 5000
    assert stats["dir"] == str(cache)

    result = clear_cache(cache)
    assert result["cleared"] == 2
    assert result["bytes"] == 3000
    assert cache_stats(cache, None)["entries"] == 0


def test_cache_stats_missing_dir(tmp_path):
    stats = cache_stats(tmp_path / "nope", max_bytes=None)
    assert stats["entries"] == 0 and stats["bytes"] == 0


def test_api_cache_endpoints(tmp_path):
    cache = tmp_path / "cache"
    _entry(cache, "a" * 64, 1234, mtime=100)
    client = TestClient(create_app(Settings(root=DATA_DIR, cache_dir=cache)))

    stats = client.get("/api/cache").json()
    assert stats["entries"] == 1 and stats["bytes"] == 1234
    assert stats["max_bytes"] == 5 * 1024**3  # default cap

    assert client.delete("/api/cache").json()["cleared"] == 1
    assert client.get("/api/cache").json()["entries"] == 0


def test_api_cache_respects_unlimited_cap(tmp_path):
    client = TestClient(
        create_app(Settings(root=DATA_DIR, cache_dir=tmp_path / "c", cache_max_bytes=None))
    )
    assert client.get("/api/cache").json()["max_bytes"] is None
