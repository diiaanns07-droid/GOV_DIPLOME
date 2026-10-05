// K12 round 8, stage 2: import atomicity, no payload execution, source_snapshot mismatch on isolated data copies,
// cancellation and late results — for a city-plan-v2 implementation behind an adapter (see HANDOFF.md).
// Plus v1 cross-checks against BUILD web/whatif.js (v1 keeps working; v1/v2 kept apart).
// Node >= 18, headless. All inputs are SYNTHETIC fixtures; nothing is fetched; payload strings are inert data.
//
//   node stage2_runtime.cjs --app-root <prototypes/city-evidence copy> [--adapter adapters/reference_v2_adapter.cjs] [--out r.json]
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const HERE = __dirname;
const APP = path.resolve(opt("--app-root", ""));
const ADAPTER = path.resolve(opt("--adapter", path.join(HERE, "adapters", "reference_v2_adapter.cjs")));
const OUT = opt("--out");
if (!fs.existsSync(path.join(APP, "web", "data.js"))) { console.error("usage: node stage2_runtime.cjs --app-root <dir>"); process.exit(2); }

// ---------------------------------------------------------------- guards: network, string timers
const NET = [], STRING_TIMERS = [];
const trap = (what) => function () { NET.push(what); throw new Error(`K12 network guard: ${what}`); };
for (const [mod, fns] of [["http", ["request", "get"]], ["https", ["request", "get"]], ["net", ["connect", "createConnection"]], ["tls", ["connect"]]]) {
  const m = require(mod); for (const f of fns) m[f] = trap(`${mod}.${f}`);
}
globalThis.fetch = trap("fetch");
for (const t of ["setTimeout", "setInterval"]) {
  const orig = globalThis[t];
  globalThis[t] = function (fn, ...rest) { if (typeof fn === "string") { STRING_TIMERS.push(t); return 0; } return orig(fn, ...rest); };
}

// ---------------------------------------------------------------- app contexts (original + isolated modified copies)
function loadContext(dataText) {
  const ctx = {};
  vm.createContext(ctx);
  ctx.window = ctx;
  ctx.fetch = trap("window.fetch");
  ctx.XMLHttpRequest = function () { NET.push("XMLHttpRequest"); throw new Error("K12 network guard"); };
  vm.runInContext(dataText, ctx, { filename: "data.js" });
  vm.runInContext(fs.readFileSync(path.join(APP, "web", "evidence.js"), "utf8"), ctx, { filename: "evidence.js" });
  return ctx;
}
const WEB = path.join(APP, "web");
const requireWeb = (n) => require(path.join(WEB, n));
const DATA_TEXT = fs.readFileSync(path.join(WEB, "data.js"), "utf8");
const CTX = loadContext(DATA_TEXT);
const factory = require(ADAPTER);
const A = factory({ appRoot: APP, D: CTX.CITY_EVIDENCE, EV: CTX.CITY_OBS, ctx: CTX, requireWeb });

// isolated data copy: parse the JS payload, change it, serialise back — the original file is never touched
function modifiedData(mutate) {
  const start = DATA_TEXT.indexOf("{"), end = DATA_TEXT.trimEnd().lastIndexOf(";");
  const D = JSON.parse(DATA_TEXT.slice(start, end));
  mutate(D);
  return DATA_TEXT.slice(0, start) + JSON.stringify(D) + DATA_TEXT.slice(end);
}

// ---------------------------------------------------------------- fixtures
const IDX = JSON.parse(fs.readFileSync(path.join(HERE, "FIXTURES_V2_INDEX.json"), "utf8"));
const byId = Object.fromEntries(IDX.fixtures.map((f) => [f.id, f]));
const OTHER = { shymkent: "astana", astana: "shymkent" };
const rawFx = (id) => fs.readFileSync(path.join(HERE, byId[id].file), "utf8");
const sub = (text, adapter, city = "shymkent") => text.split('"__SNAPSHOT__"').join(JSON.stringify(adapter.snapshot(city)))
  .split('"__SNAPSHOT_OTHER_CITY__"').join(JSON.stringify(adapter.snapshot(OTHER[city])));
const V01 = () => sub(rawFx("V01"), A);
const V01obj = () => JSON.parse(V01());
const view = (s) => JSON.stringify(s);

// ---------------------------------------------------------------- reporting
const results = [];
function check(group, id, title, ok, detail, advisory = false) {
  const status = ok === null ? "SKIP" : ok ? "PASS" : advisory ? "ADVISORY" : "FAIL";
  results.push({ group, id, title, status, detail: detail === undefined ? null : detail });
  console.log(`${status.padEnd(4)} ${id.padEnd(5)} ${title}${detail !== undefined && status !== "PASS" ? " — " + JSON.stringify(detail).slice(0, 220) : ""}`);
}
const protoSig = () => [Object, Array, Function, String, Number].map((C) => Object.getOwnPropertyNames(C.prototype).sort().join(",")).join("|");
const globalsSig = () => Object.keys(CTX).sort().join(",") + "|" + Object.keys(globalThis).sort().join(",");

(async () => {
  // ============================================================ A. import atomicity
  const s0 = A.importScenario(V01(), A.initialState());
  check("A", "A0", "V01 принят (стартовое состояние)", !!(s0 && s0.ok), s0 && s0.code);
  const S1 = s0.state, S1view = view(S1);
  const optBefore = A.optimize ? view(A.optimize(S1)) : null;

  // A1: every negative fixture, chained: each failed import starts from the state left by the previous one
  let st = S1, chainOk = true, failedIds = [];
  for (const f of IDX.fixtures.filter((x) => x.expect === "reject" && !x.recipe)) {
    const r = A.importScenario(sub(fs.readFileSync(path.join(HERE, f.file), "utf8"), A, f.city), st);
    if (r.ok || view(r.state) !== S1view) { chainOk = false; failedIds.push(f.id); }
    st = r.state;
  }
  check("A", "A1", "цепочка из всех негативных фикстур не меняет состояние", chainOk && view(st) === S1view, failedIds);
  check("A", "A2", "оптимизация после цепочки отказов та же", optBefore === null ? null : view(A.optimize(st)) === optBefore);

  // A3: the defect is only in the LAST element — catches importers that apply items one by one
  const lastDefects = {
    last_candidate_cost_0: (o) => { o.candidates[o.candidates.length - 1].cost = 0; },
    last_point_outside_bbox: (o) => { o.control_points[o.control_points.length - 1].lat = 42.5; },
    last_selected_unknown: (o) => { o.selected_ids = ["c1", "c2", "nope"]; },
    last_excluded_conflicts: (o) => { o.required_ids = ["c3"]; o.excluded_ids = ["c1", "c3"]; },
    trailing_garbage: null,
  };
  for (const [name, mut] of Object.entries(lastDefects)) {
    let text;
    if (mut) { const o = V01obj(); mut(o); text = JSON.stringify(o, null, 1); } else text = V01() + "\n{\"x\":1}";
    const before = view(S1), passed = JSON.parse(before);
    const r = A.importScenario(text, passed);
    check("A", "A3", `дефект только в последнем элементе (${name}): отказ, состояние прежнее`,
      !r.ok && view(r.state) === before && view(passed) === before, r.code);
  }

  // A4: non-text and hostile-length inputs are refused, never thrown
  const odd = { null: null, number: 42, object: { schema_version: "city-plan-v2" }, array: [], buffer: Buffer.from("{}"),
    braces_300k: "{".repeat(300000), quotes_200k: '"'.repeat(200000), empty: "" };
  for (const [name, input] of Object.entries(odd)) {
    let r, threw = null;
    try { r = A.importScenario(input, S1); } catch (e) { threw = e.message; }
    check("A", "A4", `вход ${name}: отказ без исключения`, !threw && r && !r.ok && view(r.state) === S1view, threw || (r && r.code));
  }

  // ============================================================ B. payloads are never executed
  const sources = typeof A.sources === "function" ? A.sources() : [];
  if (!sources.length) check("B", "B1", "статический просмотр модуля", null, "adapter.sources() не задан");
  for (const src of sources) {
    const code = fs.readFileSync(src, "utf8").replace(/\/\/.*$/gm, "");
    const bad = [/\beval\s*\(/, /new\s+Function\s*\(/, /\bFunction\s*\(\s*["'`]/, /\.innerHTML\s*=/, /document\.write/, /\bimport\s*\(/,
                 /set(Timeout|Interval)\s*\(\s*["'`]/].filter((re) => re.test(code)).map(String);
    check("B", "B1", `в ${path.basename(src)} нет eval/new Function/innerHTML/import()/строковых таймеров`, bad.length === 0, bad);
  }
  const payloads = [
    "${globalThis.__K12_PWNED__=1}", "`${process.exit(9)}`", "javascript:globalThis.__K12_PWNED__=1", "<img src=x onerror=\"globalThis.__K12_PWNED__=1\">",
    "constructor.prototype.k12_polluted=1", "__proto__", "require('child_process').execSync('touch /tmp/k12_pwned')",
  ];
  const before = { proto: protoSig(), globals: globalsSig(), net: NET.length, timers: STRING_TIMERS.length };
  const o = V01obj();
  o.derived_results = { notes: payloads, nested: Object.fromEntries(payloads.map((p, i) => [`k${i}`, p])) };
  const r1 = A.importScenario(JSON.stringify(o), A.initialState());
  check("B", "B2", "payload-строки в derived_results: принят как данные", !!(r1 && r1.ok), r1 && r1.code);
  if (r1 && r1.ok && A.optimize) A.optimize(r1.state);
  const o2 = V01obj();
  o2.control_points[0].id = payloads[0];
  const r2 = A.importScenario(JSON.stringify(o2), A.initialState());
  check("B", "B3", "payload в ID точки отклонён (bad_id)", !!(r2 && !r2.ok), r2 && r2.code);
  await new Promise((res) => setImmediate(res));
  check("B", "B4", "после импорта/оптимизации: прототипы, глобалы, сеть, строковые таймеры не изменились",
    protoSig() === before.proto && globalsSig() === before.globals && NET.length === before.net && STRING_TIMERS.length === before.timers &&
    globalThis.__K12_PWNED__ === undefined && CTX.__K12_PWNED__ === undefined && ({}).k12_polluted === undefined && !fs.existsSync("/tmp/k12_pwned"),
    { net: NET.length - before.net, timers: STRING_TIMERS.length - before.timers });
  check("B", "B5", "в результатах нет payload-строк (derived_results не попал в вывод)",
    r1 && r1.ok ? !payloads.some((p) => JSON.stringify(A.evaluate ? A.evaluate(r1.state) : {}).includes(p) ||
      JSON.stringify(A.optimize ? A.optimize(r1.state) : {}).includes(p)) : null);

  // ============================================================ C. source_snapshot mismatch on isolated copies
  const variants = {
    moved_record: (D) => { const p = D.cities.shymkent.places.find((x) => x.group === "school"); p.lon = +(p.lon + 0.0001).toFixed(6); },
    other_release: (D) => { D.cities.shymkent.release = "2026-08-20.0"; },
    removed_record: (D) => { const i = D.cities.shymkent.places.findIndex((x) => x.group === "school"); D.cities.shymkent.places.splice(i, 1); },
    other_file_hash: (D) => { D.cities.shymkent.files.places_social.sha256 = "0".repeat(64); },
  };
  for (const [name, mut] of Object.entries(variants)) {
    const ctx2 = loadContext(modifiedData(mut));
    const A2 = factory({ appRoot: APP, D: ctx2.CITY_EVIDENCE, EV: ctx2.CITY_OBS, ctx: ctx2, requireWeb });
    const changed = A2.snapshot("shymkent") !== A.snapshot("shymkent");
    const old = A2.importScenario(V01(), A2.initialState());           // scenario made on the original slice
    const fresh = A2.importScenario(sub(rawFx("V01"), A2), A2.initialState());
    const astanaSame = A2.snapshot("astana") === A.snapshot("astana");
    check("C", "C1", `изолированная копия (${name}): snapshot меняется, старый сценарий отклонён, новый принят, Астана не затронута`,
      changed && !old.ok && fresh.ok && astanaSame, { changed, old: old.code, fresh: fresh.ok, astanaSame });
  }
  check("C", "C2", "исходный data.js не изменён тестом", fs.readFileSync(path.join(WEB, "data.js"), "utf8") === DATA_TEXT);

  // ============================================================ D. cancellation and late results
  if (typeof A.optimizeAsync !== "function" || typeof A.gate !== "function") {
    check("D", "D0", "отмена и поздние результаты", null, "adapter.optimizeAsync()/gate() не заданы");
  } else {
    const big = A.importScenario(sub(rawFx("V04"), A), A.initialState()).state;   // 16 candidates, 65536 subsets
    // D1: cancel mid-run
    const ac = new AbortController();
    let yields = 0;
    const r = await A.optimizeAsync(big, { requestId: "x", signal: ac.signal, chunk: 1024,
      yieldFn: () => new Promise((res) => { if (++yields === 3) ac.abort(); setImmediate(res); }) });
    check("D", "D1", "отмена посреди перебора: status≠optimal, неполный, целей нет",
      r.status === "cancelled" && r.complete === false && r.evaluated < 65536 && !r.objectives.mean, { status: r.status, evaluated: r.evaluated });
    const g = A.gate();
    g.begin(r.problem_digest);
    check("D", "D2", "отменённый результат не применяется", !g.accept({ ...r, request_id: "x" }).accepted);

    // D3: late result for an older problem (budget changed meanwhile)
    const gate = A.gate();
    const pa = big;
    const pbText = JSON.stringify({ ...JSON.parse(sub(rawFx("V04"), A)), budget: 5000 });
    const pb = A.importScenario(pbText, A.initialState()).state;
    const idA = gate.begin(A.problemDigest(pa));
    const runA = A.optimizeAsync(pa, { requestId: idA, chunk: 2048, yieldFn: () => new Promise((res) => setImmediate(res)) });
    const idB = gate.begin(A.problemDigest(pb));                            // user changed the budget before A finished
    const resA = await runA;
    const resB = await A.optimizeAsync(pb, { requestId: idB, chunk: 2048, yieldFn: () => new Promise((res) => setImmediate(res)) });
    const accA = gate.accept(resA), accB = gate.accept(resB);
    check("D", "D3", "поздний результат старой задачи отклонён, новый принят", !accA.accepted && accB.accepted, { A: accA.reason, B: accB.reason });
    // D4: same problem, two requests: only the latest one
    const g2 = A.gate();
    const d = A.problemDigest(pa);
    const i1 = g2.begin(d), i2 = g2.begin(d);
    const rr = A.optimize(pa);
    check("D", "D4", "тот же problem_digest, повторный запрос: принят только последний",
      !g2.accept({ ...rr, request_id: i1 }).accepted && g2.accept({ ...rr, request_id: i2 }).accepted);
    // D5: city/category switch resets
    const g3 = A.gate();
    const i3 = g3.begin(d);
    g3.reset();
    check("D", "D5", "после смены города/категории (reset) старый ответ не применяется", !g3.accept({ ...rr, request_id: i3 }).accepted);
    // D6: tampered digest
    const g4 = A.gate();
    const i4 = g4.begin(d);
    check("D", "D6", "результат с чужим problem_digest отклонён", !g4.accept({ ...rr, request_id: i4, problem_digest: "0".repeat(64) }).accepted);
    // D7: event loop stays responsive during the async search
    let ticks = 0, maxChunkMs = 0, last = process.hrtime.bigint();
    const timer = setInterval(() => { ticks++; }, 1);
    const t0 = Date.now();
    const full = await A.optimizeAsync(big, { requestId: "t", chunk: 1024, yieldFn: () => new Promise((res) => {
      const now = process.hrtime.bigint(); maxChunkMs = Math.max(maxChunkMs, Number(now - last) / 1e6); setTimeout(() => { last = process.hrtime.bigint(); res(); }, 0); }) });
    clearInterval(timer);
    check("D", "D7", "async-поиск не блокирует цикл событий: таймер срабатывал, чанк < 50 мс, итог optimal и равен синхронному",
      ticks > 0 && maxChunkMs < 50 && full.status === "optimal" && view(full.objectives) === view(A.optimize(big).objectives),
      { ticks, maxChunkMs: +maxChunkMs.toFixed(2), total_ms: Date.now() - t0 });
  }

  // ============================================================ E. v1 keeps working; v1/v2 apart (BUILD web/whatif.js)
  let W = null, F = null;
  try { W = requireWeb("whatif.js"); F = requireWeb("facts.js"); } catch (e) { W = null; }
  if (!W) check("E", "E0", "v1 whatif.js в BUILD", null, "web/whatif.js отсутствует");
  else {
    const D = CTX.CITY_EVIDENCE;
    const v1 = { schema_version: "city-whatif-v1", city_id: "shymkent", source_snapshot: W.sourceSnapshot(D, "shymkent", F), category: "school",
      control_points: [{ id: "cp1", lon: 69.6, lat: 42.31 }], proposed_object: { id: "p1", lon: 69.605, lat: 42.315, category: "school", kind: "hypothetical" } };
    const poisoned = { ...v1, derived_results: { rows: [{ id: "cp1", before_m: 1, after_m: 0, delta_m: 999999999 }], note: payloads[3] } };
    let ok1 = false, rows = null;
    try { const r = W.importScenario(JSON.stringify(poisoned), D, F); ok1 = true; rows = r.result.rows; } catch (e) { ok1 = e.code; }
    check("E", "E1", "BUILD v1: подделанные derived_results приняты как данные и пересчитаны (999999999 нет в выводе)",
      ok1 === true && !JSON.stringify(rows).includes("999999999"), ok1);
    let code = null;
    try { W.importScenario(V01(), D, F); code = "accepted"; } catch (e) { code = e.code; }
    check("E", "E2", "BUILD v1 отклоняет сценарий city-plan-v2 (режимы раздельны)", code !== "accepted", code);
    check("E", "E2a", "BUILD v1: код отказа bad_version (понятнее, чем unknown_field)", code === "bad_version", code, true);
    const r3 = A.importScenario(JSON.stringify(v1), A.initialState());
    check("E", "E3", "v2-импорт отклоняет сценарий city-whatif-v1", !r3.ok, r3.code);
    check("E", "E3a", "v2-импорт: код отказа bad_version", r3.code === "bad_version", r3.code, true);
  }

  const summary = { adapter: path.basename(ADAPTER), app_root: path.basename(APP), total: results.length,
    pass: results.filter((x) => x.status === "PASS").length, fail: results.filter((x) => x.status === "FAIL").map((x) => `${x.id}:${x.title.slice(0, 40)}`),
    skip: results.filter((x) => x.status === "SKIP").map((x) => x.id),
    advisory: results.filter((x) => x.status === "ADVISORY").map((x) => `${x.id}:${JSON.stringify(x.detail)}`), network_attempts: NET.length, string_timers: STRING_TIMERS.length };
  console.log(JSON.stringify(summary));
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, results }, null, 1) + "\n");
  process.exit(summary.fail.length ? 1 : 0);
})();
