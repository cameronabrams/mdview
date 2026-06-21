"""The file endpoint must not serve anything outside the data root."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "attack",
    [
        "../../../../etc/passwd",
        "..%2f..%2f..%2fetc%2fpasswd",
        "/etc/passwd",
    ],
)
def test_path_traversal_is_rejected(client, attack):
    resp = client.get(f"/api/file/{attack}")
    # Either the route rejects it (404) or it never matches; never a 200 with
    # out-of-root content.
    assert resp.status_code != 200
    assert b"root:" not in resp.content


def test_resolve_within_root_rejects_escape(tmp_path):
    from mdview.files import resolve_within_root

    root = tmp_path / "data"
    root.mkdir()
    (root / "ok.pdb").write_text("ATOM\n")
    (tmp_path / "secret.txt").write_text("nope")

    assert resolve_within_root(root, "ok.pdb") is not None
    assert resolve_within_root(root, "../secret.txt") is None
    assert resolve_within_root(root, "missing.pdb") is None
