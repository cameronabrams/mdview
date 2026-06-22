"""Runtime configuration for an mdview server instance."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
    extensions: dict[str, str] = field(default_factory=lambda: dict(STATIC_EXTENSIONS))

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"data root is not a directory: {self.root}")
        # Renders land here; created lazily on first write (need not exist yet).
        self.render_dir = Path(self.render_dir).expanduser().resolve()

    def format_for(self, suffix: str) -> str | None:
        """Mol* format name for a file suffix, or None if unsupported."""
        return self.extensions.get(suffix.lower())
