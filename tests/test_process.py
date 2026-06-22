"""Phase 4: server-side trajectory processing (strip / stride / align).

Skipped when the optional ``process`` extra (MDAnalysis) is absent.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from mdview.process import process_available, prepare, ProcessError

DATA_DIR = Path(__file__).parent / "data"
PSF = DATA_DIR / "alad_wb.psf"  # 844 atoms (dipeptide in water)
DCD = DATA_DIR / "go_fixed_phi_psi.dcd"  # 40 frames

needs_mda = pytest.mark.skipif(
    not process_available(), reason="process extra (MDAnalysis) not installed"
)


def _mol2_bond_count(path: Path) -> int:
    text = path.read_text()
    if "@<TRIPOS>BOND" not in text:
        return 0
    block = text.split("@<TRIPOS>BOND", 1)[1].split("@<TRIPOS>", 1)[0]
    return len([ln for ln in block.splitlines() if ln.strip()])


def _dcd_nset(path: Path) -> int:
    return struct.unpack("<i", path.read_bytes()[8:12])[0]


@needs_mda
def test_strip_water_reduces_model_to_solute_with_bonds(tmp_path, monkeypatch):
    import mdview.process as P

    monkeypatch.setattr(P, "CACHE_DIR", tmp_path)
    res = prepare(PSF, DCD, select="not resname TIP3")
    assert res["n_atoms"] == 22  # solute only (844 -> 22)
    model = (tmp_path / res["id"] / "model.mol2")
    assert _mol2_bond_count(model) == 21


@needs_mda
def test_stride_reduces_frame_count(tmp_path, monkeypatch):
    import mdview.process as P

    monkeypatch.setattr(P, "CACHE_DIR", tmp_path)
    res = prepare(PSF, DCD, select="not resname TIP3", stride=3)
    assert res["n_frames"] == 14  # ceil(40 / 3)
    traj = tmp_path / res["id"] / "traj.dcd"
    assert _dcd_nset(traj) == 14  # MDAnalysis writes a correct NSET header


@needs_mda
def test_align_runs_and_changes_coordinates(tmp_path, monkeypatch):
    import mdview.process as P

    monkeypatch.setattr(P, "CACHE_DIR", tmp_path)
    # ALAD is not recognised as a protein, so use an explicit multi-atom fit.
    plain = prepare(PSF, DCD, select="not resname TIP3", align=False)
    aligned = prepare(
        PSF, DCD, select="not resname TIP3", align=True,
        align_select="name CL CLP CA CRP CR",
    )
    assert aligned["id"] != plain["id"]
    a = (tmp_path / aligned["id"] / "traj.dcd").read_bytes()
    b = (tmp_path / plain["id"] / "traj.dcd").read_bytes()
    assert a != b  # alignment moved atoms


@needs_mda
def test_empty_selection_errors(tmp_path, monkeypatch):
    import mdview.process as P

    monkeypatch.setattr(P, "CACHE_DIR", tmp_path)
    with pytest.raises(ProcessError):
        prepare(PSF, DCD, select="resname NOPE")


@needs_mda
def test_cache_hit_returns_same_id(tmp_path, monkeypatch):
    import mdview.process as P

    monkeypatch.setattr(P, "CACHE_DIR", tmp_path)
    a = prepare(PSF, DCD, select="not resname TIP3", stride=2)
    b = prepare(PSF, DCD, select="not resname TIP3", stride=2)
    assert a["id"] == b["id"]
