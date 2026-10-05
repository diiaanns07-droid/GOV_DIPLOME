// K02 round 5 REVIEW: регрессия JS-объяснений web/facts.js сборки city-evidence.
// Независимые случаи (не сравнение текста со старым Python K02).
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
  const mod = { exports: {} }, fctx = { module: mod, exports: mod.exports, globalThis: {}, console };
  vm.createContext(fctx);
  vm.runInContext(await source("facts.js"), fctx, { filename: "facts.js" });
  return { F: shim(mod.exports), D: ctx.CITY_EVIDENCE, EV: ctx.CITY_OBS };
}

// ADAPTER (BUILD r6): the test targets the facts.js API of BUILD 0bf27de/round-4 names. The v1.2 build has:
//   * indicator ids  overture_place_records.<g>.conf_ge_0_0, segments_foot_access.unknown (round 4: places.<g>, segments.foot_unknown);
//   * fact ids with city "kz.<city>" (round 4: "<city>");
//   * StubSelector.select(view, digest) and validatePlan(plan, built) / render(plan, built, lang).
// The shim only translates names and call shapes; validation logic and assertions are the build's and the test's own.
const IND = { "places.school": "overture_place_records.school.conf_ge_0_0", "segments.foot_unknown": "segments_foot_access.unknown" };
function shim(F) {
  const kz = (id) => (typeof id === "string" && /^(shymkent|astana)\//.test(id) ? "kz." + id : id);
  const built = new WeakMap();
  const wrapBuild = (b) => { built.set(b.catalog, b); return b; };
  return { ...F,
    buildCatalog: (...a) => wrapBuild(F.buildCatalog(...a)),
    StubSelector: { name: F.StubSelector.name, select: (view, opts) => F.StubSelector.select(view, opts && typeof opts === "object" ? opts.digest : opts) },
    validatePlan: (plan, catalog, city, scenario) => {
      const b = built.get(catalog) || { catalog, city: "kz." + city, scenario, digest: F.catalogDigest(catalog) };
      const p = { ...plan, sections: (plan.sections || []).map((s) => ({ ...s, fact_ids: (s.fact_ids || []).map(kz) })) };
      return F.validatePlan(p, b);
    },
    render: (plan, catalog, scenario, lang) => F.render(plan, built.get(catalog) || { catalog, scenario }, lang),
  };
}

const clone = (x) => JSON.parse(JSON.stringify(x));
const ALL = (F) => new Set(F.GROUP_ORDER);
function attempt(fn) {
  try { return { status: "accepted", value: fn() }; }
  catch (e) { return { status: e && e.code ? e.code : "error", error: e && (e.constructor && e.constructor.name), message: String(e && e.message).slice(0, 160) }; }
}
function setObs(EV, city, indicator, patch) {
  indicator = IND[indicator] || indicator;  // ADAPTER: v1.2 indicator id
  const o = EV.cities[city].observations.find((x) => x.indicator_id === indicator);
  if (!o) throw new Error(`нет наблюдения ${city}/${indicator}`);
  Object.assign(o, patch);
  return o;
}
// План как сделал бы селектор по старому каталогу; если API digest есть — с digest старого каталога.
function planFor(F, built) {
  const view = F.catalogView(built.catalog);
  const digest = typeof F.catalogDigest === "function" ? F.catalogDigest(built.catalog) : undefined;
  return F.StubSelector.select(view, { digest });
}

const TESTS = [];
const test = (id, title, fn) => TESTS.push({ id, title, fn });

// T1–T3: тот же город и срез, старый план, изменённый каталог.
for (const [id, title, mutate] of [
  ["T1_value_change", "изменение значения при том же городе и срезе: старый план отклоняется",
    (EV) => setObs(EV, "shymkent", "places.school", { value: 16 })],
  ["T2_unit_change", "изменение единицы при том же городе и срезе: старый план отклоняется",
    // ADAPTER: "km" is not a unit of the v1.2 build — buildCatalog refuses it outright ("unknown unit", stricter than
    // stale_catalog; recorded separately). A valid unit change ("segments" -> "records") tests the digest invariant.
    (EV) => setObs(EV, "shymkent", "segments.foot_unknown", { unit: "records" })],
  ["T3_coverage_change", "изменение охвата при том же городе и срезе: старый план отклоняется",
    (EV) => setObs(EV, "shymkent", "segments.foot_unknown", { coverage: { ...EV.cities.shymkent.observations.find((o) => o.indicator_id === IND["segments.foot_unknown"]).coverage, complete: false } })],
]) {
  test(id, title, ({ F, D, EV }) => {
    const before = F.buildCatalog(D, EV, "shymkent", ALL(F));
    const plan = planFor(F, before);
    const ev2 = clone(EV); mutate(ev2);
    const after = F.buildCatalog(D, ev2, "shymkent", ALL(F));
    const r = attempt(() => F.validatePlan(plan, after.catalog, "shymkent", after.scenario));
    return { pass: r.status === "stale_catalog", observed: r.status, scenario_same: before.scenario === after.scenario };
  });
}

test("T4_digest_distinguishes", "старый срез и изменённый каталог различимы (catalogDigest), одинаковые — равны", ({ F, D, EV }) => {
  if (typeof F.catalogDigest !== "function") return { pass: false, observed: "API отсутствует: catalogDigest" };
  const a = F.buildCatalog(D, EV, "shymkent", ALL(F)), a2 = F.buildCatalog(D, clone(EV), "shymkent", ALL(F));
  const ev2 = clone(EV); setObs(ev2, "shymkent", "places.school", { value: 16 });
  const b = F.buildCatalog(D, ev2, "shymkent", ALL(F));
  const da = F.catalogDigest(a.catalog), db = F.catalogDigest(b.catalog);
  return { pass: da === F.catalogDigest(a2.catalog) && da !== db, observed: { same_scenario: a.scenario === b.scenario, da, db } };
});

test("T5_duplicate_across_sections", "повтор одного ID в двух секциях отклоняется (duplicate_id)", ({ F, D, EV }) => {
  const b = F.buildCatalog(D, EV, "shymkent", ALL(F));
  const fid = `shymkent/${b.scenario}/places.school`;
  const plan = { sections: [{ type: "summary", fact_ids: [fid] }, { type: "risks", fact_ids: [fid] }] };
  if (typeof F.catalogDigest === "function") plan.catalog_digest = F.catalogDigest(b.catalog);
  const r = attempt(() => F.validatePlan(plan, b.catalog, "shymkent", b.scenario));
  return { pass: r.status === "duplicate_id", observed: r.status };
});

test("T6_null_vs_zero", "null: только в data_gaps и «нет данных»; настоящий 0 печатается как 0", ({ F, D, EV }) => {
  const b = F.buildCatalog(D, EV, "shymkent", ALL(F));
  const nul = `kz.shymkent/${b.scenario}/capacity.school_places`, zero = `kz.shymkent/${b.scenario}/district_status.ambiguous`;  // ADAPTER: kz. prefix
  const dg = typeof F.catalogDigest === "function" ? { catalog_digest: F.catalogDigest(b.catalog) } : {};
  const outside = attempt(() => F.validatePlan({ sections: [{ type: "summary", fact_ids: [nul] }], ...dg }, b.catalog, "shymkent", b.scenario));
  const gaps = F.validatePlan({ sections: [{ type: "data_gaps", fact_ids: [nul] }, { type: "risks", fact_ids: [zero] }], ...dg }, b.catalog, "shymkent", b.scenario);
  const ru = F.render(gaps, b.catalog, b.scenario, "ru").text, kk = F.render(gaps, b.catalog, b.scenario, "kk").text;
  const ok = outside.status === "null_as_fact" && /нет данных/.test(ru) && /дерек жоқ/.test(kk)
    && /неоднозначным районом: 0( \S+)? \(/.test(ru)  /* ADAPTER: unit after the number (K02 r4 fixed) */ && b.catalog.get(nul).value === null && b.catalog.get(zero).value === 0;
  return { pass: ok, observed: { outside: outside.status, ru_lines: ru.split("\n").filter((l) => l.startsWith("- ")) } };
});

test("T7_city_substitution_observations", "наблюдения другого города под ключом города отклоняются при buildCatalog", ({ F, D, EV }) => {
  const ev2 = clone(EV); ev2.cities.shymkent.observations = clone(EV.cities.astana.observations);
  const r = attempt(() => F.buildCatalog(D, ev2, "shymkent", ALL(F)));
  return { pass: r.status !== "accepted", observed: r.status === "accepted" ? "принято: числа kz.astana под shymkent" : r.status };
});

test("T8_city_switch_stale_plan", "план по Астане против каталога Шымкента отклоняется (foreign_city или stale_catalog)", ({ F, D, EV }) => {
  const a = F.buildCatalog(D, EV, "astana", ALL(F)), s = F.buildCatalog(D, EV, "shymkent", ALL(F));
  const r = attempt(() => F.validatePlan(planFor(F, a), s.catalog, "shymkent", s.scenario));
  return { pass: r.status === "foreign_city" || r.status === "stale_catalog", observed: r.status };
});

for (const [id, bad] of [["T9_nonfinite_nan", NaN], ["T9_nonfinite_inf", Infinity]]) {
  test(id, `неконечное число (${bad}) отклоняется при buildCatalog, а не падает в render`, ({ F, D, EV }) => {
    const ev2 = clone(EV); // clone теряет NaN/Infinity (→ null), поэтому подставляем после клонирования
    setObs(ev2, "shymkent", "places.school", { value: bad });
    const r = attempt(() => F.buildCatalog(D, ev2, "shymkent", ALL(F)));
    let renderStatus = null;
    if (r.status === "accepted") {
      const plan = planFor(F, r.value);
      const v = attempt(() => F.validatePlan(plan, r.value.catalog, "shymkent", r.value.scenario));
      renderStatus = v.status === "accepted" ? attempt(() => F.render(v.value, r.value.catalog, r.value.scenario, "ru")).status : v.status;
    }
    return { pass: r.status !== "accepted", observed: r.status === "accepted" ? `buildCatalog принял; render: ${renderStatus}` : r.status };
  });
}

test("T10_incomplete_coverage_visible", "значения при coverage.complete=false помечены в тексте объяснения", ({ F, D, EV }) => {
  // ADAPTER: v1.2 square counts have coverage.complete=true; make one value incomplete to test the marking itself.
  const ev2 = clone(EV); setObs(ev2, "shymkent", "places.school", { coverage: { ...ev2.cities.shymkent.observations.find((o) => o.indicator_id === IND["places.school"]).coverage, complete: false } });
  const r = F.explain(D, ev2, "shymkent", ALL(F), "ru");
  const line = r.text.split("\n").find((l) => l.includes("Записи") || l.includes("записей в квадрате")) || "";
  return { pass: /неполн/.test(r.text), observed: line };
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
