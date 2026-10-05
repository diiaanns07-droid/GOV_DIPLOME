// K11 round 8 stage 3 — Unicode export/import of city-plan-v2 scenario files.
// Usage: node tests/export_unicode.cjs [--out runs/stage3_export_unicode.json] [--no-browser] [--no-python]
//   Node part (always): bytes of the export, re-import of all 11 fixtures, Notepad variants (BOM+CRLF, UTF-16 LE),
//   Windows-1251 "ANSI" bytes rejected, strict JSON, derived_results never trusted, Windows-safe file names.
//   Python part: the independent oracle solves the exported file from another cwd, path with Kazakh letters and spaces
//   (python3/python from PATH or $PYTHON; absent -> not_run, never PASS).
//   Browser part: example page over http and file://, real download (file name + bytes) and file input import
//   (needs Playwright via NODE_PATH="$(npm root -g)"; absent -> not_run).
// Exit 0 = no FAIL. not_run checks are listed separately and are not counted as PASS.
"use strict";
const fs = require("fs"), os = require("os"), path = require("path"), http = require("http"), cp = require("child_process");
const { pathToFileURL } = require("url");
const ROOT = path.resolve(__dirname, "..");
const CORE = require(path.join(ROOT, "src/plan_core.js"));
const EXP = require(path.join(ROOT, "src/plan_export.js"));
const R = require(path.join(ROOT, "src/plan_runner.js"));

const results = [], notRun = [];
function check(name, ok, detail) { results.push({ name, ok: !!ok, detail: detail === undefined ? null : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (ok || detail === undefined ? "" : " :: " + JSON.stringify(detail).slice(0, 300))); }
function skip(name, why) { notRun.push({ name, why }); console.log("NOT_RUN " + name + " :: " + why); }
const errCode = (f) => { try { f(); return null; } catch (e) { return e.code || e.name || String(e); } };
const load = (d, f) => JSON.parse(fs.readFileSync(path.join(ROOT, "fixtures", d, f), "utf8"));
const FIX = [];
for (const d of ["synthetic", "real"]) for (const f of fs.readdirSync(path.join(ROOT, "fixtures", d)).sort())
  if (f.endsWith(".json") && f !== "expected_oracle.json") FIX.push({ d, f, fx: load(d, f) });
const EXPECTED = { synthetic: load("synthetic", "expected_oracle.json"), real: load("real", "expected_oracle.json") };
const byName = (f) => FIX.find((x) => x.f === f);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const ids = (r) => r.objectives ? Object.fromEntries(Object.entries(r.objectives).map(([k, v]) => [k, v.selected_ids])) : null;

// Windows-1251 encoder for ASCII + Russian Cyrillic only (А..я, Ё, ё): models a Notepad "ANSI" save on a Russian Windows.
function cp1251(s) {
  const out = [];
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if (c < 0x80) out.push(c);
    else if (c >= 0x410 && c <= 0x44f) out.push(0xc0 + c - 0x410);
    else if (c === 0x401) out.push(0xa8); else if (c === 0x451) out.push(0xb8);
    else throw new Error("not encodable in cp1251: U+" + c.toString(16));
  }
  return Buffer.from(out);
}
function findPython() {
  for (const exe of [process.env.PYTHON, "python3", "python"].filter(Boolean)) {
    const r = cp.spawnSync(exe, ["-c", "import sys; print(sys.version.split()[0])"], { encoding: "utf8" });
    if (r.status === 0) return { exe, version: r.stdout.trim() };
  }
  return null;
}

async function nodePart(tmp) {
  // 1. export bytes of the Unicode fixture with a real runner envelope
  const uni = byName("syn_unicode_ids.json").fx;
  const runner = R.createPlanRunner({ engine: CORE, mode: "chunks" });
  const env = await runner.run(uni.context, uni.scenario).promise;
  runner.dispose();
  const sc = CORE.validatePlanScenario(uni.scenario, uni.context);
  const file = EXP.exportPlanFile(sc, env);
  const bytes = Buffer.from(file.text, "utf8");
  const allIds = [...sc.control_points.map((p) => p.id), ...sc.candidates.map((c) => c.id)];
  check("1a export bytes: UTF-8 without BOM, LF only, final newline", bytes[0] === 0x7b && !bytes.includes(0x0d) && bytes[bytes.length - 1] === 0x0a,
    { first: bytes[0], has_cr: bytes.includes(0x0d) });
  check("1b export keeps Cyrillic/Kazakh/PUA/emoji letters (no \\u escapes) and every id byte-exact",
    !file.text.includes("\\u") && allIds.every((id) => bytes.includes(Buffer.from(JSON.stringify(id), "utf8"))),
    allIds.filter((id) => !bytes.includes(Buffer.from(JSON.stringify(id), "utf8"))));
  check("1c export is strict JSON, <= 256 KiB, derived_results labelled and equal to the run", (() => {
    const o = EXP.parseStrict(file.text);
    return bytes.length <= EXP.MAX_BYTES && o.derived_results && /never trusted/.test(o.derived_results.note) &&
      o.derived_results.problem_digest === env.problem_digest && same(ids(o.derived_results), ids(env.result));
  })());
  const keys = Object.keys(JSON.parse(file.text));
  check("1d top-level key order is fixed (schema first, derived_results last)", keys[0] === "schema_version" && keys[keys.length - 1] === "derived_results", keys);

  // 2. every fixture: export -> file on disk -> bytes import -> same scenario and digest (synthetic & real)
  const dir = path.join(tmp, "K11 сынақ қалта ә");
  fs.mkdirSync(dir, { recursive: true });
  const rt = [];
  for (const { d, f, fx } of FIX) {
    const v = CORE.validatePlanScenario(fx.scenario, fx.context);
    const out = EXP.exportPlanFile(v, null, f.replace(/\.json$/, ""));
    const p = path.join(dir, out.filename);
    fs.writeFileSync(p, out.text, "utf8");
    const back = EXP.importPlanBytes(fs.readFileSync(p), fx.context, CORE);
    rt.push({ fixture: d + "/" + f, filename: out.filename, ok: same(back.scenario, v) && CORE.scenarioDigest(back.scenario) === CORE.scenarioDigest(v) && !back.bom });
  }
  check("2 all 11 fixtures: export -> file in a Kazakh-named folder -> import gives the same scenario and digest", rt.every((x) => x.ok), rt.filter((x) => !x.ok));

  // 3. Notepad variants
  const shy = byName("real_shymkent_school_16x25.json").fx;
  const shySc = CORE.validatePlanScenario(shy.scenario, shy.context);
  const shyText = EXP.exportPlanFile(shySc, null).text;
  const bomCrlf = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(shyText.replace(/\n/g, "\r\n"), "utf8")]);
  const a = EXP.importPlanBytes(bomCrlf, shy.context, CORE);
  check("3a Notepad UTF-8 with BOM + CRLF accepted, same scenario", a.bom && a.encoding === "utf-8" && same(a.scenario, shySc));
  const u16 = Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from(shyText.replace(/\n/g, "\r\n"), "utf16le")]);
  const b = EXP.importPlanBytes(u16, shy.context, CORE);
  check("3b Notepad 'Unicode' (UTF-16 LE with BOM) accepted, same scenario", b.encoding === "utf-16le" && same(b.scenario, shySc));
  check("3c text-path import (string with BOM) also accepted", EXP.importPlanText("\ufeff" + shyText, shy.context, CORE).bom === true);
  // Windows-1251 ("ANSI"): a Russian-only renamed scenario, so the bytes are a real cp1251 encoding of a valid file
  const ru = JSON.parse(JSON.stringify(byName("syn_ties.json").fx));
  const rename = (id) => "школа-" + id.replace(/[^a-z0-9]/gi, "");
  ru.scenario.candidates.forEach((c) => { c.id = rename(c.id); });
  ru.scenario.control_points.forEach((p) => { p.id = "точка-" + p.id.replace(/[^a-z0-9]/gi, ""); });
  for (const k of ["required_ids", "excluded_ids", "selected_ids"]) ru.scenario[k] = ru.scenario[k].map(rename);
  const ruSc = CORE.validatePlanScenario(ru.scenario, ru.context);
  const ruText = EXP.exportPlanFile(ruSc, null).text;
  check("3d Windows-1251 bytes of a valid Russian file -> not_utf8 (no silent mojibake)", errCode(() => EXP.importPlanBytes(cp1251(ruText), ru.context, CORE)) === "not_utf8");
  const lossy = new TextDecoder("utf-8").decode(cp1251(ruText));  // what File.text() / readAsText would give
  check("3e same file decoded lossily as text -> replacement_char error, not an import", errCode(() => EXP.importPlanText(lossy, ru.context, CORE)) === "replacement_char");
  check("3f same Russian scenario as UTF-8 imports fine", same(EXP.importPlanBytes(Buffer.from(ruText, "utf8"), ru.context, CORE).scenario, ruSc));

  // 4. strict JSON
  const bad = {
    duplicate_key: '{"a":1,"a":2}', non_finite_number: '{"a":1e999}', bad_json_nan: '{"a":NaN}', bad_json_inf: '{"a":Infinity}',
    bad_json_neg_inf: '{"a":-Infinity}', bad_json_trailing: '{"a":1} x', bad_json_comma: '{"a":1,}', bad_json_comment: '{"a":1 /*c*/}',
    bad_json_single_quote: "{'a':1}", bad_json_leading_zero: '{"a":01}', bad_json_ctrl_in_string: '{"a":"x\ty"}', lone_surrogate: '{"a":"\\ud800"}',
    bad_json_deep: "[".repeat(100) + "]".repeat(100),
  };
  const got = Object.fromEntries(Object.entries(bad).map(([k, t]) => [k, errCode(() => EXP.parseStrict(t))]));
  const want = (k) => (k.startsWith("bad_json") ? "bad_json" : k);
  check("4a strict parser rejects duplicate keys, NaN/Infinity, 1e999, trailing data, comments, lone surrogates, depth>64",
    Object.entries(got).every(([k, c]) => c === want(k)), got);
  const proto = EXP.parseStrict('{"__proto__":{"x":1},"b":[1,2.5,-3e2,true,false,null,"ә\\n😀"]}');
  check("4b accepted JSON equals JSON.parse; __proto__ stays a plain data key", Object.getPrototypeOf(proto) === Object.prototype && proto.__proto__.x === 1 && ({}).x === undefined &&
    same(proto.b, JSON.parse('[1,2.5,-3e2,true,false,null,"ә\\n😀"]')) && FIX.every(({ fx }) => same(EXP.parseStrict(JSON.stringify(fx)), fx)));
  check("4c > 256 KiB rejected before parsing", errCode(() => EXP.importPlanText('{"x":"' + "ә".repeat(140000) + '"}', uni.context, CORE)) === "too_large");
  const t0 = Date.now(); EXP.parseStrict(JSON.stringify({ a: Array.from({ length: 12000 }, (_, i) => "қ" + i) })); const parseMs = Date.now() - t0;
  check("4d parser is linear: 12k strings (~150 KB) parse fast", parseMs < 1500, { parse_ms: parseMs });

  // 5. export refuses what JSON.stringify would silently change
  check("5a export with NaN budget -> non_finite_number (not 'null' in the file)", errCode(() => EXP.exportPlanFile(Object.assign({}, sc, { budget: NaN }), null)) === "non_finite_number");
  check("5b export with a lone surrogate id -> lone_surrogate (not '\\ud800' in the file)",
    errCode(() => EXP.exportPlanFile(Object.assign({}, sc, { selected_ids: ["x\ud800"] }), null)) === "lone_surrogate");
  check("5c non-optimal envelope (cancelled/infeasible) adds no derived_results",
    !("derived_results" in JSON.parse(EXP.exportPlanFile(sc, { status: "cancelled", result: null }).text)) &&
    !("derived_results" in JSON.parse(EXP.exportPlanFile(sc, { status: "infeasible", result: { objectives: null } }).text)));

  // 6. derived_results are never trusted
  const tampered = JSON.parse(file.text);
  tampered.derived_results.objectives.mean.selected_ids = ["подделка"];
  tampered.derived_results.problem_digest = "sha256:" + "0".repeat(64);
  const imp = EXP.importPlanText(JSON.stringify(tampered), uni.context, CORE);
  const re = CORE.optimizePlansSync(uni.context, imp.scenario);
  check("6 tampered derived_results ignored: flagged, dropped from scenario, recomputed result = oracle",
    imp.derived_ignored && !("derived_results" in imp.scenario) && same(ids(re), ids(EXPECTED.synthetic["syn_unicode_ids.json"].main)));

  // 7. file names (Windows rules applied by the code; this machine is Linux — names are also created here for real)
  const nfd = "мектеп\u0438\u0306".normalize("NFD");  // "й" decomposed
  const cases = {
    shymkent: [EXP.suggestFilename(shySc), "план_Шымкент_школы.json"],
    astana_clinic: [EXP.suggestFilename(byName("real_astana_outpatient_clinic_8x12.json").fx.scenario), "план_Астана_поликлиники.json"],
    label: [EXP.suggestFilename(shySc, "вариант 2"), "план_Шымкент_школы_вариант 2.json"],
    forbidden: [EXP.safeFilename('a<b>c:d"e/f\\g|h?i*j\u0001k'), "a_b_c_d_e_f_g_h_i_j_k.json"],
    reserved: [EXP.safeFilename("CON"), "_CON.json"], reserved_ext: [EXP.safeFilename("lpt1.txt"), "_lpt1.txt.json"],
    reserved_sup: [EXP.safeFilename("COM¹"), "_COM¹.json"], not_reserved: [EXP.safeFilename("CONSOLE"), "CONSOLE.json"],
    trailing: [EXP.safeFilename("  жоспар. . "), "жоспар.json"], empty: [EXP.safeFilename(" ... "), "plan.json"],
    nfc: [EXP.safeFilename(nfd), "мектепй.json"],
  };
  const long = EXP.safeFilename("😀".repeat(300));
  check("7a file names: Cyrillic kept, forbidden chars, reserved device names, trailing dots/spaces, NFC",
    Object.values(cases).every(([g, w]) => g === w), Object.fromEntries(Object.entries(cases).filter(([, [g, w]]) => g !== w)));
  check("7b long names cut to <= 120 UTF-16 units on a code point boundary", long.length <= 125 && !/\p{Cs}/u.test(long) && long.endsWith(".json"), { length: long.length });
  const created = [...Object.values(cases).map(([g]) => g), long].map((n) => { const p = path.join(dir, n); fs.writeFileSync(p, "{}\n"); return fs.readdirSync(dir).includes(n); });
  check("7c every sanitized name can be created and listed back byte-exact (this OS)", created.every(Boolean));
  return { dir, shy, shySc, uni, env };
}

function pythonPart(ctx, tmp) {
  const py = findPython();
  if (!py) { skip("8 Python oracle on the exported file", "python3/python not found"); return null; }
  const script = path.join(ROOT, "tests", "export_roundtrip.py");
  const otherCwd = fs.mkdtempSync(path.join(tmp, "cwd-"));
  const rows = [];
  for (const f of ["syn_unicode_ids.json", "real_shymkent_school_16x25.json", "real_astana_outpatient_clinic_8x12.json", "syn_infeasible_budget.json"]) {
    const { d, fx } = byName(f);
    const v = CORE.validatePlanScenario(fx.scenario, fx.context);
    const out = EXP.exportPlanFile(v, { status: "optimal", problem_digest: "x", result: { objectives: { mean: { selected_ids: ["подделка"], metrics: {} } }, pareto: [] } }, "проверка");
    const sp = path.join(ctx.dir, out.filename), cxp = path.join(ctx.dir, "контекст " + f);
    fs.writeFileSync(sp, out.text, "utf8");
    fs.writeFileSync(cxp, JSON.stringify(fx.context), "utf8");
    for (const [envName, extra] of [["default", {}], ["LC_ALL=C", { LC_ALL: "C", LANG: "C", PYTHONIOENCODING: "", PYTHONUTF8: "" }]]) {
      const r = cp.spawnSync(py.exe, [script, sp, cxp], { cwd: otherCwd, encoding: "utf8", env: Object.assign({}, process.env, extra) });
      let got = null;
      try { got = JSON.parse(r.stdout); } catch (e) { /* recorded below */ }
      const exp = EXPECTED[d][f].main;
      rows.push({ fixture: f, env: envName, exit: r.status, stderr: (r.stderr || "").slice(0, 300),
        ok: r.status === 0 && got && got.status === exp.status && same(got.objectives, exp.objectives ? ids(exp) : {}) &&
          (exp.status !== "optimal" || same(got.objectives, ids(CORE.optimizePlansSync(fx.context, v)))) });
    }
  }
  check("8 Python oracle reads the exported file (Kazakh path, other cwd, also LC_ALL=C), ignores fake derived_results, = JS = expected",
    rows.every((x) => x.ok), rows.filter((x) => !x.ok));
  return { python: py, rows };
}

// Chromium on Linux names a download "download" when its locale is not UTF-8 (observed here with LANG=C), so the main
// browser checks run with LANG=C.UTF-8 and the C-locale behaviour is recorded as an observation (9d).
async function browserPart(tmp) {
  let chromium;
  try { ({ chromium } = require("playwright")); } catch (e) { skip("9 browser download/import (http, file://)", "playwright not resolvable (NODE_PATH)"); return null; }
  const srv = http.createServer((req, res) => {
    const p = path.normalize(path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname)));
    if (!p.startsWith(ROOT + path.sep) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
    const t = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8" }[path.extname(p)] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": t }); fs.createReadStream(p).pipe(res);
  });
  await new Promise((r) => srv.listen(0, "127.0.0.1", r));
  const utf8Env = Object.assign({}, process.env, { LANG: "C.UTF-8", LC_ALL: "C.UTF-8" });
  const browser = await chromium.launch({ env: utf8Env });
  const out = {};
  let cLocale = null;
  try {
    const targets = { http: `http://127.0.0.1:${srv.address().port}/example/index.html`, file: pathToFileURL(path.join(ROOT, "example", "index.html")).href };
    const fx = byName("real_shymkent_school_16x25.json").fx;
    const sc = CORE.validatePlanScenario(fx.scenario, fx.context);
    for (const [name, url] of Object.entries(targets)) {
      const ctx = await browser.newContext({ acceptDownloads: true });
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
      await page.goto(url);
      await page.waitForFunction(() => !!window.K11_DEMO && !!window.CITY_PLAN_EXPORT);
      await page.selectOption("#fixture", "real_shymkent_school_16x25.json");
      // a) plain scenario download
      let [dl] = await Promise.all([page.waitForEvent("download"), page.click("#export")]);
      const p1 = path.join(tmp, name + "-1.json"); await dl.saveAs(p1);
      const b1 = fs.readFileSync(p1);
      const name1 = dl.suggestedFilename();
      // b) after an optimal run: derived_results included and equal to the run
      const env = await page.evaluate(() => window.K11_DEMO.run("real_shymkent_school_16x25.json", "auto", false).then((e) => ({ status: e.status, mode: e.mode, mean: e.result.objectives.mean.selected_ids })));
      [dl] = await Promise.all([page.waitForEvent("download"), page.click("#export")]);
      const p2 = path.join(tmp, name + "-2.json"); await dl.saveAs(p2);
      const o2 = JSON.parse(fs.readFileSync(p2, "utf8"));
      // c) import through <input type=file>: Notepad BOM+CRLF accepted; Windows-1251 rejected; other slice rejected
      const imports = {};
      const variants = {
        bom_crlf: Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(fs.readFileSync(p2, "utf8").replace(/\n/g, "\r\n"), "utf8")]),
        cp1251_bytes: Buffer.concat([Buffer.from(fs.readFileSync(p1, "utf8").split("нүкте")[0], "utf8"), cp1251("школа")]),
        other_slice: Buffer.from(EXP.exportPlanFile(CORE.validatePlanScenario(byName("real_astana_school_16x25.json").fx.scenario, byName("real_astana_school_16x25.json").fx.context), null).text, "utf8"),
      };
      for (const [v, buf] of Object.entries(variants)) {
        await page.setInputFiles("#import", { name: "сценарий " + v + ".json", mimeType: "application/json", buffer: buf });
        await page.waitForFunction(() => window.K11_DEMO.lastImport);
        imports[v] = await page.evaluate(async () => { const r = await window.K11_DEMO.lastImport; window.K11_DEMO.lastImport = null; return Object.assign(r, { text: window.K11_DEMO.fileStatus() }); });
      }
      const after = await page.evaluate(() => window.K11_DEMO.run("real_shymkent_school_16x25.json", "auto", false).then((e) => ({ status: e.status, mean: e.result.objectives.mean.selected_ids })));
      out[name] = { name1, bytes1: b1.length, no_bom: b1[0] === 0x7b, no_cr: !b1.includes(0x0d),
        same_as_node: b1.equals(Buffer.from(EXP.exportPlanFile(sc, null).text, "utf8")),
        run: env, derived_ok: !!o2.derived_results && same(o2.derived_results.objectives.mean.selected_ids, env.mean) && o2.derived_results.status === "optimal",
        imports, after_import: after, errors };
      await ctx.close();
    }
    // 9d observation: same download with the browser process in the C locale
    const cb = await chromium.launch({ env: Object.assign({}, process.env, { LANG: "C", LC_ALL: "C" }) });
    try {
      const ctx = await cb.newContext({ acceptDownloads: true });
      const page = await ctx.newPage();
      await page.goto(targets.file);
      await page.waitForFunction(() => !!window.K11_DEMO);
      await page.selectOption("#fixture", "real_shymkent_school_16x25.json");
      const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#export")]);
      const p = path.join(tmp, "c-locale.json"); await dl.saveAs(p);
      cLocale = { suggested: dl.suggestedFilename(), same_bytes: fs.readFileSync(p).equals(Buffer.from(EXP.exportPlanFile(sc, null).text, "utf8")) };
    } finally { await cb.close(); }
  } finally { await browser.close(); await new Promise((r) => srv.close(r)); }
  const expMean = EXPECTED.real["real_shymkent_school_16x25.json"].main.objectives.mean.selected_ids;
  for (const [name, o] of Object.entries(out).filter(([k]) => k !== "c_locale_observation")) {
    check(`9a ${name}: download name "${o.name1}" and bytes = Node export (UTF-8, no BOM, LF)`, o.name1 === "план_Шымкент_школы.json" && o.no_bom && o.no_cr && o.same_as_node, o);
    check(`9b ${name}: export after an optimal run carries derived_results of that run`, o.derived_ok && same(o.run.mean, expMean), o.run);
    check(`9c ${name}: file input imports BOM+CRLF, rejects Windows-1251 and another slice with a visible reason`,
      o.imports.bom_crlf.ok && o.imports.bom_crlf.bom && o.imports.bom_crlf.derived_ignored && o.imports.cp1251_bytes.code === "not_utf8" &&
      o.imports.other_slice.code === "bad_city" && /другого города/.test(o.imports.other_slice.text) && /UTF-8/.test(o.imports.cp1251_bytes.text) && same(o.after_import.mean, expMean) && o.errors.length === 0, o.imports);
  }
  check(`9d observation, Linux C locale: download name "${cLocale.suggested}" (Cyrillic name ${cLocale.suggested === "план_Шымкент_школы.json" ? "kept" : "replaced by Chromium"}), file bytes unchanged`, cLocale.same_bytes, cLocale);
  out.c_locale_observation = cLocale;
  return out;
}

(async () => {
  const args = process.argv.slice(2);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "k11-export-"));
  let py = null, br = null;
  try {
    const ctx = await nodePart(tmp);
    py = args.includes("--no-python") ? (skip("8 Python oracle on the exported file", "--no-python"), null) : pythonPart(ctx, tmp);
    br = args.includes("--no-browser") ? (skip("9 browser download/import (http, file://)", "--no-browser"), null) : await browserPart(tmp);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
  const fail = results.filter((r) => !r.ok).length;
  const report = { tool: "tests/export_unicode.cjs", node: process.version, platform: process.platform, pass: results.length - fail, fail,
    not_run: notRun, python: py && py.python, results, python_rows: py && py.rows, browser: br };
  const i = args.indexOf("--out");
  if (i >= 0) fs.writeFileSync(args[i + 1], JSON.stringify(report, null, 1) + "\n");
  console.log(`${results.length - fail} PASS / ${fail} FAIL / ${notRun.length} NOT_RUN`);
  process.exitCode = fail ? 1 : 0;
})().catch((e) => { console.error(e); process.exitCode = 1; });
