# mdview

Browser-served, interactive visualization of molecular dynamics (MD) systems —
designed to run on a workstation and be reached from a laptop over an SSH tunnel.

The backend (FastAPI) lists and serves structure files from a directory you
point it at; the browser-side [Mol\*](https://molstar.org/) viewer renders them
with full rotate / zoom / select / measure / representation controls.

## Status

**Phase 1 (MVP): static-structure inspection.** Loads single-structure formats
that Mol\* reads natively: `.pdb` `.ent` `.pqr` `.cif`/`.mmcif` `.gro`.
Trajectory playback (PSF+DCD / XTC) is planned — see *Roadmap*.

## Install

Requires Python ≥ 3.10 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # runtime only
uv sync --extra dev     # + pytest/httpx for the test suite
```

## Run

```bash
uv run mdview serve --root /path/to/your/structures --port 8000
```

Binds `127.0.0.1` by default (tunnel-only; no authentication).

### Access over an SSH tunnel

On the workstation:

```bash
uv run mdview serve --root ~/simulations --port 8000
```

From your laptop:

```bash
ssh -L 8000:localhost:8000 panacea
```

then open <http://localhost:8000> in your browser.

## How it works

- `GET /api/files` — lists loadable structures under the data root (recursive,
  extension-allowlisted).
- `GET /api/file/{relpath}` — serves one structure's bytes (path-traversal
  guarded; restricted to the data root).
- `/` — the single-page Mol\* viewer; the vendored Mol\* build lives under
  `src/mdview/static/vendor/molstar/` (no frontend build step required).

## Roadmap

- **Phase 2** — optional server-side conversion via [ParmEd](https://parmed.github.io/ParmEd/)
  (`uv sync --extra convert`): normalize/merge topology+coordinates → mmCIF for
  formats Mol\* can't read directly.
- **Phase 3** — trajectory playback: load PSF+DCD / XTC / TRR via Mol\*'s
  topology+coordinates path, with server-side frame decimation for large DCDs.
- **Phase 4** — optional Docker packaging.

## License

MIT
