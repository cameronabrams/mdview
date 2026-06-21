"""Phase 3: trajectory listing and raw topology/trajectory serving.

Playback itself is a browser concern (Mol* downloads the topology + trajectory
and animates frames); here we test the server contract that makes it possible.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mdview.app import create_app
from mdview.config import Settings


def test_lists_trajectories(client):
    body = client.get("/api/files").json()
    trajs = {t["relpath"]: t for t in body["trajectories"]}
    assert "alad_v.dcd" in trajs
    assert trajs["alad_v.dcd"]["format"] == "dcd"


def test_serves_topology_bytes(client):
    # Mol* fetches the PSF directly as a topology-url, so /api/file must serve it
    # (it used to be rejected as a non-native structure type).
    resp = client.get("/api/file/alad_v.psf")
    assert resp.status_code == 200
    assert b"PSF" in resp.content[:32]


def test_serves_trajectory_bytes_as_binary(client):
    resp = client.get("/api/file/alad_v.dcd")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/octet-stream"
    assert resp.content[4:8] == b"CORD"  # DCD magic, after the 4-byte block length


def test_unsupported_extension_is_415(tmp_path):
    (tmp_path / "notes.xyzzy").write_text("not a structure")
    client = TestClient(create_app(Settings(root=tmp_path)))
    resp = client.get("/api/file/notes.xyzzy")
    assert resp.status_code == 415
