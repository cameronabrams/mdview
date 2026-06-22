"""Phase 4: the /api/prepare + /api/prepared endpoints."""

from __future__ import annotations

import pytest

from mdview.process import process_available

needs_mda = pytest.mark.skipif(
    not process_available(), reason="process extra (MDAnalysis) not installed"
)


@pytest.fixture(autouse=True)
def _cache_in_tmp(tmp_path, monkeypatch):
    import mdview.process as P

    monkeypatch.setattr(P, "CACHE_DIR", tmp_path)


def test_files_reports_process_available(client):
    body = client.get("/api/files").json()
    assert body["process_available"] == process_available()


@needs_mda
def test_prepare_returns_urls_and_serves_files(client):
    resp = client.post(
        "/api/prepare",
        json={"top": "alad_wb.psf", "traj": "go_fixed_phi_psi.dcd",
              "strip": True, "stride": 2},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["n_atoms"] == 22 and data["n_frames"] == 20
    assert data["model_url"].endswith("/model")
    assert data["trajectory_url"].endswith("/trajectory")

    model = client.get(data["model_url"])
    assert model.status_code == 200
    assert "@<TRIPOS>BOND" in model.text

    traj = client.get(data["trajectory_url"])
    assert traj.status_code == 200
    assert traj.headers["content-type"] == "application/octet-stream"
    assert traj.content[4:8] == b"CORD"


@needs_mda
def test_prepare_is_cached(client):
    payload = {"top": "alad_wb.psf", "traj": "go_fixed_phi_psi.dcd", "stride": 4}
    a = client.post("/api/prepare", json=payload).json()
    b = client.post("/api/prepare", json=payload).json()
    assert a["id"] == b["id"]


def test_prepare_rejects_top_outside_root(client):
    resp = client.post(
        "/api/prepare",
        json={"top": "../../../../etc/passwd", "traj": "go_fixed_phi_psi.dcd"},
    )
    assert resp.status_code == 404


def test_prepared_rejects_bad_key(client):
    assert client.get("/api/prepared/not-a-hash/model").status_code == 404
