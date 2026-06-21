"""Safe discovery and resolution of structure files under the data root."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Settings


def list_structures(settings: Settings) -> list[dict]:
    """Walk the data root and return loadable structures, sorted by relpath.

    Each entry: ``{"relpath": str, "size": int, "format": str}``. Only files
    whose suffix is in the configured extension allowlist are returned. Hidden
    files and directories (dot-prefixed) are skipped.
    """
    root = settings.root
    out: list[dict] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        fmt = settings.format_for(path.suffix)
        if fmt is None:
            continue
        out.append(
            {
                "relpath": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "format": fmt,
            }
        )
    out.sort(key=lambda e: e["relpath"])
    return out


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
