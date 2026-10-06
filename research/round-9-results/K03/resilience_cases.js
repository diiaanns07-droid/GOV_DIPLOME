/* K03 r9: построитель случаев «условно не учитывать исходные записи» для city-resilience-v1 (research/round-9/CORE_SPEC.txt).
 * Чистые функции без DOM. Только явный выбор пользователя: одна запись, пользовательская группа или указанная пользователем
 * QA-группа COLOCATED. Ничего не исключается автоматически; QA-метка не доказывает ошибку записи.
 * Исходные data.js/evidence.js и контекст plan.js не изменяются: случай — это список ID, а caseView — отфильтрованная копия
 * списка мест с тем же source_snapshot. Это анализ допущений о данных, не прогноз закрытия, кризиса или риска.
 * Браузер: window.CITY_RESILIENCE_CASES (после facts.js и plan.js). Node: require("./resilience_cases.js").
 * Независимый Python-оракул: resilience_cases_ref.py.
 */
(function (root) {
  "use strict";
  const ENVELOPE = "city-resilience-v1", VERSION = "k03-cases-v1", MANIFEST = "k03-exclusion-manifest-v1";
  const CATEGORIES = ["school", "outpatient_clinic"];
  const LIMITS = { user_cases: 7, label: 120, id: 64 };
  const RESERVED_CASE_ID = "base";
  const NOTE_RU = "Условно исключаем из расчёта; это не подтверждение закрытия. Пустые исходные данные не означают отсутствие услуги.";
  const ID_CHARS = /^[\p{L}\p{N}_.-]+$/u;  // как ID в web/plan.js сборки: буквы любого письма, цифры, _ . -; NFC; 1..64 code points
  const isId = (v) => typeof v === "string" && v.normalize("NFC") === v && [...v].length >= 1 && [...v].length <= LIMITS.id && ID_CHARS.test(v);
  const BAD_LABEL_CHAR = /[\p{Cc}\p{Cs}]/u;  // управляющие символы и одиночные суррогаты

  class CaseError extends Error {
    constructor(code, path, detail) { super(code + " @ " + path + (detail ? ": " + detail : "")); this.code = code; this.path = path; this.detail = detail || ""; }
  }
  const fail = (code, path, detail) => { throw new CaseError(code, path, detail); };
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const deepFreeze = (o) => { if (o && typeof o === "object" && !Object.isFrozen(o)) { Object.freeze(o); for (const v of Object.values(o)) deepFreeze(v); } return o; };
  const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  // Канонический JSON: ключи объектов по UTF-16, без пробелов (для record_sha256 и digest исключений)
  const canon = (v) => (Array.isArray(v) ? "[" + v.map(canon).join(",") + "]" : isObj(v)
    ? "{" + Object.keys(v).sort(cmpStr).map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}" : JSON.stringify(v));
  const decimals = (x) => { const s = String(Math.abs(x)); if (/e/i.test(s)) return null; const i = s.indexOf("."); return i < 0 ? 0 : s.length - i - 1; };

  // ---------- каталог исходных записей выбранного города/категории (то, из чего пользователь выбирает) ----------
  /* sourceCatalog(data, evidence, ctx, category, F): ctx = CITY_PLAN.makeContext(...); F.sha256hex — из facts.js.
   * Записи — копии из data.js с provenance и QA; отсортированы по ID. Контекст и данные не изменяются. */
  function sourceCatalog(data, evidence, ctx, category, F) {
    if (!CATEGORIES.includes(category)) fail("bad_category", "category", String(category).slice(0, 40));
    const city = ctx.city_id, c = data && data.cities && data.cities[city];
    if (!c) fail("bad_city", "city", String(city).slice(0, 40));
    const inCtx = new Set(ctx.places.filter((p) => p.group === category).map((p) => p.id));
    const e = evidence && evidence.cities && evidence.cities[city], qa = e && e.qa ? e.qa : null;
    const xy = new Map();
    for (const p of c.places) { const k = p.lon + "," + p.lat; if (!xy.has(k)) xy.set(k, []); xy.get(k).push(p); }
    const records = c.places.filter((p) => inCtx.has(p.id)).sort((a, b) => cmpStr(a.id, b.id)).map((p) => {
      const same = xy.get(p.lon + "," + p.lat).filter((o) => o.id !== p.id);
      const col = qa ? qa.colocated.find((g) => g.ids.includes(p.id)) : null;
      const dups = qa ? qa.possible_duplicates.filter((d) => d.a === p.id || d.b === p.id)
        .map((d) => ({ other: d.a === p.id ? d.b : d.a, rule: d.rule, distance_m: d.distance_m })).sort((a, b) => cmpStr(a.other, b.other)) : [];
      const doubt = qa && qa.category_doubt[p.id] ? { rule: qa.category_doubt[p.id].rule, reason: qa.category_doubt[p.id].reason } : null;
      return {
        id: p.id, category: p.group, name: p.name === undefined ? null : p.name, address: p.address === undefined ? null : p.address,
        lon: p.lon, lat: p.lat, coord_decimals: { lon: decimals(p.lon), lat: decimals(p.lat) },
        provenance: { overture_category: p.category === undefined ? null : p.category, overture_version: p.overture_version === undefined ? null : p.overture_version,
          confidence: p.confidence === undefined ? null : p.confidence, operating_status: p.operating_status === undefined ? null : p.operating_status,
          sources: (p.sources || []).map((s) => ({ dataset: s.dataset === undefined ? null : s.dataset, record_id: s.record_id === undefined ? null : s.record_id,
            license: s.license === undefined ? null : s.license, update_time: s.update_time === undefined ? null : s.update_time })) },
        record_sha256: F.sha256hex(canon(p)),
        position_status: "source_reported_unverified",
        qa: { available: !!qa, colocated: col ? { lon: col.lon, lat: col.lat, size: col.ids.length, ids: col.ids.slice().sort(cmpStr) } : null,
          possible_duplicates: dups, category_doubt: doubt },
        same_coordinates: { in_category: same.filter((o) => o.group === category).map((o) => o.id).sort(cmpStr),
          other_categories: same.filter((o) => o.group !== category).map((o) => o.id).sort(cmpStr) },
      };
    });
    return deepFreeze({ version: VERSION, city_id: city, category, source_snapshot: ctx.source_snapshot, release: c.release,
      qa_available: !!qa, records });
  }
  // Индекс всех исходных записей всех городов: ID → [{city, group}] (для кода ошибки «другой город/категория»)
  function sourceIndex(data) {
    const m = new Map();
    for (const [city, c] of Object.entries(data.cities)) for (const p of c.places) { if (!m.has(p.id)) m.set(p.id, []); m.get(p.id).push({ city, group: p.group }); }
    return m;
  }

  // ---------- проверка одного ID и списка исключений ----------
  function classify(cat, index, candidateIds, id, path) {
    if (typeof id !== "string" || !isId(id)) fail("bad_source_id", path, JSON.stringify(id === undefined ? null : id).slice(0, 60));
    if (cat.records.some((r) => r.id === id)) return id;
    const where = index ? index.get(id) : null;
    if (where && where.some((w) => w.city === cat.city_id)) fail("other_category_source", path, `${id}: запись другой категории`);
    if (where) fail("other_city_source", path, `${id}: запись другого города`);
    if (candidateIds && candidateIds.has(id)) fail("candidate_not_source", path, `${id}: ID кандидата, а не исходной записи`);
    fail("unknown_source_id", path, `${id}: такой исходной записи нет`);
  }
  function exclusionList(cat, ids, path, index, candidateIds) {
    if (!Array.isArray(ids)) fail("bad_shape", path, "ожидается массив ID");
    if (ids.length < 1) fail("empty_exclusion", path, "нужно не меньше одной записи");
    if (ids.length > cat.records.length) fail("too_many_exclusions", path, `не больше ${cat.records.length} записей категории`);
    const seen = new Set();
    ids.forEach((id, k) => {
      classify(cat, index, candidateIds, id, `${path}[${k}]`);
      if (seen.has(id)) fail("duplicate_source_id", `${path}[${k}]`, id);
      seen.add(id);
    });
    return ids.slice().sort(cmpStr);
  }
  function checkLabel(v, path) {
    if (typeof v !== "string" || v.length === 0) fail("bad_label", path, "непустая строка");
    if ([...v].length > LIMITS.label) fail("bad_label", path, `не больше ${LIMITS.label} символов`);
    if (BAD_LABEL_CHAR.test(v)) fail("bad_label", path, "управляющие символы не допускаются");
    return v;
  }
  function checkCaseId(v, path) {
    if (!isId(v)) fail("bad_case_id", path, JSON.stringify(v === undefined ? null : v).slice(0, 60));
    if (v === RESERVED_CASE_ID) fail("reserved_case_id", path, "base добавляется автоматически");
    return v;
  }

  /* validateCases(cat, cases, {index, candidateIds}) -> {cases (ID исключений отсортированы), with_base, identical_sets}
   * cases — пользовательские случаи из envelope (1..7); base добавляется здесь, в with_base, а не принимается из файла. */
  function validateCases(cat, cases, opts) {
    const index = opts && opts.index, candidateIds = opts && opts.candidateIds ? new Set(opts.candidateIds) : null;
    if (!Array.isArray(cases)) fail("bad_shape", "cases", "ожидается массив");
    if (cases.length < 1) fail("no_cases", "cases", "нужен хотя бы один пользовательский случай");
    if (cases.length > LIMITS.user_cases) fail("too_many_cases", "cases", `не больше ${LIMITS.user_cases} пользовательских случаев (+ base)`);
    const ids = new Set();
    const clean = cases.map((c, i) => {
      const p = `cases[${i}]`;
      if (!isObj(c)) fail("bad_shape", p, "ожидается объект");
      for (const k of Object.keys(c)) if (!["id", "label", "disabled_source_ids"].includes(k)) fail("unknown_field", `${p}.${k}`.slice(0, 80), "поле не допускается");
      for (const k of ["id", "label", "disabled_source_ids"]) if (!(k in c)) fail("missing_field", `${p}.${k}`);
      checkCaseId(c.id, `${p}.id`);
      if (ids.has(c.id)) fail("duplicate_case_id", `${p}.id`, c.id);
      ids.add(c.id);
      checkLabel(c.label, `${p}.label`);
      return { id: c.id, label: c.label, disabled_source_ids: exclusionList(cat, c.disabled_source_ids, `${p}.disabled_source_ids`, index, candidateIds) };
    });
    const bySet = new Map();
    for (const c of clean) { const k = JSON.stringify(c.disabled_source_ids); if (!bySet.has(k)) bySet.set(k, []); bySet.get(k).push(c.id); }
    const identical_sets = [...bySet.values()].filter((g) => g.length > 1).map((g) => g.slice().sort(cmpStr)).sort((a, b) => cmpStr(a[0], b[0]));
    return { cases: clean, with_base: [{ id: RESERVED_CASE_ID, label: "Исходные данные", disabled_source_ids: [] }, ...clean], identical_sets };
  }

  // ---------- явные построители (ничего не выбирают сами) ----------
  const clip = (s, n) => { const cp = [...String(s).replace(/[\p{Cc}\p{Cs}]/gu, " ")]; return cp.length <= n ? cp.join("") : cp.slice(0, n - 1).join("") + "…"; };
  const nameOf = (r) => r.name || "без названия";
  function defaultLabel(kind, recs, extra) {
    if (kind === "single") return clip(`Условно без записи: ${nameOf(recs[0])}`, LIMITS.label);
    if (kind === "group") return clip(`Условно без выбранных записей (${recs.length}): ${recs.map(nameOf).join(", ")}`, LIMITS.label);
    return clip(`Условно без записей QA-группы COLOCATED (${extra.lon}, ${extra.lat}): ${recs.length} из ${extra.size}`, LIMITS.label);
  }
  function make(cat, ids, kind, opts, index, candidateIds, extra) {
    const id = checkCaseId(opts && opts.id, "id");
    const sorted = exclusionList(cat, ids, "disabled_source_ids", index, candidateIds ? new Set(candidateIds) : null);
    const recs = sorted.map((x) => cat.records.find((r) => r.id === x));
    const label = checkLabel(opts && opts.label !== undefined ? opts.label : defaultLabel(kind, recs, extra), "label");
    return { id, label, disabled_source_ids: sorted };
  }
  // одна запись, выбранная пользователем
  const singleCase = (cat, sourceId, opts) => make(cat, [sourceId], "single", opts, opts && opts.index, opts && opts.candidateIds);
  // пользовательская группа (явный список ID; повтор ID — ошибка, а не молчаливое удаление)
  const groupCase = (cat, sourceIds, opts) => make(cat, sourceIds, "group", opts, opts && opts.index, opts && opts.candidateIds);
  /* QA-группы COLOCATED города, в которых есть записи этой категории или нет — для показа; ничего не создают.
   * Нет QA-меток среза → qa_available=false; нет групп → пустой список (группа не придумывается). */
  function colocatedGroups(evidence, cat) {
    const e = evidence && evidence.cities && evidence.cities[cat.city_id];
    if (!e || !e.qa) return { qa_available: false, groups: [] };
    const mine = new Set(cat.records.map((r) => r.id));
    return { qa_available: true, groups: e.qa.colocated.map((g, index) => ({ index, lon: g.lon, lat: g.lat, size: g.ids.length,
      ids_in_category: g.ids.filter((i) => mine.has(i)).sort(cmpStr), ids_other_categories: g.ids.filter((i) => !mine.has(i)).sort(cmpStr) })) };
  }
  /* Случай из QA-группы, которую пользователь указал индексом. Исключаются только записи выбранной категории из этой группы;
   * записи других категорий не трогаются, соседние записи вне группы (например, в 1 м) не добавляются. */
  function colocatedCase(evidence, cat, groupIndex, opts) {
    const g = colocatedGroups(evidence, cat);
    if (!g.qa_available) return { status: "qa_unavailable", case: null, group: null, reason: "в срезе нет QA-меток; группа не создаётся" };
    if (!g.groups.length) return { status: "no_qa_group", case: null, group: null, reason: "в срезе нет групп COLOCATED; группа не создаётся" };
    if (!Number.isInteger(groupIndex) || groupIndex < 0 || groupIndex >= g.groups.length) fail("unknown_qa_group", "group", String(groupIndex).slice(0, 20));
    const grp = g.groups[groupIndex];
    if (!grp.ids_in_category.length) return { status: "no_records_in_category", case: null, group: grp, reason: "в группе нет записей этой категории" };
    return { status: "ok", case: make(cat, grp.ids_in_category, "colocated", opts, opts && opts.index, opts && opts.candidateIds, grp), group: grp };
  }
  function nextCaseId(existing) { const s = new Set(existing); for (let k = 1; ; k++) if (!s.has("case-" + k)) return "case-" + k; }

  // ---------- envelope (только вход; производные поля не принимаются) ----------
  const DERIVED = ["derived_results", "per_case", "worst_vector", "worst_case_ids", "nominal", "robust", "evaluated", "feasible_count",
    "resilience_problem_digest", "resilience_scenario_digest", "price_of_robustness_m", "verified", "imported"];
  function checkEnvelopeShape(obj) {
    if (!isObj(obj)) fail("bad_shape", "$", "ожидается объект");
    for (const k of Object.keys(obj)) if (!["schema_version", "plan", "cases"].includes(k))
      fail(DERIVED.includes(k) ? "derived_not_accepted" : "unknown_field", k.slice(0, 60), "поле не допускается");
    for (const k of ["schema_version", "plan", "cases"]) if (!(k in obj)) fail("missing_field", k);
    if (obj.schema_version !== ENVELOPE) fail("bad_version", "schema_version", String(obj.schema_version).slice(0, 40));
    if (!isObj(obj.plan)) fail("bad_shape", "plan", "ожидается полный city-plan-v2");
    if ("derived_results" in obj.plan) fail("derived_not_accepted", "plan.derived_results", "в r9 envelope производные поля не принимаются");
    return obj;
  }
  function makeEnvelope(plan, cases) { return checkEnvelopeShape({ schema_version: ENVELOPE, plan, cases }); }

  // ---------- вычислительное представление случая: копия списка мест без исключённых, snapshot тот же ----------
  function caseView(ctx, disabledIds) {
    if (!Array.isArray(disabledIds)) fail("bad_shape", "disabled_source_ids", "ожидается массив");
    const have = new Set(ctx.places.map((p) => p.id)), off = new Set();
    disabledIds.forEach((id, k) => { if (typeof id !== "string" || !have.has(id)) fail("unknown_source_id", `disabled_source_ids[${k}]`, String(id).slice(0, 60)); off.add(id); });
    return Object.freeze({ ...ctx, places: Object.freeze(ctx.places.filter((p) => !off.has(p.id))) });
  }

  // ---------- digest исключений и неизменяемый manifest исключаемых записей ----------
  function exclusionDigest(cat, cases, F) {
    const rows = cases.map((c) => [c.id, c.label, c.disabled_source_ids.slice().sort(cmpStr)]).sort((a, b) => cmpStr(a[0], b[0]));
    return "sha256:" + F.sha256hex(JSON.stringify([VERSION, cat.city_id, cat.category, cat.source_snapshot, rows]));
  }
  /* exclusionManifest(cat, validated, F, build): копии исключаемых записей (категория, координаты, provenance, QA, record_sha256)
   * на базовом срезе; не входит в envelope и не принимается при импорте — служит отчёту и проверке. */
  function exclusionManifest(cat, validated, F, build) {
    const used = [...new Set(validated.cases.flatMap((c) => c.disabled_source_ids))].sort(cmpStr);
    const records = {};
    for (const id of used) records[id] = cat.records.find((r) => r.id === id);
    const same = new Map(validated.identical_sets.flatMap((g) => g.map((id) => [id, g.filter((x) => x !== id)])));
    return deepFreeze(JSON.parse(JSON.stringify({ schema: MANIFEST, note: NOTE_RU, city_id: cat.city_id, category: cat.category,
      base_source_snapshot: cat.source_snapshot, release: cat.release, qa_available: cat.qa_available, build: build || null,
      exclusion_digest: exclusionDigest(cat, validated.cases, F),
      cases: validated.cases.map((c) => ({ id: c.id, label: c.label, disabled_source_ids: c.disabled_source_ids, identical_to: same.get(c.id) || [] })),
      records })));
  }

  const api = { ENVELOPE, VERSION, MANIFEST, CATEGORIES, LIMITS, RESERVED_CASE_ID, NOTE_RU, CaseError, isId, canon, sourceCatalog, sourceIndex,
    validateCases, singleCase, groupCase, colocatedGroups, colocatedCase, nextCaseId, defaultLabel, checkEnvelopeShape, makeEnvelope,
    caseView, exclusionDigest, exclusionManifest };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_RESILIENCE_CASES = api;
})(typeof window !== "undefined" ? window : globalThis);
