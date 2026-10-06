// K02 r9 этап 2: факты и renderer устойчивости (manual/nominal/robust). node tests/s2_resilience.cjs --app-root <d865dd4>
const { F, PL, R, RF, resSolve, test, finish, code } = require("./res_common.cjs");
const fact = (s, p) => s.built.catalog.get(`${s.built.city}/${s.built.scenario}/${p}`);

test("R1_facts_from_engine", "факты = выход движка: worst-векторы, худшие случаи, цена, метрики по случаям", () => {
  const s = resSolve("res_shymkent_school"), mism = [];
  for (const [p, r] of [["manual", s.man], ["nominal", s.opt.nominal], ["robust", s.opt.robust]]) {
    if (fact(s, `plan.${p}.worst.weighted_sum_mm`).value !== r.worst_vector.weighted_sum_mm) mism.push(p + ".W");
    if (fact(s, `plan.${p}.worst.case_ids`).value !== r.worst_case_ids.join(", ")) mism.push(p + ".worst_ids");
    r.per_case.forEach((pc, i) => { if (fact(s, `case.c${i}.${p}.max`).value !== pc.metrics.max_mm) mism.push(`${p}.c${i}.max`); });
  }
  if (fact(s, "price.robustness").value !== s.opt.price_of_robustness_m) mism.push("price");
  return { pass: mism.length === 0, observed: mism };
});
test("R2_all_worst_case_ids_listed", "при равных худших векторах перечислены ВСЕ худшие случаи, отсортированно", () => {
  const s = resSolve("res_shymkent_school", (env) => { const all = env.cases.find((c) => c.id === "все-записи"); env.cases.push({ id: "все-записи-2", label: "Дубль всех", disabled_source_ids: all.disabled_source_ids.slice().reverse() }); });
  const w = fact(s, "plan.nominal.worst.case_ids").value;
  return { pass: w === "все-записи, все-записи-2" && s.text().includes("худшие случаи: все-записи, все-записи-2"), observed: w };
});
test("R3_price_and_same_plans", "цена устойчивости: Шымкент > 0 из движка; Астана — планы совпали, цена 0 и «компромисса нет»", () => {
  const sh = resSolve("res_shymkent_school"), as = resSolve("res_astana_clinic");
  const ok = sh.opt.price_of_robustness_m > 0 && /увеличивает взвешенное среднее без исключений на 98,1 м/.test(sh.text())
    && as.opt.price_of_robustness_m === 0 && /Обычный и устойчивый планы совпадают: цена устойчивости 0 м — компромисса нет/.test(as.text());
  return { pass: ok, observed: [sh.opt.price_of_robustness_m, as.opt.price_of_robustness_m] };
});
test("R4_null_with_reason_not_zero", "пустой ручной выбор + все записи исключены: «нет данных (у части точек нет расстояния)», не 0; null-цена с причиной", () => {
  const s = resSolve("res_shymkent_school", (env) => { env.plan.selected_ids = []; });
  const i = s.norm.cases.findIndex((c) => c.id === "все-записи"), m = fact(s, `case.c${i}.manual.weighted_mean`);
  const line = s.text().split("\n").find((l) => l.startsWith("  - все-записи:"));
  const inf = resSolve("res_synthetic_infeasible"), p = fact(inf, "price.robustness");
  return { pass: m.value === null && m.missing_reason === "unknown_points" && /нет данных \(у части точек нет расстояния\)/.test(line) && !/ 0 м/.test(line)
    && p.value === null && p.missing_reason === "infeasible" && /нет данных \(нет допустимого плана\)/.test(inf.text()), observed: [line, p.missing_reason] };
});
test("R5_excluded_records_listed", "исключённые записи перечислены с ID и именем, дубль случаев отмечен, оговорка «не подтверждение закрытия»", () => {
  const t = resSolve("res_shymkent_school").text();
  return { pass: /исключено 2: 01961e84-815f-4bd1-85c3-6bf1734256ec «Реклама 42»/.test(t) && /Случаи без-ближайшей-север, дубль-север исключают одинаковые записи/.test(t)
    && /не подтверждение закрытия/.test(t) && /полный список — в факте excluded_ids/.test(t) && !/\\\(/.test(t), observed: t.split("\n").slice(4, 8) };
});
test("R6_manual_infeasible_flagged", "недопустимый ручной план помечен «НЕДОПУСТИМ, не рекомендуется» с причиной движка", () => {
  const t = resSolve("res_astana_clinic").text();
  return { pass: /Ручной план \(k-a, k-c, 170 усл\. ед\.\) — НЕДОПУСТИМ, не рекомендуется: стоимость 170/.test(t), observed: t.split("\n").find((l) => /НЕДОПУСТИМ/.test(l)) };
});
test("R7_template_not_llm_kk_draft", "шаблон назван шаблоном (не LLM/AI); kk-текст с пометкой о языковой проверке", () => {
  const s = resSolve("res_astana_clinic"), ru = s.text("ru"), kk = s.text("kk");
  return { pass: /шаблонное объяснение .*не LLM и не AI/.test(ru) && kk.includes(RF.KK_DRAFT) && /тілдік тексеруді қажет етеді/.test(kk), observed: kk.split("\n").slice(0, 2) };
});
test("R8_numbers_from_facts", "числа в таблицах/цене/фактах — значения каталога (ID, метки и имена исключены как текст данных)", () => {
  const bad = {};
  for (const n of ["res_shymkent_school", "res_astana_clinic", "res_synthetic_tie"]) {
    const s = resSolve(n), A = new Set();
    for (const f of s.built.catalog.values()) if (typeof f.value === "number") [f.value, Math.round(f.value / 1000), Math.round(f.value * 10) / 10].forEach((v) => A.add(F.formatValue(v)));
    for (const r of s.man.infeasible_reasons.concat(s.opt.reasons || [])) for (const x of String(r.text).match(/\d+/g) || []) A.add(x);
    const body = s.text().split("**Результаты по случаям**")[1].split("**Ограничения**")[0]
      .replace(/^  - [^:]+:/gm, "").replace(/\(([^()]*), (\d+ усл\. ед\.)\)/g, "($2)")  /* перечень кандидатов = текстовый факт selection */.replace(/худшие случаи: .*$/gm, "").replace(/кандидаты: .*$/gm, "");
    const extra = (body.match(/\d+(?:,\d+)?/g) || []).filter((x) => !A.has(x)); if (extra.length) bad[n] = extra.slice(0, 8);
  }
  return { pass: Object.keys(bad).length === 0, observed: bad };
});
finish("s2_resilience", { build_sha: "d865dd4a124291e10dd0b7bb1d9eada20d34c268", note: "движок устойчивости в BUILD отсутствует; результаты — resilience_ref.js поверх plan.js сборки" });
