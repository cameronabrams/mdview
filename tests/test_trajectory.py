"""Phase 3: trajectory listing and raw topology/trajectory serving.

Playback itself is a browser concern (Mol* downloads the topology + trajectory
and animates frames); here we test the server contract that makes it possible.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mdview.app import create_app
from mdview.config import Settings

DATA_DIR = Path(__file__).parent / "data"


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


def test_dcd_nset_header_is_repaired_when_served(client):
    import struct

    # The fixture's header NSET is 0; the file actually holds 10 frames. Mol*
    # trusts NSET, so the served bytes must carry the corrected count.
    raw = (DATA_DIR / "alad_v.dcd").read_bytes()
    assert struct.unpack("<i", raw[8:12])[0] == 0  # on-disk header is wrong

    served = client.get("/api/file/alad_v.dcd").content
    assert struct.unpack("<i", served[8:12])[0] == 10  # patched
    # everything else is identical, and the file is otherwise untouched
    assert served[:8] == raw[:8]
    assert served[12:] == raw[12:]
    assert len(served) == len(raw)


def test_dcd_repair_plan_detects_wrong_nset():
    from mdview.dcd import repair_plan

    plan = repair_plan(DATA_DIR / "alad_v.dcd")
    assert plan is not None
    nset, endian = plan
    assert nset == 10 and endian == "<"


def test_unsupported_extension_is_415(tmp_path):
    (tmp_path / "notes.xyzzy").write_text("not a structure")
    client = TestClient(create_app(Settings(root=tmp_path)))
    resp = client.get("/api/file/notes.xyzzy")
    assert resp.status_code == 415
