// K02 r7: тесты адаптера фактов «Если добавить объект» на данных и facts.js указанной сборки.
//   node tests/whatif_facts_test.cjs --app-root <prototypes/city-evidence> [--json out.json]
// Код выхода: 0 — всё PASS, 1 — есть FAIL, 2 — сборка не загрузилась. Пропусков нет: каждый тест исполняется.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const APP = arg("--app-root"), OUT = arg("--json");
const HERE = path.resolve(__dirname, "..");
const Calc = require(path.join(HERE, "whatif_calc.js")), W = require(path.join(HERE, "whatif_facts.js"));

function load() {
  const c = {}; vm.createContext(c); c.window = c;
  for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(APP, "web", f), "utf8"), c, { filename: f });
  const F = require(path.resolve(APP, "web/facts.js"));
  return { D: c.CITY_EVIDENCE, EV: c.CITY_OBS, F };
}
const clone = (x) => JSON.parse(JSON.stringify(x));
function attempt(fn) { try { return { status: "accepted", value: fn() }; } catch (e) { return { status: e.code || "error", message: String(e.message).slice(0, 200) }; } }

const results = [];
const test = (id, title, fn, app) => {
  let r; try { r = fn(app); } catch (e) { r = { pass: false, observed: "исключение теста: " + e.message }; }
  results.push({ id, title, pass: !!r.pass, observed: r.observed });
  console.log(`${r.pass ? "PASS" : "FAIL"} ${id} — ${title}` + (r.pass ? "" : "\n     observed: " + JSON.stringify(r.observed)));
};

function main() {
  let app; try { app = load(); } catch (e) { console.error("LOAD ERROR:", e.message); process.exit(2); }
  const { D, EV, F } = app;
  const deps = { sha256hex: F.sha256hex, PlanError: F.PlanError, validatePlan: F.validatePlan, formatValue: F.formatValue };
  const bb = (city) => D.cities[city].bbox;
  const mid = (city, fx = 0.5, fy = 0.5) => { const b = bb(city); return { lon: b[0] + (b[2] - b[0]) * fx, lat: b[1] + (b[3] - b[1]) * fy }; };
  const sc = (city, category, proj, pts) => ({ city_id: city, category,
    control_points: pts || [{ id: "p-a", ...mid(city, 0.2, 0.3) }, { id: "p-b", ...mid(city, 0.7, 0.6) }, { id: "p-c", ...mid(city, 0.5, 0.9) }],
    proposed_object: proj === undefined ? { id: "proj", ...mid(city, 0.25, 0.35), category, kind: "hypothetical" } : proj });
  const run = (data, s) => Calc.compute(data, s, F.sha256hex);
  const built = (data, s) => W.buildWhatifCatalog(run(data, s), deps, EV.cities[s.city_id].qa);
  const planOf = (b) => W.StubSelector.select(W.catalogView(b.catalog), b.digest);
  const stale = (oldB, newB) => attempt(() => F.validatePlan(planOf(oldB), newB)).status;

  const base = sc("shymkent", "school"), b0 = built(D, base);

  test("W01_move_project_stale", "перемещение проекта: старый digest отклоняется (stale_catalog)", () => {
    const moved = clone(base); moved.proposed_object.lon += 0.0005;
    const b1 = built(D, moved);
    return { pass: stale(b0, b1) === "stale_catalog" && b0.scenario === b1.scenario && b0.digest !== b1.digest, observed: { status: stale(b0, b1), same_scenario: b0.scenario === b1.scenario } };
  });
  test("W02_category_change_stale", "смена категории: старый план отклоняется", () => {
    const s = sc("shymkent", "outpatient_clinic"); const b1 = built(D, s);
    return { pass: stale(b0, b1) === "stale_catalog", observed: stale(b0, b1) };
  });
  test("W03_city_change_stale", "смена города: старый план отклоняется", () => {
    const b1 = built(D, sc("astana", "school"));
    return { pass: stale(b0, b1) === "stale_catalog", observed: stale(b0, b1) };
  });
  test("W04_remove_project", "удаление проекта: старый план устарел; after=before, delta=0 печатается как 0 м", () => {
    const s = clone(base); s.proposed_object = null; const b1 = built(D, s);
    const deltas = [...b1.catalog.values()].filter((f) => f.id.endsWith(".delta"));
    const text = W.explain(run(D, s), "ru", deps, EV.cities.shymkent.qa).text;
    const ok = stale(b0, b1) === "stale_catalog" && deltas.every((f) => f.value === 0 && f.kind === "derived" && !f.hypothetical) && /сокращение расстояния по прямой: 0 м/.test(text);
    return { pass: ok, observed: { status: stale(b0, b1), deltas: deltas.map((f) => f.value) } };
  });
  test("W05_zero_distance_not_missing", "точка на исходной записи: before=0 — расчёт, не missing", () => {
    const rec = Calc.sourceRecords(D, "shymkent", "school")[0];
    const s = sc("shymkent", "school", null, [{ id: "on-record", lon: rec.lon, lat: rec.lat }]);
    const r = run(D, s), b = W.buildWhatifCatalog(r, deps), f = [...b.catalog.values()].find((x) => x.id.endsWith("cp1.before"));
    const text = W.explain(r, "kk", deps).text;
    return { pass: f.value === 0 && f.kind === "derived" && f.missing_reason === null && /: 0 м/.test(text), observed: { value: f.value, kind: f.kind } };
  });
  test("W06_no_source_records", "в срезе нет записей категории: before=null, delta=null, after=до проекта, подпись спецификации", () => {
    const d2 = clone(D); d2.cities.shymkent.places = d2.cities.shymkent.places.filter((p) => p.group !== "school");
    const r = run(d2, base), b = W.buildWhatifCatalog(r, deps);
    const fs_ = [...b.catalog.values()];
    const cnt = fs_.find((f) => f.id.endsWith("whatif.source_records"));
    const okVals = r.rows.every((x) => x.before_m === null && x.delta_m === null && x.after_m === x.distance_to_proposed_m) && cnt.value === 0 && cnt.kind === "derived";
    const ex = W.explain(r, "ru", deps).text;
    return { pass: okVals && /в срезе нет исходных записей; улучшение не вычисляется/.test(ex), observed: { count: cnt.value, rows: r.rows.map((x) => [x.before_m, x.after_m, x.delta_m]) } };
  });
  test("W07_tie_by_id", "равные расстояния: выбирается запись с меньшим id", () => {
    const d2 = clone(D), c = d2.cities.shymkent, p = mid("shymkent");
    c.places = [{ id: "zzz", group: "school", lon: p.lon + 0.001, lat: p.lat, name: "Z" }, { id: "aaa", group: "school", lon: p.lon - 0.001, lat: p.lat, name: "A" }];
    const r = run(d2, sc("shymkent", "school", null, [{ id: "x", ...p }]));
    return { pass: r.rows[0].nearest_source.id === "aaa", observed: r.rows[0].nearest_source.id };
  });
  test("W08_tampered_result_rejected", "адаптер отклоняет подделанный результат (delta, NaN, before=null при записях, after>before)", () => {
    const r = run(D, base), codes = [];
    for (const mut of [(x) => { x.rows[0].delta_m += 5; }, (x) => { x.rows[0].after_m = NaN; }, (x) => { x.rows[0].before_m = null; },
      (x) => { x.rows[0].after_m = x.rows[0].before_m + 10; }, (x) => { x.source_snapshot = "file:data.js"; }, (x) => { x.proposed_object.kind = "planned"; }]) {
      const t = clone(r); t.rows.forEach((row, i) => { row.after_m = r.rows[i].after_m; }); mut(t);
      codes.push(attempt(() => W.buildWhatifCatalog(t, deps)).status);
    }
    return { pass: codes.every((c) => c !== "accepted"), observed: codes };
  });
  test("W09_imported_values_recomputed", "импортированные distances/delta не доверяются: расчёт пересчитывает", () => {
    const s = clone(base); s.rows = [{ point_id: "p-a", before_m: 1, after_m: 0, delta_m: 999999 }];
    const a = run(D, base), b = run(D, s);
    return { pass: JSON.stringify(a.rows) === JSON.stringify(b.rows), observed: b.rows[0].delta_m };
  });
  test("W10_invalid_input_rejected", "вне bbox, NaN, 1e999, дубликат id, >10 точек, чужая категория проекта — отказ", () => {
    const b = bb("shymkent"), codes = [];
    const cases = [
      [{ id: "out", lon: b[2] + 0.01, lat: b[1] + 0.001 }], [{ id: "nan", lon: NaN, lat: 42.31 }], [{ id: "inf", lon: 1e999, lat: 42.31 }],
      [{ id: "d", ...mid("shymkent") }, { id: "d", ...mid("shymkent", 0.3) }], Array.from({ length: 11 }, (_, i) => ({ id: "p" + i, ...mid("shymkent", 0.05 * (i + 1)) }))];
    for (const pts of cases) codes.push(attempt(() => run(D, sc("shymkent", "school", null, pts))).status);
    codes.push(attempt(() => run(D, sc("shymkent", "school", { id: "pr", ...mid("shymkent"), category: "outpatient_clinic", kind: "hypothetical" }))).status);
    codes.push(attempt(() => run(D, sc("astana", "school", { id: "pr", ...mid("shymkent"), category: "school", kind: "hypothetical" }))).status);
    return { pass: codes.every((c) => c !== "accepted"), observed: codes };
  });
  test("W11_snapshot_from_data", "source_snapshot зависит от данных (координата записи), стабилен при повторном расчёте", () => {
    const a = run(D, base), a2 = run(clone(D), base), d2 = clone(D);
    d2.cities.shymkent.places.find((p) => p.group === "school").lon += 1e-6;
    const c = run(d2, base);
    return { pass: a.source_snapshot === a2.source_snapshot && a.source_snapshot !== c.source_snapshot && W.buildWhatifCatalog(a, deps).digest === W.buildWhatifCatalog(a2, deps).digest,
      observed: [a.source_snapshot.slice(0, 20), c.source_snapshot.slice(0, 20)] };
  });
  test("W12_numbers_in_text_from_facts", "ru/kk: числа в строках фактов — округлённые значения каталога; в подписях нет цифр", () => {
    const r = run(D, base), b = W.buildWhatifCatalog(r, deps, EV.cities.shymkent.qa), out = {};
    let ok = true;
    for (const lang of ["ru", "kk"]) {
      const ex = W.explain(r, lang, deps, EV.cities.shymkent.qa);
      const allowed = new Set(ex.facts_used.filter((f) => f.value !== null).map((f) => String(f.unit === "m" ? Math.round(f.value) : f.value)));
      const factLines = ex.text.split("\n").filter((l) => l.startsWith("- ") && !l.includes("«"));
      const nums = factLines.flatMap((l) => (l.split(": ").slice(1).join(": ").match(/\d+/g) || []));
      out[lang] = nums; ok = ok && nums.every((n) => allowed.has(n)) && ex.facts_used.length > 0;
    }
    ok = ok && [...b.catalog.values()].every((f) => !/\d/.test(f.label.ru + f.label.kk));
    return { pass: ok, observed: out };
  });
  test("W13_haversine_reference", "гаверсинус: 1° широты = 2πR/360 м; одинаковые точки = 0", () => {
    const d = Calc.haversineM([69.6, 42.3], [69.6, 43.3]), exp = 2 * Math.PI * 6371008.8 / 360;
    return { pass: Math.abs(d - exp) < 1e-6 && Calc.haversineM([71.4, 51.1], [71.4, 51.1]) === 0, observed: [d, exp] };
  });

  const failed = results.filter((r) => !r.pass).length;
  console.log(failed ? `${failed} FAILED of ${results.length}` : `all ${results.length} passed`);
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ app_root: path.resolve(APP), node: process.version, results }, null, 1) + "\n");
  process.exit(failed ? 1 : 0);
}
main();
