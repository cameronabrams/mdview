"""Tests for the structure-listing and file-serving API."""

from __future__ import annotations


def test_list_includes_sample(client):
    resp = client.get("/api/files")
    assert resp.status_code == 200
    body = resp.json()
    relpaths = {f["relpath"] for f in body["files"]}
    assert "sample.pdb" in relpaths
    entry = next(f for f in body["files"] if f["relpath"] == "sample.pdb")
    assert entry["format"] == "pdb"
    assert entry["size"] > 0


def test_serve_file_returns_bytes(client):
    resp = client.get("/api/file/sample.pdb")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("chemical/x-pdb")
    assert b"ALA" in resp.content


def test_unknown_file_is_404(client):
    resp = client.get("/api/file/does-not-exist.pdb")
    assert resp.status_code == 404


def test_index_is_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "mdview" in resp.text
