// K03 r10: ограниченный замер routing.js на графах обоих городов (Node, без DOM). Не универсальная оценка скорости.
//   node bench.cjs [runs=5] > runs/bench.json
// Нагрузка как лимит CONTRACT r10: 25 origins × (школы среза + 16 кандидатов), strict и exploratory, каждый прогон с холодным кэшем.
"use strict";
const fs = require("fs"), path = require("path"), os = require("os"), crypto = require("crypto");
const R = require(path.join(__dirname, "routing.js"));
const runs = Number(process.argv[2] || 5);
const sha256hex = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
let seed = 20261006;
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
const median = (a) => { const s = a.slice().sort((x, y) => x - y); return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2; };
const out = { environment: { node: process.version, platform: `${os.platform()} ${os.release()}`, arch: os.arch(), cpu: (os.cpus()[0] || {}).model || "unknown",
  cpus: os.cpus().length, note: "один процесс, без воркеров; замер этого окружения, не гарантия для браузера или Windows" }, runs, cities: {} };
for (const city of ["shymkent", "astana"]) {
  const text = fs.readFileSync(path.join(__dirname, `graph/${city}.graph.json`), "utf8");
  const g0 = JSON.parse(text), b = g0.bbox;
  const pts = (n, p) => Array.from({ length: n }, (_, i) => ({ id: `${p}${i}`, lon: b[0] + (b[2] - b[0]) * (0.05 + 0.9 * rnd()), lat: b[1] + (b[3] - b[1]) * (0.05 + 0.9 * rnd()) }));
  const origins = pts(25, "o"), cands = pts(16, "c");
  const schools = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/city_pairs.json"), "utf8")).cities[city].targets.filter((t) => t.kind === "observed_secondary").map(({ id, lon, lat }) => ({ id, lon, lat }));
  const targets = schools.concat(cands);
  const T = { parse_ms: [], prepare_hash_ms: [], prepare_ms: [], matrix_strict_ms: [], matrix_exploratory_ms: [], max_single_route_ms: [] };
  let statuses = null;
  for (let r = 0; r < runs; r++) {
    let t0 = performance.now(); const g = JSON.parse(text); T.parse_ms.push(performance.now() - t0);
    t0 = performance.now(); R.prepare(g, { sha256hex }); T.prepare_hash_ms.push(performance.now() - t0);
    t0 = performance.now(); const G = R.prepare(g); T.prepare_ms.push(performance.now() - t0);
    let maxOne = 0; const st = {};
    for (const [pol, key] of [["pedestrian-v1-strict", "matrix_strict_ms"], ["pedestrian-v1-exploratory", "matrix_exploratory_ms"]]) {
      t0 = performance.now();
      for (const o of origins) for (const t of targets) {
        const t1 = performance.now(); const x = R.route(G, o, t, pol); maxOne = Math.max(maxOne, performance.now() - t1);
        st[pol] = st[pol] || {}; st[pol][x.status] = (st[pol][x.status] || 0) + 1;
      }
      T[key].push(performance.now() - t0);
    }
    T.max_single_route_ms.push(maxOne); statuses = st;
  }
  out.cities[city] = { graph_sha256: g0.graph_sha256, graph_bytes: Buffer.byteLength(text), nodes: g0.nodes.length, edges: g0.edges.length,
    origins: origins.length, targets: targets.length, schools: schools.length, pairs_per_policy: origins.length * targets.length,
    median_ms: Object.fromEntries(Object.entries(T).map(([k, v]) => [k, Math.round(median(v) * 10) / 10])), statuses_last_run: statuses,
    note: "точки и кандидаты — seeded synthetic; первая строка от точки включает её привязку и полный обход Дейкстры, следующие берут кэш" };
}
process.stdout.write(JSON.stringify(out, null, 1) + "\n");
