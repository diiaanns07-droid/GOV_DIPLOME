// K03 r10: проверка модуля в Chromium (Playwright) с sha256hex из facts.js базы d2ff344 — это НЕ проверка интегрированного сайта.
//   NODE_PATH="$(npm root -g)" node browser_check.cjs [out.json]
// Временный localhost-сервер раздаёт routing.js, school-access-routing.js, graph/*.json, examples/*_case.json и facts.js (git show d2ff344).
// В браузере: prepare с проверкой graph_sha256 функцией CITY_FACTS.sha256hex → distanceMatrix (прямая, strict, exploratory) → сравнение с Node.
"use strict";
const http = require("http"), fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const { chromium } = require("playwright");
const R = require("./routing.js"), A = require("./school-access-routing.js");
const BASE = "d2ff344c5ec9b9a729ea59df50ec81f981e619de";
const outFile = process.argv[2] || path.join(__dirname, "runs/browser_check.json");
const facts = execFileSync("git", ["-C", __dirname, "show", `${BASE}:web/govtech/core/facts.js`]);
const files = { "/routing.js": fs.readFileSync(path.join(__dirname, "routing.js")), "/school-access-routing.js": fs.readFileSync(path.join(__dirname, "school-access-routing.js")),
  "/facts.js": facts };
for (const c of ["shymkent", "astana"]) {
  files[`/graph/${c}.graph.json`] = fs.readFileSync(path.join(__dirname, `graph/${c}.graph.json`));
  files[`/examples/${c}_case.json`] = fs.readFileSync(path.join(__dirname, `examples/${c}_case.json`));
}
files["/index.html"] = Buffer.from(`<!doctype html><meta charset="utf-8"><title>k03</title>
<script src="/facts.js"></script><script src="/routing.js"></script><script src="/school-access-routing.js"></script>
<script>
window.K03_RUN = async () => {
  const out = {};
  for (const city of ["shymkent", "astana"]) {
    const g = await (await fetch("/graph/" + city + ".graph.json")).json();
    const kase = await (await fetch("/examples/" + city + "_case.json")).json();
    let t0 = performance.now(); const G = K03_ROUTING.prepare(g, { sha256hex: CITY_FACTS.sha256hex }); const prep = performance.now() - t0;
    const bad = JSON.parse(JSON.stringify(g)); bad.edges[0].len_mm += 1; let tamper;
    try { K03_ROUTING.prepare(bad, { sha256hex: CITY_FACTS.sha256hex }); tamper = "accepted"; } catch (e) { tamper = e.code; }
    const res = {};
    for (const [m, p] of [["geodesic", null], ["pedestrian-v1", "pedestrian-v1-strict"], ["pedestrian-v1", "pedestrian-v1-exploratory"]]) {
      t0 = performance.now(); const mx = K03_SCHOOL_ROUTING.distanceMatrix({ ...kase, parameters: { ...kase.parameters, distance_method: m, routing_policy_id: p } }, G);
      res[p || m] = { ms: performance.now() - t0, rows: mx.rows };
    }
    out[city] = { prepare_with_hash_ms: prep, tamper, res };
  }
  return out;
};
</script>`);
const server = http.createServer((q, s) => { const f = files[q.url]; if (!f) { s.writeHead(404); s.end(); return; }
  s.writeHead(200, { "content-type": q.url.endsWith(".js") ? "text/javascript; charset=utf-8" : q.url.endsWith(".json") ? "application/json" : "text/html; charset=utf-8" }); s.end(f); });
server.listen(0, "127.0.0.1", async () => {
  const port = server.address().port, results = [];
  const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: ok ? undefined : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? " — " + String(detail).slice(0, 300) : "")); };
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [], external = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("request", (r) => { if (!r.url().startsWith(`http://127.0.0.1:${port}/`)) external.push(r.url()); });
  await page.goto(`http://127.0.0.1:${port}/index.html`);
  const B = await page.evaluate(() => window.K03_RUN());
  const timing = {};
  for (const city of ["shymkent", "astana"]) {
    const G = R.prepare(JSON.parse(files[`/graph/${city}.graph.json`]));
    const kase = JSON.parse(files[`/examples/${city}_case.json`]);
    check(`${city}: graph_sha256 проверен в браузере функцией CITY_FACTS.sha256hex базы`, B[city].prepare_with_hash_ms >= 0);
    check(`${city}: подмена длины ребра в браузере → graph_hash_mismatch`, B[city].tamper === "graph_hash_mismatch", B[city].tamper);
    for (const [m, p] of [["geodesic", null], ["pedestrian-v1", "pedestrian-v1-strict"], ["pedestrian-v1", "pedestrian-v1-exploratory"]]) {
      const node = A.distanceMatrix({ ...kase, parameters: { ...kase.parameters, distance_method: m, routing_policy_id: p } }, G).rows;
      const br = B[city].res[p || m].rows;
      check(`${city} ${p || m}: ${br.length} строк браузера = Node (статус, мм, рёбра, геометрия, допущения)`, JSON.stringify(br) === JSON.stringify(node));
    }
    timing[city] = { prepare_with_hash_ms: Math.round(B[city].prepare_with_hash_ms), matrix_ms: Object.fromEntries(Object.entries(B[city].res).map(([k, v]) => [k, Math.round(v.ms)])),
      rows: B[city].res.geodesic.rows.length };
  }
  check("нет ошибок страницы", errors.length === 0, errors.join(" | "));
  check("нет запросов вне localhost", external.length === 0, external.join(" "));
  const version = browser.version();
  await browser.close(); server.close();
  fs.writeFileSync(outFile, JSON.stringify({ what: "модуль в Chromium с sha256hex facts.js d2ff344; не интегрированный сайт", browser: `Chromium ${version}`,
    platform: process.platform, results, timing_ms: timing }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
});
