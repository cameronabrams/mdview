# Design: VMD-like atom selections

Status: **planned** (Mid-term roadmap item 1). Owner: cfa.
Last updated: 2026-07-20.

## Goal

Give mdview a selection box that accepts a VMD/MDAnalysis-style string —
`resname POPC`, `chain A and resid 1 to 40`, `protein and not water`,
`within 5 of resname ANE5AC` — and uses it to:

1. **highlight / focus** the matched atoms in the Mol\* viewer,
2. drive **per-selection representations** (show the selection as licorice, the
   rest as cartoon, isolate it, color it), and
3. feed the existing **Phase-4 server-side strip** (`/api/prepare` `select`),

so one language covers both viewing and processing.

## Spike findings (why "own the grammar")

Investigated the vendored viewer bundle (`molstar` 5.10.1,
`static/vendor/molstar/molstar.js`):

- **Mol\*'s VMD transpiler / `Script` helper is NOT reachable.** The `molstar`
  global exposes only 13 curated names (`Viewer`, `PluginExtensions`,
  `ExtensionMap`, `ViewerAutoPreset`, `lib`, `version`, debug toggles). `Script`
  and its language transpilers are compiled in but locked in an internal module,
  so `molstar.Script(expr, 'vmd')` does not exist at runtime.
- **The structure query engine IS reachable** via `lib`: the global's `lib`
  object is `{ structure: {...mol-model/structure}, plugin: {...}, math: {...}, … }`,
  so `molstar.lib.structure.StructureQuery`, `.Queries`, `.StructureSelection`,
  `.StructureElement`, `.StructureProperties`, `.Structure` are all available.
- Re-vendoring is a plain `cp` of the prebuilt `build/viewer/molstar.{js,css}`
  (see `vendor/molstar/VENDOR.txt`) plus `tools/patch_molstar_lipids.py`. There
  is **no local bundler step**, and the project deliberately keeps it that way
  ("no frontend build step").

**Decision — Option A: mdview owns a small selection grammar** and compiles it to
(a) a Mol\* query built from `molstar.lib.structure` for the viewer and (b) an
MDAnalysis string for the server strip. This needs **no build step** and does not
depend on Mol\*'s unreachable VMD transpiler. Cost: we implement a parser for a
**common subset** (extensible over time) rather than inheriting VMD's full grammar.

(Rejected Option B: add an esbuild vendor step to re-export `Script`. More VMD
coverage for free, but adds a Node toolchain to re-vendoring on top of the
existing lipid patch. Revisit only if the subset proves too limiting.)

## The mdview selection grammar (common subset)

Case-insensitive keywords; residue/atom **names are case-sensitive** (CHARMM names
like `ANE5AC` matter — see [[ane5-glycan-symbol]]).

```
selection := orExpr
orExpr    := andExpr ('or' andExpr)*
andExpr   := notExpr ('and' notExpr)*
notExpr   := 'not' notExpr | primary
primary   := '(' selection ')'
           | 'within' NUMBER 'of' primary          # distance (Phase A stretch / B)
           | macro
           | propSel
macro     := 'all' | 'none' | 'protein' | 'nucleic' | 'water' | 'ion'
           | 'backbone' | 'sidechain' | 'hydrogen'
propSel   := PROP item (item)*
PROP      := 'name' | 'resname' | 'resid' | 'chain' | 'index' | 'element' | 'segid'
item      := WORD | INT | INT 'to' INT | INT '-' INT   # ranges for resid/index
```

Macros are defined as ordinary predicates (kept identical between the viewer and
the server so both agree): e.g. `water` = residue name in the Phase-4 water set,
`protein` = residue name in the standard amino-acid set, `backbone` = `protein and
name N CA C O`. Defining them ourselves (rather than leaning on Mol\* or MDAnalysis
built-ins, which differ) guarantees viewer/server parity.

## Architecture: one grammar, two compile targets

```
        selection string
               │
          parse()  ──►  AST            (pure JS, no molstar/DOM deps → unit-testable)
               │
      ┌────────┴─────────┐
      ▼                  ▼
 toMolstarQuery(ast)   toMDAnalysis(ast)
   (browser/viewer)      (server strip, Phase C)
      │                  │
 lib.structure query   MDAnalysis string ──► existing POST /api/prepare `select`
```

The parser and both emitters live client-side in `static/select.js` as **pure
functions**. Phase C sends the *compiled MDAnalysis string* to the current
`/api/prepare` contract — so the server needs **no new parser** and its existing
422-on-bad-selection validation still applies.

### Browser target — `toMolstarQuery(ast)`

For the per-atom subset (`name`/`resname`/`resid`/`chain`/`index`/`element` +
`and`/`or`/`not` + macros), compile the AST to a single JS predicate over atom
properties and wrap it once:

```js
const S = molstar.lib.structure;              // StructureProperties, Queries, …
const P = S.StructureProperties;
// AST → (StructureElement.Location) => boolean, with and/or/not as &&/||/!
const atomTest = compile(ast);                // e.g. l => P.residue.label_comp_id(l) === 'POPC'
const query = S.Queries.generators.atoms({ atomTest });
const sel   = S.StructureQuery.run(query, structure);   // structure from viewer.plugin
const loci  = S.StructureSelection.toLociWithSourceUnits(sel);
```

Booleans over per-atom properties are plain `&&`/`||`/`!` in the compiled
predicate — no Mol\* combinators needed. `within N of …` is the exception (not a
per-atom property): implement it with Mol\*'s surroundings modifier
(`Queries.modifiers.includeSurroundings`, radius `N`) composed at the query level;
scope it to Phase A-stretch/Phase B.

Applying `loci` to the view (exact plugin calls to be finalized at the console
during implementation — `viewer.plugin` exposes the managers/builders regardless
of the global exports):

- **highlight / focus:** `plugin.managers.interactivity.lociHighlights` /
  `plugin.managers.camera.focusLoci(loci)`.
- **select:** `plugin.managers.structure.selection.fromLoci('set', loci)`.
- **represent / isolate:** create a component from the selection and add a
  representation; hide the base representation for "isolate". Primary approach:
  the structure-component manager; fallback: build the component from the current
  selection. Confirm the precise call against the reachable `lib`/plugin API.

Because the component is created on the trajectory **model**, the representation
persists across frames during playback (MD-relevant).

### Server target — `toMDAnalysis(ast)` (Phase C)

Emit an MDAnalysis selection string. Mostly identity for the subset; the known
divergences to encode:

| mdview grammar    | Mol\* (`StructureProperties`)      | MDAnalysis            | note |
|-------------------|------------------------------------|-----------------------|------|
| `resname X`       | `residue.label_comp_id`            | `resname X`           | names case-sensitive |
| `name X`          | `atom.label_atom_id`               | `name X`              | |
| `resid N to M`    | `residue.auth_seq_id` in range     | `resid N:M`           | |
| `chain X`         | `chain.auth_asym_id`               | `segid X` *(usually)* | **divergent** — CHARMM/PSF chain vs segid; document + make configurable |
| `index N`         | element index (0-based)            | `index N` (0-based)   | 0-based both; **not** the PDB serial |
| `element X`       | `atom.type_symbol`                 | `element X`           | |
| `within N of S`   | `includeSurroundings` (incl. S)    | `(S) or (around N (S))` | VMD `within` includes S; MDAnalysis `around` excludes it |
| `and`/`or`/`not`  | `&&`/`||`/`!`                      | `and`/`or`/`not`      | |

## UI

A persistent **Selection** panel in the sidebar (below the viewer-independent
controls, not per-file):

- text input (placeholder shows an example), Apply / Clear;
- representation `<select>` (licorice / ball+stick / cartoon / surface / hide-rest)
  and a color swatch;
- inline readout: matched-atom count, or a parse-error message with the offending
  token. Empty/`none` clears.

## File layout

- **new** `static/select.js` — `parse()`, `toMolstarQuery()`, `toMDAnalysis()`,
  macro tables. Pure functions (no DOM); loaded before `app.js`.
- **edit** `static/index.html` — the Selection panel markup + `<script>` include.
- **edit** `static/app.js` — wire the panel: on Apply, get the current structure
  from `viewer.plugin`, run the query, apply the loci; Clear removes components.
- **edit (Phase C)** `static/app.js` — route the same string into the
  `/api/prepare` `select` field (compiled to MDAnalysis).
- Docs: update README ("How it works" / Trajectories) and ROADMAP when shipped.

## Phasing

- **Phase A — browser selection core (no backend).** Grammar + `parse()` +
  `toMolstarQuery()` for the per-atom subset; Selection panel; highlight / focus /
  represent / isolate; match count + parse errors. `within` is a stretch here.
- **Phase B — multiple selections & presets.** Named selections each with their
  own representation + toggle; one-click presets ("membrane", "protein + glycans")
  as canned mdview strings; `within N of …` via surroundings modifier. Folds in
  the roadmap "representation presets" item.
- **Phase C — unify with the server strip.** `toMDAnalysis()`; a "use this
  selection for processing" affordance feeding `/api/prepare`; the current
  free-text MDAnalysis box becomes an "advanced/raw" fallback.

## Testing

- The parser and both emitters are pure JS → cover with a **Node test** (e.g.
  `tests/js/select.test.mjs` run via `node --test`): parse round-trips, operator
  precedence, ranges, macro expansion, and `toMDAnalysis` divergences (`chain`,
  `within`→`around`, index base). Keeps the tricky translation under test without
  a browser.
- Viewer application (loci → representation) verified in-browser (no JS DOM
  harness today); consider a smoke check when a harness exists.
- No new Python tests unless we later choose to translate server-side.

## Risks / to confirm at the console

1. **`molstar.lib.structure` query execution** — reachability confirmed
   statically; confirm a real `Queries.generators.atoms` + `StructureQuery.run`
   round-trip against a loaded structure, and the exact `StructureProperties`
   accessors for resid/chain, at the console before building.
2. **Component/representation creation call** — pick the exact plugin method for
   "represent selection" / "isolate" (component manager vs. current-selection
   flow) during Phase A.
3. **`chain` semantics** — auth_asym_id (Mol\*) vs segid/chainID (MDAnalysis) vs
   how ParmEd/PSF populate them; may need a small `chain`↔`segid` toggle.
4. **Grammar drift** between the JS emitters — mitigated by shared macro tables
   and Node tests over both emitters.

## Non-goals

- Full VMD grammar (`same … as`, `pbwithin`, `sequence`, boolean over bonded
  graph). Start with the documented subset; grow on demand.
- A general selection-language server API. The browser owns the grammar; the
  server keeps its existing MDAnalysis `select` contract.
