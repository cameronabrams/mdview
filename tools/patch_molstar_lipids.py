#!/usr/bin/env python3
"""Patch the vendored Mol* bundle for CHARMM membranes (idempotent, stdlib only).

Two independent fixes to ``molstar.js``, both re-applied by running this script
after re-vendoring Mol* (see VENDOR.txt):

1. **Recognition** — Mol* classifies a residue as a lipid only if its name is in
   an internal set ``cK = new Set(["DAPC", ...])``. It omits cholesterol (CHL1),
   sphingomyelins (PSM, ...), stearoyl-oleoyl lipids (SOPE/SOPS, ...), so those
   render/select as generic ligands. We add the missing names.

2. **Residue-name colors** — Mol*'s "Residue Name" color theme uses a fixed map of
   amino-acid/nucleotide names (``{ARG:255,ASP:16711680, ...}``) and paints every
   other residue with one "Unknown" color, so all lipids look identical. We inject
   distinct colors for lipid residue names.
"""

from __future__ import annotations

import colorsys
import sys
from pathlib import Path

# (1) CHARMM36 lipid/sterol names commonly absent from Mol*'s recognition set.
EXTRA_LIPIDS = [
    "CHL1", "CHOL", "ERG",                          # sterols
    "PSM", "SSM", "OSM", "BSM", "LSM", "NSM",       # sphingomyelins
    "SOPC", "SOPE", "SOPS", "SOPA", "SOPG",         # stearoyl-oleoyl
    "DMPC", "DMPG", "DSPC", "DSPE", "DSPG", "DPPG",  # common saturated
]
NAME_ANCHOR = '"POPC",'  # unique token inside the recognition Set

# (2) Lipid residue names to colorize in the residue-name color theme's map.
LIPID_COLOR_NAMES = [
    "POPC", "POPE", "POPS", "POPG", "POPA", "POPI",
    "DOPC", "DOPE", "DPPC", "DPPE", "DPPS", "DMPC", "DMPG", "DLPC", "DSPC",
    "SOPC", "SOPE", "SOPS", "SOPA",
    "CHL1", "CHOL", "ERG", "PSM", "SSM", "OSM", "BSM", "NSM",
]
# Front of the residue-name theme's color map (`aR = {ALA:..., ARG:..., ...}`,
# referenced as `ResidueName:aR` / `colors.name==="default" ? aR : ...`). Unique.
# (Note: there's a *different* amino-acid map `{ARG:255,...}` used elsewhere — not
# this one.)
COLOR_ANCHOR = "{ALA:9240460,ARG:124,"

BUNDLE = (
    Path(__file__).resolve().parent.parent
    / "src" / "mdview" / "static" / "vendor" / "molstar" / "molstar.js"
)


_GOLDEN = 0.6180339887498949  # golden-ratio conjugate — spreads hues maximally


def lipid_colors() -> dict[str, int]:
    """Deterministic, distinct 24-bit RGB color per lipid name.

    Hues step by the golden ratio so even alphabetically-adjacent names get very
    different colors (and value alternates slightly for extra separation).
    """
    names = sorted(set(LIPID_COLOR_NAMES))
    out: dict[str, int] = {}
    for i, name in enumerate(names):
        hue = (i * _GOLDEN) % 1.0
        val = 0.95 if i % 2 == 0 else 0.78
        r, g, b = colorsys.hsv_to_rgb(hue, 0.62, val)
        out[name] = (round(r * 255) << 16) | (round(g * 255) << 8) | round(b * 255)
    return out


def _inject_names(text: str) -> tuple[str, list[str]]:
    missing = [n for n in EXTRA_LIPIDS if f'"{n}"' not in text]
    if not missing:
        return text, []
    if NAME_ANCHOR not in text:
        raise RuntimeError(f"name anchor {NAME_ANCHOR!r} not found — Mol* changed.")
    injected = NAME_ANCHOR + "".join(f'"{n}",' for n in missing)
    return text.replace(NAME_ANCHOR, injected, 1), missing


def _inject_colors(text: str) -> tuple[str, list[str]]:
    colors = lipid_colors()
    mi = text.find(COLOR_ANCHOR)
    region = text[mi : mi + 6000] if mi >= 0 else ""
    missing = [n for n in colors if f"{n}:" not in region]
    if not missing:
        return text, []
    if mi < 0:
        raise RuntimeError(f"color anchor {COLOR_ANCHOR!r} not found — Mol* changed.")
    injected = COLOR_ANCHOR + "".join(f"{n}:{colors[n]}," for n in missing)
    return text.replace(COLOR_ANCHOR, injected, 1), missing


def patch(bundle_path: Path) -> list[str]:
    """Apply both injections idempotently; return everything added (empty if none)."""
    text = bundle_path.read_text()
    text, added_names = _inject_names(text)
    text, added_colors = _inject_colors(text)
    added = added_names + added_colors
    if added:
        bundle_path.write_text(text)
    return added


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    bundle = Path(args[0]) if args else BUNDLE
    added = patch(bundle)
    if added:
        print(f"patched {bundle.name}: added {len(added)} item(s): {', '.join(added)}")
    else:
        print(f"{bundle.name}: lipid names + colors already applied (no change)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
