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

Test suite: 57 tests across 10 files.

## Near-term (correctness / rough edges)

- **Async `/api/prepare`.** Currently synchronous, so the first strip/stride/align
  of a very large trajectory blocks the request (repeats are instant from cache).
  Add a job + progress API (submit → poll → stream), with a progress bar in the
  Trajectories panel.
- **Processing-cache eviction.** The content-addressed cache under the system temp
  dir has no size/age cap. Add an LRU or total-size ceiling, a `--cache-dir` /
  `--cache-max` flag, and a way to inspect/clear it.
- **Reconcile docs on every phase.** Keep README Status, the `/api/*` "How it
  works" list, and this file in lockstep as features land (Phase 7–9 drift already
  happened once). Add `/api/match-topology` to the README endpoint list.

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
  CI (lint + the 57-test suite) on push.

## Non-goals (for now)

- Full editing / building of structures — this is a *viewer*.
- Replacing VMD/PyMOL for publication rendering — the render path is for quick,
  data-adjacent figures, not ray-traced finals.
- Multi-user accounts / persistence beyond the single-workstation, tunnel-first
  model.
