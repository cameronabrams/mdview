# mdview

Browser-served, interactive visualization of molecular dynamics (MD) systems —
designed to run on a workstation and be reached from a laptop over an SSH tunnel.

The backend (FastAPI) lists and serves structure files from a directory you
point it at; the browser-side [Mol\*](https://molstar.org/) viewer renders them
with full rotate / zoom / select / measure / representation controls.

## Status

**Phase 1: static-structure inspection.** Loads single-structure formats that
Mol\* reads natively: `.pdb` `.ent` `.pqr` `.cif`/`.mmcif` `.gro`.

**Phase 2: server-side conversion (optional `convert` extra).** Topology-only
formats — CHARMM/NAMD `.psf`, Amber `.prmtop`/`.parm7` — are paired with a
coordinate file (`.pdb`/`.gro`/`.crd`/`.rst7`/…) and merged to mmCIF/PDB via
[ParmEd](https://parmed.github.io/ParmEd/) so they display as a single
structure. In the UI these appear under **Topologies**, with a coordinate-file
picker. Enable with `uv sync --extra convert`.

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

- `GET /api/files` — lists `files` (natively loadable), `topologies` (need
  coordinates), and `coordinates` (usable as a coordinate source) under the data
  root, plus `convert_available`. Recursive, extension-allowlisted.
- `GET /api/file/{relpath}` — serves one structure's bytes (path-traversal
  guarded; restricted to the data root).
- `GET /api/convert/{relpath}?coords={relpath}&format=cif|pdb` — merges a
  topology with a coordinate file via ParmEd and returns mmCIF/PDB (both paths
  guarded to the data root). Requires the `convert` extra.
- `/` — the single-page Mol\* viewer; the vendored Mol\* build lives under
  `src/mdview/static/vendor/molstar/` (no frontend build step required).

## Roadmap

- **Phase 3** — trajectory playback: load PSF+DCD / XTC / TRR via Mol\*'s
  topology+coordinates path, with server-side frame decimation for large DCDs.
- **Phase 4** — optional Docker packaging.

## License

MIT
