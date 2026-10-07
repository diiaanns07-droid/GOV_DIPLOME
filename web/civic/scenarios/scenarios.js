/* R07 CivicScenarios (раунд 13) — сравнение пешей доступности: база, вариант A, вариант B.
 *
 * window.CivicScenarios.mount({root, map, api, apiPrefix?}) -> {destroy, cancelTool}
 *   api.request(method, path, body, {signal}) -> Promise<data> (R01); путь = apiPrefix + "/scenarios/...".
 *   map — основной MapLibre instance или null (тогда без карты).
 *
 * Пользовательский путь без знания ID: указать места на карте -> точка привязывается к ближайшему узлу
 * сети с ПОДТВЕРЖДЁННЫМ пешим доступом (≤150 м; дальше — отказ), показаны исходная и найденная точки;
 * варианты A/B — явно выбранные участки сети и период; результат — длина пути в метрах (не время);
 * объяснение — помощник R09 по расчёту сервера ("result:" + result_digest), без цифр из браузера.
 *
 * Карта: клики перехватываются ТОЛЬКО в явном режиме выбора (кнопка «Указать на карте» / «Выбрать участки»).
 * Режим объявляется событием "civic-scenarios:tool" {active, kind} (как civic-editor:tool у R04);
 * Escape завершает режим (preventDefault — оболочка не закрывает панель); destroy снимает всё.
 * Текст выводится через textContent. Слои/источники/классы — префикс civic-r07-.
 */
(function (root) {
  "use strict";
  const P = "civic-r07-";
  const SNAP_MAX_M = 150, SEARCH_MAX_M = 1000, CELL_DEG_LAT = 0.002, R_EARTH = 6371008.8;
  const MAX_PLACES = 5;
  const PLAN_IDS = ["A", "B"];
  const PLAN_COLORS = { A: "#d9480f", B: "#7048e8" };
  const ROUTE_COLORS = { base: "#1971c2", A: "#d9480f", B: "#7048e8" };
  const STATUS_LABEL = { unknown: "доступ не подтверждён", unreachable: "нет пути в модели" };
  const REASON_LABEL = {
    path_only_via_unknown_access: "путь есть только через участки с неизвестным пешим доступом — он не считается",
    path_may_exist_outside_graph: "путь может проходить вне выгрузки сети",
    no_path_within_model: "в этой модели сети пути нет; это не доказанная недоступность на местности",
  };
  const ACCESS_LABEL = { allowed: "пеший доступ подтверждён", unknown: "доступ неизвестен", denied: "доступ запрещён" };
  const EVIDENCE_LABEL = { synthetic: "СИНТЕТИКА", derived: "производные данные", observed: "наблюдение", hypothesis: "гипотеза" };

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
  const fmtCoord = (p) => p[1].toFixed(5) + ", " + p[0].toFixed(5);
  const isoWithOffset = (local, off) => (local.length === 16 ? local + ":00" : local) + off;
  function splitIso(s) {
    const m = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.exec(s || "");
    return m ? { local: m[1], off: m[2] === "Z" ? "+00:00" : m[2] } : { local: "", off: "+05:00" };
  }
  const active = (c, at) => Date.parse(c.start_at) <= at && at < Date.parse(c.end_at);

  // ------------------------------------------------------------------ привязка к сети
  // Повтор engine/civic_scenarios/snap.py: те же кандидаты, порог, ничья по ID, компоненты.
  function haversine(a, b) {
    const r = Math.PI / 180, p1 = a[1] * r, p2 = b[1] * r;
    const h = Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin((b[0] - a[0]) * r / 2) ** 2;
    return 2 * R_EARTH * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  function buildSnapIndex(graph) {
    const coords = new Map(graph.nodes.map((n) => [n.id, [n.lon, n.lat]]));
    const mid = graph.nodes.reduce((s, n) => s + n.lat, 0) / Math.max(1, graph.nodes.length);
    const cellLat = CELL_DEG_LAT, cellLon = CELL_DEG_LAT / Math.max(0.2, Math.cos(mid * Math.PI / 180));
    const parent = new Map(), allowed = new Set(), other = new Set();
    const find = (x) => { while (parent.get(x) !== x) { parent.set(x, parent.get(parent.get(x))); x = parent.get(x); } return x; };
    for (const e of graph.edges) {
      if (e.access === "allowed") {
        allowed.add(e.from); allowed.add(e.to);
        if (!parent.has(e.from)) parent.set(e.from, e.from);
        if (!parent.has(e.to)) parent.set(e.to, e.to);
        const a = find(e.from), b = find(e.to);
        if (a !== b) { if (a < b) parent.set(b, a); else parent.set(a, b); }   // корень — минимальный ID
      } else { other.add(e.from); other.add(e.to); }
    }
    const size = new Map();
    for (const e of graph.edges) if (e.access === "allowed") { const r = find(e.from); size.set(r, (size.get(r) || 0) + 1); }
    let main = null;
    for (const [r, s] of size) if (main === null || s > size.get(main) || (s === size.get(main) && r > main)) main = r;
    const comp = new Map([...allowed].map((n) => [n, find(n)]));
    const key = (lon, lat) => Math.floor(lon / cellLon) + "," + Math.floor(lat / cellLat);
    const grid = (ids) => {
      const g = new Map();
      for (const id of [...ids].sort()) { const c = coords.get(id); const k = key(c[0], c[1]); if (!g.has(k)) g.set(k, []); g.get(k).push(id); }
      return g;
    };
    for (const n of allowed) other.delete(n);
    return { coords, cellLat, cellLon, key, comp, size, main, bbox: Array.isArray(graph.bbox) && graph.bbox.length === 4 ? graph.bbox : null,
      allowed: grid(allowed), other: grid(other), mainGrid: grid([...allowed].filter((n) => comp.get(n) === main)) };
  }
  function nearest(idx, grid, lon, lat, limit) {
    const cx = Math.floor(lon / idx.cellLon), cy = Math.floor(lat / idx.cellLat);
    const rings = Math.ceil(limit / (idx.cellLat * 111000)) + 1;
    let best = null;
    for (let dx = -rings; dx <= rings; dx++) for (let dy = -rings; dy <= rings; dy++) {
      for (const n of grid.get((cx + dx) + "," + (cy + dy)) || []) {
        const d = haversine([lon, lat], idx.coords.get(n));
        if (d <= limit && (best === null || d < best[0] || (d === best[0] && n < best[1]))) best = [d, n];
      }
    }
    return best;
  }
  const r1 = (x) => Math.round(x * 10) / 10;
  function snapPoint(idx, lon, lat, maxM) {
    maxM = maxM || SNAP_MAX_M;
    const out = { input: [lon, lat], max_m: maxM, status: null, node_id: null, node: null, distance_m: null, nearest_allowed_m: null,
      nearer_unverified_m: null, component_edges: null, main_component: null, main_alternative: null };
    if (idx.bbox && !(idx.bbox[0] <= lon && lon <= idx.bbox[2] && idx.bbox[1] <= lat && lat <= idx.bbox[3])) { out.status = "outside_graph"; return out; }
    const best = nearest(idx, idx.allowed, lon, lat, SEARCH_MAX_M);
    const other = nearest(idx, idx.other, lon, lat, best ? best[0] : SEARCH_MAX_M);
    if (other && (!best || other[0] < best[0])) out.nearer_unverified_m = r1(other[0]);
    if (!best) { out.status = "too_far"; return out; }
    out.nearest_allowed_m = r1(best[0]);
    if (best[0] > maxM) { out.status = "too_far"; return out; }
    const c = idx.comp.get(best[1]);
    Object.assign(out, { status: "ok", node_id: best[1], node: idx.coords.get(best[1]).slice(), distance_m: r1(best[0]),
      component_edges: idx.size.get(c), main_component: c === idx.main });
    if (!out.main_component) {
      const alt = nearest(idx, idx.mainGrid, lon, lat, maxM);
      if (alt) out.main_alternative = { node_id: alt[1], node: idx.coords.get(alt[1]).slice(), distance_m: r1(alt[0]) };
    }
    return out;
  }
  function fromNode(idx, id, label) {   // точка кейса задана узлом: привязка не требуется
    const c = idx.coords.get(id);
    if (!c) return null;
    const comp = idx.comp.get(id);
    return { input: c.slice(), node_id: id, node: c.slice(), distance_m: 0, status: "ok", max_m: SNAP_MAX_M, label,
      component_edges: comp ? idx.size.get(comp) : 0, main_component: comp === idx.main, nearer_unverified_m: null, main_alternative: null, from_case: true };
  }

  // ------------------------------------------------------------------ компонент
  function mount(opts) {
    const host = opts && opts.root, map = (opts && opts.map) || null, api = opts && opts.api;
    if (!host || !api || typeof api.request !== "function") throw new Error("CivicScenarios.mount: нужны root и api.request");
    const prefix = (opts.apiPrefix === undefined ? "/api/civic/v1" : opts.apiPrefix) + "/scenarios";
    const S = {
      graphs: [], cases: [], graph: null, idx: null, edgeIndex: new Map(), graphSeq: 0, drawnGraph: null,
      places: { origins: [], dests: [] }, plans: { A: [], B: [] }, editPlan: "A", analysisAt: "2026-10-10T12:00:00+05:00",
      tool: null, chooser: null,
      run: { seq: 0, controller: null, pending: false, error: null, result: null, resultKey: null, payload: null },
      selectedPair: null, assistant: null, assistantFor: null, destroyed: false,
    };
    const mapHandlers = [], docHandlers = [];
    const ui = {};
    const wrap = el("section", { class: P + "panel", "aria-label": "Сравнение вариантов ограничений" });
    host.appendChild(wrap);
    const req = (method, path, body, o) => api.request(method, prefix + path, body, o);

    ui.notice = el("div", { class: P + "notice", role: "note" }, [
      el("strong", { text: "Гипотетический сценарий на снимке данных." }),
      " Перекрытия задаёте вы — это не официальное решение. Считается длина пешего пути по сети OSM (снимок, не live);" +
      " время в пути, пробки и транспорт не моделируются. Фон карты вне линий сети не означает, что там можно посчитать путь.",
    ]);
    ui.graphSel = el("select", { class: P + "select", "aria-label": "Сеть", onchange: () => selectGraph(ui.graphSel.value, null) });
    ui.caseSel = el("select", { class: P + "select", "aria-label": "Пример", onchange: () => applyCase(ui.caseSel.value) });
    ui.graphInfo = el("div", { class: P + "graphinfo" });
    ui.caseNote = el("p", { class: P + "hint", hidden: true });
    ui.tool = el("div", { class: P + "toolbar", role: "status", "aria-live": "polite", hidden: true });
    ui.places = el("div", { class: P + "places" });
    ui.planTabs = el("div", { class: P + "tabs", role: "tablist" });
    ui.planBody = el("div", { class: P + "plan" });
    ui.chooser = el("div", { class: P + "chooser", hidden: true });
    ui.atLocal = el("input", { type: "datetime-local", class: P + "input", "aria-label": "Момент анализа", onchange: syncAt });
    ui.atOff = el("select", { class: P + "select " + P + "off", "aria-label": "Смещение UTC", onchange: syncAt },
      ["+05:00", "+06:00", "+00:00"].map((o) => el("option", { value: o, text: "UTC" + o })));
    ui.atInfo = el("div", { class: P + "hint" });
    ui.run = el("button", { class: P + "btn " + P + "primary", type: "button", text: "Сравнить", disabled: true, onclick: run });
    ui.cancel = el("button", { class: P + "btn", type: "button", text: "Отменить расчёт", hidden: true, onclick: () => cancelRun(false) });
    ui.runInfo = el("div", { class: P + "hint", role: "status", "aria-live": "polite" });
    ui.err = el("div", { class: P + "error", role: "alert", hidden: true });
    ui.stale = el("div", { class: P + "stale", role: "status", hidden: true });
    ui.out = el("div", { class: P + "result", "aria-live": "polite" });
    ui.assistant = el("div", { class: P + "assistant" });

    wrap.append(
      el("h2", { class: P + "title", text: "Сравнение вариантов: база, A и B" }),
      ui.notice,
      el("div", { class: P + "row" }, [el("label", { class: P + "lbl" }, ["Сеть ", ui.graphSel]), el("label", { class: P + "lbl" }, ["Пример ", ui.caseSel])]),
      ui.graphInfo, ui.caseNote, ui.tool,
      el("h3", { class: P + "step", text: "1. Откуда и куда" }), ui.places,
      el("h3", { class: P + "step", text: "2. Варианты ограничений" }), ui.planTabs, ui.planBody, ui.chooser,
      el("h3", { class: P + "step", text: "3. Момент, на который сравниваем" }),
      el("div", { class: P + "row" }, [el("label", { class: P + "lbl" }, ["Дата и время ", ui.atLocal]), ui.atOff]), ui.atInfo,
      el("div", { class: P + "row" }, [ui.run, ui.cancel]), ui.runInfo,
      ui.err, ui.stale, ui.out, ui.assistant,
    );

    function showError(e) {
      ui.err.hidden = false;
      ui.err.textContent = "Ошибка: " + ((e && (e.message || e.code)) || String(e)) + (e && e.code ? " [" + e.code + "]" : "");
    }
    function clearError() { ui.err.hidden = true; ui.err.textContent = ""; }

    // ---------------------------------------------------------------- загрузка
    Promise.all([req("GET", "/graphs"), req("GET", "/cases")]).then(([g, c]) => {
      if (S.destroyed) return;
      S.graphs = g.items || []; S.cases = c.items || [];
      ui.graphSel.replaceChildren(...S.graphs.map((x) => el("option", { value: x.id, text: (x.evidence_type === "synthetic" ? "[СИНТЕТИКА] " : "") + x.label })));
      for (const nr of g.not_ready || []) ui.graphSel.appendChild(el("option", { disabled: true, text: "[NOT_READY] " + nr.mode + ": нет проверенного графа" }));
      const preferred = S.graphs.find((x) => x.default === true) || S.graphs[0];
      if (preferred) selectGraph(preferred.id, null);
    }).catch((e) => { if (!S.destroyed) showError(e); });

    function selectGraph(id, caseId) {
      clearError(); setTool(null);
      const seq = ++S.graphSeq;
      invalidate("graph");
      S.graph = null; S.idx = null; S.drawnGraph = null; S.places = { origins: [], dests: [] }; S.plans = { A: [], B: [] };
      ui.run.disabled = true; ui.caseSel.disabled = true;
      const meta = S.graphs.find((x) => x.id === id);
      ui.graphInfo.textContent = "Загружаем сеть" + (meta && meta.edges > 20000 ? " (" + meta.edges.toLocaleString("ru-RU") + " участков, это может занять несколько секунд)…" : "…");
      ui.graphSel.value = id;
      renderAll();
      if (map) for (const s of SOURCES) { const src = map.getSource(s); if (src) src.setData(fc([])); }
      return req("GET", "/graphs/" + encodeURIComponent(id)).then((d) => {
        if (S.destroyed || seq !== S.graphSeq) return;   // пользователь уже выбрал другую сеть
        const g = d.graph;
        S.graph = g; S.edgeIndex = new Map(g.edges.map((e) => [e.id, e])); S.idx = buildSnapIndex(g);
        renderGraphInfo();
        const cases = S.cases.filter((c) => c.payload.graph_id === id);
        ui.caseSel.replaceChildren(el("option", { value: "", text: "— свой сценарий —" }), ...cases.map((c) => el("option", { value: c.case_id, text: c.title })));
        ui.caseSel.disabled = false;
        if (caseId) { ui.caseSel.value = caseId; applyCase(caseId); } else renderAll();
        drawGraph(g.nodes.length < 10000);
      }).catch((e) => { if (!S.destroyed && seq === S.graphSeq) { ui.graphInfo.textContent = "Сеть не загружена."; showError(e); } });
    }

    function renderGraphInfo() {
      const g = S.graph;
      const lim = el("ul", { class: P + "lim" }, (g.limitations || []).map((t) => el("li", { text: t })));
      const snap = g.source && g.source.snapshot_at ? "Снимок OSM: " + g.source.snapshot_at.slice(0, 10) + (g.source.retrieved_at ? ", получен " + g.source.retrieved_at : "") + ". " : "";
      ui.graphInfo.replaceChildren(
        el("div", {}, [el("span", { class: P + "badge " + P + "ev-" + g.evidence_type, text: EVIDENCE_LABEL[g.evidence_type] || g.evidence_type }),
          " пешая сеть · участков " + g.edges.length.toLocaleString("ru-RU")]),
        el("p", { class: P + "hint", text: snap + "Маршрут строится только по участкам с подтверждённым пешим доступом; участки с неизвестным доступом (серый пунктир) не используются." }),
        el("details", {}, [el("summary", { text: "Пределы данных и источник" }), lim,
          el("div", { class: P + "src", text: "graph " + g.id + " · digest " + g.digest + (g.license && g.license.id ? " · " + g.license.id : "") })]),
      );
    }

    function applyCase(caseId) {
      if (!S.graph) return;
      setTool(null); invalidate("case");
      const c = S.cases.find((x) => x.case_id === caseId);
      S.places = { origins: [], dests: [] }; S.plans = { A: [], B: [] };
      if (c) {
        const p = c.payload, places = c.places || {};
        // Места кейса с координатами проходят ту же привязку, что и клик пользователя.
        const fromPlace = (pl, fallbackId, label) => {
          if (pl && Array.isArray(pl.input)) { const s = snapPoint(S.idx, pl.input[0], pl.input[1]); s.label = pl.label || label; return s.status === "ok" ? s : null; }
          return fromNode(S.idx, fallbackId, label);
        };
        S.places.origins = p.origin_node_ids.map((id, i) => fromPlace(i === 0 ? places.origin : null, id, "старт из примера")).filter(Boolean);
        S.places.dests = p.destination_node_ids.map((id, i) => fromPlace(i === 0 ? places.destination : null, id, "цель из примера")).filter(Boolean);
        for (const pl of p.plans) S.plans[pl.id] = pl.closures.map((x) => ({ edge_ids: x.edge_ids.slice(), start_at: x.start_at, end_at: x.end_at }));
        S.analysisAt = p.analysis_at;
      }
      ui.caseNote.hidden = !(c && c.note);
      ui.caseNote.textContent = c && c.note ? "Пример (" + (EVIDENCE_LABEL[c.evidence_type] || c.evidence_type) + "): " + c.note : "";
      const s = splitIso(S.analysisAt);
      ui.atLocal.value = s.local; if ([...ui.atOff.options].some((o) => o.value === s.off)) ui.atOff.value = s.off;
      renderAll(); drawOverlays();
      const pts = [...S.places.origins, ...S.places.dests].map((x) => x.node);
      if (pts.length) fitCoordinates(pts);
    }
    function syncAt() {
      if (!ui.atLocal.value) return;
      const at = isoWithOffset(ui.atLocal.value, ui.atOff.value);
      if (at !== S.analysisAt) { S.analysisAt = at; inputChanged(); }
    }

    // ---------------------------------------------------------------- вход сценария
    function buildPayload() {
      const g = S.graph;
      const uniq = (list) => [...new Set(list.map((x) => x.node_id))];
      return { schema_version: "civic-scenario-v1", city: g.city, graph_id: g.id, graph_digest: g.digest, mode: g.mode,
        analysis_at: S.analysisAt, origin_node_ids: uniq(S.places.origins), destination_node_ids: uniq(S.places.dests),
        plans: PLAN_IDS.map((id) => ({ id, closures: S.plans[id].filter((c) => c.edge_ids.length).map((c) => ({ edge_ids: c.edge_ids.slice().sort(), start_at: c.start_at, end_at: c.end_at })) })) };
    }
    const inputKey = () => (S.graph ? JSON.stringify(buildPayload()) : null);
    function inputChanged() {
      // Вход изменился во время расчёта: этот расчёт уже не про текущий сценарий — отменяем его,
      // чтобы поздний ответ не появился на экране.
      if (S.run.pending) { cancelRun(true); S.run.cancelNote = "Вход изменён во время расчёта — расчёт отменён. Нажмите «Сравнить»."; }
      renderAll(); drawOverlays();
    }
    function invalidate() {   // смена сети/примера: прежний результат больше не про текущий вход
      cancelRun(true);
      S.run.result = null; S.run.resultKey = null; S.selectedPair = null; S.run.error = null;
      destroyAssistant();
    }

    // ---------------------------------------------------------------- места
    function renderPlaces() {
      ui.places.replaceChildren();
      if (!S.graph) return;
      const block = (key, title, verb) => {
        const list = S.places[key];
        const rows = list.map((p, i) => placeRow(key, p, i, title));
        const pick = el("button", { type: "button", class: P + "btn" + (S.tool && S.tool.kind === key ? " " + P + "active" : ""),
          text: list.length ? verb + " заново" : "Указать на карте", onclick: () => setTool({ kind: key, replace: true }) });
        const add = list.length && list.length < MAX_PLACES ? el("button", { type: "button", class: P + "btn", text: "+ ещё", onclick: () => setTool({ kind: key, replace: false }) }) : null;
        return el("div", { class: P + "placeblock", "data-role": key }, [el("strong", { text: title }), ...rows, el("div", { class: P + "row" }, [pick, add])]);
      };
      ui.places.append(block("origins", "Откуда", "Указать"), block("dests", "Куда", "Указать"));
      const o = new Set(S.places.origins.map((x) => x.node_id));
      if (S.places.dests.some((d) => o.has(d.node_id))) ui.places.append(el("p", { class: P + "warn", text: "Старт и цель привязаны к одному узлу сети — длина такой пары 0 м по определению." }));
    }
    function placeRow(key, p, i, title) {
      const lines = [];
      if (p.from_case) lines.push(el("div", { class: P + "hint", text: "Узел сети из примера (" + fmtCoord(p.node) + ")." }));
      else {
        lines.push(el("div", { text: "Указано: " + fmtCoord(p.input) + (p.label ? " · " + p.label : "") }));
        lines.push(el("div", { class: P + "hint", text: "Привязано к узлу сети в " + fmtM(p.distance_m) + " (порог " + p.max_m + " м). Отрезок до сети не входит в длину и не проверен как путь — убедитесь, что точка на вашей стороне улицы или реки." }));
      }
      if (p.nearer_unverified_m !== null) lines.push(el("div", { class: P + "hint", text: "Ближе (" + fmtM(p.nearer_unverified_m) + ") есть линия, где пеший доступ в OSM не подтверждён: она в расчёт не берётся." }));
      if (p.main_component === false) {
        lines.push(el("div", { class: P + "warn", text: "Найденный узел — во фрагменте сети из " + p.component_edges + " участков, не связанном с основной пешей сетью модели. Путь в другую часть города, скорее всего, не найдётся." }));
        if (p.main_alternative) lines.push(el("button", { type: "button", class: P + "btn", text: "Использовать узел основной сети (" + fmtM(p.main_alternative.distance_m) + ")",
          onclick: () => { Object.assign(p, { node_id: p.main_alternative.node_id, node: p.main_alternative.node, distance_m: p.main_alternative.distance_m, main_component: true, component_edges: S.idx.size.get(S.idx.main), main_alternative: null, chosen_alternative: true }); inputChanged(); } }));
      }
      if (p.chosen_alternative) lines.push(el("div", { class: P + "hint", text: "Выбран узел основной сети по вашему решению." }));
      const remove = el("button", { type: "button", class: P + "link", text: "убрать", "aria-label": "Убрать: " + title + " " + (i + 1), onclick: () => { S.places[key].splice(i, 1); inputChanged(); } });
      return el("div", { class: P + "place", "data-node": p.node_id }, [el("div", { class: P + "row" }, [el("span", { class: P + "chip", text: title + (S.places[key].length > 1 ? " " + (i + 1) : "") }), remove]), ...lines]);
    }
    function onPlaceClick(lngLat) {
      const s = snapPoint(S.idx, lngLat.lng, lngLat.lat);
      const kind = S.tool.kind;
      if (s.status !== "ok") {
        S.tool.message = s.status === "outside_graph"
          ? "Точка вне выгрузки сети (" + fmtCoord(s.input) + "): здесь расчёт невозможен. Укажите место внутри рамки."
          : "Рядом нет участка с подтверждённым пешим доступом: ближайший " + (s.nearest_allowed_m !== null ? "в " + fmtM(s.nearest_allowed_m) : "дальше 1 км") + ", порог " + SNAP_MAX_M + " м. Точку не переносим — укажите место ближе к тротуару или пешеходной дорожке.";
        S.tool.lastInput = s.input;
        renderTool(); drawOverlays();
        return;
      }
      if (S.tool.replace) S.places[kind] = [s]; else if (S.places[kind].length < MAX_PLACES) S.places[kind].push(s);
      setTool(null);
      inputChanged();
    }

    // ---------------------------------------------------------------- варианты A/B
    function closedSet(id, onlyActive) {
      const at = Date.parse(S.analysisAt), s = new Set();
      for (const c of S.plans[id]) if (!onlyActive || active(c, at)) for (const e of c.edge_ids) s.add(e);
      return s;
    }
    function defaultClosure() {
      const at = splitIso(S.analysisAt), d = new Date(at.local + ":00Z");
      const end = new Date(d.getTime() + 8 * 3600e3).toISOString().slice(0, 16);
      return { edge_ids: [], start_at: at.local + ":00" + at.off, end_at: end + ":00" + at.off };
    }
    function renderPlans() {
      ui.planTabs.replaceChildren(); ui.planBody.replaceChildren();
      if (!S.graph) return;
      ui.planTabs.append(...PLAN_IDS.map((id) => el("button", {
        type: "button", role: "tab", class: P + "tab" + (S.editPlan === id ? " " + P + "active" : ""), "aria-selected": S.editPlan === id ? "true" : "false",
        style: "border-color:" + PLAN_COLORS[id], onclick: () => { S.editPlan = id; if (S.tool && S.tool.kind === "close") S.tool.plan = id; renderPlans(); renderTool(); },
        text: "Вариант " + id + " · участков: " + closedSet(id).size })));
      const plan = S.plans[S.editPlan], at = Date.parse(S.analysisAt);
      const items = plan.map((c, i) => {
        const s = splitIso(c.start_at), e = splitIso(c.end_at);
        const sIn = el("input", { type: "datetime-local", class: P + "input", value: s.local, "aria-label": "Начало", onchange: () => { c.start_at = isoWithOffset(sIn.value, s.off); inputChanged(); } });
        const eIn = el("input", { type: "datetime-local", class: P + "input", value: e.local, "aria-label": "Конец", onchange: () => { c.end_at = isoWithOffset(eIn.value, e.off); inputChanged(); } });
        const bad = !(Date.parse(c.start_at) < Date.parse(c.end_at));
        const segs = c.edge_ids.map((id) => {
          const ed = S.edgeIndex.get(id);
          return el("li", {}, [el("span", { text: segmentLabel(ed, id) }),
            el("button", { type: "button", class: P + "link", text: "×", "aria-label": "Открыть участок " + id, onclick: () => { c.edge_ids = c.edge_ids.filter((x) => x !== id); inputChanged(); } })]);
        });
        return el("li", { class: P + "closure" }, [
          el("div", { class: P + "row" }, [el("label", { class: P + "lbl" }, ["с ", sIn]), el("label", { class: P + "lbl" }, ["до ", eIn])]),
          el("div", { class: bad ? P + "warn" : P + "hint", text: bad ? "Конец должен быть позже начала." : "Период [с, до): начало включительно, конец — нет. В выбранный момент: " + (active(c, at) ? "действует" : "не действует") + "." }),
          el("ul", { class: P + "segs" }, segs.length ? segs : [el("li", { class: P + "hint", text: "Участки не выбраны." })]),
          plan.length > 1 ? el("button", { type: "button", class: P + "link", text: "удалить период", onclick: () => { plan.splice(i, 1); inputChanged(); } }) : null,
        ]);
      });
      if (!plan.length) plan.push(defaultClosure());
      const picking = S.tool && S.tool.kind === "close";
      ui.planBody.append(
        el("ul", { class: P + "closures" }, items.length ? items : []),
        el("div", { class: P + "row" }, [
          el("button", { type: "button", class: P + "btn" + (picking ? " " + P + "active" : ""), text: picking ? "Готово" : "Выбрать участки на карте",
            onclick: () => setTool(picking ? null : { kind: "close", plan: S.editPlan }) }),
          el("button", { type: "button", class: P + "link", text: "+ период", onclick: () => { plan.push(defaultClosure()); renderPlans(); } }),
        ]),
        el("p", { class: P + "hint", text: "Закрывается выбранный участок сети целиком и в обе стороны. Произвольную область нарисовать нельзя: линии, пересекающиеся только на экране (мост, тоннель, разные уровни), в модели не связаны — при наложении выберите нужную в списке." }),
      );
      if (!items.length) renderPlans();
    }
    function segmentLabel(ed, id) {
      if (!ed) return id;
      return (ed.name || "участок без названия") + " · " + fmtM(ed.length_m) + " · " + (ACCESS_LABEL[ed.access] || ed.access) + (ed.osm_way_id ? " · OSM way " + ed.osm_way_id : "") ;
    }
    function toggleEdge(id) {
      const plan = S.plans[S.tool.plan];
      const holder = plan.find((c) => c.edge_ids.includes(id));
      if (holder) holder.edge_ids = holder.edge_ids.filter((x) => x !== id);
      else { if (!plan.length) plan.push(defaultClosure()); plan[plan.length - 1].edge_ids.push(id); }
      S.chooser = null; renderChooser();
      inputChanged();
    }
    function onSegmentClick(point) {
      const bb = [[point.x - 8, point.y - 8], [point.x + 8, point.y + 8]];
      const layers = [P + "edges-allowed", P + "edges-unknown", P + "edges-denied"].filter((l) => map.getLayer(l));
      const ids = [...new Set(map.queryRenderedFeatures(bb, { layers }).map((f) => f.properties.id))].filter((id) => S.edgeIndex.has(id));
      if (!ids.length) { S.tool.message = "Здесь нет участка сети. Фон карты — не дорожный объект модели; приблизьте карту к линии."; renderTool(); return; }
      if (ids.length === 1) { toggleEdge(ids[0]); return; }
      S.chooser = { ids: ids.slice(0, 8) }; renderChooser(); drawOverlays();
    }
    function renderChooser() {
      if (!S.chooser) { ui.chooser.hidden = true; ui.chooser.replaceChildren(); return; }
      ui.chooser.hidden = false;
      const plan = S.tool ? S.tool.plan : S.editPlan, sel = closedSet(plan);
      ui.chooser.replaceChildren(
        el("strong", { text: "Под курсором несколько участков (" + S.chooser.ids.length + "). Линии на экране пересекаются, но в модели они связаны только общими узлами OSM. Какой закрыть в варианте " + plan + "?" }),
        el("ul", {}, S.chooser.ids.map((id) => el("li", {}, [el("button", { type: "button", class: P + "btn", text: (sel.has(id) ? "Открыть: " : "Закрыть: ") + segmentLabel(S.edgeIndex.get(id), id),
          onmouseenter: () => { S.chooser.hover = id; drawOverlays(); }, onfocus: () => { S.chooser.hover = id; drawOverlays(); },
          onclick: () => toggleEdge(id) })]))),
        el("button", { type: "button", class: P + "link", text: "Отмена", onclick: () => { S.chooser = null; renderChooser(); drawOverlays(); } }),
      );
    }

    // ---------------------------------------------------------------- режим выбора на карте
    function setTool(tool) {
      const was = !!S.tool;
      S.tool = tool;
      if (!tool) { S.chooser = null; renderChooser(); }
      if (map) { try { map.getCanvas().style.cursor = tool ? "crosshair" : ""; } catch (e) { /* карта снята */ } }
      if (was !== !!tool || tool) wrap.dispatchEvent(new CustomEvent("civic-scenarios:tool", { bubbles: true, detail: { active: !!tool, kind: tool ? tool.kind : null } }));
      renderTool(); renderPlaces(); renderPlans(); drawOverlays();
    }
    function renderTool() {
      const t = S.tool;
      ui.tool.hidden = !t;
      if (!t) { ui.tool.replaceChildren(); return; }
      const what = t.kind === "origins" ? "место «Откуда»" : t.kind === "dests" ? "место «Куда»" : "участки для варианта " + t.plan;
      ui.tool.replaceChildren(
        el("strong", { text: "Режим выбора: " + what + "." }),
        " Щёлкните по карте. Esc или «Готово» — выйти; пока режим включён, клики по карте не открывают карточки объектов.",
        t.message ? el("div", { class: P + "warn", text: t.message }) : null,
        el("button", { type: "button", class: P + "btn", text: "Готово", onclick: () => setTool(null) }),
      );
    }
    function onMapClick(e) {
      if (!S.tool || !S.graph || S.destroyed) return;   // без явного режима клик принадлежит публичной карте
      if (S.tool.kind === "close") onSegmentClick(e.point); else onPlaceClick(e.lngLat);
    }
    function onKey(e) {
      if (e.key !== "Escape" || !S.tool) return;
      e.preventDefault();          // оболочка R01 не закроет панель: Escape завершил только режим выбора
      setTool(null);
    }

    // ---------------------------------------------------------------- расчёт
    function readiness() {
      if (!S.graph) return "Сеть ещё загружается.";
      if (!S.places.origins.length || !S.places.dests.length) return "Укажите на карте, откуда и куда.";
      for (const id of PLAN_IDS) for (const c of S.plans[id]) if (!(Date.parse(c.start_at) < Date.parse(c.end_at))) return "У варианта " + id + " конец периода раньше начала.";
      return null;
    }
    function renderRunBar() {
      const notReady = readiness();
      ui.run.disabled = !!notReady || S.run.pending;
      ui.run.textContent = S.run.pending ? "Считаю…" : "Сравнить";
      ui.cancel.hidden = !S.run.pending;
      ui.runInfo.textContent = S.run.pending ? "Расчёт на сервере; можно отменить. Изменение входа отменит этот расчёт." : S.run.cancelNote || notReady || "";
      const at = Date.parse(S.analysisAt);
      ui.atInfo.textContent = Number.isFinite(at) ? PLAN_IDS.map((id) => "вариант " + id + ": " + (closedSet(id, true).size ? "закрыто участков " + closedSet(id, true).size : "в этот момент ничего не закрыто")).join(" · ") : "";
    }
    function run() {
      if (S.run.pending || readiness()) return;
      clearError(); setTool(null);
      const payload = buildPayload(), key = JSON.stringify(payload);
      const seq = ++S.run.seq;
      const controller = typeof AbortController === "function" ? new AbortController() : null;
      S.run.controller = controller; S.run.pending = true; S.run.error = null; S.run.cancelNote = null;
      renderAll();
      req("POST", "/compare", payload, controller ? { signal: controller.signal } : undefined).then((r) => {
        if (S.destroyed || seq !== S.run.seq) return;       // поздний ответ на отменённый/прежний расчёт
        S.run.result = r; S.run.resultKey = key; S.run.payload = payload;
        const first = r.baseline.routes[0];
        S.selectedPair = first ? first.origin_node_id + ">" + first.destination_node_id : null;
        fitSelectedRoute();
      }).catch((e) => {
        if (S.destroyed || seq !== S.run.seq) return;
        if (e && (e.code === "aborted" || e.name === "AbortError")) return;
        S.run.error = e; showError(e);
      }).finally(() => {
        if (S.destroyed || seq !== S.run.seq) return;
        S.run.pending = false; S.run.controller = null; renderAll(); drawOverlays();
      });
    }
    function cancelRun(silent) {
      if (!S.run.pending) return;
      ++S.run.seq;                                          // ответ, даже если придёт, будет проигнорирован
      if (S.run.controller) try { S.run.controller.abort(); } catch (e) { /* уже завершён */ }
      S.run.pending = false; S.run.controller = null;
      if (!silent) { S.run.cancelNote = "Расчёт отменён; результат на экране (если есть) — от прежнего расчёта."; renderAll(); }
    }
    const isStale = () => !!S.run.result && S.run.resultKey !== inputKey();

    function cell(row, delta) {
      if (!row) return el("td", { text: "—" });
      if (row.status !== "ok") return el("td", { class: P + "st-" + row.status, title: REASON_LABEL[row.reason] || "" }, [el("div", { text: STATUS_LABEL[row.status] || row.status }), el("div", { class: P + "hint", text: REASON_LABEL[row.reason] || "" })]);
      return el("td", {}, [el("div", { text: fmtM(row.length_m) }), delta !== undefined && delta !== null ? el("div", { class: P + "delta" + (delta > 0 ? " " + P + "up" : ""), text: fmtD(delta) }) : null,
        row.equal_cost_alternatives ? el("div", { class: P + "hint", text: "есть другой путь той же длины" }) : null]);
    }
    function renderResult() {
      const r = S.run.result;
      ui.stale.hidden = !isStale();
      ui.stale.textContent = isStale() ? "Вход изменён после расчёта: таблица и объяснение ниже относятся к ПРЕЖНЕМУ варианту (расчёт " + r.result_digest.slice(0, 8) + "). Нажмите «Сравнить», чтобы пересчитать." : "";
      ui.out.classList.toggle(P + "is-stale", isStale());
      if (!r) { ui.out.replaceChildren(); if (S.assistantFor) destroyAssistant(); return; }
      const inp = r.input, plans = Object.fromEntries(r.plans.map((p) => [p.id, p]));
      const key = (x) => x.origin_node_id + ">" + x.destination_node_id;
      const idx = (rows) => new Map((rows || []).map((x) => [key(x), x]));
      const name = (id, list, title) => { const i = list.findIndex((p) => p.node_id === id); return i < 0 ? id : title + (list.length > 1 ? " " + (i + 1) : ""); };
      const aR = idx(plans.A && plans.A.routes), bR = idx(plans.B && plans.B.routes), dA = idx(plans.A && plans.A.vs_baseline.pairs), dB = idx(plans.B && plans.B.vs_baseline.pairs), ab = idx(r.a_vs_b && r.a_vs_b.pairs);
      const rows = r.baseline.routes.map((b) => {
        const k = key(b);
        return el("tr", { class: P + "pair" + (S.selectedPair === k ? " " + P + "active" : ""), tabindex: "0",
          onclick: () => { S.selectedPair = k; renderResult(); drawOverlays(); fitSelectedRoute(); },
          onkeydown: (ev) => { if (ev.key === "Enter") { S.selectedPair = k; renderResult(); drawOverlays(); fitSelectedRoute(); } } }, [
          el("td", { text: name(b.origin_node_id, S.places.origins, "Откуда") + " → " + name(b.destination_node_id, S.places.dests, "Куда") }),
          cell(b), cell(aR.get(k), dA.get(k) && dA.get(k).delta_m), cell(bR.get(k), dB.get(k) && dB.get(k).delta_m),
          el("td", { text: ab.get(k) && ab.get(k).delta_m !== null ? fmtD(ab.get(k).delta_m) : "—" })]);
      });
      const planLine = (p) => {
        const s = p.vs_baseline.summary, ch = s.changes;
        const closed = p.active_closed_edge_ids.length;
        return el("div", { class: P + "card", style: "border-top-color:" + PLAN_COLORS[p.id] }, [
          el("h4", { text: "Вариант " + p.id }),
          el("div", { text: closed ? "В выбранный момент закрыто участков: " + closed + (p.closed_on_baseline_routes ? "; из них на базовых путях: " + p.closed_on_baseline_routes.length : "") : "В выбранный момент ничего не закрыто." }),
          el("div", { text: "Удлинилось пар: " + ch.longer + " · без изменений: " + ch.unchanged + " · нет пути в модели: " + ch.lost_within_model + " · стало неизвестно: " + ch.became_uncertain }),
          s.comparable_pairs ? el("div", { text: "Средний прирост длины по сопоставимым парам: " + fmtD(s.mean_delta_m_comparable) }) : el("div", { text: "Сопоставимых пар нет — среднее не считается." }),
          ...p.warnings.filter((w) => w.code !== "no_active_closures").map((w) => el("div", { class: P + "warn", text: w.message })),
        ]);
      };
      ui.out.replaceChildren(
        el("div", { class: P + "meta" }, [
          el("div", { text: "Расчёт " + r.result_digest.slice(0, 8) + " · момент " + inp.analysis_at + " · сеть " + inp.graph_id }),
          el("div", { class: P + "hint", text: "Длина пешего пути по сети в метрах; время в пути не рассчитывается. «Нет пути в модели» — не 0 м и не доказанная недоступность." }),
        ]),
        el("div", { class: P + "table-wrap" }, el("table", { class: P + "table" }, [el("thead", {}, el("tr", {}, ["Пара", "База", "Вариант A", "Вариант B", "B − A"].map((t) => el("th", { text: t })))), el("tbody", {}, rows)])),
        el("div", { class: P + "cards" }, r.plans.map(planLine)),
        ...r.warnings.filter((w) => w.code !== "graph_is_slice").map((w) => el("div", { class: P + "warn", text: w.message })),
        el("details", {}, [el("summary", { text: "Ограничения модели" }), el("ul", { class: P + "lim" }, r.limitations.map((t) => el("li", { text: t })))]),
      );
      // Объяснение всегда про ТЕКУЩИЙ результат: устарел вход — снимаем; вход снова совпал — возвращаем.
      if (isStale()) detachAssistant();
      else if (S.assistantFor !== r.result_digest) mountAssistant(r);
    }

    // ---------------------------------------------------------------- объяснение (R09)
    function destroyAssistant() {
      if (S.assistant) try { S.assistant.destroy(); } catch (e) { /* модуль соседа */ }
      S.assistant = null; S.assistantFor = null; ui.assistant.replaceChildren();
    }
    function detachAssistant() {
      if (S.assistantFor === "detached") return;
      destroyAssistant();
      S.assistantFor = "detached";
      ui.assistant.append(el("p", { class: P + "hint", text: "Объяснение относилось к прежнему расчёту и снято. После «Сравнить» появится объяснение нового расчёта." }));
    }
    function mountAssistant(result) {
      destroyAssistant();
      S.assistantFor = result.result_digest;
      const scenarioId = "result:" + result.result_digest;
      const head = el("h3", { class: P + "step", text: "Объяснение этого расчёта (" + result.result_digest.slice(0, 8) + ")" });
      const note = el("p", { class: P + "hint", text: "Помощник берёт цифры с сервера по номеру расчёта; браузер их не передаёт." });
      const box = el("div", { class: P + "assistant-root" });
      ui.assistant.append(head, note, box);
      const A = root.CivicAssistant;
      if (!A || typeof A.mount !== "function") { box.append(el("p", { class: P + "hint", text: "Помощник (R09) не загружен в этой сборке — объяснение недоступно; таблица выше остаётся результатом расчёта." })); return; }
      // Ответ «расчёт не найден» (кэш сервера истёк или не подключён) — просим пересчитать, а не подставляем пример.
      const watched = { request: (m, path, body, o) => api.request(m, path, body, o).then((d) => {
        if (path === "/assistant" && d && d.source === "unavailable" && (d.warnings || []).indexOf("scenario_not_found") >= 0 && !S.destroyed)
          note.textContent = "Сервер не нашёл расчёт " + result.result_digest.slice(0, 8) + " (срок хранения истёк или кэш не подключён). Нажмите «Сравнить» ещё раз — объяснение подставит только ваш расчёт.";
        return d;
      }) };
      try { S.assistant = A.mount({ root: box, api: watched, scenarioId }); }
      catch (e) { box.append(el("p", { class: P + "warn", text: "Помощник не запустился: " + (e && e.message) })); }
    }

    function renderAll() {
      if (S.destroyed) return;
      renderPlaces(); renderPlans(); renderChooser(); renderRunBar(); renderResult();
    }

    // ---------------------------------------------------------------- карта
    const LAYERS = [P + "coverage", P + "edges-allowed", P + "edges-unknown", P + "edges-denied", P + "closed-A", P + "closed-B", P + "closed-A-other", P + "closed-B-other",
      P + "cand", P + "route-base", P + "route-A", P + "route-B", P + "connect", P + "pt-input", P + "pt-node"];
    const SOURCES = [P + "coverage", P + "graph", P + "closed", P + "cand", P + "routes", P + "places"];
    const fc = (features) => ({ type: "FeatureCollection", features });
    function edgeLine(e) { return e.geometry; }
    function routeLine(row) {
      let cs = [];
      row.edge_ids.forEach((id, i) => {
        const e = S.edgeIndex.get(id); let g = edgeLine(e);
        if (e.from !== row.node_ids[i]) g = g.slice().reverse();
        cs = cs.concat(cs.length ? g.slice(1) : g);
      });
      return cs;
    }
    function setData(id, data) { const s = map.getSource(id); if (s) s.setData(data); else map.addSource(id, { type: "geojson", data }); }
    function ensureLayers() {
      if (map.getLayer(P + "edges-allowed")) return;
      const line = (id, src, filter, paint, layout) => map.addLayer({ id, type: "line", source: src, filter, layout: Object.assign({ "line-cap": "round", "line-join": "round" }, layout || {}), paint });
      line(P + "coverage", P + "coverage", ["==", ["geometry-type"], "LineString"], { "line-color": "#5d67a0", "line-width": 2, "line-dasharray": [4, 3] });
      line(P + "edges-allowed", P + "graph", ["==", ["get", "access"], "allowed"], { "line-color": "#437b68", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.6, 14, 2, 17, 3] });
      line(P + "edges-unknown", P + "graph", ["==", ["get", "access"], "unknown"], { "line-color": "#adb5bd", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.4, 14, 1.8], "line-opacity": 0.6, "line-dasharray": [2, 2] });
      line(P + "edges-denied", P + "graph", ["==", ["get", "access"], "denied"], { "line-color": "#c92a2a", "line-width": 1.2, "line-opacity": 0.6 });
      for (const k of PLAN_IDS) {
        line(P + "closed-" + k + "-other", P + "closed", ["==", ["get", "c" + k], "other"], { "line-color": PLAN_COLORS[k], "line-width": 5, "line-offset": k === "A" ? -3 : 3, "line-opacity": 0.35, "line-dasharray": [1, 1.5] });
        line(P + "closed-" + k, P + "closed", ["==", ["get", "c" + k], "active"], { "line-color": PLAN_COLORS[k], "line-width": 7, "line-offset": k === "A" ? -3 : 3, "line-opacity": 0.85 });
      }
      line(P + "cand", P + "cand", ["==", ["geometry-type"], "LineString"], { "line-color": "#f59f00", "line-width": ["match", ["get", "hover"], 1, 9, 5], "line-opacity": 0.8 });
      for (const [k, off] of [["base", 0], ["A", -5], ["B", 5]])
        line(P + "route-" + k, P + "routes", ["==", ["get", "kind"], k], { "line-color": ROUTE_COLORS[k], "line-width": k === "base" ? 5 : 3.5, "line-offset": off, "line-opacity": 0.9 });
      line(P + "connect", P + "places", ["==", ["get", "kind"], "connect"], { "line-color": "#495057", "line-width": 1.5, "line-dasharray": [1, 2] });
      map.addLayer({ id: P + "pt-input", type: "circle", source: P + "places", filter: ["==", ["get", "kind"], "input"], paint: {
        "circle-radius": 6, "circle-color": "rgba(255,255,255,0.6)", "circle-stroke-width": 2, "circle-stroke-color": ["match", ["get", "role"], "origins", "#2b8a3e", "rejected", "#c92a2a", "#212529"] } });
      map.addLayer({ id: P + "pt-node", type: "circle", source: P + "places", filter: ["==", ["get", "kind"], "node"], paint: {
        "circle-radius": 6, "circle-color": ["match", ["get", "role"], "origins", "#2b8a3e", "#212529"], "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
    }
    function fitCoordinates(coords) {
      if (!map || !coords.length) return;
      const b = coords.reduce((box, n) => [Math.min(box[0], n[0]), Math.min(box[1], n[1]), Math.max(box[2], n[0]), Math.max(box[3], n[1])], [180, 90, -180, -90]);
      const mobile = root.innerWidth < 761;
      const padding = mobile ? { top: 85, left: 24, right: 60, bottom: Math.round(root.innerHeight * 0.64) }
        : { top: 120, left: 50, right: Math.min(root.innerWidth * 0.65, 650), bottom: 60 };
      try { map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding, maxZoom: 16, duration: 0 }); } catch (e) { map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 40, maxZoom: 16, duration: 0 }); }
    }
    function fitSelectedRoute() {
      const r = S.run.result;
      if (!r || !S.selectedPair) return;
      const rows = [r.baseline.routes, ...r.plans.map((p) => p.routes)];
      fitCoordinates(rows.flatMap((rs) => rs.filter((x) => x.status === "ok" && x.origin_node_id + ">" + x.destination_node_id === S.selectedPair).flatMap(routeLine)));
    }
    function drawGraph(fit) {
      if (!map || !S.graph) return;
      const go = () => { if (S.destroyed) return; drawOverlays(); if (fit) fitCoordinates(S.graph.nodes.map((n) => [n.lon, n.lat])); };
      if (styleReady) go(); else pendingDraw = go;
    }
    function drawOverlays() {
      if (!map || !styleReady || !S.graph || S.destroyed) return;
      if (!map.getSource(P + "graph") || S.drawnGraph !== S.graph.id) {
        const [w, s, e, n] = S.graph.bbox || S.graph.nodes.reduce((b, p) => [Math.min(b[0], p.lon), Math.min(b[1], p.lat), Math.max(b[2], p.lon), Math.max(b[3], p.lat)], [180, 90, -180, -90]);
        setData(P + "coverage", fc([{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [[w, s], [e, s], [e, n], [w, n], [w, s]] } }]));
        setData(P + "graph", fc(S.graph.edges.map((ed) => ({ type: "Feature", properties: { id: ed.id, access: ed.access }, geometry: { type: "LineString", coordinates: edgeLine(ed) } }))));
        S.drawnGraph = S.graph.id;
      }
      const cA = closedSet("A"), cB = closedSet("B"), aA = closedSet("A", true), aB = closedSet("B", true);
      const st = (all, act, id) => (act.has(id) ? "active" : all.has(id) ? "other" : "no");
      setData(P + "closed", fc([...new Set([...cA, ...cB])].map((id) => S.edgeIndex.get(id)).filter(Boolean).map((ed) => ({
        type: "Feature", properties: { id: ed.id, cA: st(cA, aA, ed.id), cB: st(cB, aB, ed.id) }, geometry: { type: "LineString", coordinates: edgeLine(ed) } }))));
      setData(P + "cand", fc(S.chooser ? S.chooser.ids.map((id) => S.edgeIndex.get(id)).filter(Boolean).map((ed) => ({
        type: "Feature", properties: { id: ed.id, hover: S.chooser.hover === ed.id ? 1 : 0 }, geometry: { type: "LineString", coordinates: edgeLine(ed) } })) : []));
      const routes = [];
      if (S.run.result && S.selectedPair && !isStale()) {
        const pick = (rows) => rows.find((x) => x.origin_node_id + ">" + x.destination_node_id === S.selectedPair);
        const add = (row, kind) => { if (row && row.status === "ok" && row.edge_ids.length) routes.push({ type: "Feature", properties: { kind }, geometry: { type: "LineString", coordinates: routeLine(row) } }); };
        add(pick(S.run.result.baseline.routes), "base");
        for (const p of S.run.result.plans) add(pick(p.routes), p.id);
      }
      setData(P + "routes", fc(routes));
      const pts = [];
      for (const role of ["origins", "dests"]) for (const p of S.places[role]) {
        pts.push({ type: "Feature", properties: { kind: "node", role }, geometry: { type: "Point", coordinates: p.node } });
        if (!p.from_case) {
          pts.push({ type: "Feature", properties: { kind: "input", role }, geometry: { type: "Point", coordinates: p.input } });
          pts.push({ type: "Feature", properties: { kind: "connect", role }, geometry: { type: "LineString", coordinates: [p.input, p.node] } });
        }
      }
      if (S.tool && S.tool.lastInput) pts.push({ type: "Feature", properties: { kind: "input", role: "rejected" }, geometry: { type: "Point", coordinates: S.tool.lastInput } });
      setData(P + "places", fc(pts));
      ensureLayers();
    }
    let styleReady = false, pendingDraw = null;
    function onStyle() {
      if (S.destroyed) return;
      styleReady = true;
      const f = pendingDraw; pendingDraw = null;
      S.drawnGraph = null;          // новый стиль — источники нужно добавить заново
      if (f) f(); else drawOverlays();
    }
    if (map) {
      map.on("click", onMapClick); mapHandlers.push(["click", onMapClick]);
      map.on("style.load", onStyle); mapHandlers.push(["style.load", onStyle]);
      if ((map.isStyleLoaded && map.isStyleLoaded()) || (map.style && map.style._loaded)) styleReady = true;
    }
    document.addEventListener("keydown", onKey, true); docHandlers.push(["keydown", onKey, true]);

    function destroy() {
      if (S.destroyed) return;
      cancelRun(true);
      if (S.tool) setTool(null);
      S.destroyed = true;
      destroyAssistant();
      for (const [ev, fn, cap] of docHandlers) document.removeEventListener(ev, fn, cap);
      if (map) {
        for (const [ev, fn] of mapHandlers) map.off(ev, fn);
        try { map.getCanvas().style.cursor = ""; } catch (e) { /* карта снята */ }
        for (const l of LAYERS) if (map.getLayer(l)) map.removeLayer(l);
        for (const s of SOURCES) if (map.getSource(s)) map.removeSource(s);
      }
      wrap.remove();
    }
    return { destroy, cancelTool: () => setTool(null) };
  }

  root.CivicScenarios = { mount, _internal: { buildSnapIndex, snapPoint, haversine, SNAP_MAX_M } };
})(typeof window !== "undefined" ? window : globalThis);
