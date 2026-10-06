// K09 r9 — регрессия для предлагаемого патча BUILD (patches/build_33cc635_k09.patch). Без DOM.
//   node patches/test_build_r9_patch.cjs <copy>/prototypes/city-evidence/web
// На исходном 33cc635 ожидаются FAIL (находки воспроизводятся); после патча — все PASS.
// Находки — независимый обзор resilience.js @ 33cc635 (results/stage3/build_review/findings.json), воспроизведены K09.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const W = process.argv[2];
const c0 = {}; vm.createContext(c0); c0.window = c0;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), c0, { filename: "data.js" });
const F = require(path.resolve(W, "facts.js")), PL = require(path.resolve(W, "plan.js")), RS = require(path.resolve(W, "resilience.js"));
const D = c0.CITY_EVIDENCE, sh = PL.makeContext(D, "shymkent", F), ctxFor = (c) => PL.makeContext(D, c, F);
let fails = 0;
const check = (name, ok, detail) => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : " — " + String(detail).slice(0, 200))); };
const code = (fn) => { try { const r = fn(); return r && r.status ? "status:" + r.status : "accepted"; } catch (e) { return e.code || "THROW:" + e.constructor.name; } };

function env(nCand, nCases) {
  const [w, s, e, n] = sh.bbox;
  const src = sh.places.filter((p) => p.group === "school").map((p) => p.id);
  const pt = (k, t) => ({ lon: w + (e - w) * ((k * 37 + t * 11) % 97 + 1) / 99, lat: s + (n - s) * ((k * 53 + t * 7) % 89 + 1) / 91 });
  return { schema_version: RS.SCHEMA, cases: Array.from({ length: nCases }, (_, k) => ({ id: "k" + k, label: "случай " + k, disabled_source_ids: [src[k % src.length]] })),
    plan: { schema_version: PL.SCHEMA, city_id: "shymkent", source_snapshot: sh.source_snapshot, category: "school",
      control_points: Array.from({ length: 6 }, (_, k) => ({ id: "P" + k, ...pt(k, 1), weight: 1 + k })),
      candidates: Array.from({ length: nCand }, (_, k) => ({ id: "C" + k, ...pt(k, 2), category: "school", kind: "hypothetical", cost: 1 + k })),
      budget: 1000, max_selected: 5, coverage_radius_m: 500, required_ids: [], excluded_ids: [], selected_ids: [] } };
}
const lying = (arr, honestAfter) => { let reads = 0; return new Proxy(arr, { get(t, p, r) { if (p === "length") return reads++ < honestAfter ? 5 : t.length; return Reflect.get(t, p, r); } }); };

// F1: пределы проверяются по чистой копии (getter/Proxy не обходят 12 кандидатов, 16 в v2, 1..7 случаев, ≥1 исключение)
{ const e = env(18, 2); e.plan.candidates = lying(e.plan.candidates, 2);
  const got = code(() => RS.optimizeResilience(sh, e, { F }));
  check("F1a Proxy-кандидаты (18) → too_many_candidates, не optimal", got === "too_many_candidates", got); }
{ const e = env(16, 2); const all = e.plan.candidates, few = all.slice(0, 5); let n = 0;
  Object.defineProperty(e.plan, "candidates", { enumerable: true, get() { return n++ < 2 ? few : all; } });
  const got = code(() => RS.optimizeResilience(sh, e, { F })); check("F1d getter кандидатов (16) → too_many_candidates", got === "too_many_candidates", got); }
{ const e = env(4, 1); const many = Array.from({ length: 30 }, (_, k) => ({ ...e.cases[0], id: "m" + k }));
  let reads = 0; e.cases = new Proxy(many, { get(t, p, r) { if (p === "length") return reads++ < 2 ? 1 : t.length; return Reflect.get(t, p, r); } });
  const got = code(() => RS.optimizeResilience(sh, e, { F })); check("F1b Proxy-случаи (30) → bad_cases", got === "bad_cases", got); }
{ const e = env(4, 1); let reads = 0;
  e.cases[0].disabled_source_ids = new Proxy([], { get(t, p, r) { if (p === "length") return reads++ < 2 ? 1 : t.length; return Reflect.get(t, p, r); } });
  check("F1c пустое исключение через Proxy → bad_exclusions", code(() => RS.validateResilience(e, sh)) === "bad_exclusions"); }
{ const sc = env(17, 1).plan; sc.candidates = lying(sc.candidates, 1);
  check("F1e plan.js v2: Proxy-кандидаты (17) → too_many_candidates", code(() => PL.validatePlanScenario(sc, sh)) === "too_many_candidates"); }
// F2: U+FFFD в метке — свой экспорт должен импортироваться обратно, либо метка отклоняется сразу
{ const e = env(4, 1); e.cases[0].label = "a�b";
  const v = code(() => RS.validateResilience(e, sh));
  const rt = v === "accepted" ? code(() => RS.importResilience(RS.exportResilience(sh, e), ctxFor)) : "rejected-at-validate";
  check("F2 метка с U+FFFD: отказ при проверке или успешный круг экспорт→импорт", v === "bad_label" || rt === "accepted", `validate=${v} roundtrip=${rt}`); }
// F4: selectedIds — типизированная ошибка
for (const [n, s] of [["undefined", undefined], ["null", null], ["число", 5], ["объект", {}], ["строка", "C0"]])
  check(`F4 evaluateResilience(selectedIds=${n}) → typed bad_shape`, code(() => RS.evaluateResilience(sh, env(4, 1), s)) === "bad_shape");
// F5: невидимые/управляющие метки
for (const [n, l] of [["только ZWSP", "​"], ["RLO", "a‮b"], ["одиночный суррогат", "a\ud800b"]]) {
  const e = env(4, 1); e.cases[0].label = l; check(`F5 метка «${n}» → bad_label`, code(() => RS.validateResilience(e, sh)) === "bad_label"); }
// не сломано: обычные метки и входы
{ const e = env(4, 1); e.cases[0].label = "Қала 👩‍👩‍👧 мектебі"; check("казахская метка с эмодзи-ZWJ принимается", code(() => RS.validateResilience(e, sh)) === "accepted"); }
check("12 кандидатов, 7 случаев — optimal", code(() => RS.optimizeResilience(sh, env(12, 7), { F })) === "status:optimal");
check("v2 по-прежнему решает 16 кандидатов", PL.optimizePlans(sh, PL.validatePlanScenario(env(16, 1).plan, sh), { F }).status === "optimal");
console.log(fails ? `${fails} FAIL` : "all K09 r9 patch checks passed");
process.exit(fails ? 1 : 0);
