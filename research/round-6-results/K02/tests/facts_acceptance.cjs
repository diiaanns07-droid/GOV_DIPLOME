// K02 round 6 REVIEW: приёмка web/facts.js сборки city-evidence (адаптер теста K02 r5 @ 26fd30c).
// Те же 11 инвариантов. Адаптация (TEST_INCOMPATIBLE r5 → r6), критерии не ослаблены:
//   1) vm-контекст facts.js получает TextEncoder (новый синхронный SHA-256 его использует);
//   2) API: buildCatalog → {catalog, scenario, city, digest}; StubSelector.select(view, digest);
//      validatePlan(plan, built); render(plan, built, lang) — определяется автоматически (API_R6);
//   3) индикаторы K05 v1.2: places.school ← overture_place_records.school.conf_ge_0_0,
//      segments.foot_unknown ← segments_foot_access.unknown; город в ID — kz.<city>;
//   4) T7: исключение, не связанное с проверкой города, больше не засчитывается как отказ (в r5 TextEncoder
//      давал ложный PASS) — нужен PlanError foreign_city;
//   5) T10: реальные счётчики квадрата теперь complete=true, поэтому неполный охват задаётся подменой.
//
// Запуск (без зависимостей, Node >= 18):
//   node facts_regression.cjs --app-root <путь к извлечённой prototypes/city-evidence>
//   node facts_regression.cjs --url http://127.0.0.1:8765/      (serve.py сборки; читает facts.js, data.js, evidence.js)
//   добавить --json <файл>, чтобы сохранить результат.
//
// Код выхода: 0 — все тесты PASS; 1 — есть FAIL; 2 — не удалось загрузить сборку.
// Ожидаемое API после исправления (см. ../REPORT.md):
//   catalogDigest(catalog) -> string; планы несут catalog_digest; validatePlan отклоняет несовпадение
//   кодом "stale_catalog"; повтор ID между секциями -> "duplicate_id"; неконечные числа и чужой city_id
//   в наблюдениях -> ошибка при buildCatalog; факты несут unit и coverage_complete; неполный охват виден в render.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");

function arg(name) { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : null; }
const APP_ROOT = arg("--app-root"), URL_BASE = arg("--url"), JSON_OUT = arg("--json");

async function source(name) {
  if (APP_ROOT) return fs.readFileSync(path.join(APP_ROOT, "web", name), "utf8");
  if (URL_BASE) {
    const res = await fetch(new URL(name, URL_BASE.endsWith("/") ? URL_BASE : URL_BASE + "/"));
    if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
    return await res.text();
  }
  throw new Error("нужен --app-root или --url");
}

async function load() {
  const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
  for (const f of ["data.js", "evidence.js"]) vm.runInContext(await source(f), ctx, { filename: f });
  // facts.js: CommonJS-ветка, выполняем в отдельном контексте с module.exports
  const mod = { exports: {} }, fctx = { module: mod, exports: mod.exports, globalThis: {}, console, TextEncoder, TextDecoder };
  vm.createContext(fctx);
  vm.runInContext(await source("facts.js"), fctx, { filename: "facts.js" });
  return { F: mod.exports, D: ctx.CITY_EVIDENCE, EV: ctx.CITY_OBS };
}

const clone = (x) => JSON.parse(JSON.stringify(x));
// ---- адаптер API ----
const IND = { "places.school": "overture_place_records.school.conf_ge_0_0", "segments.foot_unknown": "segments_foot_access.unknown" };
const indicator = (path) => IND[path] || path;
const isR6 = (F) => F.validatePlan.length === 2;
const build = (F, D, EV, city, groups) => F.buildCatalog(D, EV, city, groups);
const validate = (F, plan, b, city) => (isR6(F) ? F.validatePlan(plan, b) : F.validatePlan(plan, b.catalog, city, b.scenario));
const renderText = (F, acc, b, lang) => (isR6(F) ? F.render(acc, b, lang) : F.render(acc, b.catalog, b.scenario, lang)).text;
const fid = (b, city, p) => `${b.city || city}/${b.scenario}/${p}`;
const digestOf = (F, b) => (b.digest !== undefined ? b.digest : typeof F.catalogDigest === "function" ? F.catalogDigest(b.catalog) : undefined);
const ALL = (F) => new Set(F.GROUP_ORDER);
function attempt(fn) {
  try { return { status: "accepted", value: fn() }; }
  catch (e) { return { status: e && e.code ? e.code : "error", error: e && (e.constructor && e.constructor.name), message: String(e && e.message).slice(0, 160) }; }
}
function setObs(EV, city, path, patch) {
  const o = EV.cities[city].observations.find((x) => x.indicator_id === indicator(path));
  if (!o) throw new Error(`нет наблюдения ${city}/${indicator(path)}`);
  Object.assign(o, patch);
  return o;
}
// План как сделал бы селектор по старому каталогу; если API digest есть — с digest старого каталога.
function planFor(F, built) {
  const view = F.catalogView(built.catalog), digest = digestOf(F, built);
  return isR6(F) ? F.StubSelector.select(view, digest) : F.StubSelector.select(view, { digest });
}

const TESTS = [];
const test = (id, title, fn) => TESTS.push({ id, title, fn });

// T1–T3: тот же город и срез, старый план, изменённый каталог.
for (const [id, title, mutate] of [
  ["T1_value_change", "изменение значения при том же городе и срезе: старый план отклоняется",
    (EV) => setObs(EV, "shymkent", "places.school", { value: 16 })],
  ["T2_unit_change", "изменение единицы при том же городе и срезе: старый план отклоняется",
    // r6: таблица единиц закрыта (неизвестная "km" отклоняется при buildCatalog — проверено отдельно в REPORT);
    // смена на другую допустимую единицу должна делать старый план устаревшим.
    (EV) => setObs(EV, "shymkent", "segments.foot_unknown", { unit: "records" })],
  ["T3_coverage_change", "изменение охвата при том же городе и срезе: старый план отклоняется",
    (EV) => setObs(EV, "shymkent", "segments.foot_unknown", { coverage: { ...EV.cities.shymkent.observations.find((o) => o.indicator_id === indicator("segments.foot_unknown")).coverage, complete: false } })],
]) {
  test(id, title, ({ F, D, EV }) => {
    const before = build(F, D, EV, "shymkent", ALL(F));
    const plan = planFor(F, before);
    const ev2 = clone(EV); mutate(ev2);
    const after = build(F, D, ev2, "shymkent", ALL(F));
    const r = attempt(() => validate(F, plan, after, "shymkent"));
    return { pass: r.status === "stale_catalog", observed: r.status, scenario_same: before.scenario === after.scenario };
  });
}

test("T4_digest_distinguishes", "старый срез и изменённый каталог различимы (catalogDigest), одинаковые — равны", ({ F, D, EV }) => {
  if (typeof F.catalogDigest !== "function") return { pass: false, observed: "API отсутствует: catalogDigest" };
  const a = build(F, D, EV, "shymkent", ALL(F)), a2 = build(F, D, clone(EV), "shymkent", ALL(F));
  const ev2 = clone(EV); setObs(ev2, "shymkent", "places.school", { value: 16 });
  const b = build(F, D, ev2, "shymkent", ALL(F));
  const da = F.catalogDigest(a.catalog), db = F.catalogDigest(b.catalog);
  const builtOk = digestOf(F, a) === da && digestOf(F, b) === db;
  return { pass: da === F.catalogDigest(a2.catalog) && da !== db && builtOk, observed: { same_scenario: a.scenario === b.scenario, da, db } };
});

test("T5_duplicate_across_sections", "повтор одного ID в двух секциях отклоняется (duplicate_id)", ({ F, D, EV }) => {
  const b = build(F, D, EV, "shymkent", ALL(F));
  const id = fid(b, "shymkent", "places.school");
  const plan = { sections: [{ type: "summary", fact_ids: [id] }, { type: "risks", fact_ids: [id] }], catalog_digest: digestOf(F, b) };
  const r = attempt(() => validate(F, plan, b, "shymkent"));
  return { pass: r.status === "duplicate_id", observed: r.status };
});

test("T6_null_vs_zero", "null: только в data_gaps и «нет данных»; настоящий 0 печатается как 0", ({ F, D, EV }) => {
  const b = build(F, D, EV, "shymkent", ALL(F));
  const nul = fid(b, "shymkent", "capacity.school_places"), zero = fid(b, "shymkent", "district_status.ambiguous");
  const dg = { catalog_digest: digestOf(F, b) };
  const outside = attempt(() => validate(F, { sections: [{ type: "summary", fact_ids: [nul] }], ...dg }, b, "shymkent"));
  const gaps = validate(F, { sections: [{ type: "data_gaps", fact_ids: [nul] }, { type: "risks", fact_ids: [zero] }], ...dg }, b, "shymkent");
  const ru = renderText(F, gaps, b, "ru"), kk = renderText(F, gaps, b, "kk");
  const zeroLine = ru.split("\n").find((l) => l.includes(b.catalog.get(zero).label.ru + ":")) || "";
  const ok = outside.status === "null_as_fact" && /нет данных/.test(ru) && /дерек жоқ/.test(kk)
    && /: 0( |\()/.test(zeroLine) && b.catalog.get(nul).value === null && b.catalog.get(zero).value === 0;
  return { pass: ok, observed: { outside: outside.status, ru_lines: ru.split("\n").filter((l) => l.startsWith("- ")) } };
});

test("T7_city_substitution_observations", "наблюдения другого города под ключом города отклоняются при buildCatalog", ({ F, D, EV }) => {
  const ev2 = clone(EV); ev2.cities.shymkent.observations = clone(EV.cities.astana.observations);
  const r = attempt(() => build(F, D, ev2, "shymkent", ALL(F)));
  // r6: засчитывается только контролируемый отказ по городу (в r5 любое исключение давало ложный PASS)
  return { pass: r.status === "foreign_city", observed: r.status === "accepted" ? "принято: числа kz.astana под shymkent" : r };
});

test("T8_city_switch_stale_plan", "план по Астане против каталога Шымкента отклоняется (foreign_city или stale_catalog)", ({ F, D, EV }) => {
  const a = build(F, D, EV, "astana", ALL(F)), s = build(F, D, EV, "shymkent", ALL(F));
  const r = attempt(() => validate(F, planFor(F, a), s, "shymkent"));
  return { pass: r.status === "foreign_city" || r.status === "stale_catalog", observed: r.status };
});

for (const [id, bad] of [["T9_nonfinite_nan", NaN], ["T9_nonfinite_inf", Infinity]]) {
  test(id, `неконечное число (${bad}) отклоняется при buildCatalog, а не падает в render`, ({ F, D, EV }) => {
    const ev2 = clone(EV); // clone теряет NaN/Infinity (→ null), поэтому подставляем после клонирования
    setObs(ev2, "shymkent", "places.school", { value: bad });
    const r = attempt(() => build(F, D, ev2, "shymkent", ALL(F)));
    let renderStatus = null;
    if (r.status === "accepted") {
      const plan = planFor(F, r.value);
      const v = attempt(() => validate(F, plan, r.value, "shymkent"));
      renderStatus = v.status === "accepted" ? attempt(() => renderText(F, v.value, r.value, "ru")).status : v.status;
    }
    return { pass: r.status !== "accepted", observed: r.status === "accepted" ? `buildCatalog принял; render: ${renderStatus}` : r.status };
  });
}

test("T10_incomplete_coverage_visible", "значения при coverage.complete=false помечены в тексте объяснения", ({ F, D, EV }) => {
  const ev2 = clone(EV);
  setObs(ev2, "shymkent", "segments.foot_unknown", { coverage: { ...ev2.cities.shymkent.observations.find((o) => o.indicator_id === indicator("segments.foot_unknown")).coverage, complete: false } });
  const b = build(F, D, ev2, "shymkent", ALL(F));
  const id = fid(b, "shymkent", "segments.foot_unknown");
  const acc = validate(F, { sections: [{ type: "risks", fact_ids: [id] }], catalog_digest: digestOf(F, b) }, b, "shymkent");
  const ru = renderText(F, acc, b, "ru"), kk = renderText(F, acc, b, "kk");
  const line = ru.split("\n").find((l) => l.startsWith("- ")) || "";
  return { pass: /неполный охват/.test(line) && /толық емес қамту/.test(kk), observed: line };
});

(async () => {
  let app;
  try { app = await load(); } catch (e) { console.error("LOAD ERROR:", e.message); process.exit(2); }
  const target = APP_ROOT ? { app_root: path.resolve(APP_ROOT) } : { url: URL_BASE };
  const results = [];
  for (const t of TESTS) {
    let r;
    try { r = t.fn(app); } catch (e) { r = { pass: false, observed: "исключение теста: " + e.message }; }
    results.push({ id: t.id, title: t.title, pass: !!r.pass, observed: r.observed, ...(r.scenario_same !== undefined ? { scenario_same: r.scenario_same } : {}) });
    console.log(`${r.pass ? "PASS" : "FAIL"} ${t.id} — ${t.title}${r.pass ? "" : "\n     observed: " + JSON.stringify(r.observed)}`);
  }
  const failed = results.filter((r) => !r.pass).length;
  console.log(failed ? `${failed} FAILED of ${results.length}` : `all ${results.length} passed`);
  if (JSON_OUT) fs.writeFileSync(JSON_OUT, JSON.stringify({ target, node: process.version, results }, null, 1) + "\n");
  process.exit(failed ? 1 : 0);
})();
