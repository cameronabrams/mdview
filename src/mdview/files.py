"""Safe discovery and resolution of structure files under the data root."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .config import COORD_EXTENSIONS, TOPOLOGY_EXTENSIONS, TRAJECTORY_EXTENSIONS

if TYPE_CHECKING:
    from .config import Settings


def scan(settings: Settings) -> dict[str, list[dict]]:
    """Walk the data root once and bucket files into four lists.

    Returns ``{"files", "topologies", "coordinates", "trajectories"}`` where each
    entry is ``{"relpath", "size", "format"}``. A single file may appear in more
    than one bucket (e.g. a ``.pdb`` is both natively loadable and usable as a
    coordinate source). Hidden files/directories (dot-prefixed) are skipped;
    results are sorted by relpath.
    """
    root = settings.root
    files: list[dict] = []
    topologies: list[dict] = []
    coordinates: list[dict] = []
    trajectories: list[dict] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        suffix = path.suffix.lower()
        base = {"relpath": rel.as_posix(), "size": path.stat().st_size}

        fmt = settings.format_for(suffix)
        if fmt is not None:
            files.append({**base, "format": fmt})
        if suffix in TOPOLOGY_EXTENSIONS:
            topologies.append({**base, "format": TOPOLOGY_EXTENSIONS[suffix]})
        if suffix in COORD_EXTENSIONS:
            coordinates.append({**base, "format": COORD_EXTENSIONS[suffix]})
        if suffix in TRAJECTORY_EXTENSIONS:
            trajectories.append({**base, "format": TRAJECTORY_EXTENSIONS[suffix]})

    for bucket in (files, topologies, coordinates, trajectories):
        bucket.sort(key=lambda e: e["relpath"])
    return {
        "files": files,
        "topologies": topologies,
        "coordinates": coordinates,
        "trajectories": trajectories,
    }


def list_structures(settings: Settings) -> list[dict]:
    """Natively loadable structures only (convenience wrapper around :func:`scan`)."""
    return scan(settings)["files"]


def resolve_within_root(root: Path, relpath: str) -> Path | None:
    """Resolve ``relpath`` under ``root``, or None if it escapes the root.

    Guards against ``..`` traversal and symlinks that point outside the root by
    resolving the final path and confirming ``root`` is one of its parents.
    """
    root = root.resolve()
    candidate = (root / relpath).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate
