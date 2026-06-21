"""Runtime configuration for an mdview server instance."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Structure formats Mol* can load directly in the browser.
#
# MVP (static inspection): single-file structures with coordinates.
# Phase 3 will add topology+coordinate trajectory formats (.psf/.dcd/.xtc/.trr),
# which Mol* loads as a topology paired with a coordinates file.
STATIC_EXTENSIONS: dict[str, str] = {
    ".pdb": "pdb",
    ".ent": "pdb",
    ".pqr": "pdb",
    ".cif": "mmcif",
    ".mmcif": "mmcif",
    ".gro": "gro",
}

# Topology-only formats: no coordinates of their own, so they must be paired with
# a coordinate file and converted server-side (parmed) before display. Phase 2.
TOPOLOGY_EXTENSIONS: dict[str, str] = {
    ".psf": "psf",
    ".prmtop": "amber",
    ".parm7": "amber",
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

# MIME types for serving raw structure bytes. Molecular formats are plain text;
# the Mol* loader keys off the format we pass in JS, not the content-type, so
# text/plain is a safe default that also renders sanely if opened directly.
CONTENT_TYPES: dict[str, str] = {
    ".cif": "chemical/x-cif",
    ".mmcif": "chemical/x-mmcif",
    ".pdb": "chemical/x-pdb",
    ".ent": "chemical/x-pdb",
    ".pqr": "text/plain",
    ".gro": "text/plain",
}


@dataclass
class Settings:
    """Resolved settings for one running server."""

    root: Path
    host: str = "127.0.0.1"
    port: int = 8000
    extensions: dict[str, str] = field(default_factory=lambda: dict(STATIC_EXTENSIONS))

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"data root is not a directory: {self.root}")

    def format_for(self, suffix: str) -> str | None:
        """Mol* format name for a file suffix, or None if unsupported."""
        return self.extensions.get(suffix.lower())
