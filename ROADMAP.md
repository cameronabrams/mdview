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

- **Optional authentication.** Today `--host 0.0.0.0` exposes an unauthenticated
  server. Add an opt-in token (`--token` / env) so a non-tunnel deployment behind
  a reverse proxy is safe, plus documented nginx/Caddy examples.
- **Shareable view state.** Serialize the current Mol\* state (camera,
  representations, selections, loaded pair) into a URL or a small saved snapshot,
  so a view can be reopened or handed to a colleague.
- **Trajectory / movie export.** Extend the Phase-6 render path to capture a frame
  range to an MP4/GIF on the server (reuse the supersampling + `--render-dir`
  plumbing).
- **Broaden topology matching.** Atom-count matching is the current key; add
  filename-stem matching and better disambiguation when several topologies match
  (the pestifer build dir has ~103 PDBs / 8 stage-prefixed PSFs). Surface *why* a
  match was chosen.

## Longer-term / ideas

- **Format coverage.** Multi-model PDB/mmCIF, Gromacs `.tpr`, Amber `.nc` edge
  cases, assemblies; verify 6-char CHARMM resnames survive ParmEd's MOL2 writer
  end-to-end (glycan-symbol correctness).
- **Representation presets.** One-click "membrane", "protein + glycans", "cartoon +
  ligand" setups tuned for MD systems.
- **Selection helpers.** MDAnalysis/VMD-style selection box that drives both the
  server-side strip and the in-browser Mol\* selection.
- **Publish to PyPI** as `mdview-web`; slim `browse+play`-only Docker variant;
  CI (lint + the test suite) on push.

## Non-goals (for now)

- Full editing / building of structures — this is a *viewer*.
- Replacing VMD/PyMOL for publication rendering — the render path is for quick,
  data-adjacent figures, not ray-traced finals.
- Multi-user accounts / persistence beyond the single-workstation, tunnel-first
  model.
