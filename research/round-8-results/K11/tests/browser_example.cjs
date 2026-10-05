// K11 round 8 — headless browser check of example/index.html (Playwright Chromium).
// Usage: NODE_PATH="$(npm root -g)" node tests/browser_example.cjs [--file] [--out report.json]
//   default: served over http://127.0.0.1:<free port> by this script's own static server (stopped at the end)
//   --file : also opened as file:// (via url.pathToFileURL) — worker must come from the inlined Blob bundle
// Exit 0 all pass, 1 failures, 3 playwright not resolvable (not_run).
"use strict";
const fs = require("fs"), path = require("path"), http = require("http"), { pathToFileURL } = require("url");
const ROOT = path.resolve(__dirname, "..");
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { console.log("NOT_RUN playwright not resolvable (set NODE_PATH or npm i playwright locally)"); process.exit(3); }

const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: detail === undefined ? null : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (ok || detail === undefined ? "" : " :: " + JSON.stringify(detail).slice(0, 400))); };
const expected = JSON.parse(fs.readFileSync(path.join(ROOT, "fixtures/synthetic/expected_oracle.json"), "utf8"))["syn_bench_16x25.json"].main;
const expectedReal = JSON.parse(fs.readFileSync(path.join(ROOT, "fixtures/real/expected_oracle.json"), "utf8"))["real_shymkent_school_16x25.json"].main;
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json" };

function serve() {
  const srv = http.createServer((req, res) => {
    const u = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const p = path.normalize(path.join(ROOT, u));
    if (!p.startsWith(ROOT + path.sep) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end("not found"); return; }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(p)] || "application/octet-stream" });
    fs.createReadStream(p).pipe(res);
  });
  return new Promise((r) => srv.listen(0, "127.0.0.1", () => r(srv)));
}

async function exercise(page, label) {
  const errors = [], external = [];
  page.on("pageerror", (e) => errors.push(String(e.message)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("request", (r) => { const u = r.url(); if (!/^(file:|blob:|http:\/\/127\.0\.0\.1)/.test(u)) external.push(u); });
  const objIds = (env) => env.result && Object.fromEntries(Object.entries(env.result.objectives).map(([k, v]) => [k, v.selected_ids]));
  const want = Object.fromEntries(Object.entries(expected.objectives).map(([k, v]) => [k, v.selected_ids]));
  for (const mode of ["worker", "chunks", "auto"]) {
    const env = await page.evaluate((m) => window.K11_DEMO.run("syn_bench_16x25.json", m, false).then((e) => ({ status: e.status, mode: e.mode, fallback: e.fallback, elapsed_ms: e.elapsed_ms, result: e.result })), mode);
    const pr = await page.evaluate(() => window.K11_DEMO.probe());
    check(`${label} mode=${mode}: optimal, ran as ${mode === "auto" ? "worker" : mode}, objectives = Python oracle`,
      env.status === "optimal" && env.mode === (mode === "auto" ? "worker" : mode) && JSON.stringify(objIds(env)) === JSON.stringify(want),
      { status: env.status, mode: env.mode, fallback: env.fallback, ids: objIds(env) });
    results[results.length - 1].measure = { elapsed_ms: env.elapsed_ms, frames: pr.frames, max_frame_gap_ms: Math.round(pr.maxGapMs) };
  }
  const envR = await page.evaluate(() => window.K11_DEMO.run("real_shymkent_school_16x25.json", "worker", true).then((e) => ({ status: e.status, ids: e.result.objectives.mean.selected_ids, sens: e.result.sensitivity.map((s) => [s.budget, s.status]) })));
  check(`${label} real Shymkent slice + sensitivity in worker: mean plan = oracle, 3 budgets`,
    envR.status === "optimal" && JSON.stringify(envR.ids) === JSON.stringify(expectedReal.objectives.mean.selected_ids) && envR.sens.length === 3, envR);
  const canc = await page.evaluate(async () => {
    const p = window.K11_DEMO.run("syn_bench_16x25.json", "worker", true);
    await new Promise((r) => setTimeout(r, 15));
    window.K11_DEMO.cancel();
    const env = await p;
    await new Promise((r) => setTimeout(r, 400));
    return { status: env.status, hasResult: !!env.result, state: window.K11_DEMO.state(), applyDisabled: document.getElementById("apply").disabled };
  });
  check(`${label} cancel in browser: cancelled, no result, Apply disabled, no pending cancel`,
    canc.status === "cancelled" && !canc.hasResult && canc.applyDisabled && canc.state.pending_cancels === 0, canc);
  const inf = await page.evaluate(() => window.K11_DEMO.run("syn_infeasible_budget.json", "worker", false).then((e) => ({ status: e.status, reasons: e.result && e.result.reasons, text: document.getElementById("status").textContent })));
  check(`${label} infeasible shown with reason, not as optimal`, inf.status === "infeasible" && inf.reasons.includes("required_exceeds_budget") && /required_exceeds_budget/.test(inf.text), inf);
  check(`${label} no page errors, no external requests`, errors.length === 0 && external.length === 0, { errors, external });
}

(async () => {
  const srv = await serve();
  const port = srv.address().port;
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${port}/example/index.html`);
    await page.waitForFunction(() => !!window.K11_DEMO);
    await exercise(page, "http");
    await page.close();
    if (process.argv.includes("--file")) {
      const p2 = await browser.newPage();
      await p2.goto(pathToFileURL(path.join(ROOT, "example", "index.html")).href);
      await p2.waitForFunction(() => !!window.K11_DEMO);
      check("file:// page detected as fileMode (Blob worker from inlined sources)", await p2.evaluate(() => window.K11_DEMO.fileMode));
      await exercise(p2, "file");
      await p2.close();
    }
  } finally {
    await browser.close();
    await new Promise((r) => srv.close(r));
  }
  const summary = { pass: results.filter((r) => r.ok).length, fail: results.filter((r) => !r.ok).length };
  console.log("summary:", JSON.stringify(summary));
  const i = process.argv.indexOf("--out");
  if (i > 0) fs.writeFileSync(process.argv[i + 1], JSON.stringify({ tool: "tests/browser_example.cjs", node: process.version, summary, results }, null, 1) + "\n");
  process.exitCode = summary.fail ? 1 : 0;
})();
