/* K02 r9: узкий адаптер фактов + шаблонный renderer для «Устойчивость к допущениям» (city-resilience-v1).
 * Вход — ТОЛЬКО результаты движка: evaluateResilience (ручной) и optimizeResilience (обычный/устойчивый, цена, digest).
 * Адаптер ничего не вычисляет, кроме записи значений в факты; renderer формулирует. Шаблон, НЕ LLM, НЕ AI.
 * Русский текст — основной; казахский — черновик, ТРЕБУЕТ языковой проверки носителем.
 * Каталог совместим с web/facts.js сборки (validatePlan: stale_catalog, duplicate_id, null_as_fact).
 * deps = { F: web/facts.js }.  Браузер: window.CITY_RESILIENCE_FACTS.
 */
(function (root) {
  "use strict";
  const PLANS = ["manual", "nominal", "robust"];
  const TEMPLATE = "шаблонное объяснение (детерминированный шаблон по фактам; не LLM и не AI)";
  const KK_DRAFT = "Қазақша мәтін — жоба, тілдік тексеруді қажет етеді.";
  const PL_LABEL = { manual: ["Ручной план", "Қолмен жоспар"], nominal: ["Обычный план (оптимум по среднему без исключений)", "Қалыпты жоспар"],
    robust: ["Устойчивый план (лучший худший случай)", "Тұрақты жоспар"] };
  const M_LABEL = { weighted_mean: ["взвешенное среднее", "өлшенген орташа"], max: ["худшая точка", "ең нашар нүкте"],
    unknown_count: ["точек без расстояния", "қашықтығы жоқ нүктелер"], covered_weight: ["вес в радиусе", "радиустағы салмақ"], cost: ["условная стоимость", "шартты құны"] };
  const lx = (p, lang) => p[lang === "kk" ? 1 : 0];
  const fin = (v) => typeof v === "number" && Number.isFinite(v);
  // Пользовательский/исходный текст (ID случаев, метки, имена записей): вывод — простой текст; UI обязан вставлять его через
  // textContent/экранирование HTML, не innerHTML и не markdown. Здесь только удаляются управляющие символы.
  const txt = (v) => String(v ?? "").replace(/[\u0000-\u001f\u007f]/g, " ");

  function check(cond, F, code, detail) { if (!cond) throw new F.PlanError(code, detail); }

  /** env = нормализованный envelope {sc, cases[{id,label,disabled_source_ids}]} (base первым), names = {source_id: name},
   *  manualEval = evaluateResilience(ручной), opt = optimizeResilience, request = {resilience_problem_digest}. */
  function buildResilienceCatalog(env, manualEval, opt, names, deps, request) {
    const F = deps.F;
    check(opt && typeof opt.resilience_problem_digest === "string", F, "bad_result", "нет resilience_problem_digest");
    check(request && request.resilience_problem_digest === opt.resilience_problem_digest, F, "stale_problem", "результат относится к другой задаче устойчивости");
    check(env.cases[0] && env.cases[0].id === "base" && env.cases[0].disabled_source_ids.length === 0, F, "bad_result", "первым должен быть base без исключений");
    const caseIds = env.cases.map((c) => c.id);
    const plans = { manual: manualEval, nominal: opt.nominal, robust: opt.robust };
    for (const p of PLANS) if (plans[p]) {
      check(JSON.stringify(plans[p].per_case.map((x) => x.case_id)) === JSON.stringify(caseIds), F, "bad_result", `${p}: случаи не совпадают с envelope`);
      for (const w of plans[p].worst_case_ids) check(caseIds.includes(w), F, "bad_result", `${p}: худший случай ${w} не из envelope`);
    }
    check(JSON.stringify(manualEval.selected_ids) === JSON.stringify(env.sc.selected_ids.slice().sort()), F, "stale_explanation", "ручная оценка для другого выбора");
    if (opt.status === "optimal") {
      check(opt.nominal && opt.robust, F, "bad_result", "optimal без обычного/устойчивого плана");
      const nm = opt.nominal.per_case[0].metrics.weighted_mean_mm, rm = opt.robust.per_case[0].metrics.weighted_mean_mm, pr = opt.price_of_robustness_m;
      if (opt.nominal.selected_ids.join() === opt.robust.selected_ids.join()) check(pr === 0, F, "bad_result", "планы совпадают, а цена устойчивости не 0");
      if (nm !== null && rm !== null) check(fin(pr) && Math.abs(pr * 1000 - (rm - nm)) < 1e-6, F, "bad_result", "цена устойчивости не согласована со средними base");
      else check(pr === null, F, "bad_result", "цена при неизвестном среднем должна быть null");
    } else {
      check(!opt.nominal && !opt.robust, F, "bad_result", `статус ${opt.status}: оптимальные планы не заявляются`);
      check(opt.price_of_robustness_m === null || opt.price_of_robustness_m === undefined, F, "bad_result", "цена без optimal");
    }
    const city = "kz." + env.sc.city_id, scenario = `resilience-${env.sc.category.replace(/_/g, "-")}-${opt.resilience_problem_digest.slice(7, 19)}`;
    const cat = new Map();
    const add = (path, value, unit, kind, scope, label, extra = {}) => {
      const id = `${city}/${scenario}/${path}`;
      check(!cat.has(id), F, "duplicate_id", id);
      check(value === null || typeof value === "string" || fin(value), F, "non_finite", `${path}=${value}`);
      for (const l of label) if (/\d/.test(l)) throw new Error(`${path}: подпись с цифрами`);
      cat.set(id, { id, path, city, scenario, value, unit, kind: value === null ? "unknown" : kind, scope, label: { ru: label[0], kk: label[1] },
        hypothetical: false, missing_reason: null, ...extra });
    };
    // случаи: c0 = base, cN — пользовательские (ID/label — текст пользователя, не в подписях фактов)
    env.cases.forEach((c, i) => {
      add(`case.c${i}.excluded_count`, c.disabled_source_ids.length, "count", "user_input", "assumption_case", ["Условно исключено записей", "Шартты түрде алынған жазбалар"], { case_id: c.id });
      add(`case.c${i}.excluded_ids`, c.disabled_source_ids.join(", "), "text", "user_input", "assumption_case", ["Условно исключённые записи", "Шартты түрде алынған жазбалар"],
        { case_id: c.id, case_label: c.label, names: c.disabled_source_ids.map((s) => names[s] ?? null) });
    });
    for (const p of PLANS) {
      const r = plans[p]; if (!r) continue;
      const hyp = r.selected_ids.length > 0;
      add(`plan.${p}.selection`, r.selected_ids.join(", "), "text", "derived", "plan", [`${lx(PL_LABEL[p], "ru")}: кандидаты`, `${lx(PL_LABEL[p], "kk")}: үміткерлер`], { hypothetical: hyp });
      add(`plan.${p}.feasible`, r.feasible ? 1 : 0, "flag", "derived", "plan", [`${lx(PL_LABEL[p], "ru")}: допустим`, `${lx(PL_LABEL[p], "kk")}: рұқсат`], { reasons: r.infeasible_reasons || [] });
      r.per_case.forEach((pc, i) => {
        const m = pc.metrics, unk = m.unknown_count > 0 ? { missing_reason: "unknown_points" } : {};
        for (const [k, v, u] of [["weighted_mean", m.weighted_mean_mm, "mm"], ["max", m.max_mm, "mm"], ["unknown_count", m.unknown_count, "count"],
          ["covered_weight", m.covered_weight, "weight"], ["cost", m.cost, "conditional_units"]])
          add(`case.c${i}.${p}.${k}`, v, u, "derived", "assumption_case", [`${lx(PL_LABEL[p], "ru")}: ${M_LABEL[k][0]}`, `${lx(PL_LABEL[p], "kk")}: ${M_LABEL[k][1]}`],
            { hypothetical: hyp, case_id: env.cases[i].id, ...(k === "weighted_mean" || k === "max" ? unk : {}) });
      });
      const W = r.worst_vector;
      add(`plan.${p}.worst.unknown_count`, W.unknown_count, "count", "derived", "plan", [`${lx(PL_LABEL[p], "ru")}: худший случай, точек без расстояния`, `${lx(PL_LABEL[p], "kk")}: ең нашар жағдай, қашықтығы жоқ`], { hypothetical: hyp });
      add(`plan.${p}.worst.weighted_sum_mm`, W.weighted_sum_mm, "mm_weight", "derived", "plan", [`${lx(PL_LABEL[p], "ru")}: худший случай, сумма взвешенных расстояний`, `${lx(PL_LABEL[p], "kk")}: ең нашар жағдай, өлшенген қосынды`], { hypothetical: hyp });
      add(`plan.${p}.worst.max`, W.max_mm, "mm", "derived", "plan", [`${lx(PL_LABEL[p], "ru")}: худший случай, худшая точка`, `${lx(PL_LABEL[p], "kk")}: ең нашар жағдай, ең нашар нүкте`],
        { hypothetical: hyp, ...(W.max_mm === null ? { missing_reason: "unknown_points" } : {}) });
      add(`plan.${p}.worst.case_ids`, r.worst_case_ids.join(", "), "text", "derived", "plan", [`${lx(PL_LABEL[p], "ru")}: худшие случаи`, `${lx(PL_LABEL[p], "kk")}: ең нашар жағдайлар`]);
    }
    add("price.robustness", opt.price_of_robustness_m ?? null, "m", "derived", "plan", ["Цена устойчивости: рост среднего без исключений", "Тұрақтылық бағасы"],
      { missing_reason: opt.price_of_robustness_m === null || opt.price_of_robustness_m === undefined ? (opt.price_reason || (opt.status === "optimal" ? "unknown" : "not_optimal")) : null, hypothetical: true });
    add("search.evaluated", opt.evaluated, "count", "derived", "search_space", ["Проверено наборов", "Тексерілген жиындар"]);
    add("search.feasible_count", opt.feasible_count, "count", "derived", "search_space", ["Допустимых наборов", "Рұқсат етілген жиындар"]);
    const sel = env.sc.selected_ids.slice().sort();
    const digest = factsDigest(cat, opt.resilience_problem_digest, sel, opt.status, F);
    return { catalog: cat, city, scenario, digest, _sel: sel, resilience_problem_digest: opt.resilience_problem_digest, status: opt.status, reasons: opt.reasons || [], ncases: env.cases.length };
  }

  // Отпечаток по ВСЕМ полям фактов, включая текстовые и вспомогательные (имена, причины): подмена любого факта меняет его.
  function factsDigest(cat, rpd, sel, status, F) {
    const rows = [...cat.values()].map((f) => JSON.stringify([f.id, f.value, f.kind, f.unit, f.scope, f.missing_reason, f.case_id ?? null, f.case_label ?? null,
      f.names ?? null, f.reasons ?? null, f.hypothetical])).sort();
    return F.sha256hex(JSON.stringify(["resilience-facts-v1", rpd, sel, status, rows])).slice(0, 16);
  }
  const view = (b) => [...b.catalog.values()].map((f) => ({ id: f.id, path: f.path, has_value: f.value !== null }));
  // Заглушка выбора (не LLM): подсветить цену устойчивости и худшие векторы; null — только в data_gaps.
  const StubSelector = { name: TEMPLATE, select(v, digest) {
    const pick = (paths) => paths.map((p) => v.find((x) => x.path === p)).filter(Boolean);
    const summary = pick(["price.robustness", "plan.nominal.worst.max", "plan.robust.worst.max", "plan.manual.worst.max"]).filter((x) => x.has_value).map((x) => x.id);
    const risks = pick(["plan.nominal.worst.case_ids", "plan.robust.worst.case_ids", "search.feasible_count"]).filter((x) => x.has_value).map((x) => x.id);
    const gaps = v.filter((x) => !x.has_value && /^(price|plan)\./.test(x.path)).map((x) => x.id).slice(0, 6);
    return { sections: [{ type: "summary", fact_ids: summary }, { type: "risks", fact_ids: risks }, { type: "data_gaps", fact_ids: gaps }].filter((s) => s.fact_ids.length),
      comment: null, catalog_digest: digest }; } };

  const REASON = { unknown_points: ["у части точек нет расстояния", "кейбір нүктелердің қашықтығы жоқ"], unknown_base_mean: ["среднее без исключений неизвестно (есть точки без расстояния)", "ерекшеліксіз орташа белгісіз"],
    infeasible: ["нет допустимого плана", "рұқсат етілген жоспар жоқ"], not_optimal: ["поиск не завершён — оптимум не заявляется", "іздеу аяқталмады"] };
  function val(f, lang, F) {
    if (f.value === null) return lx(["нет данных", "дерек жоқ"], lang) + (f.missing_reason ? ` (${lx(REASON[f.missing_reason] || [f.missing_reason, f.missing_reason], lang)})` : "");
    if (f.unit === "mm") return F.formatValue(Math.round(f.value / 1000)) + " м";
    if (f.unit === "mm_weight") return F.formatValue(Math.round(f.value / 1000)) + lx([" м·вес", " м·салмақ"], lang);
    if (f.unit === "m") return F.formatValue(Math.round(f.value * 10) / 10) + " м";
    if (f.unit === "conditional_units") return F.formatValue(f.value) + lx([" усл. ед.", " шартты бірл."], lang);
    if (f.unit === "text") return f.value === "" ? lx(["нет", "жоқ"], lang) : txt(f.value);
    return F.formatValue(f.value);
  }

  function render(accepted, b, lang, deps, request, caseInfo) {
    const F = deps.F;
    check(request && request.resilience_problem_digest === b.resilience_problem_digest, F, "stale_problem", "объяснение запрошено для другой задачи");
    check(factsDigest(b.catalog, b.resilience_problem_digest, b._sel, b.status, F) === b.digest, F, "tampered_catalog", "каталог фактов изменён после построения");
    const g = (p) => b.catalog.get(`${b.city}/${b.scenario}/${p}`);
    const out = [lx([`**Устойчивость к допущениям — ${TEMPLATE}.**`, `**Болжамдарға тұрақтылық — шаблон (LLM емес).**`], lang)];
    if (lang === "kk") out.push(KK_DRAFT);
    out.push(lx(["Условно исключаем записи из расчёта; это не подтверждение закрытия объектов, не прогноз и не оценка риска.", "Жазбаларды есептен шартты түрде алып тастаймыз; бұл жабылуды растау емес."], lang));
    // случаи и исключения (ID/label/имена — текст пользователя/данных, экранирован)
    out.push("", lx(["**Случаи**", "**Жағдайлар**"], lang));
    const groups = new Map();
    for (let i = 0; i < b.ncases; i++) {
      const e = g(`case.c${i}.excluded_ids`), ids = e.value ? e.value.split(", ") : [];
      const names = ids.slice(0, 5).map((id, j) => `${txt(id)}${e.names[j] ? " «" + txt(e.names[j]) + "»" : ""}`);
      const more = ids.length > 5 ? lx(["; … полный список — в факте excluded_ids и HTML-отчёте", "; … толық тізім — есепте"], lang) : "";
      out.push(`- ${txt(e.case_id)} — «${txt(e.case_label)}»: ` + (i === 0 ? lx(["без исключений", "ерекшеліксіз"], lang) : lx(["исключено ", "алынды "], lang) + `${val(g(`case.c${i}.excluded_count`), lang, F)}: ${names.join("; ")}${more}`));
      if (i > 0) { const k = e.value; groups.set(k, (groups.get(k) || []).concat(e.case_id)); }
    }
    for (const ids of groups.values()) if (ids.length > 1) out.push(lx([`- Случаи ${ids.join(", ")} исключают одинаковые записи — это один и тот же расчёт.`, `- ${ids.join(", ")} жағдайлары бірдей — бір есеп.`], lang));
    if (b.status !== "optimal") {
      out.push("", lx(["**Поиск**", "**Іздеу**"], lang), "- " + lx([`статус ${b.status}: ${(b.reasons || []).map((r) => r.text || r.code).join("; ") || "оптимум не заявляется"}. Ограничения не снимались.`,
        `мәртебе ${b.status}; шектеулер алынбады.`], lang));
    }
    // таблица по случаям
    const present = PLANS.filter((p) => g(`plan.${p}.selection`));
    out.push("", lx(["**Результаты по случаям** (среднее | худшая точка | без расстояния | вес в радиусе)", "**Жағдайлар бойынша нәтижелер**"], lang));
    for (const p of present) {
      const infeasible = g(`plan.${p}.feasible`).value === 0;
      out.push(`${lx(PL_LABEL[p], lang)} (${val(g(`plan.${p}.selection`), lang, F)}, ${val(g(`case.c0.${p}.cost`), lang, F)})` +
        (infeasible ? lx([" — НЕДОПУСТИМ, не рекомендуется: ", " — рұқсат етілмеген: "], lang) + g(`plan.${p}.feasible`).reasons.map((r) => r.text || r.code).join("; ") : "") + ":");
      for (let i = 0; i < b.ncases; i++) out.push(`  - ${txt(g(`case.c${i}.excluded_ids`).case_id)}: ${val(g(`case.c${i}.${p}.weighted_mean`), lang, F)} | ${val(g(`case.c${i}.${p}.max`), lang, F)} | ${val(g(`case.c${i}.${p}.unknown_count`), lang, F)} | ${val(g(`case.c${i}.${p}.covered_weight`), lang, F)}`);
      out.push(lx([`  худший вектор (без расстояния, сумма, худшая точка): ${val(g(`plan.${p}.worst.unknown_count`), lang, F)}, ${val(g(`plan.${p}.worst.weighted_sum_mm`), lang, F)}, ${val(g(`plan.${p}.worst.max`), lang, F)}; худшие случаи: ${val(g(`plan.${p}.worst.case_ids`), lang, F)}`,
        `  ең нашар вектор: ${val(g(`plan.${p}.worst.unknown_count`), lang, F)}, ${val(g(`plan.${p}.worst.weighted_sum_mm`), lang, F)}, ${val(g(`plan.${p}.worst.max`), lang, F)}; ең нашар жағдайлар: ${val(g(`plan.${p}.worst.case_ids`), lang, F)}`], lang));
    }
    // цена устойчивости и совпадение планов
    const same = present.includes("nominal") && present.includes("robust") && g("plan.nominal.selection").value === g("plan.robust.selection").value;
    const price = g("price.robustness");
    out.push("", lx(["**Цена устойчивости**", "**Тұрақтылық бағасы**"], lang));
    if (same) out.push("- " + lx(["Обычный и устойчивый планы совпадают: цена устойчивости ", "Қалыпты және тұрақты жоспарлар бірдей: баға "], lang) + val(price, lang, F) + lx([" — компромисса нет.", "."], lang));
    else if (price.value === null) out.push("- " + val(price, lang, F));
    else out.push("- " + lx([`Устойчивый план увеличивает взвешенное среднее без исключений на ${val(price, lang, F)} ради лучшего худшего случая (сравнение векторов: сначала точки без расстояния, затем сумма, затем худшая точка).`,
      `Тұрақты жоспар ерекшеліксіз орташаны ${val(price, lang, F)} арттырады.`], lang));
    out.push("", lx(["**Отмеченные факты**", "**Белгіленген деректер**"], lang));
    for (const s of accepted.sections) for (const id of s.fact_ids) { const f = b.catalog.get(id); out.push(`- ${f.label[lang]}: ${val(f, lang, F)}`); }
    out.push("", lx(["**Ограничения**", "**Шектеулер**"], lang),
      "- " + lx(["Случаи равноправны: нет вероятностей, «среднего риска» и прогноза кризиса; худший вектор — лексикографический максимум, а не сумма худших компонентов разных случаев.", "Жағдайлар тең: ықтималдық пен тәуекел жоқ."], lang),
      "- " + lx(["Расстояния по прямой в квадрате среза; вес точки — приоритет пользователя, не жители; стоимость условная, не тенге. QA-флаг не доказывает ошибку записи.", "Түзу бойынша қашықтық; салмақ — басымдық; құн шартты."], lang),
      "- " + lx(["Пустые исходные данные в случае не означают отсутствие услуги в городе.", "Бос деректер қалада қызмет жоқ дегенді білдірмейді."], lang));
    return { text: out.join("\n"), template: TEMPLATE, resilience_problem_digest: b.resilience_problem_digest, catalog_digest: accepted.catalog_digest };
  }

  function explain(b, lang, deps, request, selector) {
    const s = selector || StubSelector;
    return render(deps.F.validatePlan(s.select(view(b), b.digest), b), b, lang, deps, request);
  }
  const api = { PLANS, TEMPLATE, KK_DRAFT, buildResilienceCatalog, view, StubSelector, render, explain };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_RESILIENCE_FACTS = api;
})(typeof window !== "undefined" ? window : globalThis);
