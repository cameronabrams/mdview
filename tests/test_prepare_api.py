"""Phase 4: the /api/prepare (async job) + /api/prepared endpoints."""

from __future__ import annotations

import time

import pytest

from mdview.process import process_available

needs_mda = pytest.mark.skipif(
    not process_available(), reason="process extra (MDAnalysis) not installed"
)


def _prepare(client, payload, timeout=30.0):
    """POST /api/prepare and drive the job to completion, returning the payload.

    A cache hit comes back ``done`` synchronously; otherwise we poll the job the
    way the browser does.
    """
    resp = client.post("/api/prepare", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    deadline = time.monotonic() + timeout
    while data.get("status") != "done":
        assert data.get("status") != "error", data.get("detail")
        assert data.get("job_id"), data
        assert time.monotonic() < deadline, "prepare did not finish in time"
        time.sleep(0.1)
        data = client.get(f"/api/prepare/{data['job_id']}").json()
    return data


def test_files_reports_process_available(client):
    body = client.get("/api/files").json()
    assert body["process_available"] == process_available()


@needs_mda
def test_prepare_returns_urls_and_serves_files(client):
    data = _prepare(
        client,
        {"top": "alad_wb.psf", "traj": "go_fixed_phi_psi.dcd",
         "strip": True, "stride": 2},
    )
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
    a = _prepare(client, payload)
    # Second identical request is a synchronous cache hit (no job needed).
    resp = client.post("/api/prepare", json=payload)
    b = resp.json()
    assert b["status"] == "done" and b["job_id"] is None
    assert a["id"] == b["id"]


@needs_mda
def test_prepare_reports_progress(client):
    payload = {"top": "alad_wb.psf", "traj": "go_fixed_phi_psi.dcd"}
    data = _prepare(client, payload)
    # Once done, current == total == the frame count that was written.
    assert data["total"] == data["n_frames"]
    assert data["current"] == data["total"]


def test_prepare_rejects_bad_stride(client):
    resp = client.post(
        "/api/prepare",
        json={"top": "alad_wb.psf", "traj": "go_fixed_phi_psi.dcd", "stride": 0},
    )
    assert resp.status_code == 422


def test_prepare_rejects_top_outside_root(client):
    resp = client.post(
        "/api/prepare",
        json={"top": "../../../../etc/passwd", "traj": "go_fixed_phi_psi.dcd"},
    )
    assert resp.status_code == 404


def test_prepare_status_rejects_unknown_job(client):
    assert client.get("/api/prepare/deadbeef").status_code == 404
    assert client.get("/api/prepare/" + "0" * 32).status_code == 404


def test_prepared_rejects_bad_key(client):
    assert client.get("/api/prepared/not-a-hash/model").status_code == 404
