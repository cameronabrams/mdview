"""Runtime configuration for an mdview server instance."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .process import CACHE_DIR

# Default cap for the on-disk processing cache. Processed trajectories are small
# relative to the raw runs, so a few GB holds many; override with --cache-max.
DEFAULT_CACHE_MAX_BYTES: int = 5 * 1024**3  # 5 GiB


def parse_size(text: str | int | None) -> int | None:
    """Parse a human size (``"5G"``, ``"500M"``, ``"2048"``) to bytes.

    ``0``/``""``/``none``/``unlimited``/``off`` mean "no cap" (returns ``None``).
    Suffixes K/M/G/T are binary (1024-based); a trailing ``B`` is ignored.
    """
    if text is None:
        return None
    s = str(text).strip().lower()
    if s in ("", "0", "none", "unlimited", "off"):
        return None
    if s.endswith("b"):  # accept a trailing byte marker: 5GB, 500MB, 2048B
        s = s[:-1].strip()
    units = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    mult = 1
    if s and s[-1] in units:
        mult = units[s[-1]]
        s = s[:-1].strip()
    try:
        value = float(s)
    except ValueError as exc:
        raise ValueError(f"bad size {text!r} (try e.g. 5G, 500M, 0)") from exc
    if value < 0:
        raise ValueError(f"size cannot be negative: {text!r}")
    return int(value * mult) or None

# Structure formats Mol* can load directly in the browser. The values are Mol*'s
# own format ids (used as the `model` format when loading), so a .pdb is "pdb",
# .cif is "mmcif", etc. — single-file structures that carry coordinates.
STATIC_EXTENSIONS: dict[str, str] = {
    ".pdb": "pdb",
    ".ent": "pdb",
    ".pqr": "pdb",
    ".cif": "mmcif",
    ".mmcif": "mmcif",
    ".gro": "gro",
}

# Topology-only formats: no coordinates of their own. Values are Mol*'s topology
# format ids, so the same field works both as a display label and as the
# `topology-url` format when pairing with a trajectory (Phase 3). For static
# display they are merged with a coordinate file via parmed (Phase 2).
TOPOLOGY_EXTENSIONS: dict[str, str] = {
    ".psf": "psf",
    ".prmtop": "prmtop",
    ".parm7": "prmtop",
}

# Binary trajectory (coordinates) formats Mol* streams as frames, paired with a
# model/topology. Values are Mol*'s `coordinates-url` format ids. Phase 3.
TRAJECTORY_EXTENSIONS: dict[str, str] = {
    ".dcd": "dcd",
    ".xtc": "xtc",
    ".trr": "trr",
    ".nc": "nctraj",
    ".netcdf": "nctraj",
    ".ncdf": "nctraj",
}

# Files that can supply coordinates for a topology. Includes the native
# coordinate-bearing structures (.pdb/.gro) plus Amber coordinate/restart files.
COORD_EXTENSIONS: dict[str, str] = {
    ".pdb": "pdb",
    ".ent": "pdb",
    ".gro": "gro",
    ".crd": "charmmcrd",
    ".rst7": "amber",
    ".inpcrd": "amber",
    ".restrt": "amber",
    ".ncrst": "amber",
}

# MIME types for serving raw structure bytes. Molecular text formats are plain
# text; the Mol* loader keys off the format we pass in JS, not the content-type,
# so text/plain is a safe default. Binary trajectories use octet-stream.
CONTENT_TYPES: dict[str, str] = {
    ".cif": "chemical/x-cif",
    ".mmcif": "chemical/x-mmcif",
    ".pdb": "chemical/x-pdb",
    ".ent": "chemical/x-pdb",
    ".pqr": "text/plain",
    ".gro": "text/plain",
    ".psf": "text/plain",
    ".prmtop": "text/plain",
    ".parm7": "text/plain",
    ".dcd": "application/octet-stream",
    ".xtc": "application/octet-stream",
    ".trr": "application/octet-stream",
    ".nc": "application/octet-stream",
    ".netcdf": "application/octet-stream",
    ".ncdf": "application/octet-stream",
}

# Every suffix mdview will serve raw over /api/file: native structures, topology
# files, coordinate files, and trajectories. Used to gate /api/file.
SERVEABLE_EXTENSIONS: frozenset[str] = frozenset(
    {*STATIC_EXTENSIONS, *TOPOLOGY_EXTENSIONS, *COORD_EXTENSIONS, *TRAJECTORY_EXTENSIONS}
)


@dataclass
class Settings:
    """Resolved settings for one running server."""

    root: Path
    host: str = "127.0.0.1"
    port: int = 8000
    render_dir: Path = field(default_factory=lambda: Path.home() / "mdview-renders")
    # On-disk processing cache (Phase 4). `cache_dir=None` falls back to the shared
    # default; `cache_max_bytes=None` disables eviction (unbounded growth).
    cache_dir: Path | None = None
    cache_max_bytes: int | None = DEFAULT_CACHE_MAX_BYTES
    extensions: dict[str, str] = field(default_factory=lambda: dict(STATIC_EXTENSIONS))

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"data root is not a directory: {self.root}")
        # Renders land here; created lazily on first write (need not exist yet).
        self.render_dir = Path(self.render_dir).expanduser().resolve()
        # Cache dir is created lazily on first prepare; default is process.CACHE_DIR.
        self.cache_dir = (
            Path(self.cache_dir).expanduser().resolve() if self.cache_dir else CACHE_DIR
        )

    def format_for(self, suffix: str) -> str | None:
        """Mol* format name for a file suffix, or None if unsupported."""
        return self.extensions.get(suffix.lower())
