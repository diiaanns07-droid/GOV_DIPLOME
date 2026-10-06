/* K03 r10: пешеходные расстояния по сети pedestrian-v1 для школьного кейса (school-access-case-v1, CONTRACT r10).
 * Чистые функции без DOM и без внешних API. Граф — graph/<city>.graph.json (build_graph.py). Прямая — отдельный метод geodesic.
 * Расстояние — целые мм (haversine-mm-v1 по кускам: привязка, части рёбер, рёбра; каждый кусок округлён один раз).
 * Статусы: ok | access_unknown | disconnected | outside_coverage | unsnappable. При status ≠ ok distance_mm = null, geometry = null:
 * прямая никогда не подставляется. Exploratory-маршрут — «маршрут по неполным данным», не гарантированно доступный путь.
 * Браузер: window.K03_ROUTING; Node: require("./routing.js"). Независимый Python-оракул: routing_ref.py.
 */
(function (root) {
  "use strict";
  const SCHEMA = "k03-pedestrian-graph-v1", METHOD = "pedestrian-v1", ROUTE_SCHEMA = "k03-route-v1";
  const POLICIES = { "pedestrian-v1-strict": "s", "pedestrian-v1-exploratory": "x" };
  const R_EARTH = 6371008.8;
  const LABEL = { "pedestrian-v1-strict": "маршрут по пешеходным рёбрам OSM/Overture (не проверено на месте)",
    "pedestrian-v1-exploratory": "маршрут по неполным данным (не гарантированно доступный пешеходный путь)" };

  class RoutingError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
  const fail = (code, d) => { throw new RoutingError(code, d); };
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const mm = (m) => Math.round(m * 1000);
  function haversine(a, b) {  // [lon, lat] → м
    const r = Math.PI / 180, p1 = a[1] * r, p2 = b[1] * r, dp = (b[1] - a[1]) * r, dl = (b[0] - a[0]) * r;
    let h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    h = Math.min(1, Math.max(0, h));
    return 2 * R_EARTH * Math.asin(Math.sqrt(h));
  }
  const lineM = (cs) => { let s = 0; for (let i = 1; i < cs.length; i++) s += haversine(cs[i - 1], cs[i]); return s; };
  // канонический JSON (ключи по UTF-16) — для проверки graph_sha256 переданной функцией sha256hex
  const canon = (v) => (Array.isArray(v) ? "[" + v.map(canon).join(",") + "]" : v !== null && typeof v === "object"
    ? "{" + Object.keys(v).sort(cmpStr).map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}" : JSON.stringify(v));

  // ---------- граф ----------
  /* prepare(graph, {sha256hex}) → индекс. Проверяет форму; с sha256hex — и graph_sha256 по содержимому (подмена отклоняется). */
  function prepare(g, opts) {
    if (!g || g.schema !== SCHEMA || !Array.isArray(g.nodes) || !Array.isArray(g.edges) || !Array.isArray(g.bbox)) fail("bad_graph", "ожидается " + SCHEMA);
    if (opts && opts.sha256hex) {
      const body = {}; for (const k of ["schema", "city", "bbox", "release", "policy_family", "policy_sha256", "max_snap_m", "inputs", "nodes", "edges"]) body[k] = g[k];
      if (opts.sha256hex(canon(body)) !== g.graph_sha256) fail("graph_hash_mismatch", "содержимое графа не совпадает с graph_sha256");
    }
    const nodes = new Map();
    for (const n of g.nodes) {
      if (typeof n.id !== "string" || nodes.has(n.id) || !Number.isFinite(n.lon) || !Number.isFinite(n.lat)) fail("bad_graph", "узел " + String(n.id).slice(0, 60));
      nodes.set(n.id, n);
    }
    const seen = new Set(), out = { s: new Map(), x: new Map() }, inn = { s: new Map(), x: new Map() };
    for (const k of ["s", "x"]) for (const id of nodes.keys()) { out[k].set(id, []); inn[k].set(id, []); }
    g.edges.forEach((e, i) => {
      if (typeof e.id !== "string" || seen.has(e.id) || !nodes.has(e.from) || !nodes.has(e.to) || !Number.isInteger(e.len_mm) || e.len_mm < 0
        || !Array.isArray(e.coords) || e.coords.length < 2) fail("bad_graph", "ребро " + String(e.id).slice(0, 80));
      seen.add(e.id);
      for (const k of ["s", "x"]) {
        if (e[k][0] === "ok") { out[k].get(e.from).push({ e: i, d: 0, to: e.to }); inn[k].get(e.to).push({ e: i, d: 0, from: e.from }); }
        if (e[k][1] === "ok") { out[k].get(e.to).push({ e: i, d: 1, to: e.from }); inn[k].get(e.from).push({ e: i, d: 1, from: e.to }); }
      }
    });
    const ord = (a, b) => cmpStr(g.edges[a.e].id, g.edges[b.e].id) || a.d - b.d;
    for (const k of ["s", "x"]) for (const m of [out[k], inn[k]]) for (const l of m.values()) l.sort(ord);
    return { g, nodes, out, inn, idx: new Map(g.edges.map((e, i) => [e.id, i])), cache: new Map() };
  }

  // ---------- привязка точки к ребру ----------
  const usable = (e, k) => e[k][0] === "ok" || e[k][1] === "ok";
  function snap(G, pt, k) {
    const lat0 = pt[1], kx = Math.cos(lat0 * Math.PI / 180);
    let best = null;
    G.g.edges.forEach((e, ei) => {
      if (!usable(e, k)) return;
      for (let i = 0; i + 1 < e.coords.length; i++) {
        const A = e.coords[i], B = e.coords[i + 1];
        const ax = (A[0] - pt[0]) * kx, ay = A[1] - pt[1], bx = (B[0] - pt[0]) * kx, by = B[1] - pt[1];
        const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
        let t = L2 > 0 ? -(ax * dx + ay * dy) / L2 : 0;
        t = t < 0 ? 0 : t > 1 ? 1 : t;
        const q = [A[0] + t * (B[0] - A[0]), A[1] + t * (B[1] - A[1])];
        const d = mm(haversine(pt, q));
        if (best === null || d < best.d || (d === best.d && (cmpStr(e.id, G.g.edges[best.e].id) < 0 || (e.id === G.g.edges[best.e].id && i < best.i))))
          best = { e: ei, i, t, q, d };
      }
    });
    if (!best) return null;
    const e = G.g.edges[best.e];
    const head = e.coords.slice(0, best.i + 1).concat([best.q]), tail = [best.q].concat(e.coords.slice(best.i + 1));
    return { ...best, a: mm(lineM(head)), b: mm(lineM(tail)), head, tail };
  }

  // ---------- Дейкстра: (расстояние, ID узла); предшественник меняется только при строгом улучшении ----------
  function dijkstra(G, k, starts, reverse) {
    const dist = new Map(), pred = new Map(), done = new Set();
    const heap = [];
    const less = (a, b) => a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]);
    const push = (x) => { heap.push(x); let i = heap.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (!less(heap[i], heap[p])) break; [heap[i], heap[p]] = [heap[p], heap[i]]; i = p; } };
    const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i;
      if (l < heap.length && less(heap[l], heap[m])) m = l; if (r < heap.length && less(heap[r], heap[m])) m = r; if (m === i) break; [heap[i], heap[m]] = [heap[m], heap[i]]; i = m; } } return top; };
    for (const s of starts) if (!dist.has(s.node) || s.cost < dist.get(s.node)) { dist.set(s.node, s.cost); pred.set(s.node, null); }
    for (const [n, c] of dist) push([c, n]);
    const adj = reverse ? G.inn[k] : G.out[k];
    while (heap.length) {
      const [c, u] = pop();
      if (done.has(u) || c > dist.get(u)) continue;
      done.add(u);
      for (const a of adj.get(u)) {
        const v = reverse ? a.from : a.to, nd = c + G.g.edges[a.e].len_mm;
        if (!done.has(v) && (!dist.has(v) || nd < dist.get(v))) { dist.set(v, nd); pred.set(v, { u, e: a.e, d: a.d }); push([nd, v]); }
      }
    }
    return { dist, pred };
  }
  // начальные дуги от привязки: к from — против геометрии (направление 1), к to — по геометрии (0)
  // кусок нулевой длины (точка в узле) от направления не зависит: движения по ребру нет
  function startsFrom(e, sn, k) { const s = []; if (e[k][1] === "ok" || sn.a === 0) s.push({ node: e.from, cost: sn.a }); if (e[k][0] === "ok" || sn.b === 0) s.push({ node: e.to, cost: sn.b }); return s; }
  function startsTo(e, sn, k) { const s = []; if (e[k][0] === "ok" || sn.a === 0) s.push({ node: e.from, cost: sn.a }); if (e[k][1] === "ok" || sn.b === 0) s.push({ node: e.to, cost: sn.b }); return s; }
  const keyOf = (pt) => pt[0] + "," + pt[1];
  function forward(G, k, pt, sn) { const key = "f" + k + keyOf(pt); if (!G.cache.has(key)) G.cache.set(key, dijkstra(G, k, startsFrom(G.g.edges[sn.e], sn, k), false)); return G.cache.get(key); }
  function backward(G, k, pt, sn) { const key = "b" + k + keyOf(pt); if (!G.cache.has(key)) G.cache.set(key, dijkstra(G, k, startsTo(G.g.edges[sn.e], sn, k), true)); return G.cache.get(key); }
  function snapCached(G, k, pt) { const key = "s" + k + keyOf(pt); if (!G.cache.has(key)) G.cache.set(key, snap(G, pt, k)); return G.cache.get(key); }

  // ---------- маршрут ----------
  function checkPoint(p, what) {
    if (!p || typeof p !== "object" || typeof p.id !== "string" || !p.id || !Number.isFinite(p.lon) || !Number.isFinite(p.lat) || Math.abs(p.lon) > 180 || Math.abs(p.lat) > 90)
      fail("bad_point", what + ": {id, lon, lat} с конечными координатами");
  }
  const inBbox = (b, pt) => b[0] <= pt[0] && pt[0] <= b[2] && b[1] <= pt[1] && pt[1] <= b[3];
  function base(G, o, t, policyId) {
    return { schema_version: ROUTE_SCHEMA, origin_id: o.id, target_id: t.id, distance_mm: null, status: null, method: METHOD, policy_id: policyId,
      policy_sha256: G.g.policy_sha256, graph_sha256: G.g.graph_sha256, city: G.g.city, route_edge_ids: [], geometry: null, parts: [], assumptions: [], reason: null, label: null };
  }
  function bestArrival(G, k, os, ts, F) {
    // варианты: прямо по одному ребру, через from целевого ребра, через to; ничья — в этом порядке
    const eT = G.g.edges[ts.e], opts = [];
    if (os.e === ts.e) {
      const fwd = os.i < ts.i || (os.i === ts.i && os.t <= ts.t), same = os.i === ts.i && os.t === ts.t;
      if (same || (fwd && eT[k][0] === "ok") || (!fwd && eT[k][1] === "ok")) {
        const cs = fwd ? [os.q].concat(eT.coords.slice(os.i + 1, ts.i + 1), [ts.q]) : [os.q].concat(eT.coords.slice(ts.i + 1, os.i + 1).reverse(), [ts.q]);
        opts.push({ cost: mm(lineM(cs)), via: "direct", d: fwd ? 0 : 1, cs });
      }
    }
    if ((eT[k][0] === "ok" || ts.a === 0) && F.dist.has(eT.from)) opts.push({ cost: F.dist.get(eT.from) + ts.a, via: "from" });
    if ((eT[k][1] === "ok" || ts.b === 0) && F.dist.has(eT.to)) opts.push({ cost: F.dist.get(eT.to) + ts.b, via: "to" });
    let best = null; for (const x of opts) if (best === null || x.cost < best.cost) best = x;
    return best;
  }
  function pathOf(G, k, os, ts, F, arr) {
    const E = G.g.edges, eO = E[os.e], eT = E[ts.e];
    if (arr.via === "direct") return arr.cost === 0 ? { edges: [], cs: arr.cs, assume: [] } : { edges: [{ id: eT.id, d: arr.d, partial: true }], cs: arr.cs, assume: [...eT.xa[arr.d]] };
    const node = arr.via === "from" ? eT.from : eT.to, chain = [];
    for (let n = node, p = F.pred.get(n); p; n = p.u, p = F.pred.get(n)) chain.push(p);
    chain.reverse();
    const first = chain.length ? chain[0].u : node;  // узел, в который пришли из привязки
    const startD = first === eO.from ? 1 : 0;
    let cs = startD === 1 ? eO.coords.slice(0, os.i + 1).reverse() : eO.coords.slice(os.i + 1);
    cs = [os.q].concat(cs);
    const edges = [], assume = [];
    if ((startD === 1 ? os.a : os.b) > 0) { edges.push({ id: eO.id, d: startD, partial: true }); assume.push(...eO.xa[startD]); }  // кусок 0 мм не проходится
    for (const p of chain) {
      const e = E[p.e], c = p.d === 0 ? e.coords : e.coords.slice().reverse();
      cs = cs.concat(c.slice(1)); edges.push({ id: e.id, d: p.d, partial: false }); assume.push(...e.xa[p.d]);
    }
    const endD = arr.via === "from" ? 0 : 1;
    const tail = endD === 0 ? eT.coords.slice(1, ts.i + 1) : eT.coords.slice(ts.i + 1, eT.coords.length - 1).reverse();
    cs = cs.concat(tail, [ts.q]);
    if ((endD === 0 ? ts.a : ts.b) > 0) { edges.push({ id: eT.id, d: endD, partial: true }); assume.push(...eT.xa[endD]); }
    return { edges, cs, assume, nodes: [first, ...chain.map((p) => (p.d === 0 ? E[p.e].to : E[p.e].from))] };
  }
  /* boundary: нижняя граница пути через внешнюю сеть по открытым узлам (геодезия между ними) */
  function boundaryLB(G, k, F, B, found) {
    const open = (m) => [...m.dist].filter(([n, c]) => G.nodes.get(n).open && c < found);
    const A = open(F), C = open(B);
    let lb = null;
    for (const [n1, c1] of A) for (const [n2, c2] of C) {
      const n = G.nodes.get(n1), m = G.nodes.get(n2), v = c1 + mm(haversine([n.lon, n.lat], [m.lon, m.lat])) + c2;
      if (lb === null || v < lb) lb = v;
    }
    return lb;
  }
  function reachesOpen(m, G) { for (const n of m.dist.keys()) if (G.nodes.get(n).open) return true; return false; }

  /* route(G, origin{id,lon,lat}, target{id,lon,lat}, policy_id, {max_snap_m}) → строка матрицы CONTRACT r10 (+ parts/label/reason). */
  function route(G, o, t, policyId, opts) {
    checkPoint(o, "origin"); checkPoint(t, "target");
    const k = POLICIES[policyId]; if (!k) fail("bad_policy", String(policyId).slice(0, 60));
    const maxSnap = Math.round(((opts && opts.max_snap_m) || G.g.max_snap_m) * 1000);
    const r = base(G, o, t, policyId), po = [o.lon, o.lat], pt = [t.lon, t.lat];
    if (!inBbox(G.g.bbox, po) || !inBbox(G.g.bbox, pt)) return { ...r, status: "outside_coverage", reason: "point_outside_slice" };
    const os = snapCached(G, k, po), ts = snapCached(G, k, pt);
    const okSnap = (s) => s && s.d <= maxSnap;
    if (!okSnap(os) || !okSnap(ts)) {
      if (k === "s") { const ox = snapCached(G, "x", po), tx = snapCached(G, "x", pt);
        if (okSnap(ox) && okSnap(tx)) return { ...r, status: "access_unknown", reason: "no_verified_edge_within_snap" }; }
      return { ...r, status: "unsnappable", reason: "no_edge_within_max_snap", assumptions: ["max_snap_m=" + maxSnap / 1000] };
    }
    const F = forward(G, k, po, os), arr = bestArrival(G, k, os, ts, F);
    if (!arr) {
      if (k === "s") { const ox = snapCached(G, "x", po), tx = snapCached(G, "x", pt);
        if (okSnap(ox) && okSnap(tx) && bestArrival(G, "x", ox, tx, forward(G, "x", po, ox))) return { ...r, status: "access_unknown", reason: "path_only_via_unverified_edges" }; }
      const kk = "x", ox = snapCached(G, kk, po), tx = snapCached(G, kk, pt);
      const open2 = okSnap(ox) && okSnap(tx) && reachesOpen(forward(G, kk, po, ox), G) && reachesOpen(backward(G, kk, pt, tx), G);
      return open2 ? { ...r, status: "outside_coverage", reason: "path_may_exist_outside_slice" } : { ...r, status: "disconnected", reason: "no_path_in_closed_component" };
    }
    const P = pathOf(G, k, os, ts, F, arr);
    const net = arr.cost, total = os.d + net + ts.d;
    const assumptions = new Set(P.assume);
    if (os.d > 0 || ts.d > 0) assumptions.add("snap_model_connection");
    if (P.edges.some((x) => G.g.edges[G.idx.get(x.id)].out)) assumptions.add("route_partly_outside_slice");
    const B = backward(G, k, pt, ts), lb = boundaryLB(G, k, F, B, net);
    if (lb !== null && lb < net) assumptions.add("boundary_unverified");
    const coords = [po].concat(P.cs, [pt]).filter((c, i, a) => i === 0 || c[0] !== a[i - 1][0] || c[1] !== a[i - 1][1]);
    const incomplete = k === "x" && P.assume.length > 0;
    return { ...r, status: "ok", distance_mm: total, route_edge_ids: P.edges.map((x) => x.id), geometry: { type: "LineString", coordinates: coords },
      parts: [{ kind: "snap", role: "origin", length_mm: os.d, model_connection: true, edge_id: G.g.edges[os.e].id },
        { kind: "network", length_mm: net, edges: P.edges },
        { kind: "snap", role: "target", length_mm: ts.d, model_connection: true, edge_id: G.g.edges[ts.e].id }],
      assumptions: [...assumptions].sort(cmpStr),
      label: k === "s" ? LABEL[policyId] : incomplete ? LABEL[policyId] : "маршрут только по рёбрам с подтверждённым доступом (найден в exploratory)" };
  }
  /* geodesic — отдельный метод: прямая haversine-mm-v1, не маршрут. */
  function geodesic(G, o, t) {
    checkPoint(o, "origin"); checkPoint(t, "target");
    const r = { ...base(G, o, t, null), method: "geodesic", policy_sha256: null };
    const po = [o.lon, o.lat], pt = [t.lon, t.lat];
    if (!inBbox(G.g.bbox, po) || !inBbox(G.g.bbox, pt)) return { ...r, status: "outside_coverage", reason: "point_outside_slice" };
    return { ...r, status: "ok", distance_mm: mm(haversine(po, pt)), geometry: { type: "LineString", coordinates: [po, pt] },
      assumptions: ["straight_line_not_route"], label: "прямая, не маршрут" };
  }
  /* matrix(G, origins, targets, method, policy_id) → строки {origin_id, target_id, ...} в порядке origins × targets. */
  function matrix(G, origins, targets, method, policyId, opts) {
    if (!Array.isArray(origins) || !Array.isArray(targets)) fail("bad_shape", "origins/targets — массивы");
    const rows = [];
    for (const o of origins) for (const t of targets) rows.push(method === "geodesic" ? geodesic(G, o, t) : route(G, o, t, policyId, opts));
    return rows;
  }

  const api = { SCHEMA, METHOD, ROUTE_SCHEMA, POLICIES, LABEL, RoutingError, haversine, canon, prepare, snap, route, geodesic, matrix };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.K03_ROUTING = api;
})(typeof window !== "undefined" ? window : globalThis);
