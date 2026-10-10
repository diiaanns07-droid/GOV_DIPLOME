/* Preview parity: the editor's resident-card rows mean the same as R03's resident card.
 * residentView(dto, R03 CivicMapCore @ pinned SHA) must equal residentView(dto, null) (the editor's fallback), and both
 * must give the words pinned in fixtures/preview_parity.json. R03's core is read with `git show` (no checkout, not run
 * as a page); if the SHA is not available locally the R03 half is NOT_RUN (skipped), never passed.
 * Run:  node --test tests/civic/R12/editor/preview_parity.test.cjs
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const C = require("../../../../web/civic/editor/editor-core.js");

const R03_SHA = "d5ee7586592b743db0e4ab31a057e53bc4bc7fab";
const FIX = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/preview_parity.json"), "utf8"));
const REPO = path.resolve(__dirname, "../../../..");

function loadR03() {
  try {
    const src = execFileSync("git", ["-C", REPO, "show", R03_SHA + ":web/civic/map/civic-map-core.js"], { stdio: ["ignore", "pipe", "ignore"] });
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "r04-r03core-"));
    const file = path.join(dir, "civic-map-core.js");
    fs.writeFileSync(file, src);
    return require(file);
  } catch (e) { return null; }
}
const R03 = loadR03();
const flat = (v) => Object.assign({ banner: v.banner ? v.banner.text : null }, Object.fromEntries(v.rows));

test("fallback rows give the pinned resident words (no R03 needed)", () => {
  for (const c of FIX.cases) {
    const v = C.residentView(c.dto, null);
    assert.equal(v.engine, "fallback");
    const got = flat(v);
    for (const [k, want] of Object.entries(c.expect)) assert.equal(got[k], want, c.name + " · " + k);
  }
});

test("R03 CivicMapCore @ " + R03_SHA.slice(0, 7) + " gives the same rows as the fallback", { skip: R03 ? false : "R03 commit " + R03_SHA + " not available locally (NOT_RUN)" }, () => {
  for (const c of FIX.cases) {
    const a = C.residentView(c.dto, R03), b = C.residentView(c.dto, null);
    assert.equal(a.engine, "r03");
    assert.deepEqual(a.rows, b.rows, c.name);
    assert.deepEqual(a.banner, b.banner, c.name + " · banner");
    assert.equal(a.kind, b.kind, c.name + " · kind");
    assert.deepEqual(a.sources.map((s) => [s.name, s.href, s.published]), b.sources.map((s) => [s.name, s.href, s.published]), c.name + " · sources");
    assert.equal(a.noSources, b.noSources, c.name + " · no sources");
    for (const [k, want] of Object.entries(c.expect)) assert.equal(flat(a)[k], want, c.name + " · " + k + " (R03)");
  }
});

test("unknown never turns into 0 or today in the resident rows", () => {
  const v = C.residentView(FIX.cases.find((c) => /nothing known/.test(c.name)).dto, R03 || null);
  for (const [k, t] of v.rows) assert.ok(!/\b0 ₸|сегодня/.test(t), k + ": " + t);
});
