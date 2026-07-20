# mdview roadmap

Status snapshot and forward plan. For *what each shipped phase does*, see the
**Status** section of the [README](README.md); this file tracks what's next.

Current version: **0.1.0** (Beta). HEAD implements Phases 1–9 plus PDB-centric
topology pairing.

## Shipped

| # | Feature | Extra |
|---|---------|-------|
| 1 | Static single-structure viewing (`.pdb .ent .pqr .cif .gro`) | — |
| 2 | PSF/prmtop + coords → MOL2 (real bonds) via ParmEd | `convert` |
| 3 | Trajectory playback (`.dcd .xtc .trr .nc`); DCD `NSET=0` repair | — |
| 4 | Trajectory strip / stride / align with on-disk cache | `process` |
| 5 | Directory-browser sidebar (breadcrumb + ancestor pairing) | — |
| 6 | Render current view → PNG saved on the server | — |
| 7 | CHARMM lipid / sterol recognition | — |
| 8 | Distinct residue-name colors for lipids | — |
| 9 | Docker packaging (full image + docker-compose) | — |
| + | PDB-centric topology pairing (⚛ bonds: atom-count match, bonds + SNFG glycan symbols) | `convert` |
| + | Async `/api/prepare` job+progress API; LRU cache eviction (`--cache-dir`/`--cache-max`, `/api/cache`) | `process` |

Test suite: 83 tests across 11 files.

## Near-term (correctness / rough edges)

- ~~**Async `/api/prepare`.**~~ *Done.* `POST /api/prepare` submits a job (cache
  hits still return synchronously) and the browser polls `GET /api/prepare/{job_id}`
  for frame-by-frame progress; a single worker thread serializes the heavy work.
- ~~**Processing-cache eviction.**~~ *Done.* The cache is trimmed to `--cache-max`
  (default 5 GiB, `0` disables) by dropping least-recently-used entries; `--cache-dir`
  relocates it and `GET`/`DELETE /api/cache` inspect and clear it.
- ~~**Reconcile docs on every phase.**~~ *Done for now.* README Status, the `/api/*`
  list, and this file are back in sync (Phases 7–9, `/api/match-topology`, the
  prepare/cache endpoints). Keep them in lockstep as features land.

## Mid-term (reach / deployment)

- **VMD-like atom selections & representations.** Add a selection box that takes a
  VMD/MDAnalysis-style string — `resname POPC`, `chain A and resid 1 to 40`,
  `within 5 of resname ANE5AC`, `not water` — and:
  - highlights / isolates the selection in the Mol\* viewer,
  - drives per-selection representations (e.g. the selection as licorice, the rest
    as cartoon), and
  - feeds the existing Phase-4 server-side strip (which already parses MDAnalysis
    selections), so one language covers both viewing and processing.

  The wrinkle is three selection dialects — VMD, MDAnalysis, and Mol\*'s own query
  language. First cut: support a common subset (`name` / `resname` / `resid` /
  `chain` / `index` + `and`/`or`/`not` + `within … of …`) that maps cleanly to all
  three; MDAnalysis on the server already parses the full string for the strip.
  Then grow a small translator from the VMD-ish mini-language to Mol\* queries for
  the browser side. This is the backbone for representation presets (membrane /
  protein+glycans) below.
- **Trajectory / movie export.** Extend the Phase-6 render path to capture a frame
  range to an MP4/GIF on the server (reuse the supersampling + `--render-dir`
  plumbing).
- **Shareable view state.** Serialize the current Mol\* state (camera,
  representations, selections, loaded pair) into a URL or a small saved snapshot,
  so a view can be reopened or handed to a colleague.
- **Broaden topology matching.** Atom-count matching is the current key; add
  filename-stem matching and better disambiguation when several topologies match
  (the pestifer build dir has ~103 PDBs / 8 stage-prefixed PSFs). Surface *why* a
  match was chosen.
- **Optional authentication — only if you expose `--host 0.0.0.0`.** The default
  `--host 127.0.0.1` is reachable only through an SSH tunnel, which already
  authenticates and encrypts, so no app-level auth is needed for the normal
  workflow. This matters *only* when binding `0.0.0.0` to serve without a tunnel:
  add an opt-in token (`--token` / env) plus reverse-proxy (nginx/Caddy) examples.

## Longer-term / ideas

- **Format coverage.** Multi-model PDB/mmCIF, Gromacs `.tpr`, Amber `.nc` edge
  cases, assemblies; verify 6-char CHARMM resnames survive ParmEd's MOL2 writer
  end-to-end (glycan-symbol correctness).
- **Representation presets.** One-click "membrane", "protein + glycans", "cartoon +
  ligand" setups tuned for MD systems — built on the selection engine above.
- **Publish to PyPI** as `mdview-web`; slim `browse+play`-only Docker variant;
  CI (lint + the test suite) on push.

## Non-goals (for now)

- Full editing / building of structures — this is a *viewer*.
- Replacing VMD/PyMOL for publication rendering — the render path is for quick,
  data-adjacent figures, not ray-traced finals.
- Multi-user accounts / persistence beyond the single-workstation, tunnel-first
  model.
