"""FastAPI application factory for mdview."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import CONTENT_TYPES, SERVEABLE_EXTENSIONS, Settings
from .convert import (
    ConvertError,
    ConvertUnavailable,
    convert,
    parmed_available,
)
from .files import resolve_within_root, scan

STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings) -> FastAPI:
    """Build a FastAPI app that serves the viewer SPA and a structure-file API."""
    app = FastAPI(title="mdview", version=__version__)
    app.state.settings = settings

    @app.middleware("http")
    async def revalidate_static(request, call_next):
        """Force browsers to revalidate the SPA/vendor assets.

        StaticFiles sends ETag/Last-Modified but no Cache-Control, so browsers
        heuristically cache and can show a stale page after edits. "no-cache"
        means *revalidate every time*; unchanged files still return a cheap 304.
        """
        response = await call_next(request)
        if not request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    @app.get("/api/files")
    def api_files() -> dict:
        """List structures, topologies, coordinates, and trajectories in the root."""
        return {
            "root": str(settings.root),
            "convert_available": parmed_available(),
            **scan(settings),
        }

    @app.get("/api/file/{relpath:path}")
    def api_file(relpath: str) -> FileResponse:
        """Serve the raw bytes of one structure/topology/trajectory file.

        Path-traversal guarded and restricted to known, serveable extensions so
        Mol* can fetch PSF topologies and DCD/XTC trajectories directly.
        """
        resolved = resolve_within_root(settings.root, relpath)
        if resolved is None:
            raise HTTPException(status_code=404, detail="file not found")
        if resolved.suffix.lower() not in SERVEABLE_EXTENSIONS:
            raise HTTPException(status_code=415, detail="unsupported file type")
        media_type = CONTENT_TYPES.get(resolved.suffix.lower(), "text/plain")
        return FileResponse(resolved, media_type=media_type, filename=resolved.name)

    @app.get("/api/convert/{relpath:path}")
    def api_convert(relpath: str, coords: str | None = None, format: str = "mol2") -> Response:
        """Merge a topology (+ optional coordinate file) and return mol2/mmCIF/PDB.

        Used for formats Mol* can't load directly (e.g. PSF/prmtop). Defaults to
        mol2 so the topology's explicit bonds are preserved. Both paths are
        path-traversal guarded against the data root.
        """
        top = resolve_within_root(settings.root, relpath)
        if top is None:
            raise HTTPException(status_code=404, detail="file not found")
        coord_path = None
        if coords:
            coord_path = resolve_within_root(settings.root, coords)
            if coord_path is None:
                raise HTTPException(status_code=404, detail="coordinate file not found")
        try:
            text = convert(top, coord_path, fmt=format)
        except ConvertUnavailable as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except ConvertError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        media_type = {
            "mol2": "chemical/x-mol2",
            "cif": "chemical/x-mmcif",
            "pdb": "chemical/x-pdb",
        }.get(format, "text/plain")
        return Response(content=text, media_type=media_type)

    # The SPA and vendored Mol* assets. html=True serves index.html at "/".
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


def _app_from_env() -> FastAPI:
    """App factory for ``uvicorn --reload``, which needs an import string.

    Reads the data root from ``MDVIEW_ROOT`` (set by the CLI). Not for direct use.
    """
    import os

    root = os.environ.get("MDVIEW_ROOT", ".")
    return create_app(Settings(root=root))
