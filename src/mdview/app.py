"""FastAPI application factory for mdview."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import CONTENT_TYPES, Settings
from .files import list_structures, resolve_within_root

STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings) -> FastAPI:
    """Build a FastAPI app that serves the viewer SPA and a structure-file API."""
    app = FastAPI(title="mdview", version=__version__)
    app.state.settings = settings

    @app.get("/api/files")
    def api_files() -> dict:
        """List loadable structures under the data root."""
        return {"root": str(settings.root), "files": list_structures(settings)}

    @app.get("/api/file/{relpath:path}")
    def api_file(relpath: str) -> FileResponse:
        """Serve the raw bytes of one structure file (path-traversal guarded)."""
        resolved = resolve_within_root(settings.root, relpath)
        if resolved is None:
            raise HTTPException(status_code=404, detail="file not found")
        if settings.format_for(resolved.suffix) is None:
            raise HTTPException(status_code=415, detail="unsupported file type")
        media_type = CONTENT_TYPES.get(resolved.suffix.lower(), "text/plain")
        return FileResponse(resolved, media_type=media_type, filename=resolved.name)

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
