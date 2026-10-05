/* K05 r7: ручные тесты whatif.js по FEATURE_SPEC (city-whatif-v1).
 *   node tests/test_whatif.cjs --app-root <checkout>/prototypes/city-evidence [--dump OUT.json]
 * Без сети. Читает web/data.js и web/evidence.js сборки (только чтение).
 * --dump пишет расчёты фиксированных сценариев на реальных данных для сверки с whatif_ref.py.
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const W = require(path.join(__dirname, "..", "whatif.js"));

const argv = process.argv.slice(2);
const arg = (k) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : null);
const APP = arg("--app-root");
if (!APP) { console.error("нужен --app-root <путь к prototypes/city-evidence>"); process.exit(2); }

function loadWindowScript(file) {
  const sandbox = { window: {} };
  vm.runInNewContext(fs.readFileSync(path.join(APP, "web", file), "utf8"), sandbox, { filename: file });
  return sandbox.window;
}
const D = loadWindowScript("data.js").CITY_EVIDENCE;
const OBS = loadWindowScript("evidence.js").CITY_OBS;

let pass = 0, fail = 0;
const results = [];
function t(name, fn) {
  try { fn(); pass++; results.push({ name, ok: true }); console.log("PASS", name); }
  catch (e) { fail++; results.push({ name, ok: false, error: String(e.message || e) }); console.log("FAIL", name, "—", e.message); }
}

const ctx = {};
for (const c of ["shymkent", "astana"]) ctx[c] = W.makeContext(c, D.cities[c], OBS.cities[c]);

function scn(city, category, points, proposed) {
  return { schema_version: W.SCHEMA, city_id: city, source_snapshot: ctx[city].snapshots[category], category,
    control_points: points, proposed_object: proposed === undefined ? null : proposed };
}
function centre(city) { const b = ctx[city].bbox; return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]; }
const P = (id, lon, lat, category = "school") => ({ id, lon, lat, category, kind: "hypothetical" });

// ---------- формула ----------
t("гаверсинус: одна и та же точка даёт честный 0", () => {
  assert.equal(W.haversineM(69.6, 42.31, 69.6, 42.31), 0);
});
t("гаверсинус: 1° по меридиану ≈ 111 195 м (R=6371008.8)", () => {
  const d = W.haversineM(0, 0, 0, 1);
  assert.ok(Math.abs(d - 6371008.8 * Math.PI / 180) < 1e-6, d);
});
t("гаверсинус: антиподы не дают NaN (зажим в [0,1])", () => {
  assert.ok(Number.isFinite(W.haversineM(0, 0, 180, 0)));
});

// ---------- реальные срезы, оба города ----------
for (const city of ["shymkent", "astana"]) {
  for (const cat of W.CATEGORIES) {
    t(`${city}/${cat}: без проекта after=before, delta=0; источник ближайшей записи указан`, () => {
      const [x, y] = centre(city);
      const r = W.compute(ctx[city], scn(city, cat, [{ id: "c1", lon: x, lat: y }]));
      const row = r.rows[0];
      assert.ok(row.before_m > 0 || row.before_m === 0);
      assert.equal(row.after_m, row.before_m);
      assert.equal(row.delta_m, 0);
      assert.equal(row.after_source, "existing");
      assert.ok(row.before_record && row.before_record.id && row.before_record.kind === "observed_secondary");
      assert.equal(r.n_source_records, D.cities[city].places.filter((p) => p.group === cat).length);
    });
  }
  t(`${city}: проект в контрольной точке → after=0, delta=before; перемещение пересчитывает; удаление восстанавливает`, () => {
    const [x, y] = centre(city);
    const base = W.compute(ctx[city], scn(city, "school", [{ id: "c1", lon: x, lat: y }]));
    const on = W.compute(ctx[city], scn(city, "school", [{ id: "c1", lon: x, lat: y }], P("p1", x, y)));
    assert.equal(on.rows[0].after_m, 0);
    assert.equal(on.rows[0].delta_m, base.rows[0].before_m);
    assert.equal(on.rows[0].after_source, "proposed");
    const b = ctx[city].bbox;
    const moved = W.compute(ctx[city], scn(city, "school", [{ id: "c1", lon: x, lat: y }], P("p1", b[0], b[1])));
    assert.ok(moved.rows[0].after_m <= moved.rows[0].before_m);
    assert.equal(moved.rows[0].before_m, base.rows[0].before_m);
    const removed = W.compute(ctx[city], scn(city, "school", [{ id: "c1", lon: x, lat: y }], null));
    assert.deepEqual(removed.rows, base.rows);
  });
}
t("delta ≥ 0 всегда; дальний проект не меняет after (источник existing)", () => {
  const b = ctx.shymkent.bbox, [x, y] = centre("shymkent");
  const base = W.compute(ctx.shymkent, scn("shymkent", "school", [{ id: "c1", lon: x, lat: y }]));
  const far = W.compute(ctx.shymkent, scn("shymkent", "school", [{ id: "c1", lon: x, lat: y }], P("p1", b[2], b[3])));
  if (far.rows[0].distance_to_proposed_m >= base.rows[0].before_m) {
    assert.equal(far.rows[0].after_source, "existing");
    assert.equal(far.rows[0].delta_m, 0);
  }
  assert.ok(far.rows[0].delta_m >= 0);
});

// ---------- null baseline ----------
const emptyCtx = W.makeContext("shymkent", { bbox: ctx.shymkent.bbox, release: "fixture", files: {}, places: [] }, { qa: {} });
t("нет исходных записей: before=null, after=distance_to_proposed, delta=null, подпись", () => {
  const s = { schema_version: W.SCHEMA, city_id: "shymkent", source_snapshot: emptyCtx.snapshots.school, category: "school",
    control_points: [{ id: "c1", lon: 69.60, lat: 42.31 }], proposed_object: P("p1", 69.61, 42.32) };
  const r = W.compute(emptyCtx, s).rows[0];
  assert.equal(r.before_m, null);
  assert.equal(r.delta_m, null);
  assert.equal(r.after_m, W.haversineM(69.60, 42.31, 69.61, 42.32));
  assert.equal(r.note, W.NO_BASE);
  const r2 = W.compute(emptyCtx, { ...s, proposed_object: null }).rows[0];
  assert.equal(r2.after_m, null);
  assert.equal(r2.delta_m, null);
});

// ---------- ничья по расстоянию ----------
t("равные расстояния: выбирается меньший id, длина та же", () => {
  // точная ничья: две записи в одной точке (как colocated-группа среза), порядок во входе обратный
  const recs = [{ id: "b", lon: 69.601, lat: 42.31, group: "school" }, { id: "a", lon: 69.601, lat: 42.31, group: "school" }];
  const c2 = W.makeContext("shymkent", { bbox: ctx.shymkent.bbox, release: "fixture", files: {}, places: recs }, { qa: {} });
  const s = { schema_version: W.SCHEMA, city_id: "shymkent", source_snapshot: c2.snapshots.school, category: "school",
    control_points: [{ id: "c1", lon: 69.6, lat: 42.31 }], proposed_object: null };
  const r = W.compute(c2, s).rows[0];
  assert.equal(r.before_record.id, "a");
  assert.equal(r.before_m, W.haversineM(69.6, 42.31, 69.601, 42.31));
});

// ---------- QA сохраняется ----------
t("Шымкент: QA-флаги ближайшей записи передаются, запись не удалена", () => {
  const doubt = Object.keys(OBS.cities.shymkent.qa.category_doubt);
  const rec = D.cities.shymkent.places.find((p) => doubt.includes(p.id) && W.CATEGORIES.includes(p.group));
  assert.ok(rec, "в срезе есть запись школы/поликлиники с category_doubt");
  const r = W.compute(ctx.shymkent, scn("shymkent", rec.group, [{ id: "c1", lon: rec.lon, lat: rec.lat }])).rows[0];
  assert.equal(r.before_m, 0);
  assert.ok(r.before_record.qa_flags.length > 0, JSON.stringify(r.before_record));
});

// ---------- валидация ----------
const [sx, sy] = centre("shymkent");
const good = () => scn("shymkent", "school", [{ id: "c1", lon: sx, lat: sy }], P("p1", sx + 0.001, sy));
const bad = (mut, code) => {
  const s = good(); mut(s);
  const v = W.validateScenario(s, ctx.shymkent);
  assert.equal(v.ok, false);
  assert.ok(v.errors.some((e) => e.startsWith(code)), v.errors.join(" | "));
};
t("валидный сценарий проходит", () => assert.deepEqual(W.validateScenario(good(), ctx.shymkent), { ok: true, errors: [] }));
t("контрольная точка вне bbox отклоняется", () => bad((s) => { s.control_points[0].lon = ctx.shymkent.bbox[2] + 0.01; }, "OUTSIDE_BBOX"));
t("проект вне bbox отклоняется", () => bad((s) => { s.proposed_object.lat = ctx.shymkent.bbox[1] - 0.01; }, "OUTSIDE_BBOX"));
t("точка Шымкента в сценарии Астаны: город/срез не совпадают", () => {
  const s = good(); s.city_id = "astana";
  const v = W.validateScenario(s, ctx.astana);
  assert.ok(v.errors.some((e) => e.startsWith("SNAPSHOT_MISMATCH")) && v.errors.some((e) => e.startsWith("OUTSIDE_BBOX")), v.errors.join(" | "));
});
t("0 и 11 контрольных точек отклоняются", () => {
  bad((s) => { s.control_points = []; }, "CONTROL_POINTS");
  bad((s) => { s.control_points = Array.from({ length: 11 }, (_, i) => ({ id: "c" + i, lon: sx, lat: sy })); }, "CONTROL_POINTS");
});
t("дубликат id (в т.ч. точка и проект) отклоняется", () => {
  bad((s) => { s.control_points.push({ id: "c1", lon: sx, lat: sy }); }, "DUPLICATE_ID");
  bad((s) => { s.proposed_object.id = "c1"; }, "DUPLICATE_ID");
});
t("длинный/небезопасный id отклоняется", () => bad((s) => { s.control_points[0].id = "x".repeat(65); }, "control_points[0]"));
t("категория проекта ≠ category; kind ≠ hypothetical; два проекта", () => {
  bad((s) => { s.proposed_object.category = "outpatient_clinic"; }, "PROPOSED");
  bad((s) => { s.proposed_object.kind = "observed"; }, "PROPOSED");
  bad((s) => { s.proposed_object = [s.proposed_object, s.proposed_object]; }, "PROPOSED");
});
t("неизвестные город, категория, версия и чужой snapshot", () => {
  bad((s) => { s.city_id = "almaty"; }, "CITY");
  bad((s) => { s.category = "hospital"; }, "CATEGORY");
  bad((s) => { s.schema_version = "city-whatif-v2"; }, "SCHEMA_VERSION");
  bad((s) => { s.source_snapshot = ctx.shymkent.snapshots.outpatient_clinic; }, "SNAPSHOT_MISMATCH");
  bad((s) => { s.source_snapshot = "places_social.geojson"; }, "SNAPSHOT_MISMATCH");
});
t("внешний URL/код и неизвестные поля отклоняются", () => {
  bad((s) => { s.control_points[0].id = "https://x"; }, "control_points[0]");
  bad((s) => { s.note = "<script>alert(1)</script>"; }, "UNKNOWN_FIELD");
  bad((s) => { s.proposed_object.url = "https://example.org/a.json"; }, "FORBIDDEN_CONTENT");
});
t("NaN/Infinity в координатах отклоняются", () => {
  bad((s) => { s.control_points[0].lon = NaN; }, "control_points[0]");
  bad((s) => { s.proposed_object.lat = Infinity; }, "proposed_object");
});

// ---------- импорт ----------
const okText = () => JSON.stringify(W.exportScenario(good(), W.compute(ctx.shymkent, good())));
t("экспорт → импорт: результат пересчитывается, импортированный result игнорируется", () => {
  const exp = JSON.parse(okText());
  exp.result.rows[0].delta_m = 999999;
  const imp = W.parseImport(JSON.stringify(exp), ctx.shymkent);
  assert.equal(imp.ok, true, imp.errors.join(" | "));
  assert.equal(imp.ignored_result, true);
  assert.equal("result" in imp.scenario, false);
  const r = W.compute(ctx.shymkent, imp.scenario);
  assert.notEqual(r.rows[0].delta_m, 999999);
  assert.deepEqual(r.rows, W.compute(ctx.shymkent, good()).rows);
});
t("экспорт без путей/токенов: только поля контракта", () => {
  const exp = JSON.parse(okText());
  assert.deepEqual(Object.keys(exp).sort(), ["category", "city_id", "control_points", "proposed_object", "result", "schema_version", "source_snapshot"]);
  assert.ok(!/inputs\/|\/home\/|token|key=/i.test(okText()));
});
t("импорт: NaN, 1e999, повтор ключа, >256 KiB, мусор — отклоняются", () => {
  const base = okText();
  assert.equal(W.parseImport(base.replace(/"lon":[-0-9.e]+/, '"lon":NaN'), ctx.shymkent).ok, false);
  const inf = W.parseImport(base.replace(/"lon":[-0-9.e]+/, '"lon":1e999'), ctx.shymkent);
  assert.equal(inf.ok, false); assert.ok(inf.errors[0].startsWith("JSON_NONFINITE"), inf.errors.join());
  const dup = W.parseImport(base.replace('"category":"school"', '"category":"school","category":"outpatient_clinic"'), ctx.shymkent);
  assert.equal(dup.ok, false); assert.ok(dup.errors[0].startsWith("JSON_DUPLICATE_KEY"), dup.errors.join());
  const big = W.parseImport(" ".repeat(W.MAX_IMPORT_BYTES) + base, ctx.shymkent);
  assert.equal(big.ok, false); assert.ok(big.errors[0].startsWith("IMPORT_TOO_LARGE"));
  assert.equal(W.parseImport("{", ctx.shymkent).ok, false);
});

// ---------- объяснение, digest, сброс ----------
t("digest объяснения зависит от snapshot, категории, точек, проекта и значений", () => {
  const e1 = W.explain(W.compute(ctx.shymkent, good()));
  const s2 = good(); s2.proposed_object.lon += 0.001;
  const e2 = W.explain(W.compute(ctx.shymkent, s2));
  const s3 = good(); s3.control_points[0].lat += 0.001;
  const e3 = W.explain(W.compute(ctx.shymkent, s3));
  const e4 = W.explain(W.compute(ctx.shymkent, scn("shymkent", "outpatient_clinic", good().control_points, P("p1", sx + 0.001, sy, "outpatient_clinic"))));
  assert.equal(new Set([e1.digest, e2.digest, e3.digest, e4.digest]).size, 4);
  assert.equal(W.explain(W.compute(ctx.shymkent, good())).digest, e1.digest);
  assert.ok(/не LLM/.test(e1.text) && /по прямой/.test(e1.text));
});
t("смена города/категории сбрасывает сценарий с причиной", () => {
  assert.equal(W.resetOnChange({ city_id: "shymkent", category: "school" }, { city_id: "astana", category: "school" }).reset, true);
  assert.equal(W.resetOnChange({ city_id: "astana", category: "school" }, { city_id: "astana", category: "outpatient_clinic" }).reset, true);
  assert.equal(W.resetOnChange({ city_id: "astana", category: "school" }, { city_id: "astana", category: "school" }).reset, false);
});
t("snapshot вычисляется из записей: изменение координаты записи меняет отпечаток", () => {
  const places = D.cities.shymkent.places.map((p) => ({ ...p }));
  const i = places.findIndex((p) => p.group === "school");
  places[i].lon += 1e-6;
  const c2 = W.makeContext("shymkent", { ...D.cities.shymkent, places }, OBS.cities.shymkent);
  assert.notEqual(c2.snapshots.school, ctx.shymkent.snapshots.school);
  assert.equal(c2.snapshots.outpatient_clinic, ctx.shymkent.snapshots.outpatient_clinic);
});

// ---------- дамп для сверки с Python ----------
const dumpPath = arg("--dump");
if (dumpPath) {
  const out = { snapshots: {}, cases: [] };
  for (const city of ["shymkent", "astana"]) {
    out.snapshots[city] = ctx[city].snapshots;
    const b = ctx[city].bbox;
    const pts = [];
    for (let i = 0; i < 10; i++) pts.push({ id: `g${i}`, lon: b[0] + (b[2] - b[0]) * ((i * 37) % 11) / 10, lat: b[1] + (b[3] - b[1]) * ((i * 53) % 13) / 12 });
    for (const cat of W.CATEGORIES) {
      for (const prop of [null, P("p1", b[0] + (b[2] - b[0]) * 0.3, b[1] + (b[3] - b[1]) * 0.6, cat)]) {
        const s = scn(city, cat, pts, prop);
        out.cases.push({ scenario: s, rows: W.compute(ctx[city], s).rows.map((r) => ({ point_id: r.point_id, before_m: r.before_m,
          before_id: r.before_record ? r.before_record.id : null, after_m: r.after_m, after_source: r.after_source, delta_m: r.delta_m })) });
      }
    }
  }
  fs.writeFileSync(dumpPath, JSON.stringify(out, null, 1) + "\n");
}

console.log(`\n${pass} passed, ${fail} failed`);
if (arg("--json")) fs.writeFileSync(arg("--json"), JSON.stringify({ pass, fail, results }, null, 1) + "\n");
process.exit(fail ? 1 : 0);
