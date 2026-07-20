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
ParmEd as MOL2 so bonds survive. Processing runs **asynchronously** — the browser
submits a job and polls for frame-by-frame progress instead of hanging on one long
request. Results are cached on disk, content-addressed by (files + options), so
repeated loads are instant and return synchronously; the cache is trimmed to a
size cap (`--cache-max`, default 5 GiB) by dropping least-recently-used entries. In
the UI the **Trajectories** section gains stride / strip-solvent / selection /
align controls with a progress readout. Enable with `uv sync --extra process`.

**Phase 5: directory browser.** Point `--root` at a broad directory and navigate
its subfolders in the sidebar (breadcrumb + current folder), rather than reading a
flat recursive dump. Only the folder you're in is shown; the path-traversal
sandbox keeps everything confined to the root. Because MD layouts often keep the
topology in a parent dir and trajectories in an `output/` subdir, the trajectory
**model** picker also offers model-eligible files from ancestor folders (shown
with a `↑` prefix), so you can pair a `.dcd` with a `.psf` one level up.

**Load a PDB with its topology (bonds + glycan symbols).** A coordinate-bearing
structure (`.pdb`/`.gro`) in the **Structures** list carries a small **⚛ bonds**
action (when the `convert` extra is present). It finds a topology (`.psf`/
`.prmtop`) in the same folder — or an ancestor — whose **atom count matches**,
and loads the pair through the MOL2 convert path. This gives real connectivity
*and* the topology's untruncated residue names, so Mol\* draws carbohydrate
(SNFG) symbols that a bare PDB loses: CHARMM writes 6-character glycan names
(`ANE5AC`→Neu5Ac, `BGLCNA`→GlcNAc) that a PDB truncates to `ANE5`/`BGLC`, which
Mol\* can't recognize — the PSF keeps the full names. When more than one topology
matches, an inline picker appears; the conversion re-checks atom counts.

**Phase 6: render to the server.** The sidebar **Render** panel captures the
current Mol\* view (1×/2×/4× supersampling) and writes the PNG to a directory on
the **workstation** (`--render-dir`, default `~/mdview-renders`) — so figures stay
where your data and notes live instead of only downloading to the laptop. Saved
renders appear as a thumbnail gallery in the sidebar; click one to open the full
image.

**Phase 7: CHARMM lipid/sterol recognition.** The vendored Mol\* build is
patched (see [`tools/patch_molstar_lipids.py`](tools/patch_molstar_lipids.py)) to
recognize CHARMM membrane residues — phospholipids, cholesterol, sphingomyelin,
and friends — so they render as lipids rather than unknown het groups.

**Phase 8: distinct lipid colors.** Membrane residue names are given distinct,
stable Residue-Name colors so different lipid species are visually separable in a
crowded bilayer.

**Phase 9: Docker packaging.** A full image (bundling the `convert` + `process`
extras) and a `docker-compose.yml`; see the [Docker](#docker) section.

## Install

Requires Python ≥ 3.10. Installing the package puts an **`mdview`** command on
your `PATH` (the Mol\* viewer is bundled — no Node/build step for users).

**As a user** (pip, straight from GitHub):

```bash
pip install "git+https://github.com/cameronabrams/mdview"               # base: browse + play
pip install "mdview-web[process] @ git+https://github.com/cameronabrams/mdview"  # + convert & trajectory processing
```

- base = FastAPI + the viewer (static structures, raw trajectory playback).
- `[convert]` adds PSF→MOL2 conversion (ParmEd); `[process]` adds that **and**
  trajectory strip/stride/align (MDAnalysis). `[process]` is the full feature set.
- The distribution is named **`mdview-web`** (the plain `mdview` is taken on
  PyPI), but it still installs the `mdview` command and the `mdview` import — so
  the extras form is `mdview-web[process]`, while everything you *run* is `mdview`.

**From a clone** (development), with [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra process --extra dev    # full features + test deps
```

## Run

```bash
uv run mdview serve --root /path/to/your/structures --port 8000
```

Point `--root` at a broad directory (e.g. `~/` or a simulations tree) and browse
its subfolders in the sidebar to find a system. Rendered images are written to
`--render-dir` (default `~/mdview-renders`); the trajectory-processing cache lives
under `--cache-dir` (default `<tmp>/mdview-cache`) and is capped by `--cache-max`
(default `5G`; `0` disables eviction). Binds `127.0.0.1` by default
(tunnel-only; no authentication); pass `--host 0.0.0.0` to expose it on all
interfaces (only behind a trusted network or reverse proxy — there is no auth).

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

## Docker

A full image (includes the `convert` + `process` extras) via docker-compose:

```bash
MDVIEW_DATA=~/ MDVIEW_RENDERS=~/mdview-renders \
MDVIEW_UID=$(id -u) MDVIEW_GID=$(id -g) \
docker compose up --build
```

- `MDVIEW_DATA` is bind-mounted **read-only** at `/data` (the browse root);
  `MDVIEW_RENDERS` is mounted writable at `/renders`. Edit
  [`docker-compose.yml`](docker-compose.yml) to taste.
- The container listens on `0.0.0.0`, but the port is published to
  **`127.0.0.1:8000`** only — reach it over the same SSH tunnel as above.
- `MDVIEW_UID`/`MDVIEW_GID` make rendered/cached files on the host owned by you,
  not root. The processing cache persists in a named volume across restarts.
- On **SELinux-enforcing** hosts (e.g. openSUSE) the compose file sets
  `security_opt: label=disable` so the container can read the bind mounts without
  relabeling your (possibly broad) data directory.

The image is ~1–1.5 GB (scipy/MDAnalysis). For browse/play only, drop the extras
from `docker/Dockerfile` for a much smaller image.

## How it works

- `GET /api/browse?dir={reldir}` — lists one directory (non-recursive): `dirs`
  (subfolders), `parent`, this folder's `files`/`topologies`/`coordinates`/
  `trajectories`, `ancestor_models` (model files in parent folders), and the
  `convert_available`/`process_available` flags. Sandbox-guarded to the root.
- `GET /api/files` — the whole-tree recursive listing (legacy; the UI uses
  `/api/browse`).
- `GET /api/match-topology?coords={relpath}` — for a coordinate-bearing structure,
  finds topology files (`.psf`/`.prmtop`) in the same folder or an ancestor whose
  **atom count matches**, so the UI can offer the ⚛ bonds pairing. Requires the
  `convert` extra.
- `GET /api/file/{relpath}` — serves one file's raw bytes — structures,
  topologies (`.psf`/`.prmtop`), and binary trajectories (`.dcd`/`.xtc`/…)
  (path-traversal guarded; restricted to the data root and known extensions).
- `GET /api/convert/{relpath}?coords={relpath}&format=mol2|cif|pdb` — merges a
  topology with a coordinate file via ParmEd and returns MOL2 (default; preserves
  bonds), or mmCIF/PDB (which drop connectivity). Both paths guarded to the data
  root. Requires the `convert` extra.
- `POST /api/prepare` — strip/stride/align a `{top, traj, select, strip, stride,
  align, align_select}` request. A cached result returns `{"status": "done", …}`
  synchronously; otherwise the work is queued and it returns `{"job_id",
  "status"}`. Requires the `process` extra.
- `GET /api/prepare/{job_id}` — poll a queued job: `{status, current, total}`,
  plus `model_url`/`trajectory_url` + atom/frame counts once `status == "done"`.
- `GET /api/prepared/{id}/{model|trajectory}` — serve a cached processed result.
- `GET /api/cache` — processing-cache stats (`dir`, `entries`, `bytes`,
  `max_bytes`); `DELETE /api/cache` empties it.
- `POST /api/render` — save a captured PNG (data URI) into `--render-dir`;
  `GET /api/renders` lists them, `GET /api/renders/{name}` serves one. Filenames
  are basename-sanitized to the render directory.
- `/` — the single-page Mol\* viewer; the vendored Mol\* build lives under
  `src/mdview/static/vendor/molstar/` (no frontend build step required).

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full plan. Recently shipped the async
job/progress API for `POST /api/prepare` and LRU cache eviction (`--cache-max`);
next up are optional authentication, shareable view state, and movie export.

## License

MIT
