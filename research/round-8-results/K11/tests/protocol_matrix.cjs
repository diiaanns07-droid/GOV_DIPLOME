// K11 round 8 stage 3 — how the worker starts under file:// vs http://localhost (Playwright Chromium).
// Usage: NODE_PATH="$(npm root -g)" node tests/protocol_matrix.cjs [--out runs/stage3_protocol_matrix.json]
// Servers (own, 127.0.0.1, stopped at the end): "http" serves .js as text/javascript; "http_textplain" serves .js as
// text/plain — a MODEL of a Windows machine whose registry maps .js to text/plain (Python's mimetypes reads the
// registry). Only Chromium is installed here: Firefox/WebKit = not_run. Exit 3 = playwright not resolvable.
"use strict";
const fs = require("fs"), path = require("path"), http = require("http"), { pathToFileURL } = require("url");
const ROOT = path.resolve(__dirname, "..");
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { console.log("NOT_RUN playwright not resolvable"); process.exit(3); }

function serve(jsType) {
  const types = { ".html": "text/html; charset=utf-8", ".js": jsType };
  const srv = http.createServer((req, res) => {
    const p = path.normalize(path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname)));
    if (!p.startsWith(ROOT + path.sep) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "Content-Type": types[path.extname(p)] || "application/octet-stream" });
    fs.createReadStream(p).pipe(res);
  });
  return new Promise((r) => srv.listen(0, "127.0.0.1", () => r(srv)));
}

async function probe(cfg) {  // runs in the page
  const RUN = window.CITY_PLAN_RUNNER, CORE = window.CITY_PLAN_CORE, fx = window.K11_EXAMPLE["syn_bench_16x25.json"];
  const out = { page_loaded: !!(RUN && CORE && fx) };
  // 1. raw new Worker(url): constructor error, async error event, or protocol reply
  out.raw_url_worker = await new Promise((resolve) => {
    let w;
    try { w = new Worker("../src/plan_worker.js"); } catch (e) { resolve({ ok: false, stage: "constructor", error: String(e.name + ": " + e.message).slice(0, 200) }); return; }
    const t = setTimeout(() => { w.terminate(); resolve({ ok: false, stage: "timeout" }); }, 3000);
    w.onerror = (e) => { clearTimeout(t); w.terminate(); resolve({ ok: false, stage: "error_event", error: String(e.message || "error event").slice(0, 200) }); };
    w.onmessage = (e) => { clearTimeout(t); w.terminate(); resolve({ ok: e.data && e.data.type === "accepted", stage: "message", type: e.data && e.data.type }); };
    w.postMessage({ type: "start", request_id: "probe", context: fx.context, scenario: fx.scenario, options: {} });
  });
  // 2. raw Blob worker from inlined sources
  out.raw_blob_worker = await new Promise((resolve) => {
    let w;
    try { w = RUN.blobWorkerFactory(window.CITY_PLAN_WORKER_SOURCES)(); } catch (e) { resolve({ ok: false, stage: "constructor", error: String(e.message).slice(0, 200) }); return; }
    const t = setTimeout(() => { w.terminate(); resolve({ ok: false, stage: "timeout" }); }, 3000);
    w.onerror = (e) => { clearTimeout(t); w.terminate(); resolve({ ok: false, stage: "error_event", error: String(e.message || "error").slice(0, 200) }); };
    w.onmessage = (e) => { if (e.data.type === "accepted") { clearTimeout(t); w.terminate(); resolve({ ok: true, stage: "message" }); } };
    w.postMessage({ type: "start", request_id: "probe", context: fx.context, scenario: fx.scenario, options: {} });
  });
  // 3. runner behaviour with each factory
  const runWith = async (mode, factory) => {
    const r = RUN.createPlanRunner({ engine: CORE, mode, workerFactory: factory });
    const env = await r.run(fx.context, fx.scenario).promise;
    r.dispose();
    return { status: env.status, mode: env.mode, fallback: env.fallback ? String(env.fallback).slice(0, 160) : null, code: env.code || null,
      mean: env.result ? env.result.objectives.mean.selected_ids.join(",") : null };
  };
  out.runner_auto_url = await runWith("auto", RUN.urlWorkerFactory("../src/plan_worker.js"));
  out.runner_worker_url = await runWith("worker", RUN.urlWorkerFactory("../src/plan_worker.js"));
  out.runner_auto_blob = await runWith("auto", RUN.blobWorkerFactory(window.CITY_PLAN_WORKER_SOURCES));
  return out;
}

(async () => {
  const want = JSON.parse(fs.readFileSync(path.join(ROOT, "fixtures/synthetic/expected_oracle.json"), "utf8"))["syn_bench_16x25.json"].main.objectives.mean.selected_ids.join(",");
  const srvJs = await serve("text/javascript; charset=utf-8"), srvTxt = await serve("text/plain; charset=utf-8");
  const browser = await chromium.launch();
  const rows = {};
  try {
    const targets = {
      http: `http://127.0.0.1:${srvJs.address().port}/example/index.html`,
      http_textplain_modeled_windows_registry: `http://127.0.0.1:${srvTxt.address().port}/example/index.html`,
      file: pathToFileURL(path.join(ROOT, "example", "index.html")).href,
    };
    for (const [name, url] of Object.entries(targets)) {
      const page = await browser.newPage();
      const console_errors = [];
      page.on("console", (m) => { if (m.type() === "error") console_errors.push(m.text().slice(0, 200)); });
      await page.goto(url);
      const loaded = await page.waitForFunction(() => !!window.CITY_PLAN_RUNNER && !!window.K11_EXAMPLE, null, { timeout: 5000 }).then(() => true, () => false);
      rows[name] = loaded ? await page.evaluate(probe) : { page_loaded: false };
      rows[name].console_errors = console_errors;
      await page.close();
    }
  } finally {
    await browser.close();
    await new Promise((r) => srvJs.close(r));
    await new Promise((r) => srvTxt.close(r));
  }
  const verdict = {
    http_url_worker_works: rows.http.raw_url_worker.ok && rows.http.runner_auto_url.mode === "worker" && rows.http.runner_auto_url.mean === want,
    file_url_worker_blocked: !rows.file.raw_url_worker.ok,
    file_auto_falls_back_to_chunks: rows.file.runner_auto_url.mode === "chunks" && rows.file.runner_auto_url.status === "optimal" && rows.file.runner_auto_url.mean === want,
    file_explicit_worker_reports_error: rows.file.runner_worker_url.status === "error",
    file_blob_worker_works: rows.file.raw_blob_worker.ok && rows.file.runner_auto_blob.mode === "worker" && rows.file.runner_auto_blob.mean === want,
    textplain_page_still_loads: rows.http_textplain_modeled_windows_registry.page_loaded,
    textplain_url_worker_blocked: !rows.http_textplain_modeled_windows_registry.raw_url_worker.ok,
    textplain_auto_falls_back: rows.http_textplain_modeled_windows_registry.runner_auto_url.mode === "chunks" && rows.http_textplain_modeled_windows_registry.runner_auto_url.mean === want,
    textplain_blob_worker_works: rows.http_textplain_modeled_windows_registry.runner_auto_blob.mode === "worker",
  };
  const out = { tool: "tests/protocol_matrix.cjs", browser: "chromium " + (await (async () => { try { return require("playwright/package.json").version; } catch (e) { return "?"; } })()),
    not_run: ["firefox", "webkit", "real Windows"], rows, verdict };
  const i = process.argv.indexOf("--out");
  if (i > 0) fs.writeFileSync(process.argv[i + 1], JSON.stringify(out, null, 1) + "\n");
  for (const [k, v] of Object.entries(verdict)) console.log((v ? "PASS " : "FAIL ") + k);
  for (const [k, v] of Object.entries(rows)) console.log("  " + k + ": raw_url=" + JSON.stringify(v.raw_url_worker) + " auto_url=" + JSON.stringify(v.runner_auto_url));
  process.exitCode = Object.values(verdict).every(Boolean) ? 0 : 1;
})().catch((e) => { console.error(e); process.exitCode = 1; });
