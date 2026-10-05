/* Общие помощники тестов K05 r8: загрузка сборки (--app-root) и фикстуры. */
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const PL = require(path.join(__dirname, "..", "plan.js"));

function arg(k, def) { const a = process.argv.slice(2); return a.includes(k) ? a[a.indexOf(k) + 1] : def; }

// Загружает web/data.js, facts.js, whatif.js сборки в песочницу; snapshot — функцией сборки (whatif.sourceSnapshot).
function loadBuild(appRoot) {
  const sandbox = { window: {}, console };
  sandbox.window.window = sandbox.window;
  vm.createContext(sandbox);
  for (const f of ["data.js", "evidence.js", "facts.js", "whatif.js"]) {
    const p = path.join(appRoot, "web", f);
    if (fs.existsSync(p)) vm.runInContext(fs.readFileSync(p, "utf8"), sandbox, { filename: f });
  }
  const W = sandbox.window;
  const D = W.CITY_EVIDENCE;
  const snap = (city) => (W.CITY_WHATIF && W.CITY_FACTS ? W.CITY_WHATIF.sourceSnapshot(D, city, W.CITY_FACTS) : null);
  return { D, OBS: W.CITY_OBS, W, snap };
}

function buildContext(B, city) {
  return PL.contextFromCityData(city, B.D.cities[city], B.snap(city), { release: B.D.cities[city].release, snapshot_fn: "whatif.sourceSnapshot" });
}

// Детерминированный ГПСЧ для synthetic фикстур (mulberry32).
function rng(seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// Сценарий на реальном срезе с SYNTHETIC кандидатами/стоимостями/весами (не городская статистика, не цены).
function syntheticScenario(ctx, category, { seed = 1, nPoints = 8, nCand = 6, budget = 300, maxSel = 3, radius = 400,
  required = [], excluded = [], selected = [] } = {}) {
  const r = rng(seed), b = ctx.bbox;
  const at = () => [b[0] + (b[2] - b[0]) * r(), b[1] + (b[3] - b[1]) * r()];
  const control_points = Array.from({ length: nPoints }, (_, i) => { const [lon, lat] = at(); return { id: `syn_p${i}`, lon, lat, weight: 1 + Math.floor(r() * 5) }; });
  const candidates = Array.from({ length: nCand }, (_, i) => { const [lon, lat] = at(); return { id: `syn_c${String(i).padStart(2, "0")}`, lon, lat, category, kind: "hypothetical", cost: 50 + Math.floor(r() * 150) }; });
  return { schema_version: PL.SCHEMA, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot, category, control_points, candidates,
    budget, max_selected: maxSel, coverage_radius_m: radius, required_ids: required, excluded_ids: excluded, selected_ids: selected };
}

function shuffled(arr, seed) {
  const r = rng(seed), a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}

function runner() {
  let pass = 0, fail = 0, skip = 0; const results = [];
  const t = (name, fn) => {
    try { const r = fn(); if (r === "SKIP") { skip++; results.push({ name, status: "SKIP" }); console.log("SKIP", name); return; }
      pass++; results.push({ name, status: "PASS" }); console.log("PASS", name); }
    catch (e) { fail++; results.push({ name, status: "FAIL", error: String(e.stack || e) }); console.log("FAIL", name, "—", e.message); }
  };
  const done = (jsonPath) => {
    console.log(`\n${pass} passed, ${fail} failed, ${skip} skipped`);
    if (jsonPath) fs.writeFileSync(jsonPath, JSON.stringify({ pass, fail, skip, results }, null, 1) + "\n");
    return fail ? 1 : 0;
  };
  return { t, done, get counts() { return { pass, fail, skip }; } };
}

module.exports = { PL, arg, loadBuild, buildContext, rng, syntheticScenario, shuffled, runner };
