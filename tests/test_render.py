"""Phase 6: saving rendered viewport images on the server."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mdview.app import create_app
from mdview.config import Settings

DATA_DIR = Path(__file__).parent / "data"

# A minimal valid 1x1 PNG as a data URI.
PNG_1x1 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _client(render_dir):
    return TestClient(create_app(Settings(root=DATA_DIR, render_dir=render_dir)))


def test_render_saves_and_serves(tmp_path):
    rd = tmp_path / "renders"
    client = _client(rd)

    resp = client.post("/api/render", json={"image": PNG_1x1, "name": "view1"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["filename"] == "view1.png"
    assert (rd / "view1.png").is_file()

    listing = client.get("/api/renders").json()
    assert "view1.png" in {r["name"] for r in listing["renders"]}

    served = client.get(data["url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_auto_names_and_decollides(tmp_path):
    rd = tmp_path / "renders"
    client = _client(rd)
    a = client.post("/api/render", json={"image": PNG_1x1, "name": "shot"}).json()
    b = client.post("/api/render", json={"image": PNG_1x1, "name": "shot"}).json()
    assert a["filename"] == "shot.png"
    assert b["filename"] == "shot-1.png"  # de-collided, not overwritten


def test_render_rejects_non_png(tmp_path):
    client = _client(tmp_path / "renders")
    bad = client.post("/api/render", json={"image": "data:text/plain;base64,aGk="})
    assert bad.status_code == 422


def test_render_name_is_sanitized_to_basename(tmp_path):
    rd = tmp_path / "renders"
    client = _client(rd)
    resp = client.post("/api/render", json={"image": PNG_1x1, "name": "../../evil"})
    assert resp.status_code == 200
    fn = resp.json()["filename"]
    assert "/" not in fn and ".." not in fn
    # the file lands inside render_dir, nowhere else
    assert (rd / fn).is_file()
    assert not (tmp_path.parent / "evil.png").exists()


def test_render_file_traversal_rejected(tmp_path):
    client = _client(tmp_path / "renders")
    assert client.get("/api/renders/..%2f..%2fetc%2fpasswd").status_code == 404
