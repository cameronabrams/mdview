"""Tests for the parmed-backed conversion endpoint (Phase 2).

The conversion tests are skipped when the optional ``convert`` extra (parmed) is
not installed, so the suite passes in a runtime-only environment.
"""

from __future__ import annotations

import pytest

from mdview.convert import parmed_available

needs_parmed = pytest.mark.skipif(
    not parmed_available(), reason="convert extra (parmed) not installed"
)


@needs_parmed
def test_convert_default_is_mol2_with_explicit_bonds(client):
    # The default format must preserve the PSF's connectivity so Mol* does not
    # distance-guess bonds (which misfires on distorted MD coordinates).
    resp = client.get("/api/convert/alad_v.psf", params={"coords": "alad_v.pdb"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("chemical/x-mol2")
    assert "@<TRIPOS>BOND" in resp.text
    # Count bond rows in the BOND block; alad_v.psf has 21 bonds.
    bond_block = resp.text.split("@<TRIPOS>BOND", 1)[1]
    bond_block = bond_block.split("@<TRIPOS>", 1)[0]  # stop at the next section
    bond_rows = [ln for ln in bond_block.splitlines() if ln.strip()]
    assert len(bond_rows) == 21


@needs_parmed
def test_convert_psf_with_coords_pdb(client):
    resp = client.get("/api/convert/alad_v.psf", params={"coords": "alad_v.pdb", "format": "pdb"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("chemical/x-pdb")
    assert "ATOM" in resp.text or "HETATM" in resp.text


@needs_parmed
def test_convert_psf_with_coords_cif(client):
    resp = client.get("/api/convert/alad_v.psf", params={"coords": "alad_v.pdb", "format": "cif"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("chemical/x-mmcif")
    assert resp.text.startswith("data_")


@needs_parmed
def test_convert_topology_without_coords_is_422(client):
    # A PSF carries no coordinates of its own.
    resp = client.get("/api/convert/alad_v.psf")
    assert resp.status_code == 422


@needs_parmed
def test_convert_bad_output_format_is_422(client):
    resp = client.get("/api/convert/alad_v.psf", params={"coords": "alad_v.pdb", "format": "xyz"})
    assert resp.status_code == 422


@needs_parmed
def test_convert_atom_count_mismatch_is_422(client):
    # sample.pdb (10 atoms) does not match alad_v.psf (22 atoms).
    resp = client.get("/api/convert/alad_v.psf", params={"coords": "sample.pdb"})
    assert resp.status_code == 422


def test_convert_missing_topology_is_404(client):
    resp = client.get("/api/convert/nope.psf", params={"coords": "alad_v.pdb"})
    assert resp.status_code == 404


def test_convert_path_traversal_is_rejected(client):
    resp = client.get("/api/convert/../../../../etc/passwd", params={"coords": "alad_v.pdb"})
    assert resp.status_code != 200
    assert b"root:" not in resp.content
