"""Save and serve rendered viewport images on the server.

The browser captures the current Mol* view as a PNG data URI and POSTs it here;
we decode it and write it into the configured ``render_dir`` so images stay on the
workstation (where the data and figure pipeline live) instead of only downloading
to the laptop.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path

_PNG_PREFIX = "data:image/png;base64,"
_MAX_BYTES = 50 * 1024 * 1024  # generous cap for a supersampled PNG
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class RenderError(ValueError):
    """A render image could not be decoded or saved."""


def _sanitize_name(name: str | None) -> str:
    """Reduce a requested name to a safe ``.png`` basename (timestamp default)."""
    stem = Path(name or "").name  # drop any directory components
    stem = _SAFE_NAME.sub("_", stem).strip("._")
    if stem.lower().endswith(".png"):
        stem = stem[:-4]
    if not stem:
        stem = "mdview-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stem}.png"


def _unique(render_dir: Path, filename: str) -> str:
    """Append a numeric suffix if ``filename`` already exists."""
    if not (render_dir / filename).exists():
        return filename
    stem = filename[:-4]
    n = 1
    while (render_dir / f"{stem}-{n}.png").exists():
        n += 1
    return f"{stem}-{n}.png"


def save_png(render_dir: Path, data_uri: str, name: str | None = None) -> str:
    """Decode a PNG data URI and write it into ``render_dir``; return the filename."""
    if not data_uri.startswith(_PNG_PREFIX):
        raise RenderError("expected a PNG data URI (data:image/png;base64,…)")
    b64 = data_uri[len(_PNG_PREFIX):]
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception as exc:
        raise RenderError(f"could not decode image data: {exc}") from exc
    if not raw:
        raise RenderError("empty image")
    if len(raw) > _MAX_BYTES:
        raise RenderError("image exceeds the size limit")
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise RenderError("decoded data is not a PNG")

    render_dir.mkdir(parents=True, exist_ok=True)
    filename = _unique(render_dir, _sanitize_name(name))
    (render_dir / filename).write_bytes(raw)
    return filename


def list_renders(render_dir: Path) -> list[dict]:
    """List saved renders, newest first (empty if the dir doesn't exist)."""
    if not render_dir.is_dir():
        return []
    out = []
    for p in render_dir.glob("*.png"):
        if not p.is_file():
            continue
        st = p.stat()
        out.append({
            "name": p.name,
            "size": st.st_size,
            "mtime": st.st_mtime,
            "url": f"/api/renders/{p.name}",
        })
    out.sort(key=lambda e: e["mtime"], reverse=True)
    return out


def safe_render_path(render_dir: Path, name: str) -> Path | None:
    """Resolve one render file by basename, or None if it escapes ``render_dir``."""
    if name != Path(name).name:  # any separators / traversal -> reject
        return None
    candidate = (render_dir / name).resolve()
    if candidate.parent != render_dir.resolve() or not candidate.is_file():
        return None
    return candidate
