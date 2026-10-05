/* K02 r7: адаптер каталога фактов для сценария «Если добавить объект» (city-whatif-v1).
 * Вход — ТОЛЬКО результат расчётного модуля (whatif_calc.compute или совместимый); адаптер проверяет его
 * инварианты и ничего не пересчитывает сам. Выход — built {catalog, city, scenario, digest} в формате
 * web/facts.js, поэтому план проверяется существующим facts.validatePlan (stale_catalog, duplicate_id, null_as_fact…).
 * Объяснение шаблонное (детерминированная заглушка, не LLM). kk — черновик для проверки носителем.
 * Зависимости передаются явно: deps = {sha256hex, PlanError, validatePlan, formatValue} из web/facts.js сборки.
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-whatif-v1";
  const LETTERS = "ABCDEFGHIJ";  // ссылки на точки в тексте: без цифр из пользовательских ID
  const STUB_NAME = "шаблонное объяснение сценария (детерминированная заглушка, не LLM)";
  const CAT = { school: ["школы", "мектеп"], outpatient_clinic: ["поликлиники", "емхана"] };
  const L = {
    before: ["до ближайшей записи в срезе, до проекта", "кесіндідегі ең жақын жазбаға дейін, жобаға дейін"],
    after: ["после условного объекта", "шартты нысаннан кейін"],
    delta: ["сокращение расстояния по прямой", "түзу бойынша қашықтықтың қысқаруы"],
    records: ["Исходных записей категории в срезе", "Кесіндідегі санат бойынша бастапқы жазбалар"],
    point: ["Точка", "Нүкте"],
  };
  const T = {
    header: ["Проверяемая часть (значения из расчётного модуля сценария)", "Тексерілетін бөлік (мәндер сценарий есептеу модулінен)"],
    scenario: ["Сценарий", "Сценарий"],
    summary: ["Итог", "Қорытынды"], weakest: ["Наименьший эффект", "Ең аз әсер"], risks: ["Ограничения данных", "Дерек шектеулері"],
    data_gaps: ["Нет данных", "Дерек жоқ"],
    derived: ["расчёт", "есептелген"], hyp: ["с условным объектом", "шартты нысанмен"], partial: ["ближайшая только в срезе", "тек кесіндідегі ең жақын"],
    no_source: ["в срезе нет исходных записей; улучшение не вычисляется", "кесіндіде бастапқы жазбалар жоқ; жақсару есептелмейді"],
    m: [" м", " м"], records: [" записей", " жазба"],
    sources: ["Ближайшие исходные записи (данные Overture, не проверены как учреждения)", "Ең жақын бастапқы жазбалар (Overture деректері, мекеме ретінде тексерілмеген)"],
    qa: ["QA-флаг", "QA белгісі"], noqa: ["флагов нет (это не означает проверку)", "белгі жоқ (бұл тексерілді дегенді білдірмейді)"],
    limits: ["Ограничения: расстояние по прямой (гаверсинус), не время пешком и не доступность; ближайшая запись в сохранённом квадрате, не обязательно в городе; объект условный; неполнота и ошибки координат могут менять результат; положительная разница — меньшее геометрическое расстояние, не улучшение услуг.",
      "Шектеулер: түзу бойынша қашықтық (гаверсинус), жаяу жүру уақыты емес; ең жақын жазба тек сақталған шаршыда; нысан шартты; толымсыздық пен координат қателері нәтижені өзгертуі мүмкін; оң айырма — геометриялық қашықтықтың азаюы, қызмет жақсаруы емес."],
  };
  const lx = (pair, lang) => pair[lang === "kk" ? 1 : 0];
  const finite = (v) => typeof v === "number" && Number.isFinite(v);

  function fail(deps, code, detail) { throw new deps.PlanError(code, detail); }

  // Инварианты результата расчётного модуля: адаптер не исправляет и не пересчитывает, а отклоняет.
  function checkResult(r, deps) {
    if (!r || r.schema_version !== SCHEMA) fail(deps, "bad_result", "ожидается результат city-whatif-v1");
    if (!["shymkent", "astana"].includes(r.city_id)) fail(deps, "bad_result", `город ${r.city_id}`);
    if (!CAT[r.category]) fail(deps, "bad_result", `категория ${r.category}`);
    if (typeof r.source_snapshot !== "string" || !/^sha256:[0-9a-f]{64}$/.test(r.source_snapshot)) fail(deps, "bad_result", "source_snapshot должен быть sha256 среза");
    if (!Number.isInteger(r.source_record_count) || r.source_record_count < 0) fail(deps, "bad_result", "source_record_count");
    const pts = r.control_points || [];
    if (!Array.isArray(r.rows) || r.rows.length !== pts.length || pts.length < 1 || pts.length > LETTERS.length) fail(deps, "bad_result", "строк должно быть столько же, сколько точек (1..10)");
    const proj = r.proposed_object;
    if (proj !== null && (proj.kind !== "hypothetical" || proj.category !== r.category)) fail(deps, "bad_result", "проект должен быть hypothetical той же категории");
    r.rows.forEach((row, i) => {
      if (row.point_id !== pts[i].id) fail(deps, "bad_result", `строка ${i}: point_id не совпадает с точкой`);
      for (const k of ["before_m", "after_m", "delta_m", "distance_to_proposed_m"])
        if (row[k] !== null && (!finite(row[k]) || row[k] < (k === "delta_m" ? -0 : 0))) fail(deps, "non_finite", `${row.point_id}.${k}=${row[k]}`);
      if ((row.before_m === null) !== (r.source_record_count === 0)) fail(deps, "bad_result", `${row.point_id}: before=null только при отсутствии исходных записей`);
      const expectedNearest = proj === null ? (row.before_m === null ? null : "source")
        : row.before_m === null || row.distance_to_proposed_m < row.before_m ? "proposed" : "source";
      if (row.nearest_after !== expectedNearest) fail(deps, "bad_result", `${row.point_id}: nearest_after=${row.nearest_after}, ожидалось ${expectedNearest}`);
      if (row.before_m !== null) {
        if (proj === null && !(row.after_m === row.before_m && row.delta_m === 0)) fail(deps, "bad_result", `${row.point_id}: без проекта after=before, delta=0`);
        if (proj !== null && row.after_m !== Math.min(row.before_m, row.distance_to_proposed_m)) fail(deps, "bad_result", `${row.point_id}: after≠min(before, до проекта)`);
        if (row.delta_m !== row.before_m - row.after_m) fail(deps, "bad_result", `${row.point_id}: delta≠before−after`);
      } else {
        if (row.delta_m !== null) fail(deps, "bad_result", `${row.point_id}: delta должна быть null без before`);
        if (row.after_m !== (proj ? row.distance_to_proposed_m : null)) fail(deps, "bad_result", `${row.point_id}: after без исходных записей = расстояние до проекта`);
      }
    });
  }

  /** result — выход расчётного модуля; qa — CITY_OBS.cities[city].qa (необязательно). */
  function buildWhatifCatalog(result, deps, qa) {
    checkResult(result, deps);
    const city = "kz." + result.city_id;
    const scenario = `whatif-${result.category.replace(/_/g, "-")}-${result.source_snapshot.slice(7, 19)}`;
    const cat = new Map();
    const add = (path, f) => {
      const id = `${city}/${scenario}/${path}`;
      if (cat.has(id)) fail(deps, "duplicate_id", id);
      for (const l of [f.label.ru, f.label.kk]) if (/\d/.test(l)) throw new Error(`${id}: подпись содержит цифры`);
      cat.set(id, { id, city, scenario, kind: f.value === null ? "unknown" : "derived", unit: f.unit, value: f.value,
        label: f.label, source: f.source, coverage_complete: f.coverage_complete, missing_reason: f.value === null ? f.reason : null,
        hypothetical: !!f.hypothetical, point_ref: f.point_ref ?? null, point_id: f.point_id ?? null, nearest: f.nearest ?? null });
    };
    const catName = CAT[result.category];
    add("whatif.source_records", { value: result.source_record_count, unit: "records", coverage_complete: false,
      label: { ru: `${L.records[0]}: ${catName[0]}`, kk: `${L.records[1]}: ${catName[1]}` }, source: result.source_snapshot });
    result.rows.forEach((row, i) => {
      const ref = LETTERS[i], base = `whatif.cp${i + 1}`;
      const nearest = row.nearest_source ? { id: row.nearest_source.id, name: row.nearest_source.name,
        qa: qaFlags(qa, row.nearest_source.id) } : null;
      const common = { unit: "m", point_ref: ref, point_id: row.point_id, source: "whatif_calc:" + result.source_snapshot };
      const byProject = row.nearest_after === "proposed";  // «с условным объектом» — только если значение определяет проект
      add(base + ".before", { ...common, value: row.before_m, coverage_complete: false, reason: "no_source_records_in_slice", nearest,
        label: { ru: `${L.point[0]} ${ref}: ${L.before[0]}`, kk: `${L.point[1]} ${ref}: ${L.before[1]}` } });
      add(base + ".after", { ...common, value: row.after_m, coverage_complete: false, hypothetical: byProject, reason: "no_source_and_no_project",
        label: { ru: `${L.point[0]} ${ref}: ${L.after[0]}`, kk: `${L.point[1]} ${ref}: ${L.after[1]}` } });
      add(base + ".delta", { ...common, value: row.delta_m, coverage_complete: false, hypothetical: byProject, reason: "no_source_records_in_slice",
        label: { ru: `${L.point[0]} ${ref}: ${L.delta[0]}`, kk: `${L.point[1]} ${ref}: ${L.delta[1]}` } });
    });
    return { catalog: cat, city, scenario, digest: whatifDigest(cat, result, deps), result_meta: {
      city_id: result.city_id, category: result.category, source_snapshot: result.source_snapshot, proposed_object: result.proposed_object } };
  }

  function qaFlags(qa, id) {
    if (!qa) return null;
    const flags = [];
    if ((qa.colocated || []).some((g) => g.ids.includes(id))) flags.push("colocated");
    if (qa.category_doubt && id in qa.category_doubt) flags.push("category_doubt:" + qa.category_doubt[id].rule);
    if ((qa.possible_duplicates || []).some((g) => (g.ids || []).includes(id))) flags.push("possible_duplicate");
    return flags;
  }

  // Digest: source_snapshot, категория, контрольные точки, проект и вычисленные значения (без округления).
  function whatifDigest(cat, result, deps) {
    const facts = [...cat.values()].map((f) => [f.id, f.value === null ? null : String(f.value), f.kind, f.unit, f.coverage_complete, f.missing_reason, f.hypothetical,
      f.point_id, f.nearest && f.nearest.id]).sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    const pts = result.control_points.map((p) => [p.id, String(p.lon), String(p.lat)]);
    const proj = result.proposed_object && [result.proposed_object.id, String(result.proposed_object.lon), String(result.proposed_object.lat), result.proposed_object.category, result.proposed_object.kind];
    return deps.sha256hex(JSON.stringify([SCHEMA, result.city_id, result.category, result.source_snapshot, pts, proj, facts])).slice(0, 16);
  }

  function catalogView(cat) { return [...cat.values()].map((f) => ({ id: f.id, label_ru: f.label.ru, kind: f.kind, has_value: f.value !== null, value: f.value })); }

  // Заглушка выбора: точки с наибольшим сокращением — в «Итог», с наименьшим — в «Наименьший эффект».
  const StubSelector = {
    name: STUB_NAME,
    select(view, digest) {
      const by = (suffix) => view.filter((v) => v.id.endsWith(suffix));
      const deltas = by(".delta").filter((v) => v.has_value).sort((a, b) => b.value - a.value || (a.id < b.id ? -1 : 1));
      const pick = (d) => [d.id.replace(/\.delta$/, ".before"), d.id.replace(/\.delta$/, ".after"), d.id];
      const summary = deltas.slice(0, 2).flatMap(pick);
      const weakest = deltas.length > 2 ? pick(deltas[deltas.length - 1]) : [];
      const risks = by("/whatif.source_records").map((v) => v.id);
      const gaps = view.filter((v) => !v.has_value).map((v) => v.id).slice(0, 6);
      const onlyGaps = !deltas.length ? by(".after").filter((v) => v.has_value).slice(0, 6).map((v) => v.id) : [];
      const sections = [{ type: "summary", fact_ids: summary.length ? summary : onlyGaps }, { type: "weakest", fact_ids: weakest },
        { type: "risks", fact_ids: risks }, { type: "data_gaps", fact_ids: gaps }];
      return { sections: sections.filter((s) => s.fact_ids.length), comment: null, catalog_digest: digest };
    },
  };

  function renderValue(f, lang, deps) {
    if (f.value === null) return f.missing_reason && f.missing_reason.startsWith("no_source") ? lx(T.no_source, lang) : lx(["нет данных", "дерек жоқ"], lang);
    const unit = f.unit === "m" ? lx(T.m, lang) : lx(T.records, lang);
    return deps.formatValue(f.unit === "m" ? Math.round(f.value) : f.value) + unit;  // округление только при выводе
  }

  function render(plan, built, lang, deps) {
    if (lang !== "ru" && lang !== "kk") throw new Error("lang: ru | kk");
    const lines = [`**${lx(T.header, lang)}.** ${lx(T.scenario, lang)}: ${built.scenario}.`], used = [], sources = new Map();
    for (const s of plan.sections) {
      lines.push(`\n**${lx(T[s.type], lang)}**`);
      for (const fid of s.fact_ids) {
        const f = built.catalog.get(fid);
        const tags = [lx(f.value === null ? ["неизвестно", "белгісіз"] : T.derived, lang)];
        if (f.hypothetical && f.value !== null) tags.push(lx(T.hyp, lang));
        if (f.coverage_complete === false && f.value !== null && f.unit === "m" && fid.endsWith(".before")) tags.push(lx(T.partial, lang));
        lines.push(`- ${f.label[lang]}: ${renderValue(f, lang, deps)} (${tags.join(", ")})`);
        if (f.nearest && fid.endsWith(".before")) sources.set(f.point_ref, f.nearest);
        used.push({ id: fid, value: f.value, unit: f.unit, kind: f.kind, hypothetical: f.hypothetical, point_id: f.point_id,
          coverage_complete: f.coverage_complete, missing_reason: f.missing_reason, nearest_source_id: f.nearest && f.nearest.id });
      }
    }
    if (sources.size) {
      lines.push(`\n**${lx(T.sources, lang)}**`);
      for (const [ref, n] of sources) {
        const flags = n.qa === null ? "" : `; ${lx(T.qa, lang)}: ${n.qa.length ? n.qa.join(", ") : lx(T.noqa, lang)}`;
        lines.push(`- ${lx(L.point, lang)} ${ref}: «${deps.formatValue(String(n.name ?? ""))}» (id ${deps.formatValue(n.id)}${flags})`);
      }
    }
    lines.push("\n" + lx(T.limits, lang));
    return { text: lines.join("\n"), facts_used: used, catalog_digest: plan.catalog_digest, selector: STUB_NAME };
  }

  function explain(result, lang, deps, qa, selector) {
    const built = buildWhatifCatalog(result, deps, qa);
    const sel = selector || StubSelector;
    const accepted = deps.validatePlan(sel.select(catalogView(built.catalog), built.digest), built);
    return { ...render(accepted, built, lang, deps), scenario: built.scenario, digest: built.digest };
  }

  const api = { SCHEMA, STUB_NAME, checkResult, buildWhatifCatalog, whatifDigest, catalogView, StubSelector, render, explain };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_WHATIF_FACTS = api;
})(typeof window !== "undefined" ? window : globalThis);
