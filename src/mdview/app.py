"""FastAPI application factory for mdview."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .config import CONTENT_TYPES, SERVEABLE_EXTENSIONS, Settings
from .dcd import patched_stream, repair_plan
from .convert import (
    ConvertError,
    ConvertUnavailable,
    convert,
    parmed_available,
)
from .files import browse, resolve_within_root, scan
from .process import (
    DEFAULT_ALIGN_SELECTION,
    STRIP_SOLVENT_FILTER,
    ProcessError,
    ProcessUnavailable,
    prepare,
    process_available,
)
from .process import _paths as _prepared_paths
from .render import RenderError, list_renders, safe_render_path, save_png

STATIC_DIR = Path(__file__).parent / "static"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class RenderRequest(BaseModel):
    image: str
    name: str | None = None


class PrepareRequest(BaseModel):
    top: str
    traj: str
    select: str = "all"
    strip: bool = False  # AND the water+ions strip filter onto `select`
    stride: int = 1
    align: bool = False
    align_select: str = DEFAULT_ALIGN_SELECTION

    def effective_select(self) -> str:
        sel = self.select.strip() or "all"
        if not self.strip:
            return sel
        if sel == "all":
            return STRIP_SOLVENT_FILTER
        return f"({sel}) and ({STRIP_SOLVENT_FILTER})"


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
        """List ALL loadable files under the root, recursively (legacy/whole-tree)."""
        return {
            "root": str(settings.root),
            "convert_available": parmed_available(),
            "process_available": process_available(),
            **scan(settings),
        }

    @app.get("/api/browse")
    def api_browse(dir: str = "") -> dict:
        """List one directory under the root (folders + this folder's loadable files)."""
        result = browse(settings, dir)
        if result is None:
            raise HTTPException(status_code=404, detail="directory not found")
        return {
            "root": str(settings.root),
            "convert_available": parmed_available(),
            "process_available": process_available(),
            **result,
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
        suffix = resolved.suffix.lower()
        if suffix not in SERVEABLE_EXTENSIONS:
            raise HTTPException(status_code=415, detail="unsupported file type")
        media_type = CONTENT_TYPES.get(suffix, "text/plain")

        # DCDs with a wrong NSET (frame count) header break Mol*'s reader, which
        # trusts NSET. Patch it on the fly so such trajectories play.
        if suffix == ".dcd":
            plan = repair_plan(resolved)
            if plan is not None:
                nset, endian = plan
                return StreamingResponse(
                    patched_stream(resolved, nset, endian), media_type=media_type
                )
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

    @app.post("/api/prepare")
    def api_prepare(req: PrepareRequest) -> dict:
        """Strip/stride/align a trajectory, cache the result, return its URLs.

        Produces a reduced bonded model (mol2) + processed trajectory (dcd),
        content-addressed so identical requests are instant. Both input paths are
        guarded against the data root.
        """
        top = resolve_within_root(settings.root, req.top)
        traj = resolve_within_root(settings.root, req.traj)
        if top is None:
            raise HTTPException(status_code=404, detail="topology not found")
        if traj is None:
            raise HTTPException(status_code=404, detail="trajectory not found")
        try:
            result = prepare(
                top, traj,
                select=req.effective_select(), stride=req.stride,
                align=req.align, align_select=req.align_select,
            )
        except ProcessUnavailable as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except ProcessError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "id": result["id"],
            "model_url": f"/api/prepared/{result['id']}/model",
            "trajectory_url": f"/api/prepared/{result['id']}/trajectory",
            "model_format": "mol2",
            "trajectory_format": "dcd",
            "n_atoms": result["n_atoms"],
            "n_frames": result["n_frames"],
        }

    @app.get("/api/prepared/{key}/{which}")
    def api_prepared(key: str, which: str) -> FileResponse:
        """Serve a cached processed model/trajectory by its content-address id."""
        if not _HEX64.match(key) or which not in ("model", "trajectory"):
            raise HTTPException(status_code=404, detail="not found")
        model_path, traj_path = _prepared_paths(key)
        path = model_path if which == "model" else traj_path
        if not path.is_file():
            raise HTTPException(status_code=404, detail="prepared file not found")
        media_type = "chemical/x-mol2" if which == "model" else "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    @app.post("/api/render")
    def api_render(req: RenderRequest) -> dict:
        """Save a captured PNG (data URI) into the server's render directory."""
        try:
            filename = save_png(settings.render_dir, req.image, req.name)
        except RenderError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"filename": filename, "url": f"/api/renders/{filename}"}

    @app.get("/api/renders")
    def api_renders() -> dict:
        """List previously saved renders, newest first."""
        return {
            "render_dir": str(settings.render_dir),
            "renders": list_renders(settings.render_dir),
        }

    @app.get("/api/renders/{name}")
    def api_render_file(name: str) -> FileResponse:
        """Serve one saved render PNG (basename-guarded to the render directory)."""
        path = safe_render_path(settings.render_dir, name)
        if path is None:
            raise HTTPException(status_code=404, detail="render not found")
        return FileResponse(path, media_type="image/png")

    # The SPA and vendored Mol* assets. html=True serves index.html at "/".
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


def _app_from_env() -> FastAPI:
    """App factory for ``uvicorn --reload``, which needs an import string.

    Reads the data root from ``MDVIEW_ROOT`` (set by the CLI). Not for direct use.
    """
    import os

    root = os.environ.get("MDVIEW_ROOT", ".")
    render_dir = os.environ.get("MDVIEW_RENDER_DIR")
    kwargs = {"render_dir": render_dir} if render_dir else {}
    return create_app(Settings(root=root, **kwargs))
