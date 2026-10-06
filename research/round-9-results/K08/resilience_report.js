/* K08 R9: узкий адаптер отчёта устойчивости city-resilience-v1 (research/round-9/CORE_SPEC.txt) поверх API BUILD web/plan.js.
 * НЕ второй движок: геометрия, ограничения, метрики и v2-оптимум берутся из plan.js (validatePlanScenario, precompute,
 * evaluatePlan(pre), feasibility, optimizePlans, problemDigest, scenarioDigest), строгий JSON — whatif.parseStrict.
 * Отчёт всегда пересчитывается из входа; envelope не содержит и не принимает производных полей.
 *
 * API (Node и браузер; зависимости передаются явно):
 *   validateResilience(text|object, deps) -> clean envelope | throws ResilienceError(code, detail)
 *   buildResilienceReport(envelope, deps)   -> report (JSON-совместимый, null вместо Infinity)
 *   renderResilienceHtml(report)            -> статический HTML (без скриптов/внешних ресурсов, CSP default-src 'none')
 *   deps = { PL, F, X, data, obs }  (plan.js, facts.js, whatif.js, window.CITY_EVIDENCE, window.CITY_OBS|null)
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-resilience-v1";
  const OBJECTIVE = "worst-lex-v1";
  const REPORT_SCHEMA = "k08-resilience-report/v1";
  const LIMITS = { user_cases: 7, candidates: 12, label: 120, subsets: 4096 };
  const ID_CHARS = /^[\p{L}\p{N}_.-]+$/u;  // то же правило, что ID_RE в web/plan.js d865dd4
  const isId = (v) => typeof v === "string" && v.normalize("NFC") === v && [...v].length >= 1 && [...v].length <= 64 && ID_CHARS.test(v);
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  class ResilienceError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
  const fail = (code, d) => { throw new ResilienceError(code, d); };
  const shape = (o, what, keys) => {
    if (!o || typeof o !== "object" || Array.isArray(o)) fail("bad_shape", `${what}: ожидается объект`);
    const ks = Object.keys(o).sort().join(","), want = keys.slice().sort().join(",");
    if (ks !== want) fail(ks.split(",").some((k) => !keys.includes(k)) ? "unknown_field" : "missing_field", `${what}: поля {${ks.slice(0, 120)}} ≠ {${want}}`);
  };

  // ---------- validation: full envelope + plan BEFORE any computation ----------
  function validateResilience(input, deps) {
    const { PL, F, X, data } = deps;
    let obj = input;
    if (typeof input === "string") {
      try { obj = X.parseStrict(input); } catch (e) { fail(e.code === "too_large" || e.code === "bad_encoding" ? e.code : "bad_json", e.detail || e.message); }
    }
    shape(obj, "envelope", ["schema_version", "plan", "cases"]);
    if (obj.schema_version !== SCHEMA) fail("bad_version", `версия ${String(obj.schema_version).slice(0, 40)} ≠ ${SCHEMA}`);
    const plan = obj.plan;
    if (plan && typeof plan === "object" && "derived_results" in plan) fail("derived_not_accepted", "в envelope r9 производные поля не принимаются");
    if (!plan || typeof plan !== "object" || (plan.city_id !== "shymkent" && plan.city_id !== "astana")) fail("bad_city", String(plan && plan.city_id).slice(0, 40));
    if (Array.isArray(plan.candidates) && plan.candidates.length > LIMITS.candidates)
      fail("too_many_candidates", `устойчивость: кандидатов не больше ${LIMITS.candidates}, получено ${plan.candidates.length}`);
    const ctx = PL.makeContext(data, plan.city_id, F);
    let sc;
    try { sc = PL.validatePlanScenario(plan, ctx); } catch (e) { fail("bad_plan:" + (e.code || "error"), e.detail || e.message); }
    const sourceIds = new Set(ctx.places.filter((p) => p.group === sc.category).map((p) => p.id));
    const candIds = new Set(sc.candidates.map((c) => c.id));
    if (!Array.isArray(obj.cases) || obj.cases.length < 1 || obj.cases.length > LIMITS.user_cases)
      fail("bad_cases", `пользовательских случаев 1..${LIMITS.user_cases}`);
    const seen = new Set();
    const cases = obj.cases.map((c, k) => {
      shape(c, `cases[${k}]`, ["id", "label", "disabled_source_ids"]);
      if (!isId(c.id)) fail("bad_id", `cases[${k}].id`);
      if (c.id === "base") fail("reserved_id", "id base зарезервирован");
      if (seen.has(c.id)) fail("duplicate_id", `cases: ${c.id}`);
      seen.add(c.id);
      if (typeof c.label !== "string" || !c.label.trim() || [...c.label].length > LIMITS.label || /\p{Cc}/u.test(c.label))
        fail("bad_label", `${c.id}: непустая строка ≤${LIMITS.label} символов без управляющих`);
      const ds = c.disabled_source_ids;
      if (!Array.isArray(ds) || ds.length < 1 || ds.length > sourceIds.size) fail("bad_exclusions", `${c.id}: от 1 до ${sourceIds.size} исходных записей`);
      const s2 = new Set();
      for (const id of ds) {
        if (typeof id !== "string") fail("bad_exclusions", `${c.id}: id строкой`);
        if (s2.has(id)) fail("duplicate_id", `${c.id}: ${id}`);
        if (candIds.has(id) && !sourceIds.has(id)) fail("candidate_not_source", `${c.id}: ${id} — кандидат, а не исходная запись`);
        if (!sourceIds.has(id)) fail("unknown_source", `${c.id}: исходной записи ${String(id).slice(0, 40)} нет в городе/категории`);
        s2.add(id);
      }
      return { id: c.id, label: c.label, disabled_source_ids: ds.slice().sort(cmpStr) };
    });
    return { schema_version: SCHEMA, plan: sc, cases, _ctx: ctx };
  }

  // ---------- digests (order-independent; selected_ids only in the scenario digest) ----------
  function digests(env, PL, F) {
    const cs = [["base", "base", []]].concat(env.cases.slice().sort((a, b) => cmpStr(a.id, b.id)).map((c) => [c.id, c.label, c.disabled_source_ids]));
    const prob = [SCHEMA, PL.METRIC, OBJECTIVE, PL.problemDigest(env.plan, F), cs];
    return {
      resilience_problem_digest: "sha256:" + F.sha256hex(JSON.stringify(prob)),
      resilience_scenario_digest: "sha256:" + F.sha256hex(JSON.stringify([prob, env.plan.selected_ids.slice().sort(cmpStr)])),
      exclusions_digest: "sha256:" + F.sha256hex(JSON.stringify(cs.map(([id, , ex]) => [id, ex]))),
      v2_problem_digest: PL.problemDigest(env.plan, F), v2_scenario_digest: PL.scenarioDigest(env.plan, F),
    };
  }

  // L = (unknown_count, weighted_sum_mm, max_mm with null = +Infinity) — lexicographic, smaller is better
  const L = (m) => [m.unknown_count, m.weighted_sum_mm, m.max_mm === null ? Infinity : m.max_mm];
  const cmpVec = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1; return 0; };
  const cmpIds = (a, b) => { for (let i = 0; i < Math.min(a.length, b.length); i++) { const c = cmpStr(a[i], b[i]); if (c) return c; } return a.length - b.length; };
  const ext = (v) => v.map((x) => (x === Infinity ? null : x));

  function buildResilienceReport(envIn, deps) {
    const { PL, F, data, obs } = deps;
    const env = envIn._ctx ? envIn : validateResilience(envIn, deps);
    const ctx = env._ctx, sc = env.plan;
    const allCases = [{ id: "base", label: "Без исключений (base)", disabled_source_ids: [] }].concat(env.cases);
    // computational view per case: a NEW context object with filtered places; the frozen source context is untouched
    const pre = allCases.map((c) => {
      const off = new Set(c.disabled_source_ids);
      const cctx = { ...ctx, places: ctx.places.filter((p) => !off.has(p.id)) };
      return { c, cctx, pre: PL.precompute(cctx, sc) };
    });
    const evalAll = (ids) => pre.map(({ c, cctx, pre: P }) => ({ case_id: c.id, ...PL.evaluatePlan(cctx, sc, ids, P) }));
    const summary = (ev) => {
      const per = ev.map((e) => ({ case_id: e.case_id, unknown_count: e.metrics.unknown_count, weighted_sum_mm: e.metrics.weighted_sum_mm,
        weighted_mean_mm: e.metrics.weighted_mean_mm, max_mm: e.metrics.max_mm, covered_weight: e.metrics.covered_weight,
        coverage_fraction: e.metrics.coverage_fraction, cost: e.metrics.cost, vector: ext(L(e.metrics)) }));
      let W = null;
      for (const e of ev) { const v = L(e.metrics); if (W === null || cmpVec(v, W) > 0) W = v; }
      const worst = ev.filter((e) => cmpVec(L(e.metrics), W) === 0).map((e) => e.case_id).sort(cmpStr);
      return { selected_ids: ev[0].selected_ids, feasible: ev[0].feasibility.feasible, reasons: ev[0].feasibility.reasons, per_case: per,
        worst_vector: ext(W), worst_case_ids: worst, rows_by_case: ev.map((e) => ({ case_id: e.case_id, rows: e.rows })) };
    };
    // nominal = mean-optimum v2 on base
    const v2 = PL.optimizePlans(ctx, sc, { F });
    // robust = exhaustive over feasible subsets (<= 2^12), key (W, L_base, cost, sorted IDs); haversine only in precompute
    let robust = null, evaluated = 0, feasibleCount = 0, status = v2.status === "infeasible" ? "infeasible" : "optimal";
    const cands = sc.candidates.map((c) => c.id).sort(cmpStr);
    if (status === "optimal") {
      const n = cands.length;
      if ((1 << n) > LIMITS.subsets) fail("too_many_candidates", `2^${n} > ${LIMITS.subsets}`);
      for (let mask = 0; mask < (1 << n); mask++) {
        evaluated++;
        const ids = cands.filter((_, k) => mask & (1 << k));
        if (!PL.feasibility(sc, ids).feasible) continue;
        feasibleCount++;
        const ev = pre.map(({ cctx, pre: P }) => PL.evaluatePlan(cctx, sc, ids, P).metrics);
        let W = null; for (const m of ev) { const v = L(m); if (W === null || cmpVec(v, W) > 0) W = v; }
        const key = { W, Lb: L(ev[0]), cost: ev[0].cost, ids };
        if (robust === null || cmpVec(key.W, robust.W) < 0 || (cmpVec(key.W, robust.W) === 0 && (cmpVec(key.Lb, robust.Lb) < 0
          || (cmpVec(key.Lb, robust.Lb) === 0 && (key.cost < robust.cost || (key.cost === robust.cost && cmpIds(key.ids, robust.ids) < 0)))))) robust = key;
      }
      if (!feasibleCount) status = "infeasible";
    }
    const plans = { manual: summary(evalAll(sc.selected_ids)) };
    plans.nominal = status === "optimal" ? summary(evalAll(v2.objectives.mean.ids)) : null;
    plans.robust = status === "optimal" ? summary(evalAll(robust.ids)) : null;
    let price = null, price_reason = null;
    if (status !== "optimal") price_reason = "нет допустимых планов: " + (v2.reasons || []).map((r) => r.text).join("; ");
    else {
      const a = plans.robust.per_case[0].weighted_mean_mm, b = plans.nominal.per_case[0].weighted_mean_mm;
      if (a === null || b === null) price_reason = "среднее base неизвестно (есть точки без расстояния) — цена не вычисляется";
      else price = (a - b) / 1000;
    }
    // provenance of excluded and nearest source records (observed_secondary + QA labels of the build)
    const city = data.cities[sc.city_id];
    const recIds = new Set(env.cases.flatMap((c) => c.disabled_source_ids));
    for (const p of ["manual", "nominal", "robust"]) if (plans[p]) for (const rc of plans[p].rows_by_case) for (const r of rc.rows)
      for (const n of [r.nearest_before, r.nearest_after]) if (n && n.kind === "source") recIds.add(n.id);
    const q = obs && obs.cities && obs.cities[sc.city_id] ? obs.cities[sc.city_id].qa : null;
    const qaOf = (id) => {
      if (!q) return { available: false, flags: [] };
      const flags = [];
      if (q.category_doubt && q.category_doubt[id]) flags.push(q.category_doubt[id].rule);
      for (const d of q.possible_duplicates || []) if (d.a === id || d.b === id) flags.push("possible_duplicate:" + d.rule);
      for (const g of q.colocated || []) if ((g.ids || []).includes(id)) flags.push("colocated");
      return { available: true, flags };
    };
    const records = [...recIds].sort(cmpStr).map((id) => {
      const p = city.places.find((x) => x.id === id);
      return { id, name: p ? p.name : null, category_overture: p ? p.category : null, lon: p ? p.lon : null, lat: p ? p.lat : null,
        sources: p ? (p.sources || []) : [], qa: qaOf(id), excluded_in: env.cases.filter((c) => c.disabled_source_ids.includes(id)).map((c) => c.id) };
    });
    const dupSets = {};
    for (const c of env.cases) { const k = JSON.stringify(c.disabled_source_ids); (dupSets[k] = dupSets[k] || []).push(c.id); }
    return {
      report_schema: REPORT_SCHEMA, schema_version: SCHEMA, metric_version: PL.METRIC, objective_version: OBJECTIVE,
      generator: "research/round-9-results/K08/resilience_report.js (adapter over web/plan.js)",
      ...digests(env, PL, F),
      source: { city_id: sc.city_id, label: city.label, source_snapshot: sc.source_snapshot, release: city.release, bbox: city.bbox,
        places_file: city.files && city.files.places_social, records_in_slice: ctx.places.filter((p) => p.group === sc.category).length,
        attribution: city.attribution || [] },
      input: { plan: sc, cases: env.cases },
      cases: allCases.map((c) => ({ id: c.id, label: c.label, disabled_source_ids: c.disabled_source_ids,
        same_exclusions_as: c.id === "base" ? [] : dupSets[JSON.stringify(c.disabled_source_ids)].filter((x) => x !== c.id) })),
      search: { status, evaluated, feasible_count: feasibleCount, subsets_limit: LIMITS.subsets, v2_status: v2.status,
        v2_reasons: v2.reasons || [] },
      plans, price_of_robustness_m: price, price_reason,
      same_plans: { nominal_eq_robust: !!(plans.nominal && plans.robust && plans.nominal.selected_ids.join() === plans.robust.selected_ids.join()),
        manual_eq_robust: !!(plans.robust && plans.manual.selected_ids.join() === plans.robust.selected_ids.join()) },
      source_records: records,
      notes: ["Условно исключаем из расчёта; это не подтверждение закрытия.",
        "Анализ допущений о данных, не прогноз кризиса, закрытия, риска или потребностей жителей; вероятностей случаев нет.",
        "QA-флаг не доказывает ошибку и не исключает запись автоматически; исключения выбраны пользователем.",
        "Пустые исходные данные в случае не означают отсутствие услуги в городе.",
        "Расстояния по прямой (haversine-mm-v1) в квадрате среза; стоимости — условные единицы, не тенге."],
    };
  }

  // ---------- static HTML ----------
  const esc = (v) => String(v === null || v === undefined ? "нет данных" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const mText = (mm) => (mm === null || mm === undefined ? "нет данных" : (mm / 1000).toFixed(1) + " м");
  function renderResilienceHtml(r) {
    const tr = (cells, th) => "<tr>" + cells.map((c) => (th ? "<th>" : "<td>") + esc(c) + (th ? "</th>" : "</td>")).join("") + "</tr>";
    const table = (head, rows) => '<div class="tw"><table>' + tr(head, true) + rows.map((x) => tr(x)).join("") + "</table></div>";
    const label = { manual: "Ручной", nominal: "Обычный (mean, base)", robust: "Устойчивый (worst-lex)" };
    const caseLabel = Object.fromEntries(r.cases.map((c) => [c.id, c.label]));
    const P = [`<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">`,
      `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><meta name="referrer" content="no-referrer">`,
      `<title>${esc("Устойчивость к допущениям: " + r.source.label)}</title><style>body{font:14px/1.45 system-ui,sans-serif;margin:16px;max-width:1000px;color:#111;background:#fff}`,
      `table{border-collapse:collapse;margin:6px 0;font-size:12.5px}td,th{border:1px solid #ccc;padding:3px 6px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#f3f2ee}`,
      `.tw{overflow-x:auto;max-width:100%}.warn{border-left:3px solid #fab219;padding-left:8px}.muted{color:#666}@media print{.tw{overflow:visible}}</style></head><body>`,
      `<h1>${esc("Устойчивость к допущениям о данных — " + r.source.label + ", " + r.input.plan.category)}</h1>`,
      `<p class="warn">${esc(r.notes[0] + " " + r.notes[1])}</p>`,
      `<h2>Происхождение и версии</h2>` + table(["Поле", "Значение"], [["source_snapshot (из плана)", r.source.source_snapshot], ["Выпуск Overture", r.source.release],
        ["bbox среза", r.source.bbox.join(", ")], ["Файл мест", r.source.places_file ? r.source.places_file.path + " sha256 " + r.source.places_file.sha256 : null],
        ["Записей категории в срезе", r.source.records_in_slice], ["Схема / метрика / цель", `${r.schema_version} / ${r.metric_version} / ${r.objective_version}`],
        ["resilience_problem_digest", r.resilience_problem_digest], ["resilience_scenario_digest", r.resilience_scenario_digest],
        ["exclusions_digest", r.exclusions_digest], ["v2 problem / scenario digest", r.v2_problem_digest + " / " + r.v2_scenario_digest], ["Отчёт", r.report_schema]]),
      `<h2>Случаи (исключения выбраны пользователем)</h2>` + table(["ID", "Подпись", "Условно исключённые записи", "Совпадает с"],
        r.cases.map((c) => [c.id, c.label, c.disabled_source_ids.join(", ") || "—", c.same_exclusions_as.join(", ") || "—"])),
      `<h2>Сравнение планов</h2><p>Поиск: ${esc(r.search.status)}; наборов ${esc(r.search.evaluated)}, допустимых ${esc(r.search.feasible_count)}. ` +
        `Цена устойчивости (среднее base, устойчивый − обычный): <b>${esc(r.price_of_robustness_m === null ? "не вычисляется — " + r.price_reason : r.price_of_robustness_m.toFixed(3) + " м")}</b>` +
        `${r.same_plans.nominal_eq_robust ? esc(" · обычный и устойчивый планы совпадают — преимущества нет") : ""}</p>`];
    for (const k of ["manual", "nominal", "robust"]) {
      const p = r.plans[k];
      if (!p) { P.push(`<h3>${esc(label[k])}</h3><p>нет допустимого плана</p>`); continue; }
      P.push(`<h3>${esc(label[k] + ": " + (p.selected_ids.join(", ") || "без новых объектов") + (p.feasible ? "" : " — НЕДОПУСТИМ, не рекомендуется"))}</h3>`,
        table(["Случай", "Без расстояния", "Среднее", "Худшая точка", "Охват (вес)", "Стоимость, усл. ед."],
          p.per_case.map((c) => [`${c.case_id} · ${caseLabel[c.case_id]}`, c.unknown_count, mText(c.weighted_mean_mm), mText(c.max_mm), c.covered_weight, c.cost])),
        `<p>${esc("Худший вектор W = (" + p.worst_vector.map((x) => (x === null ? "∞/нет данных" : x)).join(", ") + "); худшие случаи: " + p.worst_case_ids.join(", "))}</p>`);
    }
    P.push(`<h2>Исходные записи (исключённые и ближайшие)</h2>` + table(["ID", "Название", "Категория Overture", "Источник · лицензия · дата", "QA", "Исключена в случаях"],
      r.source_records.map((x) => [x.id, x.name, x.category_overture, x.sources.map((s) => `${s.dataset} · ${s.license} · ${s.update_time || "—"}`).join("; "),
        x.qa.available ? (x.qa.flags.join(", ") || "нет флагов (≠ проверено)") : "QA недоступно", x.excluded_in.join(", ") || "—"])));
    P.push(`<h2>Ограничения</h2><ul>${r.notes.map((n) => "<li>" + esc(n) + "</li>").join("")}</ul>`,
      `<p class="muted">${esc("Атрибуция: " + [...new Set(r.source.attribution.map((a) => (typeof a === "string" ? a : a.dataset + " (" + a.license + ")")))].join("; ") + ". Отчёт пересчитан из входа; без скриптов и внешних ресурсов.")}</p></body></html>`);
    return P.join("\n") + "\n";
  }

  /* exportResilienceEnvelope: только вход (без производных), канонический порядок */
  function exportResilienceEnvelope(env) {
    const { selected_ids, ...rest } = env.plan;
    return JSON.stringify({ schema_version: SCHEMA, plan: { ...rest, selected_ids }, cases: env.cases }, null, 1) + "\n";
  }

  const api = { SCHEMA, OBJECTIVE, REPORT_SCHEMA, LIMITS, ResilienceError, validateResilience, buildResilienceReport, renderResilienceHtml, exportResilienceEnvelope };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.K08_RESILIENCE_REPORT = api;
})(typeof window !== "undefined" ? window : globalThis);
