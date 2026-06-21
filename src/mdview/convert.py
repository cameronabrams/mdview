"""Optional server-side structure conversion via ParmEd (the ``convert`` extra).

Mol* reads PDB / mmCIF / GRO (and PSF+DCD / XTC) natively in the browser, but
topology-only formats — CHARMM/NAMD ``.psf``, Amber ``.prmtop`` — carry no
coordinates and must be paired with a coordinate file and merged before a single
static structure can be displayed. This module performs that merge and emits
mmCIF or PDB text.

ParmEd is optional (``uv sync --extra convert``). When it is absent, callers get
``ConvertUnavailable`` so the API can return a clear 501 rather than crashing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

# Output formats Mol* loads happily, mapped to the suffix ParmEd writes for each.
OUTPUT_FORMATS = {"cif": ".cif", "pdb": ".pdb"}


class ConvertUnavailable(RuntimeError):
    """ParmEd (the ``convert`` extra) is not installed."""


class ConvertError(ValueError):
    """A structure could not be read, paired, or written."""


def parmed_available() -> bool:
    """True if ParmEd can be imported (the ``convert`` extra is installed)."""
    try:
        import parmed  # noqa: F401
    except Exception:
        return False
    return True


def convert(top_path: Path, coord_path: Path | None = None, fmt: str = "cif") -> str:
    """Merge a topology with coordinates and return it as ``fmt`` text.

    ``top_path`` is any ParmEd-readable file; ``coord_path``, if given, supplies
    the coordinates (its atom count must match the topology). Raises
    ``ConvertUnavailable`` if ParmEd is missing and ``ConvertError`` on any
    read/pair/write failure (including a topology left without coordinates).
    """
    if fmt not in OUTPUT_FORMATS:
        raise ConvertError(f"unsupported output format: {fmt!r} (use cif or pdb)")

    try:
        import parmed as pmd
    except Exception as exc:  # pragma: no cover - exercised only without the extra
        raise ConvertUnavailable(
            "server-side conversion requires the 'convert' extra: "
            "uv sync --extra convert"
        ) from exc

    try:
        structure = pmd.load_file(str(top_path))
    except Exception as exc:
        raise ConvertError(f"could not read {top_path.name}: {exc}") from exc

    if coord_path is not None:
        try:
            coords = pmd.load_file(str(coord_path))
        except Exception as exc:
            raise ConvertError(
                f"could not read coordinates {coord_path.name}: {exc}"
            ) from exc
        if len(coords.atoms) != len(structure.atoms):
            raise ConvertError(
                f"atom-count mismatch: {top_path.name} has {len(structure.atoms)} "
                f"atoms, {coord_path.name} has {len(coords.atoms)}"
            )
        structure.coordinates = coords.coordinates

    if structure.coordinates is None:
        raise ConvertError(
            f"{top_path.name} has no coordinates; pair it with a coordinate file"
        )

    with tempfile.NamedTemporaryFile(suffix=OUTPUT_FORMATS[fmt], delete=False) as tf:
        out = Path(tf.name)
    try:
        structure.save(str(out), overwrite=True)
        return out.read_text()
    except Exception as exc:
        raise ConvertError(f"could not write {fmt}: {exc}") from exc
    finally:
        out.unlink(missing_ok=True)
