/* R07 CivicScenarios — сравнение базового состояния и двух планов перекрытий (A/B) на одной карте.
 * Контракт: window.CivicScenarios.mount({root, map, api, apiPrefix?}) -> {destroy}.
 *   api.request(method, path, body) -> Promise<data> (R01); path = apiPrefix + "/scenarios/..." (по умолчанию "/api/civic/v1").
 *   map — существующий MapLibre instance или null (тогда только таблица).
 * Геометрию рёбер даёт подготовленный граф; закрыть можно только ребро графа (клик по линии), произвольная
 * нарисованная линия дорожным объектом не считается. Сценарий — гипотеза, не официальное перекрытие.
 * Текст из данных выводится только через textContent. Слои/источники/классы — с префиксом civic-r07-.
 */
(function (root) {
  "use strict";
  const P = "civic-r07-";
  const PLAN_COLORS = { A: "#d9480f", B: "#7048e8" };
  const ROUTE_COLORS = { base: "#1971c2", A: "#d9480f", B: "#7048e8" };
  const STATUS_LABEL = { ok: "", unknown: "нет данных о доступе", unreachable: "нет пути в модели" };
  const REASON_LABEL = {
    path_only_via_unknown_access: "путь есть только через рёбра с неизвестным доступом",
    path_may_exist_outside_graph: "путь может проходить вне среза графа",
    no_path_within_model: "в данной модели графа пути нет (не доказанная недоступность на местности)",
  };
  const EVIDENCE_LABEL = { synthetic: "СИНТЕТИКА", derived: "производные данные", observed: "наблюдение", hypothesis: "гипотеза" };
  const MODE_LABEL = { walking: "пешеход", driving: "автомобиль" };

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) for (const k of Object.keys(attrs)) {
      const v = attrs[k];
      if (v === undefined || v === null || v === false) continue;
      if (k === "text") n.textContent = String(v);
      else if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of [].concat(children || [])) if (c !== null && c !== undefined && c !== false) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    return n;
  }
  const fmtM = (m) => (m === null || m === undefined ? "—" : (Math.round(m * 10) / 10).toLocaleString("ru-RU") + " м");
  const fmtD = (m) => (m === null || m === undefined ? "—" : (m > 0 ? "+" : m < 0 ? "−" : "±") + (Math.round(Math.abs(m) * 10) / 10).toLocaleString("ru-RU") + " м");
  const short = (id) => (id.length > 14 ? "…" + id.slice(-6) : id);

  // "2026-10-07T09:00" + "+05:00" -> ISO с явным смещением
  const isoWithOffset = (local, off) => (local.length === 16 ? local + ":00" : local) + off;
  function splitIso(s) {
    const m = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.exec(s || "");
    return m ? { local: m[1], off: m[2] === "Z" ? "+00:00" : m[2] } : { local: "", off: "+05:00" };
  }

  function mount(opts) {
    const host = opts && opts.root, map = (opts && opts.map) || null, api = opts && opts.api;
    if (!host || !api || typeof api.request !== "function") throw new Error("CivicScenarios.mount: нужны root и api.request");
    const prefix = (opts.apiPrefix === undefined ? "/api/civic/v1" : opts.apiPrefix) + "/scenarios";
    const state = {
      graphs: [], cases: [], graph: null, edgeIndex: new Map(), nodeIndex: new Map(),
      payload: null, editPlan: "A", clickMode: "close", result: null, selectedPair: null, busy: false, destroyed: false,
    };
    const listeners = [];
    const ui = {};
    const wrap = el("section", { class: P + "panel", "aria-label": "Сценарии перекрытий" });
    host.appendChild(wrap);

    // ---------- каркас ----------
    ui.notice = el("div", { class: P + "notice", role: "note" }, [
      el("strong", { text: "Сценарий — гипотеза." }),
      " Это не официальное решение о перекрытии. Метрика — длина пути по графу (м), не время в пути; пробки, CO2 и аварийность не моделируются.",
    ]);
    ui.graphSel = el("select", { class: P + "select", "aria-label": "Граф", onchange: () => selectGraph(ui.graphSel.value, null) });
    ui.caseSel = el("select", { class: P + "select", "aria-label": "Кейс", onchange: () => applyCase(ui.caseSel.value) });
    ui.graphInfo = el("div", { class: P + "graphinfo" });
    ui.atLocal = el("input", { type: "datetime-local", class: P + "input", "aria-label": "Момент анализа", onchange: syncAt });
    ui.atOff = el("select", { class: P + "select " + P + "off", "aria-label": "Смещение UTC", onchange: syncAt },
      ["+05:00", "+06:00", "+00:00"].map((o) => el("option", { value: o, text: "UTC" + o })));
    ui.planTabs = el("div", { class: P + "tabs", role: "tablist" });
    ui.modeBar = el("div", { class: P + "modes" });
    ui.planBody = el("div", { class: P + "plan" });
    ui.points = el("div", { class: P + "points" });
    ui.run = el("button", { class: P + "btn " + P + "primary", type: "button", text: "Сравнить", onclick: run });
    ui.err = el("div", { class: P + "error", role: "alert", hidden: true });
    ui.out = el("div", { class: P + "result", "aria-live": "polite" });

    wrap.append(
      el("h2", { class: P + "title", text: "Последствия перекрытий: база, план A, план B" }),
      ui.notice,
      el("div", { class: P + "row" }, [el("label", { class: P + "lbl" }, ["Граф ", ui.graphSel]), el("label", { class: P + "lbl" }, ["Кейс ", ui.caseSel])]),
      ui.graphInfo,
      el("div", { class: P + "legend" }, [
        ["#495057", "solid", "доступ подтверждён"], ["#adb5bd", "dashed", "доступ неизвестен (не используется)"], ["#c92a2a", "solid", "запрет"],
        [PLAN_COLORS.A, "solid", "закрыто в плане A / путь A"], [PLAN_COLORS.B, "solid", "закрыто в плане B / путь B"], ["#adb5bd", "dotted", "перекрытие не действует в момент анализа"], [ROUTE_COLORS.base, "solid", "путь в базе"],
      ].map(([c, st, t]) => el("span", { class: P + "lg" }, [el("i", { style: "border-top:3px " + st + " " + c }), t]))),
      el("div", { class: P + "row" }, [el("label", { class: P + "lbl" }, ["Момент анализа ", ui.atLocal]), ui.atOff]),
      ui.planTabs, ui.modeBar, ui.planBody, ui.points,
      el("div", { class: P + "row" }, [ui.run]),
      ui.err, ui.out,
    );

    // ---------- загрузка ----------
    function req(method, path, body) { return api.request(method, prefix + path, body); }
    function showError(e) {
      ui.err.hidden = false;
      ui.err.textContent = "Ошибка: " + ((e && (e.message || e.code)) || String(e)) + (e && e.code ? " [" + e.code + "]" : "");
    }
    function clearError() { ui.err.hidden = true; ui.err.textContent = ""; }

    Promise.all([req("GET", "/graphs"), req("GET", "/cases")]).then(([g, c]) => {
      if (state.destroyed) return;
      state.graphs = g.items || []; state.cases = c.items || [];
      ui.graphSel.replaceChildren(...state.graphs.map((x) => el("option", { value: x.id, text: (x.evidence_type === "synthetic" ? "[СИНТЕТИКА] " : "") + x.label })));
      for (const nr of g.not_ready || []) ui.graphSel.appendChild(el("option", { disabled: true, text: "[NOT_READY] " + (MODE_LABEL[nr.mode] || nr.mode) + ": нет проверенного графа" }));
      const first = state.cases.find((x) => x.payload.graph_id !== "synthetic-tiny-v1") || state.cases[0];
      if (first) selectGraph(first.payload.graph_id, first.case_id); else if (state.graphs[0]) selectGraph(state.graphs[0].id, null);
    }).catch(showError);

    function selectGraph(id, caseId) {
      clearError();
      ui.graphSel.value = id;
      return req("GET", "/graphs/" + encodeURIComponent(id)).then((d) => {
        if (state.destroyed) return;
        const g = d.graph;
        state.graph = g; state.edgeIndex = new Map(g.edges.map((e) => [e.id, e])); state.nodeIndex = new Map(g.nodes.map((n) => [n.id, n]));
        state.result = null; state.selectedPair = null; ui.out.replaceChildren();
        renderGraphInfo();
        const cases = state.cases.filter((c) => c.payload.graph_id === id);
        ui.caseSel.replaceChildren(el("option", { value: "", text: "— пустой сценарий —" }), ...cases.map((c) => el("option", { value: c.case_id, text: c.title })));
        if (caseId) { ui.caseSel.value = caseId; applyCase(caseId); } else applyCase("");
        drawGraph(true);
      }).catch(showError);
    }

    function renderGraphInfo() {
      const g = state.graph;
      const badge = el("span", { class: P + "badge " + P + "ev-" + g.evidence_type, text: EVIDENCE_LABEL[g.evidence_type] || g.evidence_type });
      const lim = el("ul", { class: P + "lim" }, (g.limitations || []).map((t) => el("li", { text: t })));
      ui.graphInfo.replaceChildren(
        el("div", {}, [badge, " ", el("span", { text: "режим: " + (MODE_LABEL[g.mode] || g.mode) + " · узлов " + g.nodes.length + " · рёбер " + g.edges.length + " · digest " + g.digest.slice(0, 12) })]),
        el("details", {}, [el("summary", { text: "Пределы данных и источник" }), lim,
          el("div", { class: P + "src", text: g.source && g.source.commit ? "Источник: " + g.source.path + " @ " + g.source.commit.slice(0, 10) + (g.license && g.license.id ? " · лицензия " + g.license.id : "") : "Источник: " + ((g.source && g.source.kind) || "—") })]),
      );
    }

    function emptyPayload() {
      const g = state.graph;
      return { schema_version: "civic-scenario-v1", city: g.city, graph_id: g.id, graph_digest: g.digest, mode: g.mode,
        analysis_at: "2026-10-07T09:00:00+05:00", origin_node_ids: [], destination_node_ids: [],
        plans: [{ id: "A", closures: [] }, { id: "B", closures: [] }] };
    }
    function applyCase(caseId) {
      const c = state.cases.find((x) => x.case_id === caseId);
      state.payload = c ? JSON.parse(JSON.stringify(c.payload)) : emptyPayload();
      for (const id of ["A", "B"]) if (!state.payload.plans.find((p) => p.id === id)) state.payload.plans.push({ id, closures: [] });
      state.payload.plans.sort((a, b) => (a.id < b.id ? -1 : 1));
      const s = splitIso(state.payload.analysis_at);
      ui.atLocal.value = s.local; if ([...ui.atOff.options].some((o) => o.value === s.off)) ui.atOff.value = s.off;
      state.result = null; ui.out.replaceChildren();
      renderPlans(); renderPoints(); drawOverlays();
    }
    function syncAt() { if (state.payload && ui.atLocal.value) { state.payload.analysis_at = isoWithOffset(ui.atLocal.value, ui.atOff.value); drawOverlays(); } }

    // ---------- планы ----------
    const plan = (id) => state.payload.plans.find((p) => p.id === id);
    function closedIds(id) { const s = new Set(); for (const c of plan(id).closures) for (const e of c.edge_ids) s.add(e); return s; }
    // действует ли перекрытие в момент анализа: start_at <= analysis_at < end_at (Date учитывает смещение)
    function activeIds(id) {
      const at = Date.parse(state.payload.analysis_at), s = new Set();
      for (const c of plan(id).closures) if (Date.parse(c.start_at) <= at && at < Date.parse(c.end_at)) for (const e of c.edge_ids) s.add(e);
      return s;
    }
    function renderPlans() {
      ui.planTabs.replaceChildren(...["A", "B"].map((id) => el("button", {
        type: "button", role: "tab", class: P + "tab" + (state.editPlan === id ? " " + P + "active" : ""), "aria-selected": state.editPlan === id ? "true" : "false",
        style: "border-color:" + PLAN_COLORS[id], onclick: () => { state.editPlan = id; renderPlans(); },
        text: "План " + id + " (" + closedIds(id).size + " рёбер)" })));
      ui.modeBar.replaceChildren(...[["close", "Клик по ребру: закрыть/открыть"], ["origin", "Клик: старт"], ["dest", "Клик: цель"]].map(([m, t]) =>
        el("button", { type: "button", class: P + "chip" + (state.clickMode === m ? " " + P + "active" : ""), onclick: () => { state.clickMode = m; renderPlans(); drawOverlays(); }, text: t })));
      const p = plan(state.editPlan);
      const items = p.closures.map((c, i) => {
        const s = splitIso(c.start_at), e = splitIso(c.end_at);
        const sIn = el("input", { type: "datetime-local", class: P + "input", value: s.local, "aria-label": "Начало", onchange: () => { c.start_at = isoWithOffset(sIn.value, s.off); drawOverlays(); } });
        const eIn = el("input", { type: "datetime-local", class: P + "input", value: e.local, "aria-label": "Конец", onchange: () => { c.end_at = isoWithOffset(eIn.value, e.off); drawOverlays(); } });
        return el("li", { class: P + "closure" }, [
          el("div", { text: "Перекрытие " + (i + 1) + ": рёбер " + c.edge_ids.length + " · UTC" + s.off }),
          el("div", { class: P + "row" }, [el("label", { class: P + "lbl" }, ["с ", sIn]), el("label", { class: P + "lbl" }, ["до ", eIn])]),
          el("div", { class: P + "hint", text: "[начало, конец): начало включительно, конец — нет" }),
          el("button", { type: "button", class: P + "btn", text: "Удалить", onclick: () => { p.closures.splice(i, 1); renderPlans(); drawOverlays(); } }),
        ]);
      });
      ui.planBody.replaceChildren(
        el("ul", { class: P + "closures" }, items),
        el("button", { type: "button", class: P + "btn", text: "+ интервал перекрытия", onclick: () => {
          const at = splitIso(state.payload.analysis_at);
          const d = new Date(at.local + ":00Z"); const end = new Date(d.getTime() + 6 * 3600e3).toISOString().slice(0, 16);
          p.closures.push({ edge_ids: [], start_at: at.local + ":00" + at.off, end_at: end + ":00" + at.off });
          renderPlans();
        } }),
        el("div", { class: P + "hint", text: state.graph && state.graph.edges.length ? "Выберите режим «закрыть» и щёлкните линию графа на карте; ребро добавится в последнее перекрытие плана " + state.editPlan + "." : "" }),
      );
    }
    function renderPoints() {
      const mk = (ids, key, label) => el("div", {}, [el("strong", { text: label + ": " }),
        ...ids.map((id) => el("button", { type: "button", class: P + "chip", title: id, text: short(id) + " ×", onclick: () => {
          state.payload[key] = state.payload[key].filter((x) => x !== id); renderPoints(); drawOverlays(); } }))]);
      ui.points.replaceChildren(mk(state.payload.origin_node_ids, "origin_node_ids", "Старты"), mk(state.payload.destination_node_ids, "destination_node_ids", "Цели"));
    }
    function toggleEdge(id) {
      const p = plan(state.editPlan);
      const holder = p.closures.find((c) => c.edge_ids.includes(id));
      if (holder) { holder.edge_ids = holder.edge_ids.filter((x) => x !== id); if (!holder.edge_ids.length) p.closures.splice(p.closures.indexOf(holder), 1); }
      else {
        if (!p.closures.length) { const at = splitIso(state.payload.analysis_at); const d = new Date(at.local + ":00Z");
          p.closures.push({ edge_ids: [], start_at: at.local + ":00" + at.off, end_at: new Date(d.getTime() + 6 * 3600e3).toISOString().slice(0, 16) + ":00" + at.off }); }
        p.closures[p.closures.length - 1].edge_ids.push(id);
      }
      renderPlans(); drawOverlays();
    }
    function addPoint(nodeId) {
      const key = state.clickMode === "origin" ? "origin_node_ids" : "destination_node_ids";
      if (!state.payload[key].includes(nodeId)) state.payload[key].push(nodeId);
      renderPoints(); drawOverlays();
    }

    // ---------- расчёт ----------
    function run() {
      if (state.busy || !state.payload) return;
      clearError(); syncAt();
      const body = JSON.parse(JSON.stringify(state.payload));
      body.plans = body.plans.map((p) => ({ id: p.id, closures: p.closures.filter((c) => c.edge_ids.length) }));
      state.busy = true; ui.run.disabled = true; ui.run.textContent = "Считаю…";
      req("POST", "/compare", body).then((r) => {
        if (state.destroyed) return;
        state.result = r; state.sentPayload = body; state.selectedPair = null; renderResult(); drawOverlays();
      }).catch(showError).finally(() => { state.busy = false; ui.run.disabled = false; ui.run.textContent = "Сравнить"; });
    }

    function cell(row, delta) {
      if (!row) return el("td", { text: "—" });
      if (row.status !== "ok") return el("td", { class: P + "st-" + row.status, title: REASON_LABEL[row.reason] || "", text: STATUS_LABEL[row.status] });
      return el("td", {}, [el("div", { text: fmtM(row.length_m) }), delta !== undefined && delta !== null ? el("div", { class: P + "delta" + (delta > 0 ? " " + P + "up" : ""), text: fmtD(delta) }) : null,
        row.equal_cost_alternatives ? el("div", { class: P + "hint", text: "есть равный по длине путь" }) : null]);
    }
    function planCard(p) {
      const s = p.vs_baseline.summary, ch = s.changes;
      return el("div", { class: P + "card", style: "border-top-color:" + PLAN_COLORS[p.id] }, [
        el("h3", { text: "План " + p.id }),
        el("div", { text: "Действует в момент анализа: " + p.active_closed_edge_ids.length + " рёбер; неактивных интервалов: " + p.inactive_closures.length }),
        el("div", { text: "Сопоставимых пар: " + s.comparable_pairs + " из " + s.pairs }),
        el("div", { text: "Средний прирост длины (только сопоставимые): " + fmtD(s.mean_delta_m_comparable) }),
        el("div", { text: "Максимальный прирост: " + fmtD(s.max_delta_m_comparable) }),
        el("div", { text: "Удлинилось: " + ch.longer + " · без изменений: " + ch.unchanged }),
        el("div", { class: ch.lost_within_model ? P + "st-unreachable" : "", text: "Нет пути в модели (было): " + ch.lost_within_model }),
        el("div", { class: ch.became_uncertain ? P + "st-unknown" : "", text: "Стало неизвестно: " + ch.became_uncertain + " · несопоставимо: " + ch.not_comparable }),
        ...p.warnings.map((w) => el("div", { class: P + "warn", text: "⚠ " + w.message })),
      ]);
    }
    function renderResult() {
      const r = state.result, inp = r.input;
      const plans = Object.fromEntries(r.plans.map((p) => [p.id, p]));
      const pairKey = (x) => x.origin_node_id + ">" + x.destination_node_id;
      const idx = (rows) => new Map(rows.map((x) => [pairKey(x), x]));
      const bRows = r.baseline.routes, aRows = plans.A ? idx(plans.A.routes) : new Map(), bbRows = plans.B ? idx(plans.B.routes) : new Map();
      const dA = plans.A ? idx(plans.A.vs_baseline.pairs) : new Map(), dB = plans.B ? idx(plans.B.vs_baseline.pairs) : new Map();
      const head = el("div", { class: P + "meta" }, [
        el("div", { text: "Момент: " + inp.analysis_at + " (UTC " + inp.analysis_at_utc + ")" }),
        el("div", { text: "Граф " + inp.graph_id + " · " + (EVIDENCE_LABEL[inp.graph_evidence_type] || inp.graph_evidence_type) + " · режим " + (MODE_LABEL[inp.mode] || inp.mode) }),
        el("div", { class: P + "hint", text: "scenario " + inp.scenario_digest.slice(0, 12) + " · result " + r.result_digest.slice(0, 12) + " · правило " + inp.interval_rule }),
      ]);
      const cards = el("div", { class: P + "cards" }, r.plans.map(planCard));
      let ab = null;
      if (r.a_vs_b) { const s = r.a_vs_b.summary;
        ab = el("div", { class: P + "ab" }, [el("strong", { text: "B относительно A: " }),
          "сопоставимых " + s.comparable_pairs + ", средняя разница " + fmtD(s.mean_delta_m_comparable) + ", B длиннее в " + s.changes.longer + ", короче в " + s.changes.shorter + ", потеря пути в модели " + s.changes.lost_within_model]); }
      const tbody = el("tbody", {}, bRows.map((b) => {
        const k = pairKey(b);
        const tr = el("tr", { class: P + "pair" + (state.selectedPair === k ? " " + P + "active" : ""), tabindex: "0",
          onclick: () => { state.selectedPair = k; renderResult(); drawOverlays(); },
          onkeydown: (ev) => { if (ev.key === "Enter") { state.selectedPair = k; renderResult(); drawOverlays(); } } }, [
          el("td", { title: b.origin_node_id + " → " + b.destination_node_id, text: short(b.origin_node_id) + " → " + short(b.destination_node_id) }),
          cell(b), cell(aRows.get(k), dA.get(k) && dA.get(k).delta_m), cell(bbRows.get(k), dB.get(k) && dB.get(k).delta_m)]);
        return tr;
      }));
      const table = el("table", { class: P + "table" }, [el("thead", {}, el("tr", {}, ["Пара", "База", "План A", "План B"].map((t) => el("th", { text: t })))), tbody]);
      const warns = el("ul", { class: P + "lim" }, r.warnings.map((w) => el("li", { text: w.message })));
      const lims = el("ul", { class: P + "lim" }, r.limitations.map((t) => el("li", { text: t })));
      const dl = el("button", { type: "button", class: P + "btn", text: "Скачать вход и результат (JSON)", onclick: () => {
        const blob = new Blob([JSON.stringify({ payload: state.sentPayload, result: r }, null, 1)], { type: "application/json" });
        const a = el("a", { href: URL.createObjectURL(blob), download: "scenario-" + inp.scenario_digest.slice(0, 12) + ".json" });
        a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      } });
      ui.out.replaceChildren(head, cards, ab, el("div", { class: P + "hint", text: "Щёлкните строку, чтобы показать пути на карте (синий — база)." }), table,
        el("details", {}, [el("summary", { text: "Предупреждения и ограничения" }), warns, lims]), dl);
    }

    // ---------- карта ----------
    const LAYERS = [P + "edges-allowed", P + "edges-unknown", P + "edges-denied", P + "closed-A", P + "closed-B", P + "closed-A-other", P + "closed-B-other", P + "route-base", P + "route-A", P + "route-B", P + "pts"];
    const SOURCES = [P + "graph", P + "routes", P + "pts"];
    const fc = (features) => ({ type: "FeatureCollection", features });
    function edgeLine(e) { return e.geometry || [[state.nodeIndex.get(e.from).lon, state.nodeIndex.get(e.from).lat], [state.nodeIndex.get(e.to).lon, state.nodeIndex.get(e.to).lat]]; }
    function routeLine(row) {
      let cs = [];
      row.edge_ids.forEach((id, i) => {
        const e = state.edgeIndex.get(id); let g = edgeLine(e);
        if (e.from !== row.node_ids[i]) g = g.slice().reverse();
        cs = cs.concat(cs.length ? g.slice(1) : g);
      });
      return cs;
    }
    function setData(id, data) { const s = map.getSource(id); if (s) s.setData(data); else map.addSource(id, { type: "geojson", data }); }
    function ensureLayers() {
      if (map.getLayer(P + "edges-allowed")) return;
      const line = (id, src, filter, paint) => map.addLayer({ id, type: "line", source: src, filter, layout: { "line-cap": "round", "line-join": "round" }, paint });
      line(P + "edges-allowed", P + "graph", ["==", ["get", "access"], "allowed"], { "line-color": "#495057", "line-width": 2.5 });
      line(P + "edges-unknown", P + "graph", ["==", ["get", "access"], "unknown"], { "line-color": "#adb5bd", "line-width": 1.8, "line-dasharray": [2, 2] });
      line(P + "edges-denied", P + "graph", ["==", ["get", "access"], "denied"], { "line-color": "#c92a2a", "line-width": 1.2, "line-opacity": 0.6 });
      for (const k of ["A", "B"]) {
        line(P + "closed-" + k + "-other", P + "graph", ["==", ["get", "c" + k], "other"], { "line-color": PLAN_COLORS[k], "line-width": 5, "line-offset": k === "A" ? -3 : 3, "line-opacity": 0.35, "line-dasharray": [1, 1.5] });
        line(P + "closed-" + k, P + "graph", ["==", ["get", "c" + k], "active"], { "line-color": PLAN_COLORS[k], "line-width": 7, "line-offset": k === "A" ? -3 : 3, "line-opacity": 0.85 });
      }
      for (const [k, off] of [["base", 0], ["A", -5], ["B", 5]])
        line(P + "route-" + k, P + "routes", ["==", ["get", "kind"], k], { "line-color": ROUTE_COLORS[k], "line-width": k === "base" ? 5 : 3.5, "line-offset": off, "line-opacity": 0.9 });
      map.addLayer({ id: P + "pts", type: "circle", source: P + "pts", paint: {
        "circle-radius": ["match", ["get", "kind"], "node", 3, 7],
        "circle-color": ["match", ["get", "kind"], "origin", "#2b8a3e", "dest", "#212529", "#868e96"],
        "circle-stroke-color": "#fff", "circle-stroke-width": ["match", ["get", "kind"], "node", 0, 2],
        "circle-opacity": ["match", ["get", "kind"], "node", 0.5, 1] } });
    }
    function drawGraph(fit) {
      if (!map || !state.graph) return;
      const go = () => {
        if (state.destroyed) return;
        drawOverlays();
        if (fit) {
          let W = 180, S = 90, E = -180, N = -90;
          for (const n of state.graph.nodes) { W = Math.min(W, n.lon); E = Math.max(E, n.lon); S = Math.min(S, n.lat); N = Math.max(N, n.lat); }
          map.fitBounds([[W, S], [E, N]], { padding: 40, duration: 0 });
        }
      };
      if (styleReady) go(); else pending = go;
    }
    function drawOverlays() {
      // isStyleLoaded() ложно и во время обновления GeoJSON-источника, поэтому — собственный флаг готовности стиля
      if (!map || !styleReady || !state.graph || !state.payload) return;
      const cA = closedIds("A"), cB = closedIds("B"), aA = activeIds("A"), aB = activeIds("B");
      const st = (all, act, id) => (act.has(id) ? "active" : all.has(id) ? "other" : "no");
      setData(P + "graph", fc(state.graph.edges.map((e) => ({ type: "Feature", properties: { id: e.id, access: e.access, cA: st(cA, aA, e.id), cB: st(cB, aB, e.id) },
        geometry: { type: "LineString", coordinates: edgeLine(e) } }))));
      const routes = [];
      if (state.result && state.selectedPair) {
        const pick = (rows) => rows.find((x) => x.origin_node_id + ">" + x.destination_node_id === state.selectedPair);
        const add = (row, kind) => { if (row && row.status === "ok" && row.edge_ids.length) routes.push({ type: "Feature", properties: { kind }, geometry: { type: "LineString", coordinates: routeLine(row) } }); };
        add(pick(state.result.baseline.routes), "base");
        for (const p of state.result.plans) add(pick(p.routes), p.id);
      }
      setData(P + "routes", fc(routes));
      const pts = [];
      const o = new Set(state.payload.origin_node_ids), d = new Set(state.payload.destination_node_ids);
      for (const n of state.graph.nodes) {
        const kind = o.has(n.id) ? "origin" : d.has(n.id) ? "dest" : state.clickMode === "close" ? null : "node";
        if (kind) pts.push({ type: "Feature", properties: { id: n.id, kind }, geometry: { type: "Point", coordinates: [n.lon, n.lat] } });
      }
      setData(P + "pts", fc(pts));
      ensureLayers();
    }
    function onClick(ev) {
      if (!state.graph || !state.payload) return;
      const bb = [[ev.point.x - 6, ev.point.y - 6], [ev.point.x + 6, ev.point.y + 6]];
      if (state.clickMode === "close") {
        const f = map.queryRenderedFeatures(bb, { layers: [P + "edges-allowed", P + "edges-unknown", P + "edges-denied"].filter((l) => map.getLayer(l)) });
        if (f.length) toggleEdge(f[0].properties.id);
      } else {
        const f = map.queryRenderedFeatures(bb, { layers: map.getLayer(P + "pts") ? [P + "pts"] : [] });
        if (f.length) addPoint(f[0].properties.id);
      }
    }
    let styleReady = false, pending = null;
    function onStyle() {  // первая загрузка или смена стиля подложки: слои надо добавить заново
      if (state.destroyed) return;
      styleReady = true;
      const f = pending; pending = null;
      if (f) f(); else drawOverlays();
    }
    if (map) {
      map.on("click", onClick); listeners.push(["click", onClick]);
      map.on("style.load", onStyle); listeners.push(["style.load", onStyle]);
      if (map.isStyleLoaded && map.isStyleLoaded()) styleReady = true;
      else if (map.style && map.style._loaded) styleReady = true;
    }

    function destroy() {
      state.destroyed = true;
      if (map) {
        for (const [ev, fn] of listeners) map.off(ev, fn);
        for (const l of LAYERS) if (map.getLayer(l)) map.removeLayer(l);
        for (const s of SOURCES) if (map.getSource(s)) map.removeSource(s);
      }
      wrap.remove();
    }
    return { destroy };
  }

  root.CivicScenarios = { mount };
})(typeof window !== "undefined" ? window : globalThis);
