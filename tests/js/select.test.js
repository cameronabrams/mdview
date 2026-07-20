"use strict";
// Pure-JS tests for the selection grammar (docs/design/atom-selections.md).
// Run: node --test tests/js/    (no npm deps; uses the built-in runner)

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const MDSelect = require(path.join(__dirname, "..", "..", "src", "mdview", "static", "select.js"));
const { parse, compilePredicate, toMDAnalysis, SelectError } = MDSelect;

// Build a fake atom accessor for predicate tests.
function atom({ resname = "", name = "", resid = 0, index = 0, chain = "", segid = "", element = "" }) {
  return {
    resname: () => resname, name: () => name, resid: () => resid,
    index: () => index, chain: () => chain, segid: () => segid, element: () => element,
  };
}
const matches = (sel, a) => compilePredicate(parse(sel))(a);

test("parse: precedence — and binds tighter than or", () => {
  const ast = parse("resname A and resname B or resname C");
  // ((A and B) or C)
  assert.equal(ast.kind, "or");
  assert.equal(ast.left.kind, "and");
  assert.equal(ast.right.kind, "prop");
});

test("parse: not binds tighter than and", () => {
  const ast = parse("not water and protein");
  assert.equal(ast.kind, "and");
  assert.equal(ast.left.kind, "not");
});

test("parse: parentheses override precedence", () => {
  const ast = parse("resname A and (resname B or resname C)");
  assert.equal(ast.kind, "and");
  assert.equal(ast.right.kind, "or");
});

test("predicate: resname membership (case-sensitive values)", () => {
  assert.ok(matches("resname POPC", atom({ resname: "POPC" })));
  assert.ok(!matches("resname POPC", atom({ resname: "popc" })));
  assert.ok(matches("resname POPC POPE", atom({ resname: "POPE" })));
});

test("predicate: keywords are case-insensitive", () => {
  assert.ok(matches("RESNAME POPC", atom({ resname: "POPC" })));
  assert.ok(matches("resname A AND resname A", atom({ resname: "A" })));
});

test("predicate: resid ranges via 'to', '-', and ':'", () => {
  for (const sel of ["resid 1 to 40", "resid 1-40", "resid 1:40"]) {
    assert.ok(matches(sel, atom({ resid: 20 })), sel);
    assert.ok(!matches(sel, atom({ resid: 41 })), sel);
  }
  assert.ok(matches("resid 5 10 20 to 25", atom({ resid: 23 })));
  assert.ok(matches("resid 5 10 20 to 25", atom({ resid: 10 })));
  assert.ok(!matches("resid 5 10 20 to 25", atom({ resid: 11 })));
});

test("predicate: boolean composition", () => {
  const a = atom({ resname: "ALA", name: "CA", chain: "A", resid: 3 });
  assert.ok(matches("chain A and resid 1 to 40", a));
  assert.ok(!matches("chain B and resid 1 to 40", a));
  assert.ok(matches("chain B or resid 3", a));
  assert.ok(matches("not chain B", a));
});

test("predicate: macros — protein / water / backbone", () => {
  assert.ok(matches("protein", atom({ resname: "ALA" })));
  assert.ok(!matches("protein", atom({ resname: "POPC" })));
  assert.ok(matches("water", atom({ resname: "TIP3" })));
  assert.ok(matches("backbone", atom({ resname: "ALA", name: "CA" })));
  assert.ok(!matches("backbone", atom({ resname: "ALA", name: "CB" })));
  assert.ok(matches("protein and not backbone", atom({ resname: "ALA", name: "CB" })));
});

test("predicate: element is case-insensitive symbol match", () => {
  assert.ok(matches("element C", atom({ element: "c" })));
  assert.ok(matches("hydrogen", atom({ element: "H" })));
  assert.ok(!matches("hydrogen", atom({ element: "C" })));
});

test("toMDAnalysis: identity-ish for the simple subset", () => {
  assert.equal(toMDAnalysis(parse("resname POPC POPE")), "resname POPC POPE");
  assert.equal(toMDAnalysis(parse("name CA CB")), "name CA CB");
});

test("toMDAnalysis: resid ranges use colon", () => {
  assert.equal(toMDAnalysis(parse("resid 1 to 40")), "resid 1:40");
  assert.equal(toMDAnalysis(parse("resid 5 10 20-25")), "resid 5 10 20:25");
});

test("toMDAnalysis: chain -> segid divergence", () => {
  assert.equal(toMDAnalysis(parse("chain A")), "segid A");
});

test("toMDAnalysis: boolean wrapping and not", () => {
  assert.equal(toMDAnalysis(parse("resname A and resname B")),
    "(resname A) and (resname B)");
  assert.equal(toMDAnalysis(parse("not water")).startsWith("not (resname "), true);
});

test("toMDAnalysis: macros expand to explicit resname lists (viewer parity)", () => {
  assert.ok(toMDAnalysis(parse("water")).startsWith("resname TIP3"));
  assert.ok(toMDAnalysis(parse("backbone")).includes("and name N CA C O"));
});

test("errors: malformed selections raise SelectError", () => {
  assert.throws(() => parse(""), SelectError);
  assert.throws(() => parse("resname"), SelectError);         // no value
  assert.throws(() => parse("resname A and"), SelectError);    // dangling operator
  assert.throws(() => parse("(resname A"), SelectError);       // unbalanced paren
  assert.throws(() => parse("resname A extra )"), SelectError);
  assert.throws(() => parse("bogus"), SelectError);            // unknown token
});

test("errors: within is parsed but not yet compilable", () => {
  const ast = parse("within 5 of resname ANE5AC");
  assert.equal(ast.kind, "within");
  assert.equal(ast.radius, 5);
  assert.throws(() => compilePredicate(ast), SelectError);
  assert.throws(() => toMDAnalysis(ast), SelectError);
});
