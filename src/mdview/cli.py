"""Command-line entry point: ``mdview serve --root DIR``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import Settings, parse_size


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdview",
        description="Serve interactive MD-structure visualization in the browser.",
    )
    parser.add_argument("--version", action="version", version=f"mdview {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web server")
    serve.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="directory of structure files to serve (default: current dir)",
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind address (default: 127.0.0.1, tunnel-only)",
    )
    serve.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
    serve.add_argument(
        "--render-dir",
        type=Path,
        default=Path.home() / "mdview-renders",
        help="where rendered images are saved (default: ~/mdview-renders)",
    )
    serve.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="directory for the processing cache (default: <tmp>/mdview-cache)",
    )
    serve.add_argument(
        "--cache-max",
        default="5G",
        help="processing-cache size cap, e.g. 5G / 500M / 0 to disable (default: 5G)",
    )
    serve.add_argument(
        "--reload", action="store_true", help="auto-reload on code changes (dev)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "serve":
        import uvicorn

        try:
            cache_max_bytes = parse_size(args.cache_max)
        except ValueError as exc:
            print(f"mdview: --cache-max: {exc}", file=sys.stderr)
            return 2
        try:
            settings = Settings(
                root=args.root, host=args.host, port=args.port,
                render_dir=args.render_dir,
                cache_dir=args.cache_dir, cache_max_bytes=cache_max_bytes,
            )
        except (NotADirectoryError, FileNotFoundError) as exc:
            print(f"mdview: {exc}", file=sys.stderr)
            return 2

        cap = (
            f"{settings.cache_max_bytes / 1024**3:.1f} GiB"
            if settings.cache_max_bytes else "unlimited"
        )
        print(f"mdview {__version__}: serving {settings.root}")
        print(f"  -> http://{settings.host}:{settings.port}")
        print(f"  renders -> {settings.render_dir}")
        print(f"  cache -> {settings.cache_dir} (cap: {cap})")
        if settings.host == "127.0.0.1":
            print(f"  tunnel from your laptop: ssh -L {settings.port}:localhost:"
                  f"{settings.port} <this-host>")

        if args.reload:
            # reload requires an import string; expose the app via a factory env hook.
            import os

            os.environ["MDVIEW_ROOT"] = str(settings.root)
            os.environ["MDVIEW_RENDER_DIR"] = str(settings.render_dir)
            os.environ["MDVIEW_CACHE_DIR"] = str(settings.cache_dir)
            os.environ["MDVIEW_CACHE_MAX"] = str(settings.cache_max_bytes or 0)
            uvicorn.run(
                "mdview.app:_app_from_env",
                factory=True,
                host=settings.host,
                port=settings.port,
                reload=True,
            )
        else:
            from .app import create_app

            uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
