"""Phase 5: per-directory browsing (/api/browse) within the sandboxed root."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mdview.app import create_app
from mdview.config import Settings


def _make_tree(root):
    """root/top.pdb and root/sub/{inner.pdb, md.dcd}."""
    (root / "top.pdb").write_text("ATOM\n")
    sub = root / "sub"
    sub.mkdir()
    (sub / "inner.pdb").write_text("ATOM\n")
    (sub / "md.dcd").write_bytes(b"\x00" * 16)


def _client(root):
    return TestClient(create_app(Settings(root=root)))


def test_root_browse_is_non_recursive(tmp_path):
    _make_tree(tmp_path)
    body = _client(tmp_path).get("/api/browse").json()
    assert body["dir"] == "" and body["parent"] is None
    assert {d["name"] for d in body["dirs"]} == {"sub"}
    # root-level file is listed; the file inside sub/ is NOT (non-recursive)
    names = {f["name"] for f in body["files"]}
    assert names == {"top.pdb"}
    assert "convert_available" in body and "process_available" in body


def test_descend_into_subdir(tmp_path):
    _make_tree(tmp_path)
    body = _client(tmp_path).get("/api/browse", params={"dir": "sub"}).json()
    assert body["dir"] == "sub" and body["parent"] == ""
    assert {f["name"] for f in body["files"]} == {"inner.pdb"}
    assert {t["name"] for t in body["trajectories"]} == {"md.dcd"}
    # the parent's structure is offered as a model so md.dcd can be paired here
    ancestors = {m["relpath"] for m in body["ancestor_models"]}
    assert "top.pdb" in ancestors


def test_root_has_no_ancestor_models(tmp_path):
    _make_tree(tmp_path)
    body = _client(tmp_path).get("/api/browse").json()
    assert body["ancestor_models"] == []


def test_browse_rejects_escape_and_missing(tmp_path):
    _make_tree(tmp_path)
    client = _client(tmp_path)
    assert client.get("/api/browse", params={"dir": "../.."}).status_code == 404
    assert client.get("/api/browse", params={"dir": "nope"}).status_code == 404
    # a file is not a directory
    assert client.get("/api/browse", params={"dir": "top.pdb"}).status_code == 404
