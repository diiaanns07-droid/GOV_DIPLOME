/* K02 r8: каталог фактов и шаблонное объяснение для city-plan-v2 (ручной план + mean/minimax/coverage).
 * Вход — только результаты evaluatePlan/optimizePlans (plan_engine.js или совместимого модуля); значения не пересчитываются.
 * Каталог совместим с web/facts.js сборки: {catalog, city, scenario, digest}; план выбора проверяет facts.validatePlan
 * (stale_catalog, duplicate_id, null_as_fact). Объяснение — код по фактам, детерминированная заглушка, не LLM; kk — черновик.
 * deps = { F: web/facts.js } (sha256hex, PlanError, validatePlan, formatValue).
 */
(function (root) {
  "use strict";
  const ROLES = ["baseline", "manual", "mean", "minimax", "coverage"];
  const OBJECTIVES = ["mean", "minimax", "coverage"];
  const STUB = "шаблонное объяснение плана (детерминированная заглушка, не LLM)";
  const KINDS = new Set(["derived", "user_input", "unknown"]);
  const UNITS = new Set(["mm", "m", "conditional_units", "weight", "share", "count", "flag", "text"]);
  const SCOPES = new Set(["selected_control_points", "user_input", "search_space", "analysis_parameter"]);

  const RL = { baseline: ["Без новых объектов", "Жаңа нысандарсыз"], manual: ["Ручной план", "Қолмен жасалған жоспар"],
    mean: ["Оптимум по среднему расстоянию", "Орташа қашықтық бойынша оңтайлы"], minimax: ["Оптимум по худшей точке", "Ең нашар нүкте бойынша оңтайлы"],
    coverage: ["Оптимум по охвату радиуса", "Радиус қамтуы бойынша оңтайлы"] };
  const ML = { weighted_mean: ["взвешенное среднее расстояние по прямой", "түзу бойынша өлшенген орташа қашықтық"],
    max: ["расстояние для худшей точки", "ең нашар нүктеге дейінгі қашықтық"], covered_weight: ["вес точек в радиусе", "радиустағы нүктелер салмағы"],
    coverage_fraction: ["доля веса точек в радиусе", "радиустағы нүктелер салмағының үлесі"], cost: ["условная стоимость", "шартты құны"],
    count: ["число условных объектов", "шартты нысандар саны"], unknown_count: ["точек без расстояния", "қашықтығы жоқ нүктелер"],
    selection: ["выбранные кандидаты", "таңдалған үміткерлер"], feasible: ["допустим", "рұқсат етілген"] };
  const CL = { budget: ["Условный бюджет", "Шартты бюджет"], max_selected: ["Максимум объектов", "Нысандардың ең көп саны"],
    radius: ["Радиус анализа (не норматив доступности)", "Талдау радиусы (қолжетімділік нормативі емес)"],
    required: ["Обязательных кандидатов", "Міндетті үміткерлер"], excluded: ["Исключённых кандидатов", "Алынып тасталған үміткерлер"],
    points: ["Контрольных точек", "Бақылау нүктелері"], total_weight: ["Сумма весов точек (приоритет, не жители)", "Нүктелер салмағының қосындысы (басымдық, тұрғындар емес)"],
    candidates: ["Кандидатных мест", "Үміткер орындар"], sources: ["Исходных записей категории в срезе", "Кесіндідегі санаттың бастапқы жазбалары"],
    evaluated: ["Проверено наборов (полный перебор)", "Тексерілген жиындар (толық іріктеу)"], feasible_count: ["Допустимых наборов", "Рұқсат етілген жиындар"] };

  const lx = (p, lang) => p[lang === "kk" ? 1 : 0];
  const fin = (v) => typeof v === "number" && Number.isFinite(v);

  function makeFact(f) {
    if (!KINDS.has(f.kind) || !UNITS.has(f.unit) || !SCOPES.has(f.scope)) throw new Error(`${f.path}: kind/unit/scope обязательны`);
    if (f.value !== null && typeof f.value !== "string" && !fin(f.value)) throw new Error(`${f.path}: неконечное значение`);
    for (const l of [f.label.ru, f.label.kk]) if (typeof l !== "string" || /\d/.test(l)) throw new Error(`${f.path}: подпись без цифр`);
    return f;
  }

  /** evalManual = evaluatePlan(..., scenario.selected_ids); evalBaseline = evaluatePlan(..., []); opt = optimizePlans(...). */
  function buildPlanCatalog(ctx, sc, evalManual, evalBaseline, opt, deps, ids) {
    const F = deps.F;
    if (!opt || typeof opt.problem_digest !== "string") throw new F.PlanError("bad_result", "нет problem_digest");
    if (ids && ids.problem_digest !== opt.problem_digest) throw new F.PlanError("stale_problem", "результат оптимизации от другой задачи");
    const city = "kz." + sc.city_id, scenario = `plan-${sc.category.replace(/_/g, "-")}-${opt.problem_digest.slice(0, 12)}`;
    const cat = new Map();
    const add = (path, value, unit, kind, scope, label, extra = {}) => {
      const id = `${city}/${scenario}/${path}`;
      if (cat.has(id)) throw new F.PlanError("duplicate_id", id);
      const k = value === null ? "unknown" : kind;
      cat.set(id, makeFact({ id, path, city, scenario, value, unit, kind: k, scope, label: { ru: label[0], kk: label[1] },
        hypothetical: false, missing_reason: null, source: "plan_engine:" + opt.metric_version, ...extra }));
    };
    const cl = (key, value, unit, kind, scope) => add("constraint." + key, value, unit, kind, scope, CL[key]);
    cl("budget", sc.budget, "conditional_units", "user_input", "user_input");
    cl("max_selected", sc.max_selected, "count", "user_input", "user_input");
    cl("radius", sc.coverage_radius_m, "m", "user_input", "analysis_parameter");
    cl("required", sc.required_ids.length, "count", "user_input", "user_input");
    cl("excluded", sc.excluded_ids.length, "count", "user_input", "user_input");
    cl("points", sc.control_points.length, "count", "user_input", "user_input");
    cl("total_weight", sc.control_points.reduce((s, p) => s + p.weight, 0), "weight", "user_input", "user_input");
    cl("candidates", sc.candidates.length, "count", "user_input", "user_input");
    cl("sources", ctx.sources.length, "count", "derived", "search_space");
    cl("evaluated", opt.evaluated, "count", "derived", "search_space");
    cl("feasible_count", opt.feasible_count, "count", "derived", "search_space");

    const plans = { baseline: evalBaseline, manual: evalManual };
    for (const k of OBJECTIVES) plans[k] = opt.objectives[k] ? { selected_ids: opt.objectives[k].selected_ids, metrics: opt.objectives[k].metrics, feasible: true } : null;
    for (const role of ROLES) {
      const p = plans[role];
      if (!p) continue;  // цель отсутствует при infeasible: фактов нет, причина — в constraint/infeasible
      const m = p.metrics, hyp = p.selected_ids.length > 0, scope = "selected_control_points";
      const base = (key, value, unit, extra = {}) => add(`plan.${role}.${key}`, value, unit, "derived", scope,
        [`${RL[role][0]}: ${ML[key][0]}`, `${RL[role][1]}: ${ML[key][1]}`], { hypothetical: hyp, role, ...extra });
      const unk = m.unknown_count > 0 ? { missing_reason: "unknown_points" } : {};
      base("weighted_mean", m.weighted_mean_mm, "mm", unk);
      base("max", m.max_mm, "mm", unk);
      base("covered_weight", m.covered_weight, "weight");
      base("coverage_fraction", m.coverage_fraction, "share");
      base("cost", m.cost, "conditional_units");
      base("count", m.count, "count");
      base("unknown_count", m.unknown_count, "count");
      base("selection", p.selected_ids.join(", "), "text");
      if (role === "manual") base("feasible", p.feasible ? 1 : 0, "flag", { reasons: p.infeasible_reasons || [] });
    }
    // Разности между планами — факты каталога (рендерер их не вычисляет). Только для разных наборов и известных значений.
    const pm = (r) => plans[r] && plans[r].metrics, same = (a, b) => plans[a] && plans[b] && plans[a].selected_ids.join() === plans[b].selected_ids.join();
    const cmpAdd = (path, a, b, value, unit, label) => add(`compare.${path}`, value, unit, "derived", "selected_control_points", label,
      { hypothetical: true, missing_reason: value === null ? "unknown_points" : null, pair: [a, b] });
    if (pm("mean") && pm("minimax") && !same("mean", "minimax")) {
      const d1 = pm("mean").max_mm === null || pm("minimax").max_mm === null ? null : pm("mean").max_mm - pm("minimax").max_mm;
      const d2 = pm("mean").weighted_mean_mm === null || pm("minimax").weighted_mean_mm === null ? null : pm("minimax").weighted_mean_mm - pm("mean").weighted_mean_mm;
      cmpAdd("minimax_vs_mean.max_reduction", "minimax", "mean", d1, "mm", ["План по худшей точке: сокращение худшей точки", "Ең нашар нүкте жоспары: ең нашар нүктенің қысқаруы"]);
      cmpAdd("minimax_vs_mean.mean_increase", "minimax", "mean", d2, "mm", ["План по худшей точке: рост взвешенного среднего", "Ең нашар нүкте жоспары: өлшенген орташаның өсуі"]);
    }
    if (pm("mean") && pm("coverage") && !same("mean", "coverage")) {
      cmpAdd("coverage_vs_mean.weight_gain", "coverage", "mean", pm("coverage").covered_weight - pm("mean").covered_weight, "weight", ["План по охвату: прирост веса в радиусе", "Қамту жоспары: радиустағы салмақ өсімі"]);
      const d = pm("mean").weighted_mean_mm === null || pm("coverage").weighted_mean_mm === null ? null : pm("coverage").weighted_mean_mm - pm("mean").weighted_mean_mm;
      cmpAdd("coverage_vs_mean.mean_increase", "coverage", "mean", d, "mm", ["План по охвату: рост взвешенного среднего", "Қамту жоспары: өлшенген орташаның өсуі"]);
    }
    if (pm("manual") && pm("mean") && pm("manual").cost !== pm("mean").cost)
      cmpAdd("manual_vs_mean.cost_difference", "manual", "mean", pm("manual").cost - pm("mean").cost, "conditional_units", ["Ручной план минус оптимум по среднему: стоимость", "Қолмен жоспар минус орташа оңтайлы: құны"]);

    // Чувствительность к бюджету [0, ⌊B/2⌋, B] и Парето (стоимость → взвешенное среднее): только из результата optimizePlans.
    const tw = sc.control_points.reduce((s, p) => s + p.weight, 0);
    (opt.sensitivity || []).forEach((r, i) => {
      const lab = (a, b) => [a, b];
      add(`sensitivity.s${i + 1}.budget`, r.budget, "conditional_units", "user_input", "user_input", lab("Вариант бюджета", "Бюджет нұсқасы"));
      add(`sensitivity.s${i + 1}.status`, r.status, "text", "derived", "search_space", lab("Статус поиска", "Іздеу мәртебесі"));
      const m = r.objectives && r.objectives.mean ? r.objectives.mean.metrics : null;
      add(`sensitivity.s${i + 1}.mean_weighted_mean`, m ? m.weighted_mean_mm : null, "mm", "derived", "selected_control_points",
        lab("Оптимум по среднему: взвешенное среднее", "Орташа бойынша оңтайлы: өлшенген орташа"), { hypothetical: !!(m && m.count), missing_reason: m ? (m.weighted_mean_mm === null ? "unknown_points" : null) : "infeasible" });
      add(`sensitivity.s${i + 1}.mean_cost`, m ? m.cost : null, "conditional_units", "derived", "selected_control_points",
        lab("Оптимум по среднему: условная стоимость", "Орташа бойынша оңтайлы: шартты құны"), { missing_reason: m ? null : "infeasible" });
    });
    (opt.pareto || []).forEach((q, i) => {
      add(`pareto.p${i + 1}.cost`, q.cost, "conditional_units", "derived", "selected_control_points", ["Парето: условная стоимость", "Парето: шартты құны"], { hypothetical: q.selected_ids.length > 0 });
      add(`pareto.p${i + 1}.weighted_mean`, q.weighted_sum_mm / tw, "mm", "derived", "selected_control_points", ["Парето: взвешенное среднее", "Парето: өлшенген орташа"], { hypothetical: q.selected_ids.length > 0 });
      add(`pareto.p${i + 1}.selection`, q.selected_ids.join(", "), "text", "derived", "selected_control_points", ["Парето: кандидаты", "Парето: үміткерлер"], { hypothetical: q.selected_ids.length > 0 });
    });
    const meta = { problem_digest: opt.problem_digest, status: opt.status, infeasible_reasons: opt.infeasible_reasons || [],
      manual_reasons: evalManual.infeasible_reasons || [], sensitivity: opt.sensitivity || [], pareto: opt.pareto || [], exact: opt.exact === true,
      sources_empty: ctx.sources.length === 0, city_id: sc.city_id, category: sc.category, source_snapshot: sc.source_snapshot };
    const rows = [...cat.values()].map((f) => [f.id, f.value === null ? null : String(f.value), f.kind, f.unit, f.scope, f.hypothetical, f.missing_reason])
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    const digest = F.sha256hex(JSON.stringify(["plan-facts-v1", opt.problem_digest, sc.selected_ids.slice().sort(), rows, meta.status])).slice(0, 16);
    return { catalog: cat, city, scenario, digest, problem_digest: opt.problem_digest, meta };
  }

  const view = (built) => [...built.catalog.values()].map((f) => ({ id: f.id, path: f.path, has_value: f.value !== null, role: f.role || null }));

  // Заглушка выбора: какие факты подсветить. Разделы — из закрытого списка facts.js.
  const StubSelector = {
    name: STUB,
    select(v, digest) {
      const pick = (role, keys) => keys.map((k) => v.find((x) => x.path === `plan.${role}.${k}` && x.has_value)).filter(Boolean).map((x) => x.id);
      const summary = [...pick("manual", ["weighted_mean", "max", "cost"]), ...pick("mean", ["weighted_mean", "max", "cost"])];
      const weakest = [...pick("minimax", ["max", "weighted_mean"]), ...pick("coverage", ["covered_weight", "weighted_mean"])].slice(0, 6);
      const risks = ["constraint.budget", "constraint.radius", "constraint.feasible_count"].map((p) => v.find((x) => x.path === p)).filter(Boolean).map((x) => x.id);
      const gaps = v.filter((x) => !x.has_value).map((x) => x.id).slice(0, 6);
      const sections = [{ type: "summary", fact_ids: summary.slice(0, 6) }, { type: "weakest", fact_ids: weakest }, { type: "risks", fact_ids: risks }, { type: "data_gaps", fact_ids: gaps }];
      return { sections: sections.filter((s) => s.fact_ids.length), comment: null, catalog_digest: digest };
    },
  };

  // ---------- рендерер ----------
  const T = {
    header: ["Сравнение планов (значения из расчётного модуля; объекты условные)", "Жоспарларды салыстыру (мәндер есептеу модулінен; нысандар шартты)"],
    table: ["План | среднее | худшая точка | вес в радиусе | условная стоимость | объекты", "Жоспар | орташа | ең нашар нүкте | радиустағы салмақ | шартты құны | нысандар"],
    same: ["Совпадают по набору объектов", "Нысандар жиыны бойынша сәйкес"], none: ["нет", "жоқ"], unknown: ["неизвестно", "белгісіз"],
    m: [" м", " м"], ue: [" усл. ед.", " шартты бірл."],
    trade: ["Компромиссы", "Ымыралар"], infeasible: ["Невыполнимые условия", "Орындалмайтын шарттар"],
    highlight: ["Отмеченные факты", "Белгіленген деректер"], limits: ["Ограничения", "Шектеулер"],
    stale: ["Объяснение отклонено: оно построено для другой задачи (problem digest изменился).", "Түсіндірме қабылданбады: ол басқа есепке құрылған."],
  };
  const LIMITS = [
    ["Расстояния — по прямой (гаверсинус) до записей в сохранённом квадрате; не время пешком, не транспорт и не ближайшее учреждение города.", "Қашықтықтар — сақталған шаршыдағы жазбаларға дейін түзу бойынша; жаяу уақыт емес."],
    ["Веса точек — приоритет пользователя, не численность жителей; радиус — параметр анализа, не норматив доступности.", "Нүкте салмақтары — пайдаланушы басымдығы, тұрғындар саны емес; радиус — талдау параметрі."],
    ["Стоимости и бюджет условные, не тенге и не смета; вывод о снижении реальных расходов не делается.", "Құны мен бюджет шартты, теңге емес; нақты шығындар туралы қорытынды жасалмайды."],
    ["Вместимость, нагрузка, население и социальный эффект не моделировались: из этих чисел нельзя сделать вывод, что объектов достаточно или услуга улучшится.", "Сыйымдылық, жүктеме, халық және әлеуметтік әсер модельденбеді."],
    ["Оптимум найден полным перебором только среди введённых кандидатных мест и условий — это не лучший план города.", "Оңтайлы жоспар тек енгізілген үміткер орындар арасында толық іріктеумен табылды — бұл қаланың ең жақсы жоспары емес."],
  ];
  const REASON = {
    over_budget: (r, lang) => lang === "kk" ? `құны ${r.cost} > бюджет ${r.budget}` : `стоимость ${r.cost} больше бюджета ${r.budget}`,
    too_many_selected: (r, lang) => lang === "kk" ? `нысандар ${r.count} > ${r.max_selected}` : `объектов ${r.count}, допустимо не больше ${r.max_selected}`,
    missing_required: (r, lang) => (lang === "kk" ? "міндетті үміткерлер таңдалмаған: " : "не выбраны обязательные кандидаты: ") + r.ids.join(", "),
    excluded_selected: (r, lang) => (lang === "kk" ? "алынып тасталған үміткерлер таңдалған: " : "выбраны исключённые кандидаты: ") + r.ids.join(", "),
    no_feasible_subset: (r, lang) => lang === "kk" ? "рұқсат етілген жиын жоқ" : "нет ни одного допустимого набора",
  };

  function fmtVal(f, lang, F) {
    if (f.value === null) return lx(T.unknown, lang);
    if (f.unit === "mm") return F.formatValue(Math.round(f.value / 100) / 10) + lx(T.m, lang);  // показ в м, 0,1 м
    if (f.unit === "conditional_units") return F.formatValue(f.value) + lx(T.ue, lang);
    if (f.unit === "share") return F.formatValue(Math.round(f.value * 1000) / 1000);
    if (f.unit === "m") return F.formatValue(f.value) + lx(T.m, lang);
    if (f.unit === "text") return f.value === "" ? lx(T.none, lang) : F.formatValue(f.value);
    return F.formatValue(f.value);
  }

  function render(accepted, built, lang, deps, request) {
    const F = deps.F;
    if (lang !== "ru" && lang !== "kk") throw new Error("lang: ru | kk");
    if (!request || request.problem_digest !== built.problem_digest) throw new F.PlanError("stale_problem", lx(T.stale, "ru"));
    const get = (path) => built.catalog.get(`${built.city}/${built.scenario}/${path}`);
    const out = [`**${lx(T.header, lang)}.** ${built.scenario}.`, "", lx(T.table, lang)];
    const present = ROLES.filter((r) => get(`plan.${r}.cost`));
    for (const r of present) {
      const cell = (k) => fmtVal(get(`plan.${r}.${k}`), lang, F);
      const tw = get("constraint.total_weight").value;
      const flag = r === "manual" && get("plan.manual.feasible").value === 0 ? lx([" (недопустим)", " (рұқсат етілмеген)"], lang) : "";
      out.push(`${lx(RL[r], lang)}${flag} | ${cell("weighted_mean")} | ${cell("max")} | ${cell("covered_weight")} / ${F.formatValue(tw)} | ${cell("cost")} | ${cell("selection")}`);
    }
    // Совпадающие победители: один набор — одно решение, а не три разных.
    const sel = (r) => (get(`plan.${r}.selection`) || {}).value;
    const groups = [];
    for (const r of OBJECTIVES.filter((x) => present.includes(x))) { const g = groups.find((x) => sel(x[0]) === sel(r)); g ? g.push(r) : groups.push([r]); }
    for (const g of groups) if (g.length > 1) out.push(`\n${lx(T.same, lang)}: ${g.map((r) => lx(RL[r], lang)).join(" = ")} (${fmtVal(get(`plan.${g[0]}.selection`), lang, F)}).`);
    // Компромиссы: значения — факты compare.* каталога, текст — шаблон.
    const trade = [];
    const cv = (p) => get("compare." + p);
    const meter = (f) => F.formatValue(Math.round(Math.abs(f.value) / 100) / 10) + lx(T.m, lang);
    const mr = cv("minimax_vs_mean.max_reduction"), mi = cv("minimax_vs_mean.mean_increase");
    if (mr && mi && mr.value !== null && mi.value !== null) trade.push(lang === "kk"
      ? `Ең нашар нүкте бойынша жоспар ең нашар нүктені ${meter(mr)} жақсартады, бірақ орташа қашықтықты ${meter(mi)} ұлғайтады.`
      : `План по худшей точке сокращает расстояние для худшей точки на ${meter(mr)}, но увеличивает взвешенное среднее на ${meter(mi)}.`);
    const wg = cv("coverage_vs_mean.weight_gain"), ci = cv("coverage_vs_mean.mean_increase");
    if (wg) trade.push(lang === "kk"
      ? `Қамту бойынша жоспар радиустағы салмақты ${F.formatValue(wg.value)} арттырады` + (ci && ci.value !== null ? `, орташа қашықтық ${meter(ci)} өзгереді.` : ".")
      : `План по охвату добавляет ${F.formatValue(wg.value)} веса точек в радиусе` + (ci && ci.value !== null ? `, взвешенное среднее хуже на ${meter(ci)}.` : "."));
    const cd = cv("manual_vs_mean.cost_difference");
    if (cd) trade.push(lang === "kk" ? `Қолмен жасалған жоспар орташа бойынша оңтайлыдан ${F.formatValue(Math.abs(cd.value))} шартты бірлікке ${cd.value > 0 ? "қымбат" : "арзан"}.`
      : `Ручной план ${cd.value > 0 ? "дороже" : "дешевле"} оптимума по среднему на ${F.formatValue(Math.abs(cd.value))} усл. ед.`);
    if (trade.length) out.push(`\n**${lx(T.trade, lang)}**`, ...trade.map((t) => "- " + t));
    // Невыполнимость: ручной план и задача целиком.
    const inf = [];
    const manualF = get("plan.manual.feasible");
    if (manualF && manualF.value === 0) inf.push((lang === "kk" ? "Қолмен жасалған жоспар: " : "Ручной план: ") + manualF.reasons.map((r) => REASON[r.code](r, lang)).join("; "));
    if (built.meta.status === "infeasible") inf.push((lang === "kk" ? "Есеп: " : "Задача: ") + built.meta.infeasible_reasons.map((r) => REASON[r.code](r, lang)).join("; ")
      + (lang === "kk" ? ". Шектеулер үнсіз алынбайды." : ". Ограничения не снимаются молча."));
    if (inf.length) out.push(`\n**${lx(T.infeasible, lang)}**`, ...inf.map((t) => "- " + t));
    // Изменение бюджета (те же кандидаты, веса и ограничения).
    const sens = [...built.catalog.values()].filter((f) => /^sensitivity\.s\d+\.budget$/.test(f.path));
    if (sens.length) {
      out.push(`\n**${lx(["Изменение условного бюджета (те же кандидаты и веса)", "Шартты бюджетті өзгерту (сол үміткерлер мен салмақтар)"], lang)}**`);
      for (const b of sens) {
        const k = b.path.replace(/\.budget$/, ""), st = get(k + ".status").value;
        out.push(`- ${fmtVal(b, lang, F)}: ` + (st === "infeasible" ? lx(["нет допустимого плана", "рұқсат етілген жоспар жоқ"], lang)
          : `${lx(["оптимум по среднему", "орташа бойынша оңтайлы"], lang)} ${fmtVal(get(k + ".mean_weighted_mean"), lang, F)}, ${fmtVal(get(k + ".mean_cost"), lang, F)}`));
      }
    }
    const par = [...built.catalog.values()].filter((f) => /^pareto\.p\d+\.cost$/.test(f.path));
    if (par.length) {
      out.push(`\n**${lx(["Парето: стоимость → взвешенное среднее (только планы без неизвестных точек)", "Парето: құны → өлшенген орташа"], lang)}**`);
      for (const c of par) { const k = c.path.replace(/\.cost$/, ""); out.push(`- ${fmtVal(c, lang, F)} → ${fmtVal(get(k + ".weighted_mean"), lang, F)} (${fmtVal(get(k + ".selection"), lang, F)})`); }
    }
    if (built.meta.sources_empty) out.push("\n- " + (lang === "kk" ? "Кесіндіде бастапқы жазбалар жоқ: бұл қалада қызмет жоқ дегенді білдірмейді." : "В срезе нет исходных записей категории: это не доказывает отсутствие услуги в городе."));
    // Отмеченные факты по принятому плану селектора (проверен facts.validatePlan).
    out.push(`\n**${lx(T.highlight, lang)}**`);
    for (const s of accepted.sections) for (const fid of s.fact_ids) { const f = built.catalog.get(fid); out.push(`- ${f.label[lang]}: ${fmtVal(f, lang, F)}`); }
    out.push(`\n**${lx(T.limits, lang)}**`, ...LIMITS.map((p) => "- " + lx(p, lang)));
    return { text: out.join("\n"), selector: STUB, problem_digest: built.problem_digest, catalog_digest: accepted.catalog_digest };
  }

  function explain(built, lang, deps, request, selector) {
    const s = selector || StubSelector;
    const accepted = deps.F.validatePlan(s.select(view(built), built.digest), built);
    return render(accepted, built, lang, deps, request);
  }

  const api = { ROLES, OBJECTIVES, STUB, buildPlanCatalog, view, StubSelector, render, explain };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_PLAN_FACTS = api;
})(typeof window !== "undefined" ? window : globalThis);
