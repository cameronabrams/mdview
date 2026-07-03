"""PDB-centric topology pairing: count_atoms + /api/match-topology."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mdview.app import create_app
from mdview.config import Settings
from mdview.files import count_atoms, match_topologies

DATA_DIR = Path(__file__).parent / "data"


def _client(root):
    return TestClient(create_app(Settings(root=root)))


# --- count_atoms ----------------------------------------------------------
def test_count_atoms_psf_reads_natom():
    assert count_atoms(DATA_DIR / "alad_v.psf") == 22
    assert count_atoms(DATA_DIR / "alad_wb.psf") == 844


def test_count_atoms_pdb_counts_records():
    assert count_atoms(DATA_DIR / "alad_v.pdb") == 22
    assert count_atoms(DATA_DIR / "sample.pdb") == 10


def test_count_atoms_unknown_suffix_is_none(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello\n")
    assert count_atoms(p) is None


def test_count_atoms_prmtop_pointers(tmp_path):
    p = tmp_path / "sys.prmtop"
    p.write_text(
        "%VERSION\n"
        "%FLAG POINTERS\n"
        "%FORMAT(10I8)\n"
        "      42       5       0\n"
    )
    assert count_atoms(p) == 42


def test_count_atoms_cache_invalidates_on_change(tmp_path):
    p = tmp_path / "a.pdb"
    p.write_text("ATOM\nATOM\n")
    assert count_atoms(p) == 2
    # rewrite with a different size/mtime; the cache key must pick up the change
    import os, time

    p.write_text("ATOM\nATOM\nATOM\n")
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert count_atoms(p) == 3


# --- match_topologies (unit) ---------------------------------------------
def test_match_flags_the_atom_count_match():
    result = match_topologies(Settings(root=DATA_DIR), "alad_v.pdb")
    assert result["coord_atoms"] == 22
    by_name = {t["name"]: t for t in result["topologies"]}
    assert by_name["alad_v.psf"]["match"] is True
    assert by_name["alad_wb.psf"]["match"] is False
    # matches sort first
    assert result["topologies"][0]["name"] == "alad_v.psf"


def test_match_no_candidate_when_no_count_matches():
    result = match_topologies(Settings(root=DATA_DIR), "sample.pdb")  # 10 atoms
    assert result["coord_atoms"] == 10
    assert all(not t["match"] for t in result["topologies"])


def test_match_escaping_coords_returns_none():
    assert match_topologies(Settings(root=DATA_DIR), "../../etc/passwd") is None


def test_match_finds_topology_in_ancestor_folder(tmp_path):
    (tmp_path / "top.psf").write_text("PSF\n       2 !NATOM\n")
    sub = tmp_path / "run"
    sub.mkdir()
    (sub / "frame.pdb").write_text("ATOM\nATOM\n")
    result = match_topologies(Settings(root=tmp_path), "run/frame.pdb")
    match = next(t for t in result["topologies"] if t["match"])
    assert match["name"] == "top.psf"
    assert match["ancestor"] is True


# --- /api/match-topology (endpoint) --------------------------------------
def test_endpoint_returns_matches_and_convert_flag():
    body = _client(DATA_DIR).get(
        "/api/match-topology", params={"coords": "alad_v.pdb"}
    ).json()
    assert "convert_available" in body
    assert body["coord_atoms"] == 22
    assert any(t["match"] and t["name"] == "alad_v.psf" for t in body["topologies"])


def test_endpoint_404_for_missing_coords():
    resp = _client(DATA_DIR).get(
        "/api/match-topology", params={"coords": "nope.pdb"}
    )
    assert resp.status_code == 404
