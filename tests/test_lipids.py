"""Phase 7: the vendored Mol* lipid-name set is patched for CHARMM membranes.

Guards against a Mol* re-vendor silently dropping the patch (re-run
tools/patch_molstar_lipids.py), and checks the patcher is idempotent.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUNDLE = REPO / "src" / "mdview" / "static" / "vendor" / "molstar" / "molstar.js"


def _load_patcher():
    spec = importlib.util.spec_from_file_location(
        "patch_molstar_lipids", REPO / "tools" / "patch_molstar_lipids.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bundle_recognizes_charmm_lipids():
    text = BUNDLE.read_text()
    # the user's must-have membrane species
    for name in ("CHL1", "PSM", "SOPE", "SOPS"):
        assert f'"{name}"' in text, f"{name} missing — run tools/patch_molstar_lipids.py"


def test_bundle_colors_lipid_residue_names():
    text = BUNDLE.read_text()
    # lipid names must be keys in the residue-name color map (else all-one-color)
    for name in ("POPC", "POPE", "CHL1", "PSM", "SOPE", "SOPS"):
        assert f"{name}:" in text, f"{name} color missing — run tools/patch_molstar_lipids.py"


def test_lipid_colors_are_distinct_and_stable():
    patcher = _load_patcher()
    a = patcher.lipid_colors()
    b = patcher.lipid_colors()
    assert a == b  # deterministic
    assert len(set(a.values())) == len(a)  # every species a distinct color


def test_patcher_is_idempotent_on_the_bundle():
    patcher = _load_patcher()
    assert patcher.patch(BUNDLE) == []  # already fully applied → no change


def test_patch_inserts_once_without_artifacts(tmp_path):
    patcher = _load_patcher()
    fake = tmp_path / "fake.js"
    # both anchors: the recognition Set and the residue-name color map (aR)
    fake.write_text(
        'var cK=new Set(["DPPC","POPC","PRPC"]);'
        'var aR={ALA:9240460,ARG:124,ASN:16743536,ASP:10485826};'
    )

    added = patcher.patch(fake)
    assert "CHL1" in added  # a recognition name
    assert "POPC" in added  # a color-map key
    out = fake.read_text()
    assert '"POPC","CHL1"' in out  # name set extended in place
    assert "ARG:124,BSM:" in out  # colors injected (sorted) right after the anchor
    assert "POPC:" in out  # the user's species got a color key
    assert ",," not in out and '""' not in out  # no comma/quote artifacts

    # second run is a no-op
    assert patcher.patch(fake) == []
    assert fake.read_text() == out
