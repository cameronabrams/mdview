"use strict";
// mdview selection grammar (see docs/design/atom-selections.md).
//
// Parses a VMD/MDAnalysis-like selection string into an AST and compiles it two
// ways: (a) a per-atom predicate the Mol* viewer runs via
// molstar.lib.structure.Queries.generators.atoms, and (b) an MDAnalysis
// selection string for the Phase-4 server strip. Everything here is pure — no
// molstar or DOM dependency — so it runs under `node --test` as well as in the
// browser. The browser adapter that bridges a Mol* StructureElement.Location to
// the predicate's accessor lives in app.js.
//
// Grammar (common subset):
//   orExpr  := andExpr ('or' andExpr)*
//   andExpr := notExpr ('and' notExpr)*
//   notExpr := 'not' notExpr | primary
//   primary := '(' orExpr ')' | 'within' NUM 'of' primary | macro | PROP value+
//   value   := WORD | INT | INT 'to' INT | INT('-'|':')INT     (ranges: resid/index)
//
// Keywords are case-insensitive; residue/atom NAMES are case-sensitive (CHARMM
// names like ANE5AC matter).

(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MDSelect = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  // Residue-name sets. WATER/IONS mirror mdview/process.py so the viewer and the
  // server strip agree on what "water"/"ion" mean — keep them in sync.
  const WATER = new Set(["TIP3", "TIP4", "TIP5", "TIP3P", "WAT", "HOH", "SOL", "SPC", "SPCE", "T3P"]);
  const IONS = new Set(["SOD", "CLA", "POT", "CES", "CAL", "MG", "ZN2", "ZN", "NA", "CL",
    "K", "LIT", "RUB", "BAR", "FE", "FE2", "MN", "CU", "CD", "IOD", "BR"]);
  const AA = new Set(["ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "HSD", "HSE", "HSP", "HID", "HIE", "HIP", "CYX", "ASH", "GLH", "LYN", "MSE"]);
  const NUC = new Set(["A", "U", "G", "C", "T", "DA", "DT", "DG", "DC", "DU",
    "RA", "RU", "RG", "RC", "ADE", "THY", "GUA", "CYT", "URA"]);
  const BB = new Set(["N", "CA", "C", "O"]);

  // Macro -> per-atom predicate. `a` is an accessor with methods
  // resname()/name()/resid()/index()/chain()/segid()/element().
  const MACROS = {
    all: () => true,
    none: () => false,
    water: (a) => WATER.has(a.resname()),
    ion: (a) => IONS.has(a.resname()),
    protein: (a) => AA.has(a.resname()),
    nucleic: (a) => NUC.has(a.resname()),
    hydrogen: (a) => (a.element() || "").toUpperCase() === "H",
    backbone: (a) => AA.has(a.resname()) && BB.has(a.name()),
    sidechain: (a) => AA.has(a.resname()) && !BB.has(a.name()),
  };

  const OPS = new Set(["and", "or", "not"]);
  const PROPS = new Set(["name", "resname", "resid", "chain", "index", "element", "segid"]);
  const NUMERIC_PROPS = new Set(["resid", "index"]);
  const MACRO_NAMES = new Set(Object.keys(MACROS));
  // Tokens that terminate a property's value list.
  const STOP = new Set([...OPS, ...PROPS, ...MACRO_NAMES, "within", "of", "(", ")"]);

  class SelectError extends Error {
    constructor(message) {
      super(message);
      this.name = "SelectError";
    }
  }

  function tokenize(str) {
    const toks = [];
    let i = 0;
    const n = str.length;
    while (i < n) {
      const c = str[i];
      if (/\s/.test(c)) { i++; continue; }
      if (c === "(" || c === ")") { toks.push(c); i++; continue; }
      let j = i;
      while (j < n && !/\s/.test(str[j]) && str[j] !== "(" && str[j] !== ")") j++;
      toks.push(str.slice(i, j));
      i = j;
    }
    return toks;
  }

  // Recursive-descent parser -> AST of nodes tagged with `kind`.
  function parse(str) {
    const tokens = tokenize(str);
    let pos = 0;
    const peek = () => tokens[pos];
    const lc = () => (tokens[pos] === undefined ? undefined : tokens[pos].toLowerCase());

    function parseOr() {
      let node = parseAnd();
      while (lc() === "or") { pos++; node = { kind: "or", left: node, right: parseAnd() }; }
      return node;
    }
    function parseAnd() {
      let node = parseNot();
      while (lc() === "and") { pos++; node = { kind: "and", left: node, right: parseNot() }; }
      return node;
    }
    function parseNot() {
      if (lc() === "not") { pos++; return { kind: "not", child: parseNot() }; }
      return parsePrimary();
    }
    function parsePrimary() {
      const t = peek();
      if (t === undefined) throw new SelectError("unexpected end of selection");
      const tl = t.toLowerCase();
      if (t === "(") {
        pos++;
        const inner = parseOr();
        if (peek() !== ")") throw new SelectError("missing closing ')'");
        pos++;
        return inner;
      }
      if (tl === "within") {
        pos++;
        const numTok = peek();
        if (numTok === undefined || !/^-?\d*\.?\d+$/.test(numTok)) {
          throw new SelectError("'within' must be followed by a distance");
        }
        pos++;
        if (lc() !== "of") throw new SelectError("'within N' must be followed by 'of'");
        pos++;
        return { kind: "within", radius: parseFloat(numTok), child: parsePrimary() };
      }
      if (MACRO_NAMES.has(tl)) { pos++; return { kind: "macro", name: tl }; }
      if (PROPS.has(tl)) { pos++; return { kind: "prop", prop: tl, items: parseValues(tl) }; }
      throw new SelectError(`unexpected token '${t}'`);
    }
    function parseValues(prop) {
      const items = [];
      while (pos < tokens.length) {
        const t = tokens[pos];
        if (STOP.has(t.toLowerCase())) break;
        // N to M
        if (/^-?\d+$/.test(t) && tokens[pos + 1] && tokens[pos + 1].toLowerCase() === "to"
            && tokens[pos + 2] && /^-?\d+$/.test(tokens[pos + 2])) {
          items.push({ kind: "range", lo: parseInt(t, 10), hi: parseInt(tokens[pos + 2], 10) });
          pos += 3;
          continue;
        }
        // N-M or N:M
        const m = /^(-?\d+)[:-](-?\d+)$/.exec(t);
        if (m) {
          items.push({ kind: "range", lo: parseInt(m[1], 10), hi: parseInt(m[2], 10) });
          pos++;
          continue;
        }
        items.push({ kind: "val", value: t });
        pos++;
      }
      if (items.length === 0) throw new SelectError(`'${prop}' needs at least one value`);
      return items;
    }

    if (tokens.length === 0) throw new SelectError("empty selection");
    const ast = parseOr();
    if (pos < tokens.length) throw new SelectError(`unexpected token '${tokens[pos]}'`);
    return ast;
  }

  // AST -> (accessor) => boolean, for the Mol* viewer.
  function compilePredicate(ast) {
    switch (ast.kind) {
      case "or": {
        const l = compilePredicate(ast.left), r = compilePredicate(ast.right);
        return (a) => l(a) || r(a);
      }
      case "and": {
        const l = compilePredicate(ast.left), r = compilePredicate(ast.right);
        return (a) => l(a) && r(a);
      }
      case "not": {
        const c = compilePredicate(ast.child);
        return (a) => !c(a);
      }
      case "within":
        throw new SelectError("'within' selections aren't supported yet (planned for a later phase)");
      case "macro":
        return MACROS[ast.name];
      case "prop":
        return compileProp(ast);
      default:
        throw new SelectError(`cannot compile node '${ast.kind}'`);
    }
  }

  function compileProp(ast) {
    const p = ast.prop;
    if (NUMERIC_PROPS.has(p)) {
      const get = p === "resid" ? (a) => a.resid() : (a) => a.index();
      const singles = new Set();
      const ranges = [];
      for (const it of ast.items) {
        if (it.kind === "range") { ranges.push([it.lo, it.hi]); continue; }
        const v = parseInt(it.value, 10);
        if (Number.isNaN(v)) throw new SelectError(`'${p}' expects integers, got '${it.value}'`);
        singles.add(v);
      }
      return (a) => {
        const v = get(a);
        if (singles.has(v)) return true;
        for (const [lo, hi] of ranges) if (v >= lo && v <= hi) return true;
        return false;
      };
    }
    const acc = {
      name: (a) => a.name(),
      resname: (a) => a.resname(),
      chain: (a) => a.chain(),
      segid: (a) => a.segid(),
      element: (a) => (a.element() || "").toUpperCase(),
    }[p];
    const vals = new Set(ast.items.map((it) => {
      if (it.kind === "range") throw new SelectError(`'${p}' does not take numeric ranges`);
      return p === "element" ? it.value.toUpperCase() : it.value;
    }));
    return (a) => vals.has(acc(a));
  }

  // AST -> MDAnalysis selection string, for the server strip (Phase C). Macros
  // expand to explicit expressions so the server matches the viewer's predicates.
  const AA_LIST = [...AA].join(" ");
  function toMDAnalysis(ast) {
    switch (ast.kind) {
      case "or": return `(${toMDAnalysis(ast.left)}) or (${toMDAnalysis(ast.right)})`;
      case "and": return `(${toMDAnalysis(ast.left)}) and (${toMDAnalysis(ast.right)})`;
      case "not": return `not (${toMDAnalysis(ast.child)})`;
      case "within":
        throw new SelectError("'within' isn't supported in the server strip yet");
      case "macro": return macroToMDA(ast.name);
      case "prop": return propToMDA(ast);
      default: throw new SelectError(`cannot translate node '${ast.kind}'`);
    }
  }

  function macroToMDA(name) {
    switch (name) {
      case "all": return "all";
      case "none": return "not all";
      case "water": return `resname ${[...WATER].join(" ")}`;
      case "ion": return `resname ${[...IONS].join(" ")}`;
      case "protein": return `resname ${AA_LIST}`;
      case "nucleic": return `resname ${[...NUC].join(" ")}`;
      case "hydrogen": return "element H";
      case "backbone": return `(resname ${AA_LIST}) and name N CA C O`;
      case "sidechain": return `(resname ${AA_LIST}) and not (name N CA C O)`;
      default: throw new SelectError(`unknown macro '${name}'`);
    }
  }

  function propToMDA(ast) {
    const p = ast.prop;
    if (NUMERIC_PROPS.has(p)) {
      const toks = ast.items.map((it) =>
        it.kind === "range" ? `${it.lo}:${it.hi}` : it.value);
      return `${p} ${toks.join(" ")}`;
    }
    // chain has no direct MDAnalysis field; segid is the usual CHARMM/PSF analogue.
    const field = p === "chain" ? "segid" : p;
    const toks = ast.items.map((it) => {
      if (it.kind === "range") throw new SelectError(`'${p}' does not take numeric ranges`);
      return it.value;
    });
    return `${field} ${toks.join(" ")}`;
  }

  return {
    parse,
    compilePredicate,
    toMDAnalysis,
    tokenize,
    SelectError,
    // exposed for reuse/introspection (and to keep in sync with process.py)
    sets: { WATER, IONS, AA, NUC, BB },
    MACRO_NAMES,
    PROPS,
  };
});
