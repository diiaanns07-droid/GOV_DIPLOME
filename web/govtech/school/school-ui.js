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
  const pts = (n) => { const a = n % 10, b = n % 100; return n + " " + (a === 1 && b !== 11 ? "точка" : a >= 2 && a <= 4 && (b < 12 || b > 14) ? "точки" : "точек"); };
  const motion = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 1);

  const S = { city: GOV.state.city, cases: {}, view: "current", diff: false, pick: null, sel: null, card: "start", cardOpen: true, compared: false,
    cmp: null, mx: null, digest: null, msg: "", userSeq: 1, map: null, pending: false, pkg: {}, loading: true, graphs: {} };
  const RT = window.K03_ROUTING, RA = window.K03_SCHOOL_ROUTING;
  // Texts of the K03 integration note (section 3): never replaced by stronger wording.
  const METHOD_TEXT = { geodesic: "по прямой — не маршрут", "pedestrian-v1-strict": "маршрут по пешеходным рёбрам OSM/Overture (не проверено на месте)",
    "pedestrian-v1-exploratory": "маршрут по неполным данным (не гарантированно доступный пешеходный путь)" };
  const methodKey = (c) => c.parameters.distance_method === "geodesic" ? "geodesic" : c.parameters.routing_policy_id;
  // Prepared case packages, served byte-identical (see school/SCHOOL_MANIFEST.json). A city without a package, or with a
  // package that fails validation/binding to the loaded slice, uses the reproducible case built from the slice.
  const PACKAGES = { shymkent: { case: "cases/shymkent.case.json", meta: "cases/shymkent.case.meta.json", by: "K01, раунд 10" },
    astana: { case: "cases/astana.case.json", meta: "cases/astana.match-review.json", by: "K10, раунд 10" } };
  const known = () => Object.values(S.pkg).filter((p) => p.case).map((p) => ({ snapshot_id: p.case.snapshot_id, city_id: p.case.city_id }));

  // ---------- case state ----------
  const inFrame = (c, x) => c.bbox[0] <= x.lon && x.lon <= c.bbox[2] && c.bbox[1] <= x.lat && x.lat <= c.bbox[3];
  function freshCase(city) {
    const p = S.pkg[city];
    return p && p.case ? JSON.parse(JSON.stringify(p.case)) : SC.buildCase(D, city, F.qaOf);
  }
  function caseOf(city) {
    if (!S.cases[city]) S.cases[city] = freshCase(city);
    return S.cases[city];
  }
  async function loadPackages() {
    // every package must match the sha256 recorded in SCHOOL_MANIFEST.json before it is used
    let manifest = null;
    try { const r = await fetch("/govtech/school/SCHOOL_MANIFEST.json"); if (r.ok) manifest = await r.json(); } catch (e) { manifest = null; }
    const shaOf = (file) => { const it = manifest && manifest.cases.find((x) => x.file === file); return it ? it.sha256 : null; };
    const getChecked = async (file) => {
      const res = await fetch("/govtech/school/" + file);
      if (!res.ok) throw new Error(file + ": HTTP " + res.status);
      const text = await res.text(), want = shaOf(file);
      if (!want || F.sha256hex(text) !== want) throw new Error(file + ": sha256 не совпадает с SCHOOL_MANIFEST.json");
      return text;
    };
    for (const [city, f] of Object.entries(PACKAGES)) {
      try {
        const text = await getChecked(f.case);
        const raw = SC.normalizeCase(JSON.parse(text));
        const c = SC.importCase(text, D, [{ snapshot_id: raw.snapshot_id, city_id: raw.city_id }]);
        let meta = null;
        try { meta = JSON.parse(await getChecked(f.meta)); } catch (e) { meta = null; }
        S.pkg[city] = { case: c, meta, by: f.by, bind: SC.bindToSlice(c, D, known().concat([{ snapshot_id: c.snapshot_id, city_id: c.city_id }])) };
      } catch (e) { S.pkg[city] = { error: (e.code ? e.code + ": " : "") + (e.detail || e.message) }; }
    }
  }
  // Street graph of a city (K03, ODbL): loaded on first use, graph_sha256 verified against its content before use.
  function ensureGraph(city) {
    const g = S.graphs[city] || (S.graphs[city] = {});
    if (g.G || g.error) return Promise.resolve(g);
    if (!g.promise) g.promise = fetch("/govtech/k03/" + city + ".graph.json").then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then((raw) => { g.G = RT.prepare(raw, { sha256hex: F.sha256hex }); return g; }, (e) => { g.error = (e.code ? e.code + ": " : "") + (e.detail || e.message); return g; })
      .catch((e) => { g.error = (e.code ? e.code + ": " : "") + (e.detail || e.message); return g; });
    return g.promise;
  }
  function matrixOf(c) {
    if (c.parameters.distance_method === "geodesic") return SC.geodesicMatrix(c);
    const g = S.graphs[c.city_id];
    if (!g || !g.G) return null;  // never a straight line instead of a missing network matrix
    return RA.distanceMatrix(c, g.G);
  }
  function setMethod(key) {
    const c = caseOf(S.city), city = S.city;
    if (key === methodKey(c)) return;
    if (key === "geodesic") {
      Object.assign(c.parameters, { distance_method: "geodesic", routing_policy_id: null }); delete c.parameters.routing;
      S.msg = "Расстояния по прямой. Это не маршрут."; recompute(); render(); return;
    }
    if (!RT || !RA) { S.msg = "Модуль маршрутов не загружен: остаётся расчёт по прямой."; render(); return; }
    S.msg = "Загружаем сеть улиц среза…"; render();
    ensureGraph(city).then((g) => {
      if (S.city !== city) return;
      if (g.error) { S.msg = "Сеть улиц не загружена (" + g.error + "). Расчёт по прямой не подменяет маршрут: метод не изменён."; render(); return; }
      Object.assign(c.parameters, { distance_method: "pedestrian-v1", routing_policy_id: key, routing: { graph_sha256: g.G.g.graph_sha256, policy_sha256: g.G.g.policy_sha256, max_snap_m: g.G.g.max_snap_m } });
      S.msg = "Расстояния: " + METHOD_TEXT[key] + ". Точки без известного пути — «неизвестно», не 0.";
      recompute(); render();
    });
  }
  function recompute() {
    const c = caseOf(S.city);
    const mx = matrixOf(c);
    if (!mx) {  // pedestrian case restored before its graph is loaded
      S.cmp = null; S.mx = null;
      const city = S.city;
      ensureGraph(city).then((g) => {
        if (S.city !== city) return;
        if (g.error) { Object.assign(c.parameters, { distance_method: "geodesic", routing_policy_id: null }); delete c.parameters.routing; S.msg = "Сеть улиц не загружена (" + g.error + "): кейс переведён на расчёт по прямой, это видно в подписи."; }
        else if (g.G.g.graph_sha256 !== c.parameters.routing.graph_sha256) { Object.assign(c.parameters, { distance_method: "geodesic", routing_policy_id: null }); delete c.parameters.routing; S.msg = "Сохранённый кейс ссылается на другой граф улиц: переведён на расчёт по прямой."; }
        recompute(); render();
      });
      return;
    }
    S.mx = mx;
    S.cmp = SC.compareCase(c, mx);
    S.digest = S.cmp.case_digest;
    save();
  }
  const plan = (id) => S.cmp && S.cmp.plans.find((p) => p.id === id) || null;
  const viewPlan = () => plan(S.view) || plan("current");
  const cand = (id) => caseOf(S.city).candidates.find((k) => k.id === id) || null;
  const school = (id) => caseOf(S.city).schools.find((s) => s.id === id) || null;
  const target = (id) => school(id) || cand(id);
  // Package places keep their own labels («Гипотетическое место A…») in the card; on the map/buttons they are numbered,
  // so that a package label «A» is never confused with the user's variant A.
  function lab(t) {
    if (!t) return "нет данных";
    const pk = S.pkg[S.city] && S.pkg[S.city].case, i = pk ? pk.candidates.findIndex((k) => k.id === t.id) : -1;
    return i >= 0 ? "Место " + (i + 1) : t.label;
  }
  const variantLabel = (v) => { const id = caseOf(S.city).variants[v]; return id ? lab(cand(id)) : null; };
  // Records of the slice category «school» that are not targets of the case: shown on the map with the reason.
  function excludedRecords() {
    const c = caseOf(S.city), meta = S.pkg[S.city] && S.pkg[S.city].case && S.pkg[S.city].meta, inCase = new Set(c.schools.map((s) => s.id.replace(/^overture:/, "")));
    const reasons = new Map(((meta && meta.excluded_school_records) || []).map((e) => [e.id.replace(/^overture:/, ""), e.reason]));
    // K10 match-review: slice POI records attached to a package school are in the case under the package ID
    for (const r of (meta && meta.poi_records) || []) if (r.in_app_slice) {
      if (r.decision === "attach" || r.decision === "include_meta_only") inCase.add(r.record_id);
      else reasons.set(r.record_id, `${r.decision === "not_school" ? "не школа" : r.decision === "conflict_not_target" ? "конфликт источников, не цель" : r.decision}: ${r.reason || ""}`);
    }
    return D.cities[S.city].places.filter((p) => p.group === "school" && !inCase.has(p.id)).map((p) => ({ id: p.id, label: p.name || p.id, lon: p.lon, lat: p.lat,
      category: p.category, confidence: p.confidence, reason: reasons.get(p.id) || "запись среза не входит в список школ кейса", place: p }));
  }

  const isUser = (id) => /^u\d+$/.test(id);  // places the user put on the map (not package or grid places)
  function save() {
    try {
      const c = caseOf(S.city);
      const all = JSON.parse(localStorage.getItem(STORE) || "{}");
      all[S.city] = { snapshot_id: c.snapshot_id, case_id: c.case_id, variants: c.variants, method: { distance_method: c.parameters.distance_method, routing_policy_id: c.parameters.routing_policy_id, routing: c.parameters.routing || null }, threshold_m: c.parameters.threshold_m,
        include_ids: c.parameters.target_policy.include_ids, exclude_ids: c.parameters.target_policy.exclude_ids, unknown_eligibility: c.parameters.target_policy.unknown_eligibility,
        user: c.candidates.filter((k) => isUser(k.id)), compared: S.compared };
      all.__city = S.city;  // last city of the city mode; restored when the mode is opened again (F5)
      localStorage.setItem(STORE, JSON.stringify(all));
    } catch (e) { /* storage unavailable: the case still works for this tab */ }
  }
  function restore(city) {
    try {
      const all = JSON.parse(localStorage.getItem(STORE) || "{}"), r = all[city];
      if (!r) return;
      const c = freshCase(city);
      if (r.snapshot_id !== c.snapshot_id || r.case_id !== c.case_id) return;
      c.candidates.push(...(r.user || []).slice(0, SC.LIMITS.candidates - c.candidates.length));
      Object.assign(c.parameters, { threshold_m: r.threshold_m });
      if (r.method && r.method.distance_method === "pedestrian-v1" && r.method.routing) Object.assign(c.parameters, { distance_method: "pedestrian-v1", routing_policy_id: r.method.routing_policy_id, routing: r.method.routing });
      Object.assign(c.parameters.target_policy, { include_ids: r.include_ids || [], exclude_ids: r.exclude_ids || [] });
      if (r.unknown_eligibility && c.parameters.target_policy.id === SC.PACKAGE_POLICY) c.parameters.target_policy.unknown_eligibility = r.unknown_eligibility;
      c.variants = { A: r.variants?.A ?? null, B: r.variants?.B ?? null };
      SC.validateCase(c);
      S.cases[city] = c; S.compared = !!r.compared;
      S.userSeq = 1 + Math.max(0, ...c.candidates.filter((k) => isUser(k.id)).map((k) => +k.id.slice(1)));
    } catch (e) { delete S.cases[city]; S.msg = "Сохранённое состояние не восстановлено (" + (e.detail || e.message) + "): открыт исходный кейс."; }
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
      chip(p.metrics.unknown_count ? "Среднее (известные)" : "Среднее до школы", m(p.metrics.mean_distance_mm), delta(mm2m(p.metrics.mean_distance_mm), mm2m(cur.metrics.mean_distance_mm), true, " м"), "Среднее расстояние по прямой от точек сетки до ближайшей школы"),
      chip(`До ${thr.toLocaleString("ru-RU")} м`, `${p.metrics.within_threshold_count} из ${p.metrics.total_origins} точек`, delta(p.metrics.within_threshold_count, cur.metrics.within_threshold_count, false, ""), "Порог — ваш параметр анализа, не норматив. Знаменатель — все точки, включая неизвестные"),
      chip("Дальше всего", m(p.metrics.max_distance_mm), delta(mm2m(p.metrics.max_distance_mm), mm2m(cur.metrics.max_distance_mm), true, " м"), "Самая дальняя точка сетки от ближайшей школы"));
    if (p.metrics.unknown_count) metrics.append(chip("Неизвестно", pts(p.metrics.unknown_count), null, "Для этих точек нет известного расстояния; они не считаются нулём"));
    metrics.append(el("span", { class: "sc-method-tag", title: METHOD_TEXT[methodKey(c)] }, methodKey(c) === "geodesic" ? "по прямой" : methodKey(c) === "pedestrian-v1-strict" ? "по улицам" : "по улицам*"));
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
    const c = caseOf(S.city), pk = S.pkg[S.city], elig = S.cmp.eligible_school_ids.length, ex = excludedRecords();
    const total = D.cities[S.city].places.filter((p) => p.group === "school").length;
    const box = el("div", { class: "sc-box" });
    const avail = c.sources.filter((x) => x.verification_status !== "not_fetched"), nf = c.sources.length - avail.length;
    if (pk && pk.case) {
      const outside = c.schools.filter((x) => !inFrame(c, x)).length;
      box.append(el("p", null, `Кейс: подготовленный пакет ${pk.by}. Школ в кейсе ${c.schools.length}${outside ? ` (из них ${outside} — в буфере за рамкой участка)` : ""}, в расчёте ${elig}; записей среза «школа» вне расчёта с причиной: ${ex.length}.`));
      box.append(el("p", { class: "sc-prov" }, `Источники: ${avail.length} открыты (вторичные), ${nf} не открыты (NOT_FETCHED) — официальный перечень не сверялся. Снимок ${c.snapshot_id}.`));
      const pol = policyBox(); if (pol) box.append(pol);
    } else {
      box.append(el("p", null, `Кейс собран из среза по правилу «${c.parameters.target_policy.id}»: школ в расчёте ${elig} из ${total} записей категории «школа». Остальные — курсы, центры, записи с сомнением QA; их можно включить вручную.`));
      box.append(el("p", { class: "sc-prov" }, `Источник: ${c.sources[0].title}. Вторичные данные (${c.sources[0].verification_status}), получено ${String(c.sources[0].retrieved_at).slice(0, 10)}. Не официальный реестр.`));
      if (pk && pk.error) box.append(el("p", { class: "sc-warn" }, "Подготовленный пакет не принят: " + pk.error));
    }
    const d = el("details"); d.append(el("summary", null, `Все школьные записи (${total})`));
    const ul = el("ul", { class: "sc-list" });
    for (const s of c.schools) {
      const st = SC.targetStatus(c, s);
      const b = btn("", () => select("school", s.id), { class: st.eligible ? "" : "muted" });
      b.append(el("span", { class: "sc-shape " + (st.eligible ? "sc-shape-school" : "sc-shape-excl") }), el("span", null, s.label));
      const li = el("li"); li.append(b); ul.append(li);
    }
    for (const e of ex) {
      const b = btn("", () => select("school", e.id), { class: "muted" });
      b.append(el("span", { class: "sc-shape sc-shape-excl" }), el("span", null, e.label));
      const li = el("li"); li.append(b); ul.append(li);
    }
    d.append(ul); box.append(d);
    const gaps = pk && pk.case && pk.meta && pk.meta.data_gaps;
    if (gaps && gaps.length) { const g = el("details"); g.append(el("summary", null, "Пробелы данных")); for (const x of gaps) g.append(el("p", { class: "sc-note" }, x.text)); box.append(g); }
    return box;
  }
  // Package policy for schools with unknown admission: an explicit switch plus the same case under the other policy.
  function policyBox() {
    const c = caseOf(S.city), tp = c.parameters.target_policy, unk = c.schools.filter((x) => x.access_eligibility === "unknown").length, pub = c.schools.filter((x) => x.access_eligibility === "known_public").length;
    if (!(tp.id === SC.PACKAGE_POLICY && unk)) return null;
    const pol = el("div", { class: "sc-method" });
    pol.append(el("b", null, `Школы с неизвестным допуском к приёму (${unk})`));
    const seg = el("div", { class: "sc-seg sc-seg-small" });
    for (const [k, t] of [["include_flagged", "Учитывать (с пометкой)"], ["exclude", "Не учитывать"]])
      seg.append(btn(t, () => { tp.unknown_eligibility = k; S.msg = k === "exclude" ? "Школы с неизвестным допуском не учитываются: остаются только известные общедоступные." : "Школы с неизвестным допуском учитываются; строки с ними помечены."; recompute(); render(); }, { "aria-pressed": String(tp.unknown_eligibility === k), id: "sc-unk-" + k, disabled: k === "exclude" && !pub }));
    pol.append(seg);
    // sensitivity: the same case under the other policy (computed, not stored)
    if (!S.alt || S.alt.digest !== S.digest) {  // computed once per case state (a street matrix takes ~0.5 s)
      S.alt = { digest: S.digest, text: null };
      try {
        const alt = JSON.parse(JSON.stringify(c)); alt.parameters.target_policy.unknown_eligibility = tp.unknown_eligibility === "exclude" ? "include_flagged" : "exclude";
        const mx = matrixOf(alt);
        if (mx) {
          const ac = SC.compareCase(alt, mx).plans[0].metrics, cm = plan("current").metrics;
          S.alt.text = `Сейчас при другой политике: в пределах ${c.parameters.threshold_m} м ${ac.within_threshold_count} из ${ac.total_origins} (здесь ${cm.within_threshold_count}), самая дальняя ${m(ac.max_distance_mm)} (здесь ${m(cm.max_distance_mm)}).`;
        }
      } catch (e) { /* the other policy may leave no school at all: nothing to show */ }
    }
    if (S.alt.text) pol.append(el("small", null, S.alt.text));
    if (!pub) pol.append(el("small", null, "Известных общедоступных школ в кейсе нет: без школ с неизвестным допуском расчёт был бы пуст."));
    return pol;
  }
  function methodBox() {
    const c = caseOf(S.city), cur = methodKey(c), box = el("div", { class: "sc-method", role: "group", "aria-label": "Как считать расстояние" });
    box.append(el("b", null, "Как считать расстояние"));
    const seg = el("div", { class: "sc-seg sc-seg-small" });
    for (const [k, t] of [["geodesic", "По прямой"], ["pedestrian-v1-strict", "По улицам: проверенные"], ["pedestrian-v1-exploratory", "По улицам: неполные данные"]])
      seg.append(btn(t, () => setMethod(k), { "aria-pressed": String(cur === k), id: "sc-method-" + k, disabled: k !== "geodesic" && !(RT && RA) }));
    box.append(seg, el("small", null, METHOD_TEXT[cur] + (cur === "pedestrian-v1-strict" ? ". Где пешеходный доступ не отмечен в данных, путь неизвестен." : "")));
    if (cur !== "geodesic") box.append(el("small", { class: "sc-prov" }, "Пешеходный граф: © OpenStreetMap contributors (ODbL-1.0) через Overture Maps Foundation, выпуск " + D.cities[S.city].release + "; производная база данных K03."));
    return box;
  }
  // ---------- AI seam: the model picks fact IDs/intents/tools; text and numbers are built here from current facts ----------
  const AI = { seq: 0, pending: null, last: null, busy: false };
  function factText(f) {
    const plan = f.plan_id === "current" ? "сейчас" : f.plan_id === "auto" ? "лучшее по правилу" : "вариант " + f.plan_id;
    const tot = plan && S.cmp.plans.find((p) => p.id === f.plan_id), total = tot ? tot.metrics.total_origins : null;
    switch (f.metric) {
      case "mean_distance_mm": return `Среднее до школы (${plan}): ${m(f.value)}`;
      case "max_distance_mm": return `Самая дальняя точка (${plan}): ${m(f.value)}`;
      case "within_threshold_count": return `В пределах ${caseOf(S.city).parameters.threshold_m} м (${plan}): ${f.value} из ${total} точек`;
      case "unknown_count": return `Неизвестно (${plan}): ${pts(f.value)}`;
      case "closer_count": return `Стало ближе (${plan}): ${pts(f.value)}`;
      case "delta_mm": return `${f.origin_id} (${plan}): изменение ${dm(f.value)}`;
      default: return `${f.metric} (${plan}): ${f.value === null ? "нет данных" : f.value}`;
    }
  }
  const INTENT_HEAD = { data_limits: "На это расчёт не отвечает: в кейсе нет стоимости, вместимости, населения и трафика.",
    method: () => "Расстояние: " + METHOD_TEXT[methodKey(caseOf(S.city))] + ".", unsupported: "Вопрос вне этого расчёта.",
    point_detail: "Самые дальние точки по вариантам:", explain_metric: "Показатели из расчёта:", compare_variants: () => {
      const v = plan("A") && plan("B") ? SC.verdict(S.cmp, "A", "B") : null;
      return !v ? "Сравнение требует выбранных мест." : v.code === "better" ? `По правилу сравнения лучше вариант ${v.winner}.` : v.code === "tie" ? "Варианты равны по правилу." : "Ни A, ни B не сокращают расстояния."; } };
  function askBox() {
    const box = el("div", { class: "sc-ask" });
    box.append(el("b", null, "Спросить о результате"));
    const f = el("form", { class: "sc-row" });
    const q = el("input", { type: "text", id: "sc-ask-q", maxlength: 600, placeholder: "Например: почему B лучше? что значит порог?", "aria-label": "Вопрос" });
    const go = el("button", { type: "submit", class: "sc-ghost", id: "sc-ask-go", disabled: AI.busy }, AI.busy ? "Ждём ответ…" : "Спросить");
    f.append(q, go);
    f.addEventListener("submit", (e) => { e.preventDefault(); ask(q.value); });
    box.append(f);
    const r = AI.last;
    if (r && r.case_digest === S.digest) {
      const out = el("div", { class: "sc-ai", role: "status", "aria-live": "polite", id: "sc-ai-out" });
      out.append(el("span", { class: "sc-tag" }, r.source === "model" ? `Ответ AI-помощника (${r.model}): выбор фактов; числа и текст — из расчёта` : "Шаблонный ответ без AI" + (r.reason ? " — " + r.reason : "")));
      const h = INTENT_HEAD[r.intent]; if (h) out.append(el("p", null, typeof h === "function" ? h() : h));
      const byId = new Map(S.cmp.facts.map((x) => [x.id, x]));
      const ul = el("ul"); for (const id of r.fact_ids) { const fx = byId.get(id); if (fx) ul.append(el("li", null, factText(fx))); }
      if (ul.children.length) out.append(ul);
      if (r.needs_clarification) out.append(el("p", { class: "sc-note" }, "Уточните: " + r.needs_clarification));
      const acts = el("div", { class: "sc-row" });
      for (const c of r.tool_calls) {
        if (c.name === "show_view") acts.append(btn(c.args.view === "current" ? "Показать «Сейчас»" : `Показать ${c.args.view} на карте`, () => setView(c.args.view), { class: "sc-ghost" }));
        if (c.name === "select_origin") acts.append(btn("Открыть точку " + c.args.origin_id, () => select("origin", c.args.origin_id), { class: "sc-ghost" }));
        if (c.name === "open_limits") acts.append(btn("Что расчёт не говорит", () => { const d = card.querySelector(".sc-limits"); if (d) { d.open = true; d.scrollIntoView({ block: "nearest" }); } }, { class: "sc-ghost" }));
      }
      if (acts.children.length) out.append(acts, el("small", { class: "sc-note" }, "Кнопки только меняют вид. Места A/B меняете вы сами."));
      box.append(out);
    }
    return box;
  }
  function ask(question) {
    question = String(question || "").trim();
    if (!question) { S.msg = "Введите вопрос."; render(); return; }
    const rid = "q" + (++AI.seq) + "-" + Date.now().toString(36), digest = S.digest;
    const facts = S.cmp.facts.map((f) => ({ id: f.id, metric: f.metric, value: f.value, unit: f.unit, plan_id: f.plan_id, origin_id: f.origin_id }));
    const views = ["current", ...["A", "B"].filter((v) => plan(v))];
    AI.pending = { rid, digest }; AI.busy = true; S.msg = ""; render();
    fetch("/api/school-ai", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schema_version: "school-ai-request-v1", request_id: rid, case_digest: digest, question, facts, views, origin_ids: caseOf(S.city).origins.map((o) => o.id) }) })
      .then((r) => r.json().then((j) => ({ ok: r.ok, j })))
      .then(({ ok, j }) => {
        AI.busy = false;
        if (!ok) { S.msg = "Сервер отклонил вопрос: " + (j.error || "ошибка"); render(); return; }
        // the answer counts only for the request that asked it and only while the inputs are unchanged
        if (!AI.pending || j.request_id !== AI.pending.rid || j.case_digest !== AI.pending.digest || j.case_digest !== S.digest) { S.msg = "Ответ устарел: входы кейса изменились после вопроса. Спросите снова."; render(); return; }
        AI.last = j; AI.pending = null; render();
      }, () => { AI.busy = false; AI.pending = null; S.msg = "Сервер не ответил. Ответ не получен; цифры выше — из расчёта в браузере."; render(); });
  }
  function fileRow() {
    const r = el("div", { class: "sc-row sc-files" });
    if (window.SCHOOL_NOTE && (plan("A") || plan("B"))) r.append(btn("Скачать записку (HTML)", noteFile, { class: "sc-ghost", id: "sc-note", title: "Вывод, таблица, источники, ограничения и встроенные входы кейса" }));
    r.append(btn("Сохранить кейс (JSON)", exportFile, { class: "sc-ghost", id: "sc-export", title: "Входы кейса и case_digest: файл можно загрузить снова и получить те же числа" }));
    const inp = el("input", { type: "file", accept: "application/json,.json,text/html,.html", id: "sc-import-file", hidden: true });
    inp.addEventListener("change", () => { const f = inp.files && inp.files[0]; inp.value = ""; if (f) importFile(f); });
    r.append(btn("Загрузить кейс…", () => inp.click(), { class: "sc-ghost", id: "sc-import" }), inp);
    r.append(btn("Начать заново", () => { delete S.cases[S.city]; S.compared = false; S.view = "current"; S.diff = false; S.sel = null; S.msg = "Кейс города сброшен к исходному."; recompute(); render(); }, { class: "sc-ghost", id: "sc-reset" }));
    return r;
  }
  function legendItems(parent) {
    const thr = caseOf(S.city).parameters.threshold_m.toLocaleString("ru-RU");
    const pts = S.diff && S.view !== "current" ? [["sc-shape-closer", "Точке стало ближе"], ["sc-shape-same", "Без изменений"], ["sc-shape-unk", "Неизвестно (не 0)"]]
      : [["sc-shape-point", `Точка сетки ≤ ${thr} м — не жители`], ["sc-shape-far", `Точка дальше ${thr} м`]];
    const c0 = caseOf(S.city), buf = c0.schools.some((x) => !inFrame(c0, x)) ? [["sc-shape-school sc-shape-buffer", "Школа за рамкой (буфер пакета)"]] : [];
    for (const [cls, text] of [["sc-shape-school", "Школа (в расчёте)"], ...buf, ["sc-shape-excl", "Запись не в расчёте"], ...pts,
      ["sc-shape-cand", "Место-гипотеза для A/B"], ["sc-shape-line", methodKey(caseOf(S.city)) === "geodesic" ? "Связь с ближайшей школой (по прямой)" : "Путь к ближайшей школе (модель сети); пунктир — модельный отрезок до сети"]]) {
      const s = el("span"); s.append(el("i", { class: "sc-shape " + cls }), document.createTextNode(text)); parent.append(s);
    }
  }
  function startCard() {
    const c = caseOf(S.city);
    card.append(head(D.cities[S.city].label + ": доступность школ", "Участок ≈2×2 км · " + METHOD_TEXT[methodKey(caseOf(S.city))]));
    const steps = el("ol", { class: "sc-howto" });
    for (const t of ["Посмотрите, какие точки дальше от школ (оранжевые квадраты — дальше порога).", "Выберите место A и место B: пунктирные ромбы на карте или своё место внутри рамки.", "Нажмите «Сравнить»: карта и цифры покажут Сейчас / A / B."]) steps.append(el("li", null, t));
    card.append(steps, dataBox(), methodBox());
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
    card.append(as, fileRow());
  }
  function pickCard() {
    const c = caseOf(S.city);
    card.append(head(`Место для варианта ${S.pick}`, "Нажмите ромб на карте или любую точку внутри рамки участка"));
    card.append(el("p", { class: "sc-note" }, "Это гипотеза для сравнения расстояний. Свободен ли участок, сколько стоит и можно ли там строить — не проверено."));
    const ul = el("ul", { class: "sc-list sc-cands" });
    for (const k of c.candidates) {
      const other = S.pick === "A" ? "B" : "A";
      const b = btn("", () => assign(S.pick, k.id), { disabled: c.variants[other] === k.id, "aria-pressed": String(c.variants[S.pick] === k.id) });
      b.append(el("span", { class: "sc-shape sc-shape-cand" }), el("span", null, lab(k) + (isUser(k.id) ? " (ваше)" : "")));
      const li = el("li"); li.append(b); ul.append(li);
    }
    card.append(ul, btn("Отмена", () => setPick(null), { class: "sc-ghost" }));
  }
  function excludedCard(e) {
    card.append(head(e.label, "Запись среза не в расчёте"));
    const dl = el("dl", { class: "sc-dl" });
    const row = (k, v) => dl.append(el("dt", null, k), el("dd", null, v));
    row("Почему не в расчёте", e.reason); row("Категория (Overture)", e.category || "нет данных");
    row("Уверенность источника", typeof e.confidence === "number" ? e.confidence.toFixed(2) : "нет данных"); row("Координаты", `${e.lon}, ${e.lat}`);
    row("Источник", "Overture places " + D.cities[S.city].release + " (вторичные данные)");
    card.append(dl);
    for (const q of F.qaOf(S.city, e.place)) card.append(el("p", { class: "sc-warn" }, q.text));
    card.append(el("p", { class: "sc-id" }, e.id));
  }
  function schoolCard(id) {
    const c = caseOf(S.city), s = school(id);
    if (!s) { const e = excludedRecords().find((x) => x.id === id); if (e) excludedCard(e); return; }
    const st = SC.targetStatus(c, s), src = c.sources.find((x) => x.id === s.source_ids[0]);
    card.append(head(s.label, st.eligible ? "Школа в расчёте" : "Запись не в расчёте"));
    const dl = el("dl", { class: "sc-dl" });
    const row = (k, v) => dl.append(el("dt", null, k), el("dd", null, v));
    const fp = s.field_provenance || {}, cat = fp.overture_category && fp.overture_category.value ? fp.overture_category : null;
    row("Категория", cat ? cat.value : fp.category && fp.category.value ? fp.category.value : s.category);
    const conf = typeof s.confidence === "number" ? s.confidence : cat && typeof cat.confidence === "number" ? cat.confidence : null;
    row("Уверенность источника", conf === null ? "нет данных" : conf.toFixed(2));
    const ACC = { known_public: "общедоступная (вывод по вторичным данным, не официально)", known_restricted: "ограниченный приём (вывод по вторичным данным)", unknown: "неизвестно" };
    row("Допуск к приёму", ACC[s.access_eligibility] || s.access_eligibility); row("Вместимость", s.capacity === null ? "нет данных" : String(s.capacity));
    if (!inFrame(c, s)) row("Положение", "за рамкой участка, в буфере пакета — нужна для ближайшей школы у границы"); row("Почему " + (st.eligible ? "в расчёте" : "не в расчёте"), st.reason);
    row("Координаты", `${s.lon}, ${s.lat}`); row("Источник", src ? src.title : "не указан"); row("Статус источника", "вторичные данные, не реестр");
    card.append(dl);
    for (const q of F.qaOf(S.city, D.cities[S.city].places.find((p) => p.id === id.replace(/^overture:/, "")) || {})) card.append(el("p", { class: "sc-warn" }, q.text));
    for (const q of s.qa || []) if (q && typeof q === "object" && q.text) card.append(el("p", { class: "sc-warn" }, q.text));
    if (fp.type_assessment) card.append(el("p", { class: "sc-note" }, `Оценка типа (${fp.type_assessment.source_id || "обзор"}): ${fp.type_assessment.value}; ${fp.type_assessment.method || ""}`));
    if (fp.official_match) card.append(el("p", { class: "sc-note" }, "Сверка с официальным перечнем: " + (fp.official_match.status === "not_fetched" ? "не выполнена — источники не открыты (NOT_FETCHED)" : fp.official_match.status)));
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
    card.append(head(o.label, o.kind === "derived" && /здан/i.test(o.label) ? "Точка анализа — центр здания: не жители и не дети" : "Точка анализа: не дом и не жители"));
    const t = el("table", { class: "sc-table" });
    const tr = el("tr"); for (const h of ["", "Ближайшая", "Расстояние", "Изменение"]) tr.append(el("th", null, h)); t.append(tr);
    for (const p of S.cmp.plans.filter((p) => p.id !== "auto")) {
      const r = p.rows.find((x) => x.origin_id === id), tg = r.nearest_target_id && target(r.nearest_target_id);
      const row = el("tr"); row.append(el("th", null, p.id === "current" ? "Сейчас" : p.id), el("td", null, tg ? lab(tg) : "нет данных"), el("td", null, m(r.after_mm)), el("td", null, p.id === "current" ? "—" : dm(r.delta_mm)));
      t.append(row);
    }
    card.append(t);
    const cur = plan("current").rows.find((x) => x.origin_id === id);
    if (methodKey(caseOf(S.city)) === "geodesic") card.append(el("p", { class: "sc-note" }, "Расстояние по прямой до ближайшей школы из расчёта. Реальный путь по улицам длиннее и здесь не считается."));
    else if (S.mx && RA) {
      const r = cur.nearest_target_id && S.mx.rows.find((x) => x.origin_id === id && x.target_id === cur.nearest_target_id);
      if (r) card.append(el("p", { class: "sc-note" }, "Сейчас: " + RA.explainRow(r)));
      const bad = S.mx.rows.filter((x) => x.origin_id === id && x.status !== "ok" && S.cmp.eligible_school_ids.includes(x.target_id));
      if (bad.length) card.append(el("p", { class: "sc-warn" }, `До ${bad.length} школ путь неизвестен: ` + [...new Set(bad.map((x) => RA.STATUS_RU[x.status] || x.status))].join("; ") + "."));
    }
  }
  function candCard(id) {
    const c = caseOf(S.city), k = cand(id);
    const user = isUser(k.id), pk = S.pkg[S.city] && S.pkg[S.city].case && S.pkg[S.city].case.candidates.some((x) => x.id === k.id);
    card.append(head(lab(k), user ? "Ваше место-гипотеза" : pk ? "Место-гипотеза из пакета " + S.pkg[S.city].by : "Место из примера (синтетическое)"));
    const dl = el("dl", { class: "sc-dl" });
    const row = (a, b) => dl.append(el("dt", null, a), el("dd", null, b));
    row("Тип", user ? "гипотеза пользователя" : pk ? "гипотеза пакета (" + k.label + ")" : "синтетическая сетка 3×4");
    if (pk && k.field_provenance && k.field_provenance.lon_lat) row("Как выбрано", k.field_provenance.lon_lat.method || "");
    row("Участок", "не проверен"); row("Стоимость", "нет данных");
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
    card.append(head(title, "Расстояние: " + METHOD_TEXT[methodKey(c)] + " · одна карта и один масштаб"));
    card.append(el("p", { class: "sc-lead" }, lead));
    const t = el("table", { class: "sc-table", id: "sc-result" });
    const plans = [cur, A, B].filter(Boolean);
    const hr = el("tr"); hr.append(el("th", null, "")); for (const p of plans) hr.append(el("th", null, p.id === "current" ? "Сейчас" : p.id)); t.append(hr);
    const rows = [["Среднее до школы", (p) => m(p.metrics.mean_distance_mm)], [`В пределах ${c.parameters.threshold_m} м`, (p) => `${p.metrics.within_threshold_count} из ${p.metrics.total_origins}`],
      ["Самая дальняя точка", (p) => m(p.metrics.max_distance_mm)], ["Стало ближе", (p) => (p.id === "current" ? "—" : pts(p.closer_count))], ["Неизвестно", (p) => String(p.metrics.unknown_count)]];
    for (const [name, f] of rows) { const r = el("tr"); r.append(el("th", null, name)); for (const p of plans) r.append(el("td", null, f(p))); t.append(r); }
    card.append(t, methodBox());
    const pol = policyBox(); if (pol) card.append(pol);
    const ex = el("div", { class: "sc-explain" }); ex.append(el("span", { class: "sc-tag" }, "Объяснение по шаблону из вычисленных чисел (не AI)"));
    for (const line of explain()) ex.append(el("p", null, line));
    if (auto && auto.selected_candidate_ids.length && ![c.variants.A, c.variants.B].includes(auto.selected_candidate_ids[0])) {
      const k = cand(auto.selected_candidate_ids[0]);
      ex.append(el("p", null, `Для справки: среди ${c.candidates.length} мест правило выбирает «${lab(k)}» — среднее ${m(auto.metrics.mean_distance_mm)} (сейчас ${m(cur.metrics.mean_distance_mm)}).`));
    } else if (auto && !auto.selected_candidate_ids.length) ex.append(el("p", null, "Ни одно место примера не уменьшает сумму расстояний: правило оставляет текущую сеть."));
    card.append(ex);
    card.append(askBox());
    const lim = el("details", { class: "sc-assume sc-limits" }); lim.append(el("summary", null, "Что этот расчёт не говорит"));
    for (const t2 of [methodKey(c) === "geodesic" ? "Это расстояние по прямой, не пешеходный маршрут и не время в пути." : "Маршрут модельной сети среза, не проверен на месте; отсутствие пути в срезе — ограничение сети, а не доказанная недоступность. Не время в пути.", "Точки — равномерная сетка, не жители и не дети; доля — от всех точек, не от населения.",
      "Вместимость и допуск к приёму школ неизвестны: ближе — не значит, что есть места.", "Школы за рамкой участка не загружены: у края расстояния могут быть завышены.",
      "Места A/B — гипотезы: участок, стоимость и возможность строительства не проверены."]) lim.append(el("p", null, t2));
    card.append(lim);
    card.append(fileRow());
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
    S.msg = `Вариант ${v}: ${lab(cand(id))}. Карта показывает ${v}; точки окрашены по изменению.`;
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
    if (c.variants.A === id || c.variants.B === id) { S.msg = `Лучшее по правилу место «${lab(cand(id))}» уже выбрано.`; render(); return; }
    assign(c.variants.A ? "B" : "A", id);
    S.msg = `Подобрано правилом: «${lab(cand(id))}». Это минимум суммы расстояний по прямой среди мест примера, не решение о строительстве.`; render();
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
  function exportFile() {
    try {
      const c = caseOf(S.city), text = SC.exportCase(c), name = `school-case-${S.city}-${S.cmp.case_digest.slice(7, 15)}.json`;
      download(text, "application/json", name);
      S.msg = `Кейс сохранён в файл ${name}: входы и case_digest. Загрузка файла пересчитает те же числа.`;
    } catch (e) { S.msg = "Не удалось сохранить: " + (e.detail || e.message); }
    render();
  }
  function download(text, type, name) {
    const a = el("a", { href: URL.createObjectURL(new Blob([text], { type })), download: name });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  function noteFile() {
    try {
      const c = caseOf(S.city), name = `school-note-${S.city}-${S.cmp.case_digest.slice(7, 15)}.html`;
      const html = window.SCHOOL_NOTE.buildNote(c, S.cmp, { caseText: SC.exportCase(c), cityLabel: D.cities[S.city].label, label: lab,
        verdict: plan("A") && plan("B") ? SC.verdict(S.cmp, "A", "B") : null, generatedAt: new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC" });
      download(html, "text/html", name);
      S.msg = `Записка сохранена: ${name}. В ней же — входы кейса: её можно загрузить обратно.`;
    } catch (e) { S.msg = "Записка не сохранена: " + (e.detail || e.message); }
    render();
  }
  function importFile(file) {
    // size check before reading; parse, validate, bind to the loaded slice, verify digest — or refuse and change nothing
    if (file.size > 2 * SC.LIMITS.bytes) { S.msg = `Файл не загружен: больше ${2 * SC.LIMITS.bytes / 1024} КБ.`; render(); return; }
    file.text().then((text) => {
      let c;
      try {
        if (/^\s*</.test(text)) {  // a decision note: only its embedded case is read, nothing else from the HTML
          const inner = window.SCHOOL_NOTE && window.SCHOOL_NOTE.extractCase(text);
          if (!inner) throw new Error("в HTML-файле нет встроенного кейса");
          text = inner;
        }
        c = SC.importCase(text, D, known());
      } catch (e) { S.msg = "Файл не загружен, текущий кейс не изменён: " + (e.detail || e.message); render(); return; }
      S.cases[c.city_id] = c;
      S.userSeq = 1 + Math.max(0, ...c.candidates.filter((k) => isUser(k.id)).map((k) => +k.id.slice(1)));
      const msg = `Загружен кейс «${c.title}». Все числа пересчитаны из входов файла.`;
      if (c.city_id !== S.city) GOV.switchCity(c.city_id);
      S.sel = null; S.pick = null; S.compared = !!(c.variants.A || c.variants.B); S.view = c.variants.A ? "A" : c.variants.B ? "B" : "current"; S.diff = S.view !== "current";
      recompute(); S.msg = msg; render();
    }, () => { S.msg = "Файл не прочитан."; render(); });
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
    map.addLayer({ id: "sc-links-snap", type: "line", source: "sc-links", filter: ["==", ["get", "to"], "snap"],
      paint: { "line-color": "#6d7c76", "line-width": 1.2, "line-opacity": 0.8, "line-dasharray": [1, 1.5] } });
    map.addLayer({ id: "sc-schools-excl", type: "circle", source: "sc-schools", filter: ["!", ["get", "eligible"]],
      paint: { "circle-radius": 5, "circle-color": "#ffffff", "circle-stroke-color": "#8f9b95", "circle-stroke-width": 1.6 } });
    map.addLayer({ id: "sc-schools-in", type: "circle", source: "sc-schools", filter: ["get", "eligible"],
      paint: { "circle-radius": ["case", ["get", "sel"], 12, 9], "circle-color": "#176b4a", "circle-stroke-color": "#ffffff", "circle-stroke-width": 3,
        "circle-opacity": ["case", ["boolean", ["get", "outside"], false], 0.5, 1], "circle-stroke-opacity": ["case", ["boolean", ["get", "outside"], false], 0.5, 1] } });
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
    const map = S.map; if (!map || !map.getSource("sc-links") || !S.cmp) return;
    const show = active(), c = caseOf(S.city), p = viewPlan();
    const vis = show ? "visible" : "none";
    for (const id of ["sc-links-school", "sc-links-new", "sc-links-snap", "sc-schools-excl", "sc-schools-in"]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    if (!show) return;
    const selO = S.sel && S.sel.type === "origin" ? S.sel.id : null, selT = S.sel && S.sel.type !== "origin" ? S.sel.id : null;
    const lines = [], idx = new Map((S.mx ? S.mx.rows : []).map((r) => [r.origin_id + "\u0000" + r.target_id, r]));
    for (const r of p.rows) {
      if (!r.nearest_target_id) continue;
      const o = c.origins.find((x) => x.id === r.origin_id), t = target(r.nearest_target_id), mr = idx.get(r.origin_id + "\u0000" + r.nearest_target_id);
      const props = { to: cand(r.nearest_target_id) ? "candidate" : "school", hl: r.origin_id === selO || r.nearest_target_id === selT };
      if (mr && mr.method !== "geodesic" && RA) {
        // street route of the nearest target: network part solid, model connection to the network dashed (K03 routeLayers)
        for (const f of RA.routeLayers({ rows: [mr] }).features) lines.push({ type: "Feature", properties: { ...props, to: f.properties.part === "snap" ? "snap" : props.to }, geometry: f.geometry });
      } else lines.push({ type: "Feature", properties: props, geometry: { type: "LineString", coordinates: [[o.lon, o.lat], [t.lon, t.lat]] } });
    }
    map.getSource("sc-links").setData({ type: "FeatureCollection", features: lines });
    map.getSource("sc-schools").setData({ type: "FeatureCollection", features: [...c.schools.map((s) => ({ type: "Feature",
      properties: { id: s.id, eligible: SC.targetStatus(c, s).eligible, sel: s.id === selT, outside: !inFrame(c, s) }, geometry: { type: "Point", coordinates: [s.lon, s.lat] } })),
      ...excludedRecords().map((e) => ({ type: "Feature", properties: { id: e.id, eligible: false, sel: e.id === selT }, geometry: { type: "Point", coordinates: [e.lon, e.lat] } }))] });
  }
  function schedule() {
    if (S.pending) return; S.pending = true;
    requestAnimationFrame(() => { S.pending = false; drawOverlay(); });
  }
  function drawOverlay() {
    overlay.replaceChildren();
    const map = S.map;
    overlay.style.display = active() && map ? "block" : "none";
    if (!active() || !map || !S.cmp) return;
    const c = caseOf(S.city), p = viewPlan(), cur = plan("current"), thr = c.parameters.threshold_m * 1000;
    const pt = (lon, lat) => { const q = map.project([lon, lat]); return [q.x, q.y]; };
    const gL = sv("g"), gC = sv("g"), gO = sv("g"), gT = sv("g");
    overlay.append(gL, gC, gO, gT);
    // candidates: dashed diamonds (hypotheses). A/B larger with a letter.
    for (const k of c.candidates) {
      const [x, y] = pt(k.lon, k.lat), v = c.variants.A === k.id ? "A" : c.variants.B === k.id ? "B" : null;
      const r = v ? 13 : 8, sel = S.sel && S.sel.id === k.id;
      const d = sv("path", { d: `M${x} ${y - r}L${x + r} ${y}L${x} ${y + r}L${x - r} ${y}Z`, class: "sc-cand" + (v ? " sc-cand-" + v : "") + (sel ? " sc-sel" : "") + (S.pick ? " sc-pickable" : "") });
      const tt = sv("title"); tt.textContent = lab(k) + (v ? ` — вариант ${v}` : "") + " (гипотеза)"; d.append(tt);
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
    if (S.sel && S.sel.type === "school") { const s = school(S.sel.id) || excludedRecords().find((x) => x.id === S.sel.id); if (s) { const [x, y] = pt(s.lon, s.lat); const t = sv("text", { x: x + 14, y: y + 4, class: "sc-label" }); t.textContent = s.label.slice(0, 40); gT.append(t); } }
    void cur;
  }

  // ---------- render ----------
  // Same race as D1: an input's change fires on pointerdown (blur); re-rendering then replaced the pressed button and the
  // first human-speed click was lost. While a pointer is down the panels are not rebuilt; the render runs after the click.
  const PRESS = { down: false, pending: false };
  document.addEventListener("pointerdown", () => { PRESS.down = true; }, true);
  const release = () => { if (!PRESS.down) return; PRESS.down = false; if (PRESS.pending) { PRESS.pending = false; setTimeout(render, 0); } };
  for (const t of ["pointerup", "pointercancel"]) document.addEventListener(t, release, true);
  addEventListener("blur", release);
  function render() {
    if (PRESS.down) { PRESS.pending = true; return; }
    const on = active();
    strip.hidden = actions.hidden = legend.hidden = !on;
    card.hidden = !on || !S.cardOpen; reopen.hidden = !on || S.cardOpen;
    document.body.classList.toggle("sc-mode", on);
    if (!on) { overlay.style.display = "none"; mapData(); return; }
    if (!S.cmp) { strip.replaceChildren(el("div", { class: "sc-q" }, "Загружаем кейс…")); actions.replaceChildren(); card.replaceChildren(el("p", null, "Загружаем подготовленный кейс…")); return; }
    renderStrip(); renderActions(); renderCard();
    legend.replaceChildren(); legendItems(legend);
    mapData(); drawOverlay();
  }

  // ---------- hooks ----------
  GOV.EXT.onMap.push((map) => { S.map = map; ensureLayers(map); render(); });
  let cityRestored = false;
  GOV.EXT.onActive.push((on) => {
    if (on && !cityRestored && !S.loading) {
      cityRestored = true;  // once per page load: the city the user last worked with (switched while active, so labels stay right)
      let last = null;
      try { last = JSON.parse(localStorage.getItem(STORE) || "{}").__city; } catch (e) { last = null; }
      if (last && last !== S.city && D.cities[last]) { GOV.switchCity(last); return; }
    }
    if (on && !S.loading && !S.cases[S.city]) { restore(S.city); recompute(); }
    setPick(null); render();
  });
  GOV.EXT.onMode.push(() => render());
  GOV.EXT.onCity.push((city) => {
    S.city = city; S.pick = null; S.sel = null; S.view = "current"; S.diff = false; S.compared = false; S.msg = "";
    if (S.loading) { S.cmp = null; return; }
    if (!S.cases[city]) restore(city);
    recompute();
    const c = caseOf(city);
    if (c.variants.A || c.variants.B) S.msg = "Восстановлены сохранённые варианты этого города. Данные и места другого города не переносятся.";
    setTimeout(render, 0);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && active() && S.pick) { setPick(null); } });
  addEventListener("resize", schedule);
  // Page seam for colleague smoke tests (K10 ui_import_smoke.cjs): import through the same strict path as the file input.
  window.SCHOOL_ACCESS_UI = {
    importText(text) {
      try { const c = SC.importCase(String(text), D, known()); S.cases[c.city_id] = c; if (c.city_id !== S.city) GOV.switchCity(c.city_id); S.sel = null; S.pick = null; S.compared = false; S.view = "current"; AI.last = null; recompute(); render(); return { ok: true }; }
      catch (e) { return { ok: false, code: e.code || "error" }; }
    },
    state() {
      const c = caseOf(S.city);
      return { city_id: c.city_id, case_id: c.case_id, case_digest: S.digest, school_ids: c.schools.map((x) => x.id), origin_ids: c.origins.map((x) => x.id), candidate_ids: c.candidates.map((x) => x.id),
        result_digest: S.compared ? S.digest : null, ai_digest: AI.last ? AI.last.case_digest : null, labels_text: (strip.innerText || "") + "\n" + (card.innerText || "") };
    },
  };
  window.SCHOOL_UI = { state: S, caseOf, recompute, render, assign, compare, setView, select, suggest, plan, lab, excludedRecords,
    exportCase: () => SC.exportCase(caseOf(S.city)), ready: () => !S.loading };
  if (GOV.map) { S.map = GOV.map; ensureLayers(GOV.map); }
  render();
  loadPackages().then(() => { S.loading = false; restore(S.city); recompute(); render(); });
})();
