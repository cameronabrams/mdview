"""Optional server-side trajectory processing (the ``process`` extra).

Decimate (stride), strip (atom selection, e.g. solvent/ions), and align (superpose
each frame onto frame 0) a trajectory before it reaches the browser, so loads over
an SSH tunnel are small and the motion is legible.

The reduced **coordinates** are written as a DCD by MDAnalysis (which writes a
correct NSET). The reduced **model** — needed because stripping changes the atom
count — is built with ParmEd by slicing the topology on the kept atom indices and
writing MOL2, so explicit bonds survive (the same path as ``convert.py``).
MDAnalysis cannot write MOL2 from PSF-derived data, hence the split.

Results are cached on disk, content-addressed by (input files, options), so a
repeated request returns instantly.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

# Residue names treated as solvent / ions by the "strip solvent" preset. The
# free-text selection box overrides this for anything unusual.
WATER_RESNAMES = ["TIP3", "TIP4", "TIP5", "TIP3P", "WAT", "HOH", "SOL", "SPC", "SPCE", "T3P"]
ION_RESNAMES = [
    "SOD", "CLA", "POT", "CES", "CAL", "MG", "ZN2", "ZN", "NA", "CL", "K",
    "LIT", "RUB", "BAR", "CES", "FE", "FE2", "MN", "CU", "CD", "IOD", "BR",
]

# MDAnalysis selection that KEEPS everything except water + ions.
STRIP_SOLVENT_FILTER = (
    f"not (resname {' '.join(WATER_RESNAMES)} or resname {' '.join(ION_RESNAMES)})"
)

DEFAULT_ALIGN_SELECTION = "backbone"

CACHE_DIR = Path(tempfile.gettempdir()) / "mdview-cache"


class ProcessUnavailable(RuntimeError):
    """MDAnalysis (the ``process`` extra) is not installed."""


class ProcessError(ValueError):
    """A trajectory could not be processed (bad selection, empty result, …)."""


def process_available() -> bool:
    """True if MDAnalysis can be imported (the ``process`` extra is installed)."""
    try:
        import MDAnalysis  # noqa: F401
    except Exception:
        return False
    return True


def cache_key(
    top: Path, traj: Path, *, select: str, stride: int, align: bool, align_select: str
) -> str:
    """Stable content-addressed id for one processing request."""
    parts = []
    for p in (top, traj):
        st = p.stat()
        parts.append(f"{p.resolve()}:{st.st_size}:{int(st.st_mtime_ns)}")
    payload = json.dumps(
        [parts, select, int(stride), bool(align), align_select], sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _paths(key: str) -> tuple[Path, Path]:
    d = CACHE_DIR / key
    return d / "model.mol2", d / "traj.dcd"


def prepare(
    top: Path,
    traj: Path,
    *,
    select: str = "all",
    stride: int = 1,
    align: bool = False,
    align_select: str = DEFAULT_ALIGN_SELECTION,
) -> dict:
    """Process (or return a cached) trajectory; returns metadata + the cache key.

    Result: ``{"id", "n_atoms", "n_frames"}``. The model/traj files live at the
    paths from :func:`_paths` for that id. Raises ``ProcessUnavailable`` without
    MDAnalysis and ``ProcessError`` on any selection/IO failure.
    """
    if stride < 1:
        raise ProcessError("stride must be >= 1")

    key = cache_key(
        top, traj, select=select, stride=stride, align=align, align_select=align_select
    )
    model_path, traj_path = _paths(key)
    if model_path.is_file() and traj_path.is_file():
        meta = _paths(key)[0].parent / "meta.json"
        if meta.is_file():
            info = json.loads(meta.read_text())
            return {"id": key, **info}

    info = _run(
        top, traj, model_path, traj_path,
        select=select, stride=stride, align=align, align_select=align_select,
    )
    (model_path.parent / "meta.json").write_text(json.dumps(info))
    return {"id": key, **info}


def _run(
    top: Path, traj: Path, model_path: Path, traj_path: Path,
    *, select: str, stride: int, align: bool, align_select: str,
) -> dict:
    try:
        import MDAnalysis as mda
        from MDAnalysis.analysis import align as mda_align
    except Exception as exc:  # pragma: no cover - only without the extra
        raise ProcessUnavailable(
            "trajectory processing requires the 'process' extra: uv sync --extra process"
        ) from exc
    import parmed as pmd

    try:
        u = mda.Universe(str(top), str(traj))
    except Exception as exc:
        raise ProcessError(f"could not open {top.name} + {traj.name}: {exc}") from exc

    try:
        kept = u.select_atoms(select)
    except Exception as exc:
        raise ProcessError(f"bad selection {select!r}: {exc}") from exc
    if kept.n_atoms == 0:
        raise ProcessError(f"selection {select!r} matched 0 atoms")

    ref = None
    if align:
        ref = mda.Universe(str(top), str(traj))
        ref.trajectory[0]
        try:
            mobile_fit = u.select_atoms(align_select)
            ref_fit = ref.select_atoms(align_select)
        except Exception as exc:
            raise ProcessError(f"bad align selection {align_select!r}: {exc}") from exc
        if mobile_fit.n_atoms == 0:
            raise ProcessError(
                f"align selection {align_select!r} matched 0 atoms "
                "(note: 'backbone'/'protein' match nothing on non-protein systems)"
            )

    # frame-0 coordinates of the kept atoms, for the ParmEd model
    u.trajectory[0]
    frame0 = kept.positions.copy()

    model_path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = 0
    try:
        with mda.Writer(str(traj_path), kept.n_atoms) as writer:
            for _ in u.trajectory[::stride]:
                if align:
                    mda_align.alignto(u.atoms, ref.atoms, select=align_select)
                writer.write(kept)
                n_frames += 1
    except Exception as exc:
        raise ProcessError(f"failed writing trajectory: {exc}") from exc

    # Reduced model with bonds, via ParmEd (mirrors convert.py). ParmEd's
    # list-slicing drops index 0 when the list is the *complete* atom set, so use
    # the full structure when nothing was stripped (count equality => full set)
    # and slice only for real subsets.
    try:
        full = pmd.load_file(str(top))
        indices = [int(i) for i in kept.indices]
        sub = full if len(indices) == len(full.atoms) else full[indices]
        sub.coordinates = frame0
        sub.save(str(model_path), overwrite=True)
    except Exception as exc:
        raise ProcessError(f"failed writing model: {exc}") from exc

    return {"n_atoms": int(kept.n_atoms), "n_frames": int(n_frames)}
