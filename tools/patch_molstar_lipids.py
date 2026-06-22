#!/usr/bin/env python3
"""Extend Mol*'s lipid-name set so CHARMM membrane residues are recognized.

Mol* classifies a residue as a lipid only if its (upper-cased) name is in an
internal set ``cK = new Set(["DAPC", ...])`` baked into the vendored
``molstar.js``. Several common CHARMM36 species — cholesterol (CHL1),
sphingomyelins (PSM, ...), stearoyl-oleoyl lipids (SOPE/SOPS, ...) — are missing,
so they fall through to "generic ligand" and render/select poorly.

This script injects the missing names into that set. It is **idempotent** and is
meant to be re-run after re-vendoring Mol* (see VENDOR.txt). Pure stdlib.
"""

from __future__ import annotations

import sys
from pathlib import Path

# CHARMM36 lipid/sterol residue names commonly absent from Mol*'s lipid set.
# The first four are the user's must-haves; the rest are low-risk extras.
EXTRA_LIPIDS = [
    # sterols
    "CHL1", "CHOL", "ERG",
    # sphingomyelins
    "PSM", "SSM", "OSM", "BSM", "LSM", "NSM",
    # stearoyl-oleoyl glycerophospholipids
    "SOPC", "SOPE", "SOPS", "SOPA", "SOPG",
    # a few common saturated species
    "DMPC", "DMPG", "DSPC", "DSPE", "DSPG", "DPPG",
]

# Unique token inside the lipid set used as the injection point.
ANCHOR = '"POPC",'

BUNDLE = (
    Path(__file__).resolve().parent.parent
    / "src" / "mdview" / "static" / "vendor" / "molstar" / "molstar.js"
)


def patch(bundle_path: Path) -> list[str]:
    """Inject any missing EXTRA_LIPIDS into the bundle's lipid set.

    Returns the names added (empty if already fully applied). Raises if the
    anchor can't be found (Mol* internals changed — revisit this script).
    """
    text = bundle_path.read_text()
    missing = [n for n in EXTRA_LIPIDS if f'"{n}"' not in text]
    if not missing:
        return []
    if ANCHOR not in text:
        raise RuntimeError(
            f"anchor {ANCHOR!r} not found in {bundle_path.name}; "
            "the Mol* lipid set may have changed — update this script."
        )
    injection = ANCHOR + "".join(f'"{n}",' for n in missing)
    bundle_path.write_text(text.replace(ANCHOR, injection, 1))
    return missing


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    bundle = Path(args[0]) if args else BUNDLE
    added = patch(bundle)
    if added:
        print(f"patched {bundle.name}: added {len(added)} lipid name(s): "
              f"{', '.join(added)}")
    else:
        print(f"{bundle.name}: lipid names already applied (no change)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
