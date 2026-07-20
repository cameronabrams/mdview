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
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

# Reports processing progress as (frames_done, frames_total).
ProgressCb = Callable[[int, int], None]

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


def _paths(cache_dir: Path, key: str) -> tuple[Path, Path]:
    d = cache_dir / key
    return d / "model.mol2", d / "traj.dcd"


def _dir_size(path: Path) -> int:
    """Total bytes of the files directly under one cache-entry directory."""
    total = 0
    try:
        for f in path.iterdir():
            if f.is_file():
                total += f.stat().st_size
    except OSError:
        pass
    return total


def cache_stats(cache_dir: Path, max_bytes: int | None) -> dict:
    """Summarize the on-disk cache: ``{dir, entries, bytes, max_bytes}``."""
    entries = 0
    total = 0
    if cache_dir.is_dir():
        for d in cache_dir.iterdir():
            if d.is_dir():
                entries += 1
                total += _dir_size(d)
    return {"dir": str(cache_dir), "entries": entries, "bytes": total,
            "max_bytes": max_bytes}


def clear_cache(cache_dir: Path) -> dict:
    """Remove every cache entry; returns ``{cleared, bytes}`` freed."""
    cleared = 0
    freed = 0
    if cache_dir.is_dir():
        for d in list(cache_dir.iterdir()):
            if d.is_dir():
                freed += _dir_size(d)
                shutil.rmtree(d, ignore_errors=True)
                cleared += 1
    return {"cleared": cleared, "bytes": freed}


def evict(cache_dir: Path, max_bytes: int | None, *, protect: str | None = None) -> int:
    """Trim the cache to ``max_bytes`` by dropping least-recently-used entries.

    Recency is the entry directory's mtime, which :func:`prepare` bumps on every
    cache hit. ``protect`` (a key) is never evicted — pass the entry just written
    so a fresh, larger-than-the-rest result can't delete itself. Returns bytes
    freed. A ``None``/``0`` cap disables eviction.
    """
    if not max_bytes or max_bytes <= 0 or not cache_dir.is_dir():
        return 0
    infos = []  # (mtime, size, dir)
    total = 0
    for d in cache_dir.iterdir():
        if not d.is_dir():
            continue
        size = _dir_size(d)
        total += size
        try:
            mtime = d.stat().st_mtime
        except OSError:
            mtime = 0.0
        infos.append((mtime, size, d))
    if total <= max_bytes:
        return 0
    infos.sort(key=lambda t: t[0])  # oldest first
    freed = 0
    for _mtime, size, d in infos:
        if total <= max_bytes:
            break
        if protect is not None and d.name == protect:
            continue
        shutil.rmtree(d, ignore_errors=True)
        total -= size
        freed += size
    return freed


def prepare(
    top: Path,
    traj: Path,
    *,
    cache_dir: Path = CACHE_DIR,
    max_bytes: int | None = None,
    select: str = "all",
    stride: int = 1,
    align: bool = False,
    align_select: str = DEFAULT_ALIGN_SELECTION,
    progress: ProgressCb | None = None,
) -> dict:
    """Process (or return a cached) trajectory; returns metadata + the cache key.

    Result: ``{"id", "n_atoms", "n_frames"}``. The model/traj files live at the
    paths from :func:`_paths` for that id. ``progress`` (if given) is called with
    ``(frames_done, frames_total)`` as frames are written. After a fresh run the
    cache is trimmed to ``max_bytes`` (``None`` = no cap). Raises
    ``ProcessUnavailable`` without MDAnalysis and ``ProcessError`` on any
    selection/IO failure.
    """
    if stride < 1:
        raise ProcessError("stride must be >= 1")

    key = cache_key(
        top, traj, select=select, stride=stride, align=align, align_select=align_select
    )
    model_path, traj_path = _paths(cache_dir, key)
    meta = model_path.parent / "meta.json"
    if model_path.is_file() and traj_path.is_file() and meta.is_file():
        # Cache hit: bump the entry's mtime so LRU eviction treats it as recent.
        try:
            os.utime(model_path.parent)
        except OSError:
            pass
        info = json.loads(meta.read_text())
        if progress is not None:
            progress(info["n_frames"], info["n_frames"])
        return {"id": key, **info}

    info = _run(
        top, traj, model_path, traj_path,
        select=select, stride=stride, align=align, align_select=align_select,
        progress=progress,
    )
    meta.write_text(json.dumps(info))
    evict(cache_dir, max_bytes, protect=key)
    return {"id": key, **info}


def _run(
    top: Path, traj: Path, model_path: Path, traj_path: Path,
    *, select: str, stride: int, align: bool, align_select: str,
    progress: ProgressCb | None = None,
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

    # Frame total for progress reporting (len() on a sliced trajectory is cheap).
    try:
        n_total = len(u.trajectory[::stride])
    except Exception:
        n_total = 0
    if progress is not None:
        progress(0, n_total)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = 0
    try:
        with mda.Writer(str(traj_path), kept.n_atoms) as writer:
            for _ in u.trajectory[::stride]:
                if align:
                    mda_align.alignto(u.atoms, ref.atoms, select=align_select)
                writer.write(kept)
                n_frames += 1
                if progress is not None:
                    progress(n_frames, n_total)
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
