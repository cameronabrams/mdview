"""Command-line entry point: ``mdview serve --root DIR``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import Settings


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
        "--reload", action="store_true", help="auto-reload on code changes (dev)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "serve":
        import uvicorn

        try:
            settings = Settings(root=args.root, host=args.host, port=args.port)
        except (NotADirectoryError, FileNotFoundError) as exc:
            print(f"mdview: {exc}", file=sys.stderr)
            return 2

        print(f"mdview {__version__}: serving {settings.root}")
        print(f"  -> http://{settings.host}:{settings.port}")
        if settings.host == "127.0.0.1":
            print(f"  tunnel from your laptop: ssh -L {settings.port}:localhost:"
                  f"{settings.port} <this-host>")

        if args.reload:
            # reload requires an import string; expose the app via a factory env hook.
            import os

            os.environ["MDVIEW_ROOT"] = str(settings.root)
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
