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
coordinate file (`.pdb`/`.gro`/`.crd`/`.rst7`/…) and merged via
[ParmEd](https://parmed.github.io/ParmEd/) into **MOL2** so they display as a
single structure. MOL2 carries the topology's explicit `@<TRIPOS>BOND` block, so
Mol\* draws the real connectivity instead of guessing bonds from distance (which
misfires on distorted MD coordinates). In the UI these appear under
**Topologies**, with a coordinate-file picker. Enable with
`uv sync --extra convert`.

**Phase 3: trajectory playback.** A model or topology (`.pdb`/`.gro`/`.psf`/
`.prmtop`) is paired with a binary trajectory (`.dcd`/`.xtc`/`.trr`/`.nc`) and
loaded through Mol\*'s native topology+coordinates path, giving a frame
play/scrub bar. The server just streams the raw files — Mol\* decodes and
animates the frames in the browser. In the UI this is the **Trajectories**
section (model picker + trajectory picker + play). No `convert` extra needed.

Some NAMD/CHARMM DCDs store a frame count (`NSET`) of 0 in their header even
though they contain frames; Mol\* trusts `NSET` and would read zero frames. The
server detects this from the file geometry and patches `NSET` on the fly while
streaming (the rest of the file is byte-for-byte unchanged), so these
trajectories play correctly.

**Phase 4: trajectory processing (optional `process` extra).** Before a
trajectory reaches the browser the server can **decimate** (keep every Nth
frame), **strip** (drop solvent/ions, or any [MDAnalysis](https://www.mdanalysis.org/)
selection), and **align** (superpose every frame onto frame 0 to remove
translational/rotational drift). This makes multi-GB runs usable over a thin
tunnel and the motion legible. The reduced trajectory is written by MDAnalysis;
the matching reduced **model** (atom count changes when stripping) is built with
ParmEd as MOL2 so bonds survive. Results are cached on disk, content-addressed by
(files + options), so repeated loads are instant. In the UI the **Trajectories**
section gains stride / strip-solvent / selection / align controls. Enable with
`uv sync --extra process`.

**Phase 5: directory browser.** Point `--root` at a broad directory and navigate
its subfolders in the sidebar (breadcrumb + current folder), rather than reading a
flat recursive dump. Only the folder you're in is shown; the path-traversal
sandbox keeps everything confined to the root. Because MD layouts often keep the
topology in a parent dir and trajectories in an `output/` subdir, the trajectory
**model** picker also offers model-eligible files from ancestor folders (shown
with a `↑` prefix), so you can pair a `.dcd` with a `.psf` one level up.

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

Point `--root` at a broad directory (e.g. `~/` or a simulations tree) and browse
its subfolders in the sidebar to find a system. Binds `127.0.0.1` by default
(tunnel-only; no authentication).

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

- `GET /api/browse?dir={reldir}` — lists one directory (non-recursive): `dirs`
  (subfolders), `parent`, this folder's `files`/`topologies`/`coordinates`/
  `trajectories`, `ancestor_models` (model files in parent folders), and the
  `convert_available`/`process_available` flags. Sandbox-guarded to the root.
- `GET /api/files` — the whole-tree recursive listing (legacy; the UI uses
  `/api/browse`).
- `GET /api/file/{relpath}` — serves one file's raw bytes — structures,
  topologies (`.psf`/`.prmtop`), and binary trajectories (`.dcd`/`.xtc`/…)
  (path-traversal guarded; restricted to the data root and known extensions).
- `GET /api/convert/{relpath}?coords={relpath}&format=mol2|cif|pdb` — merges a
  topology with a coordinate file via ParmEd and returns MOL2 (default; preserves
  bonds), or mmCIF/PDB (which drop connectivity). Both paths guarded to the data
  root. Requires the `convert` extra.
- `POST /api/prepare` — strip/stride/align a `{top, traj, select, strip, stride,
  align, align_select}` request; returns cached `model_url` + `trajectory_url`
  plus atom/frame counts. Requires the `process` extra.
- `GET /api/prepared/{id}/{model|trajectory}` — serve a cached processed result.
- `/` — the single-page Mol\* viewer; the vendored Mol\* build lives under
  `src/mdview/static/vendor/molstar/` (no frontend build step required).

## Roadmap

- **Async processing** — `POST /api/prepare` is currently synchronous, so the
  first prepare of a very large trajectory blocks the request (the cache makes
  repeats instant). A job/progress API would smooth this over.
- **Cache eviction** — the content-addressed processing cache under the system
  temp dir has no size/age cap yet.
- **Docker packaging** — optional, for running detached.

## License

MIT
