/* Main path of the city mode: school accessibility on one slice, «Сейчас / A / B» on the same map.
 * All numbers come from SCHOOL_CASE.compareCase on the current case; the map layers are rebuilt from those rows.
 * Distances are straight lines. Grid points are not residents. Places A/B are hypotheses, not land or projects.
 */
(function () {
  "use strict";
  const SC = window.SCHOOL_CASE, GOV = window.GOVTECH, D = window.CITY_EVIDENCE, F = window.CITY_FACTS;
  if (!SC || !GOV || !D) return;
  const STORE = "govtech.school-case.v1";
  const el = (tag, attrs, text) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v);
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  };
  const sv = (tag, attrs) => {
    const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) e.setAttribute(k, v);
    return e;
  };
  const m = (mm) => (mm === null || mm === undefined ? "нет данных" : Math.round(mm / 1000).toLocaleString("ru-RU") + " м");
  const dm = (mm) => (mm === null || mm === undefined ? "нет данных" : mm === 0 ? "0 м" : (mm < 0 ? "−" : "+") + Math.round(Math.abs(mm) / 1000).toLocaleString("ru-RU") + " м");
  const motion = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 1);

  const S = { city: GOV.state.city, cases: {}, view: "current", diff: false, pick: null, sel: null, card: "start", cardOpen: true, compared: false,
    cmp: null, digest: null, msg: "", userSeq: 1, map: null, pending: false };

  // ---------- case state ----------
  function caseOf(city) {
    if (!S.cases[city]) S.cases[city] = SC.buildCase(D, city, F.qaOf);
    return S.cases[city];
  }
  function recompute() {
    const c = caseOf(S.city);
    S.cmp = SC.compareCase(c, SC.geodesicMatrix(c));
    if (S.digest && S.digest !== S.cmp.case_digest) S.compared = S.compared && false;
    S.digest = S.cmp.case_digest;
    save();
  }
  const plan = (id) => S.cmp && S.cmp.plans.find((p) => p.id === id) || null;
  const viewPlan = () => plan(S.view) || plan("current");
  const cand = (id) => caseOf(S.city).candidates.find((k) => k.id === id) || null;
  const school = (id) => caseOf(S.city).schools.find((s) => s.id === id) || null;
  const target = (id) => school(id) || cand(id);
  const variantLabel = (v) => { const id = caseOf(S.city).variants[v]; return id ? cand(id).label : null; };

  function save() {
    try {
      const c = caseOf(S.city);
      const all = JSON.parse(localStorage.getItem(STORE) || "{}");
      all[S.city] = { snapshot_id: c.snapshot_id, variants: c.variants, threshold_m: c.parameters.threshold_m,
        include_ids: c.parameters.target_policy.include_ids, exclude_ids: c.parameters.target_policy.exclude_ids,
        user: c.candidates.filter((k) => k.kind === "hypothesis"), compared: S.compared };
      localStorage.setItem(STORE, JSON.stringify(all));
    } catch (e) { /* storage unavailable: the case still works for this tab */ }
  }
  function restore(city) {
    try {
      const all = JSON.parse(localStorage.getItem(STORE) || "{}"), r = all[city];
      if (!r) return;
      const c = SC.buildCase(D, city, F.qaOf);
      if (r.snapshot_id !== c.snapshot_id) return;
      c.candidates.push(...(r.user || []).slice(0, SC.LIMITS.candidates - c.candidates.length));
      Object.assign(c.parameters, { threshold_m: r.threshold_m });
      Object.assign(c.parameters.target_policy, { include_ids: r.include_ids || [], exclude_ids: r.exclude_ids || [] });
      c.variants = { A: r.variants?.A ?? null, B: r.variants?.B ?? null };
      SC.validateCase(c);
      S.cases[city] = c; S.compared = !!r.compared;
      S.userSeq = 1 + Math.max(0, ...c.candidates.filter((k) => k.kind === "hypothesis").map((k) => +k.id.slice(1) || 0));
    } catch (e) { delete S.cases[city]; }
  }

  // ---------- DOM ----------
  const strip = el("div", { id: "sc-strip", hidden: true, role: "region", "aria-label": "Доступность школ: город и показатели" });
  const actions = el("div", { id: "sc-actions", hidden: true, role: "toolbar", "aria-label": "Действия сценария" });
  const card = el("aside", { id: "sc-card", hidden: true, "aria-label": "Карточка сценария" });
  const reopen = el("button", { id: "sc-reopen", type: "button", hidden: true }, "Карточка");
  const overlay = sv("svg", { id: "sc-overlay", "aria-hidden": "true" });
  const legend = el("div", { id: "sc-legend", hidden: true });
  document.body.append(strip, actions, card, reopen, legend);
  document.getElementById("map").append(overlay);
  reopen.addEventListener("click", () => { S.cardOpen = true; render(); card.querySelector("button, [tabindex]")?.focus(); });

  function btn(text, onClick, attrs) {
    const b = el("button", { type: "button", ...(attrs || {}) }, text);
    b.addEventListener("click", onClick);
    return b;
  }

  function renderStrip() {
    const p = viewPlan(), cur = plan("current"), c = caseOf(S.city);
    strip.replaceChildren();
    const cities = el("div", { class: "sc-cities", role: "group", "aria-label": "Город" });
    for (const id of D.city_order || ["shymkent", "astana"]) cities.append(btn(D.cities[id].label, () => GOV.switchCity(id), { "aria-pressed": String(id === S.city), "data-city": id }));
    const q = el("div", { class: "sc-q" });
    q.append(el("b", null, "Доступность школ"), el("span", null, "Какие точки участка дальше от школ и какое место A или B это лучше меняет?"));
    const metrics = el("div", { class: "sc-metrics", role: "status", "aria-live": "polite" });
    const thr = c.parameters.threshold_m;
    const chip = (label, value, delta, title) => { const d = el("div", { class: "sc-metric", title }); d.append(el("span", null, label), el("b", null, value), el("i", { class: delta ? delta.cls : "" }, delta ? delta.text : "")); return d; };
    // change against «Сейчас» in whole metres / points (null when unchanged or unknown)
    const delta = (a, b, lowerBetter, unit) => (S.view === "current" || a === null || b === null || a === b ? null
      : { text: (a > b ? "+" : "−") + Math.abs(a - b).toLocaleString("ru-RU") + unit, cls: (a < b) === lowerBetter ? "good" : "bad" });
    const mm2m = (v) => (v === null ? null : Math.round(v / 1000));
    metrics.append(el("span", { class: "sc-view-name" }, p.id === "current" ? "Сейчас" : p.label),
      chip("Среднее до школы", m(p.metrics.mean_distance_mm), delta(mm2m(p.metrics.mean_distance_mm), mm2m(cur.metrics.mean_distance_mm), true, " м"), "Среднее расстояние по прямой от точек сетки до ближайшей школы"),
      chip(`До ${thr.toLocaleString("ru-RU")} м`, `${p.metrics.within_threshold_count} из ${p.metrics.total_origins} точек`, delta(p.metrics.within_threshold_count, cur.metrics.within_threshold_count, false, ""), "Порог — ваш параметр анализа, не норматив. Знаменатель — все точки, включая неизвестные"),
      chip("Дальше всего", m(p.metrics.max_distance_mm), delta(mm2m(p.metrics.max_distance_mm), mm2m(cur.metrics.max_distance_mm), true, " м"), "Самая дальняя точка сетки от ближайшей школы"));
    if (p.metrics.unknown_count) metrics.append(chip("Неизвестно", `${p.metrics.unknown_count} точек`, null, "Для этих точек нет известного расстояния; они не считаются нулём"));
    const adv = btn("Расширенный режим", () => GOV.setSchool(false), { class: "sc-adv", title: "Прежний планировщик: несколько объектов, бюджет в условных единицах, Парето, устойчивость" });
    strip.append(cities, q, metrics, adv);
  }

  function renderActions() {
    const c = caseOf(S.city);
    actions.replaceChildren();
    const steps = el("div", { class: "sc-steps" });
    for (const v of ["A", "B"]) {
      const lab = variantLabel(v);
      const b = btn("", () => setPick(S.pick === v ? null : v), { class: "sc-step sc-pick-" + v, "aria-pressed": String(S.pick === v), id: "sc-pick-" + v });
      b.append(el("span", { class: "sc-badge sc-badge-" + v }, v), el("span", { class: "sc-long" }, S.pick === v ? "Нажмите место на карте" : lab ? lab : `Выбрать место ${v}`),
        el("span", { class: "sc-short" }, S.pick === v ? "На карте…" : lab ? lab.replace("Своё место", "Своё") : "Место"));
      steps.append(b);
    }
    const sg = btn("", suggest, { class: "sc-step", id: "sc-suggest", title: "Правило выбирает одно место из примера: меньше неизвестных, затем меньше сумма расстояний, затем меньше максимум" });
    sg.append(el("span", { class: "sc-long" }, "Подобрать лучшее"), el("span", { class: "sc-short" }, "Лучшее"));
    steps.append(sg);
    const cmpBtn = btn("Сравнить", compare, { class: "sc-step sc-primary", id: "sc-compare", disabled: !(c.variants.A || c.variants.B) });
    steps.append(cmpBtn);
    const seg = el("div", { class: "sc-seg", role: "group", "aria-label": "Что показать на карте" });
    for (const [id, text] of [["current", "Сейчас"], ["A", "A"], ["B", "B"]]) {
      seg.append(btn(text, () => setView(id), { "aria-pressed": String(S.view === id), id: "sc-view-" + id, disabled: id !== "current" && !c.variants[id] }));
    }
    seg.append(btn("Разница", () => { S.diff = !S.diff; render(); }, { "aria-pressed": String(S.diff), id: "sc-diff", disabled: S.view === "current",
      title: "Окрасить точки: кому стало ближе, у кого без изменений, где неизвестно" }));
    actions.append(steps, seg);
  }

  // ---------- card ----------
  function head(title, sub) {
    const h = el("div", { class: "sc-card-head" });
    const t = el("div"); t.append(el("h2", null, title)); if (sub) t.append(el("p", { class: "sc-sub" }, sub));
    h.append(t, btn("×", () => { S.cardOpen = false; render(); reopen.focus(); }, { class: "sc-close", "aria-label": "Скрыть карточку" }));
    return h;
  }
  function dataBox() {
    const c = caseOf(S.city), src = c.sources[0], elig = S.cmp.eligible_school_ids.length;
    const box = el("div", { class: "sc-box" });
    box.append(el("p", null, `Школ в расчёте: ${elig} из ${c.schools.length} записей категории «школа». Остальные — курсы, центры, записи с сомнением QA; их можно включить вручную.`));
    box.append(el("p", { class: "sc-prov" }, `Источник: ${src.title}. Вторичные данные (${src.verification_status}), получено ${String(src.retrieved_at).slice(0, 10)}. Не официальный реестр.`));
    const d = el("details"); d.append(el("summary", null, "Все школьные записи"));
    const ul = el("ul", { class: "sc-list" });
    for (const s of c.schools) {
      const st = SC.targetStatus(c, s);
      const b = btn("", () => select("school", s.id), { class: st.eligible ? "" : "muted" });
      b.append(el("span", { class: "sc-shape " + (st.eligible ? "sc-shape-school" : "sc-shape-excl") }), el("span", null, s.label));
      const li = el("li"); li.append(b); ul.append(li);
    }
    d.append(ul); box.append(d);
    return box;
  }
  function legendItems(parent) {
    const thr = caseOf(S.city).parameters.threshold_m.toLocaleString("ru-RU");
    const pts = S.diff && S.view !== "current" ? [["sc-shape-closer", "Точке стало ближе"], ["sc-shape-same", "Без изменений"], ["sc-shape-unk", "Неизвестно (не 0)"]]
      : [["sc-shape-point", `Точка сетки ≤ ${thr} м — не жители`], ["sc-shape-far", `Точка дальше ${thr} м`]];
    for (const [cls, text] of [["sc-shape-school", "Школа (в расчёте)"], ["sc-shape-excl", "Запись не в расчёте"], ...pts,
      ["sc-shape-cand", "Место-гипотеза для A/B"], ["sc-shape-line", "Связь с ближайшей школой (по прямой)"]]) {
      const s = el("span"); s.append(el("i", { class: "sc-shape " + cls }), document.createTextNode(text)); parent.append(s);
    }
  }
  function startCard() {
    const c = caseOf(S.city);
    card.append(head(D.cities[S.city].label + ": доступность школ", "Участок ≈2×2 км · расстояния по прямой"));
    const steps = el("ol", { class: "sc-howto" });
    for (const t of ["Посмотрите, какие точки дальше от школ (оранжевые квадраты — дальше порога).", "Выберите место A и место B: пунктирные ромбы на карте или своё место внутри рамки.", "Нажмите «Сравнить»: карта и цифры покажут Сейчас / A / B."]) steps.append(el("li", null, t));
    card.append(steps, dataBox());
    const thr = el("label", { class: "sc-thr" }, "Порог анализа, м ");
    const inp = el("input", { type: "number", min: 50, max: 5000, step: 50, value: String(c.parameters.threshold_m), id: "sc-threshold" });
    inp.addEventListener("change", () => {
      const v = Number(inp.value);
      if (!Number.isInteger(v) || v < 50 || v > 5000) { S.msg = "Порог — целое число от 50 до 5000 м."; render(); return; }
      c.parameters.threshold_m = v; S.msg = `Порог изменён на ${v} м. Это ваш параметр, не норматив.`; recompute(); render();
    });
    thr.append(inp, el("small", null, "Ваш параметр для подсчёта «в пределах», не норматив доступности."));
    card.append(thr);
    const lg = el("div", { class: "sc-legend-inline" }); legendItems(lg); card.append(lg);
    const as = el("details", { class: "sc-assume" }); as.append(el("summary", null, "Допущения модели"));
    for (const a of c.model_assumptions) as.append(el("p", null, a));
    card.append(as);
  }
  function pickCard() {
    const c = caseOf(S.city);
    card.append(head(`Место для варианта ${S.pick}`, "Нажмите ромб на карте или любую точку внутри рамки участка"));
    card.append(el("p", { class: "sc-note" }, "Это гипотеза для сравнения расстояний. Свободен ли участок, сколько стоит и можно ли там строить — не проверено."));
    const ul = el("ul", { class: "sc-list sc-cands" });
    for (const k of c.candidates) {
      const other = S.pick === "A" ? "B" : "A";
      const b = btn("", () => assign(S.pick, k.id), { disabled: c.variants[other] === k.id, "aria-pressed": String(c.variants[S.pick] === k.id) });
      b.append(el("span", { class: "sc-shape sc-shape-cand" }), el("span", null, k.label + (k.kind === "hypothesis" ? " (ваше)" : "")));
      const li = el("li"); li.append(b); ul.append(li);
    }
    card.append(ul, btn("Отмена", () => setPick(null), { class: "sc-ghost" }));
  }
  function schoolCard(id) {
    const c = caseOf(S.city), s = school(id), st = SC.targetStatus(c, s), src = c.sources.find((x) => x.id === s.source_ids[0]);
    card.append(head(s.label, st.eligible ? "Школа в расчёте" : "Запись не в расчёте"));
    const dl = el("dl", { class: "sc-dl" });
    const row = (k, v) => dl.append(el("dt", null, k), el("dd", null, v));
    row("Категория (Overture)", s.category); row("Уверенность источника", s.confidence === null ? "нет данных" : s.confidence.toFixed(2));
    row("Допуск к приёму", "неизвестно"); row("Вместимость", "нет данных"); row("Почему " + (st.eligible ? "в расчёте" : "не в расчёте"), st.reason);
    row("Координаты", `${s.lon}, ${s.lat}`); row("Источник", src ? src.title : "не указан"); row("Статус источника", "вторичные данные, не реестр");
    card.append(dl);
    for (const q of F.qaOf(S.city, D.cities[S.city].places.find((p) => p.id === id) || {})) card.append(el("p", { class: "sc-warn" }, q.text));
    const tp = c.parameters.target_policy;
    card.append(btn(st.eligible ? "Не учитывать в расчёте" : "Учитывать в расчёте", () => {
      tp.include_ids = tp.include_ids.filter((x) => x !== id); tp.exclude_ids = tp.exclude_ids.filter((x) => x !== id);
      const def = SC.targetStatus(c, s).eligible;
      if (st.eligible && def) tp.exclude_ids.push(id); else if (!st.eligible && !def) tp.include_ids.push(id);
      S.msg = `«${s.label}» ${st.eligible ? "исключена из" : "включена в"} расчёт. Все цифры пересчитаны.`;
      recompute(); render();
    }, { class: "sc-ghost", id: "sc-toggle-school" }));
    card.append(el("p", { class: "sc-id" }, s.id));
  }
  function originCard(id) {
    const o = caseOf(S.city).origins.find((x) => x.id === id);
    card.append(head(o.label, "Точка сетки анализа: не дом и не жители"));
    const t = el("table", { class: "sc-table" });
    const tr = el("tr"); for (const h of ["", "Ближайшая", "Расстояние", "Изменение"]) tr.append(el("th", null, h)); t.append(tr);
    for (const p of S.cmp.plans.filter((p) => p.id !== "auto")) {
      const r = p.rows.find((x) => x.origin_id === id), tg = r.nearest_target_id && target(r.nearest_target_id);
      const row = el("tr"); row.append(el("th", null, p.id === "current" ? "Сейчас" : p.id), el("td", null, tg ? tg.label : "нет данных"), el("td", null, m(r.after_mm)), el("td", null, p.id === "current" ? "—" : dm(r.delta_mm)));
      t.append(row);
    }
    card.append(t, el("p", { class: "sc-note" }, "Расстояние по прямой до ближайшей школы из расчёта. Реальный путь по улицам длиннее и здесь не считается."));
  }
  function candCard(id) {
    const c = caseOf(S.city), k = cand(id);
    card.append(head(k.label, k.kind === "hypothesis" ? "Ваше место-гипотеза" : "Место из примера (синтетическое)"));
    const dl = el("dl", { class: "sc-dl" });
    const row = (a, b) => dl.append(el("dt", null, a), el("dd", null, b));
    row("Тип", k.kind === "hypothesis" ? "гипотеза пользователя" : "синтетическая сетка 3×4"); row("Участок", "не проверен"); row("Стоимость", "нет данных");
    row("Координаты", `${k.lon}, ${k.lat}`);
    card.append(dl);
    const r = el("div", { class: "sc-row" });
    for (const v of ["A", "B"]) r.append(btn(c.variants[v] === id ? `Это вариант ${v}` : `Сделать вариантом ${v}`, () => assign(v, id), { disabled: c.variants[v] === id, class: "sc-ghost" }));
    if (k.kind === "hypothesis") r.append(btn("Удалить место", () => removeUser(id), { class: "sc-ghost" }));
    card.append(r);
  }
  function explain() {
    const cur = plan("current"), out = [];
    for (const v of ["A", "B"]) {
      const p = plan(v); if (!p) continue;
      const mc = p.metrics, c0 = cur.metrics;
      out.push(`${p.label} (${variantLabel(v)}): ближе стало ${p.closer_count} из ${mc.total_origins} точек; среднее ${m(c0.mean_distance_mm)} → ${m(mc.mean_distance_mm)}; в пределах порога ${c0.within_threshold_count} → ${mc.within_threshold_count} точек; самая дальняя ${m(c0.max_distance_mm)} → ${m(mc.max_distance_mm)}.`);
    }
    return out;
  }
  function resultCard() {
    const c = caseOf(S.city), A = plan("A"), B = plan("B"), auto = plan("auto"), cur = plan("current");
    let title = "Результат сравнения", lead = "";
    if (A && B) {
      const v = SC.verdict(S.cmp, "A", "B");
      if (v.code === "no_gain") { title = "Ни A, ни B не сокращают расстояния"; lead = "Это тоже результат: на этом участке новые места примера не приближают школу ни к одной точке сетки."; }
      else if (v.code === "tie") { title = "A и B дают одинаковый результат"; lead = "По правилу сравнения варианты равны."; }
      else {
        const w = plan(v.winner), l = plan(v.winner === "A" ? "B" : "A");
        title = `Лучше вариант ${v.winner}`;
        lead = `По правилу (меньше неизвестных → меньше сумма расстояний → меньше самое дальнее) ${w.label} выигрывает: сумма меньше на ${m(l.metrics.sum_distance_mm - w.metrics.sum_distance_mm)} по всем точкам.`;
        const notes = [];
        if (l.metrics.within_threshold_count > w.metrics.within_threshold_count) notes.push(`у ${l.label} больше точек в пределах порога (${l.metrics.within_threshold_count} против ${w.metrics.within_threshold_count})`);
        if (l.metrics.max_distance_mm < w.metrics.max_distance_mm) notes.push(`у ${l.label} меньше самое дальнее расстояние (${m(l.metrics.max_distance_mm)})`);
        if (notes.length) lead += " Но " + notes.join("; ") + ": выбор зависит от того, что для вас важнее.";
      }
    } else { const p = A || B; title = p.closer_count ? `${p.label}: ближе для ${p.closer_count} точек` : `${p.label} не сокращает расстояния`; lead = "Выберите второе место, чтобы сравнить два варианта."; }
    card.append(head(title, "Сравнение по прямой · одна карта и один масштаб"));
    card.append(el("p", { class: "sc-lead" }, lead));
    const t = el("table", { class: "sc-table", id: "sc-result" });
    const plans = [cur, A, B].filter(Boolean);
    const hr = el("tr"); hr.append(el("th", null, "")); for (const p of plans) hr.append(el("th", null, p.id === "current" ? "Сейчас" : p.id)); t.append(hr);
    const rows = [["Среднее до школы", (p) => m(p.metrics.mean_distance_mm)], [`В пределах ${c.parameters.threshold_m} м`, (p) => `${p.metrics.within_threshold_count} из ${p.metrics.total_origins}`],
      ["Самая дальняя точка", (p) => m(p.metrics.max_distance_mm)], ["Стало ближе", (p) => (p.id === "current" ? "—" : `${p.closer_count} точек`)], ["Неизвестно", (p) => String(p.metrics.unknown_count)]];
    for (const [name, f] of rows) { const r = el("tr"); r.append(el("th", null, name)); for (const p of plans) r.append(el("td", null, f(p))); t.append(r); }
    card.append(t);
    const ex = el("div", { class: "sc-explain" }); ex.append(el("span", { class: "sc-tag" }, "Объяснение по шаблону из вычисленных чисел (не AI)"));
    for (const line of explain()) ex.append(el("p", null, line));
    if (auto && auto.selected_candidate_ids.length && ![c.variants.A, c.variants.B].includes(auto.selected_candidate_ids[0])) {
      const k = cand(auto.selected_candidate_ids[0]);
      ex.append(el("p", null, `Для справки: среди ${c.candidates.length} мест правило выбирает «${k.label}» — среднее ${m(auto.metrics.mean_distance_mm)} (сейчас ${m(cur.metrics.mean_distance_mm)}).`));
    } else if (auto && !auto.selected_candidate_ids.length) ex.append(el("p", null, "Ни одно место примера не уменьшает сумму расстояний: правило оставляет текущую сеть."));
    card.append(ex);
    const lim = el("details", { class: "sc-assume" }); lim.append(el("summary", null, "Что этот расчёт не говорит"));
    for (const t2 of ["Это расстояние по прямой, не пешеходный маршрут и не время в пути.", "Точки — равномерная сетка, не жители и не дети; доля — от всех точек, не от населения.",
      "Вместимость и допуск к приёму школ неизвестны: ближе — не значит, что есть места.", "Школы за рамкой участка не загружены: у края расстояния могут быть завышены.",
      "Места A/B — гипотезы: участок, стоимость и возможность строительства не проверены."]) lim.append(el("p", null, t2));
    card.append(lim);
    card.append(el("p", { class: "sc-id", title: "Отпечаток входов: меняется при любом изменении данных, мест или порога" }, "case_digest " + S.cmp.case_digest.slice(7, 23)));
  }
  function renderCard() {
    card.replaceChildren();
    if (S.pick) pickCard();
    else if (S.sel && S.sel.type === "school" && school(S.sel.id)) schoolCard(S.sel.id);
    else if (S.sel && S.sel.type === "origin") originCard(S.sel.id);
    else if (S.sel && S.sel.type === "cand" && cand(S.sel.id)) candCard(S.sel.id);
    else if (S.compared && (plan("A") || plan("B"))) resultCard();
    else startCard();
    if (S.sel || (S.compared && S.card !== "start")) {
      const back = btn(S.sel ? (S.compared ? "← К результату" : "← К вопросу") : "← К вопросу", () => { if (S.sel) S.sel = null; else S.compared = false; render(); }, { class: "sc-ghost sc-back" });
      if (!S.pick) card.append(back);
    }
    const st = el("p", { class: "sc-msg", role: "status", "aria-live": "polite", id: "sc-msg" }, S.msg);
    card.append(st);
  }

  // ---------- actions ----------
  function setPick(v) {
    S.pick = v; S.sel = null; S.cardOpen = true;
    if (S.map) S.map.getCanvas().style.cursor = v ? "crosshair" : "";
    S.msg = v ? `Выбор места ${v}: нажмите ромб или точку внутри рамки. Escape — отмена.` : "";
    render();
  }
  function assign(v, id) {
    const c = caseOf(S.city), other = v === "A" ? "B" : "A";
    if (c.variants[other] === id) { S.msg = `Это место уже выбрано как ${other}.`; render(); return; }
    c.variants[v] = id; S.pick = null; S.sel = null; S.view = v; S.diff = true; S.compared = !!(c.variants.A && c.variants.B) || S.compared;
    if (S.map) S.map.getCanvas().style.cursor = "";
    S.msg = `Вариант ${v}: ${cand(id).label}. Карта показывает ${v}; точки окрашены по изменению.`;
    recompute(); render();
  }
  function placeUser(lon, lat) {
    const c = caseOf(S.city), [w, s, e, n] = c.bbox;
    if (!(w <= lon && lon <= e && s <= lat && lat <= n)) { S.msg = "Место вне рамки участка: данных о школах там нет. Выберите точку внутри рамки."; render(); return; }
    if (c.candidates.length >= SC.LIMITS.candidates) { S.msg = `Не больше ${SC.LIMITS.candidates} мест в кейсе. Удалите одно из своих мест.`; render(); return; }
    const id = "u" + S.userSeq++;
    c.candidates.push({ id, label: "Своё место " + id.slice(1), lon: Math.round(lon * 1e6) / 1e6, lat: Math.round(lat * 1e6) / 1e6, kind: "hypothesis", source_ids: [],
      field_provenance: { lon_lat: "пользователь: щелчок по карте" }, qa: [], cost: null, land_status: "unknown" });
    assign(S.pick, id);
  }
  function removeUser(id) {
    const c = caseOf(S.city);
    c.candidates = c.candidates.filter((k) => k.id !== id);
    for (const v of ["A", "B"]) if (c.variants[v] === id) c.variants[v] = null;
    if (!c.variants[S.view]) S.view = "current";
    S.sel = null; S.msg = "Место удалено."; recompute(); render();
  }
  function suggest() {
    const auto = plan("auto"), c = caseOf(S.city);
    if (!auto.selected_candidate_ids.length) { S.msg = "Ни одно место примера не уменьшает сумму расстояний — подсказывать нечего."; render(); return; }
    const id = auto.selected_candidate_ids[0];
    if (c.variants.A === id || c.variants.B === id) { S.msg = `Лучшее по правилу место «${cand(id).label}» уже выбрано.`; render(); return; }
    assign(c.variants.A ? "B" : "A", id);
    S.msg = `Подобрано правилом: «${cand(id).label}». Это минимум суммы расстояний по прямой среди мест примера, не решение о строительстве.`; render();
  }
  function compare() {
    const c = caseOf(S.city);
    if (!c.variants.A && !c.variants.B) { S.msg = "Сначала выберите хотя бы одно место."; render(); return; }
    S.compared = true; S.sel = null; S.pick = null; S.cardOpen = true;
    const v = c.variants.A && c.variants.B ? SC.verdict(S.cmp, "A", "B") : null;
    S.view = v && v.winner ? v.winner : c.variants.A ? "A" : "B"; S.diff = true;
    S.msg = ""; save(); render();
    document.getElementById("sc-card").focus?.();
  }
  function setView(v) { S.view = v; if (v === "current") S.diff = false; render(); }
  function select(type, id) { S.sel = { type, id }; S.pick = null; S.cardOpen = true; S.msg = ""; render(); }

  // ---------- map ----------
  const EMPTY = { type: "FeatureCollection", features: [] };
  function ensureLayers(map) {
    if (map.getSource("sc-links")) return;
    map.addSource("sc-links", { type: "geojson", data: EMPTY });
    map.addSource("sc-schools", { type: "geojson", data: EMPTY });
    map.addLayer({ id: "sc-links-school", type: "line", source: "sc-links", filter: ["==", ["get", "to"], "school"], layout: { "line-cap": "round" },
      paint: { "line-color": "#176b4a", "line-width": ["case", ["get", "hl"], 4, 1.6], "line-opacity": ["case", ["get", "hl"], 0.95, 0.5] } });
    map.addLayer({ id: "sc-links-new", type: "line", source: "sc-links", filter: ["==", ["get", "to"], "candidate"], layout: { "line-cap": "round" },
      paint: { "line-color": "#c06a2b", "line-width": ["case", ["get", "hl"], 4, 2], "line-opacity": ["case", ["get", "hl"], 1, 0.8], "line-dasharray": [1.5, 1.2] } });
    map.addLayer({ id: "sc-schools-excl", type: "circle", source: "sc-schools", filter: ["!", ["get", "eligible"]],
      paint: { "circle-radius": 5, "circle-color": "#ffffff", "circle-stroke-color": "#8f9b95", "circle-stroke-width": 1.6 } });
    map.addLayer({ id: "sc-schools-in", type: "circle", source: "sc-schools", filter: ["get", "eligible"],
      paint: { "circle-radius": ["case", ["get", "sel"], 12, 9], "circle-color": "#176b4a", "circle-stroke-color": "#ffffff", "circle-stroke-width": 3 } });
    map.on("move", schedule);
    map.on("click", (e) => {
      if (!active()) return;
      const hit = map.queryRenderedFeatures(e.point, { layers: ["sc-schools-in", "sc-schools-excl"] })[0];
      if (S.pick) { placeUser(e.lngLat.lng, e.lngLat.lat); return; }
      if (hit) select("school", hit.properties.id);
    });
    map.on("mousemove", (e) => {
      if (!active() || S.pick) return;
      const hit = map.queryRenderedFeatures(e.point, { layers: ["sc-schools-in", "sc-schools-excl"] }).length;
      map.getCanvas().style.cursor = hit ? "pointer" : "";
    });
  }
  const active = () => GOV.active && GOV.school;
  function mapData() {
    const map = S.map; if (!map || !map.getSource("sc-links")) return;
    const show = active(), c = caseOf(S.city), p = viewPlan();
    const vis = show ? "visible" : "none";
    for (const id of ["sc-links-school", "sc-links-new", "sc-schools-excl", "sc-schools-in"]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    if (!show) return;
    const selO = S.sel && S.sel.type === "origin" ? S.sel.id : null, selT = S.sel && S.sel.type !== "origin" ? S.sel.id : null;
    const lines = [];
    for (const r of p.rows) {
      if (!r.nearest_target_id) continue;
      const o = c.origins.find((x) => x.id === r.origin_id), t = target(r.nearest_target_id);
      const isNew = !!cand(r.nearest_target_id);
      lines.push({ type: "Feature", properties: { to: isNew ? "candidate" : "school", hl: r.origin_id === selO || r.nearest_target_id === selT },
        geometry: { type: "LineString", coordinates: [[o.lon, o.lat], [t.lon, t.lat]] } });
    }
    map.getSource("sc-links").setData({ type: "FeatureCollection", features: lines });
    map.getSource("sc-schools").setData({ type: "FeatureCollection", features: c.schools.map((s) => ({ type: "Feature",
      properties: { id: s.id, eligible: SC.targetStatus(c, s).eligible, sel: s.id === selT }, geometry: { type: "Point", coordinates: [s.lon, s.lat] } })) });
  }
  function schedule() {
    if (S.pending) return; S.pending = true;
    requestAnimationFrame(() => { S.pending = false; drawOverlay(); });
  }
  function drawOverlay() {
    overlay.replaceChildren();
    const map = S.map;
    overlay.style.display = active() && map ? "block" : "none";
    if (!active() || !map) return;
    const c = caseOf(S.city), p = viewPlan(), cur = plan("current"), thr = c.parameters.threshold_m * 1000;
    const pt = (lon, lat) => { const q = map.project([lon, lat]); return [q.x, q.y]; };
    const gL = sv("g"), gC = sv("g"), gO = sv("g"), gT = sv("g");
    overlay.append(gL, gC, gO, gT);
    // candidates: dashed diamonds (hypotheses). A/B larger with a letter.
    for (const k of c.candidates) {
      const [x, y] = pt(k.lon, k.lat), v = c.variants.A === k.id ? "A" : c.variants.B === k.id ? "B" : null;
      const r = v ? 13 : 8, sel = S.sel && S.sel.id === k.id;
      const d = sv("path", { d: `M${x} ${y - r}L${x + r} ${y}L${x} ${y + r}L${x - r} ${y}Z`, class: "sc-cand" + (v ? " sc-cand-" + v : "") + (sel ? " sc-sel" : "") + (S.pick ? " sc-pickable" : "") });
      const tt = sv("title"); tt.textContent = k.label + (v ? ` — вариант ${v}` : "") + " (гипотеза)"; d.append(tt);
      d.addEventListener("click", (e) => { e.stopPropagation(); if (S.pick) assign(S.pick, k.id); else select("cand", k.id); });
      gC.append(d);
      if (v) { const t = sv("text", { x, y: y + 4, class: "sc-cand-letter" }); t.textContent = v; gC.append(t); }
    }
    // origins: small squares; colour by distance (or by change in «Разница»).
    for (const r of p.rows) {
      const o = c.origins.find((x) => x.id === r.origin_id), [x, y] = pt(o.lon, o.lat);
      let cls = r.after_mm === null ? "unk" : r.after_mm <= thr ? "near" : "far";
      if (S.diff && S.view !== "current") cls = r.delta_mm === null ? "unk" : r.delta_mm < 0 ? "closer" : "same";
      const sel = S.sel && S.sel.type === "origin" && S.sel.id === o.id;
      const sq = sv("rect", { x: x - 6, y: y - 6, width: 12, height: 12, rx: 2, class: `sc-o sc-o-${cls}` + (sel ? " sc-sel" : "") });
      const tt = sv("title"); tt.textContent = `${o.label}: ${m(r.after_mm)} до ближайшей школы` + (S.view !== "current" ? ` (${dm(r.delta_mm)})` : ""); sq.append(tt);
      sq.addEventListener("click", (e) => { e.stopPropagation(); if (S.pick) { const ll = map.unproject([x, y]); placeUser(ll.lng, ll.lat); } else select("origin", o.id); });
      gO.append(sq);
      if (sel && r.nearest_target_id) {
        const t = target(r.nearest_target_id), [tx, ty] = pt(t.lon, t.lat);
        const lab = sv("text", { x: (x + tx) / 2, y: (y + ty) / 2 - 6, class: "sc-dist" }); lab.textContent = m(r.after_mm); gT.append(lab);
      }
    }
    // school labels only for the selected school (the map stays readable)
    if (S.sel && S.sel.type === "school") { const s = school(S.sel.id); if (s) { const [x, y] = pt(s.lon, s.lat); const t = sv("text", { x: x + 14, y: y + 4, class: "sc-label" }); t.textContent = s.label.slice(0, 40); gT.append(t); } }
    void cur;
  }

  // ---------- render ----------
  function render() {
    const on = active();
    strip.hidden = actions.hidden = legend.hidden = !on;
    card.hidden = !on || !S.cardOpen; reopen.hidden = !on || S.cardOpen;
    document.body.classList.toggle("sc-mode", on);
    if (!on) { overlay.style.display = "none"; mapData(); return; }
    renderStrip(); renderActions(); renderCard();
    legend.replaceChildren(); legendItems(legend);
    mapData(); drawOverlay();
  }

  // ---------- hooks ----------
  GOV.EXT.onMap.push((map) => { S.map = map; ensureLayers(map); render(); });
  GOV.EXT.onActive.push((on) => { if (on && !S.cases[S.city]) { restore(S.city); recompute(); } setPick(null); render(); });
  GOV.EXT.onMode.push(() => render());
  GOV.EXT.onCity.push((city) => {
    S.city = city; S.pick = null; S.sel = null; S.view = "current"; S.diff = false; S.compared = false; S.msg = "";
    if (!S.cases[city]) restore(city);
    recompute();
    const c = caseOf(city);
    if (c.variants.A || c.variants.B) S.msg = "Восстановлены сохранённые варианты этого города. Данные и места другого города не переносятся.";
    setTimeout(render, 0);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && active() && S.pick) { setPick(null); } });
  addEventListener("resize", schedule);
  window.SCHOOL_UI = { state: S, caseOf, recompute, render, assign, compare, setView, select, suggest, plan, exportCase: () => SC.exportCase(caseOf(S.city)) };
  restore(S.city); recompute();
  if (GOV.map) { S.map = GOV.map; ensureLayers(GOV.map); }
  render();
})();
