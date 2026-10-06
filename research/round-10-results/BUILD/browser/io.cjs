const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), crypto = require("crypto");
(async () => {
  const dir = process.argv[2];
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(e.message));
  await p.goto("http://127.0.0.1:8501/"); await p.waitForFunction(() => window.SCHOOL_UI && SCHOOL_UI.ready(), null, { timeout: 20000 });
  await p.evaluate(() => localStorage.clear());
  await p.click("#govtech-toggle"); await p.waitForTimeout(800);
  await p.click("#sc-strip [data-city=astana]"); await p.waitForTimeout(600);
  await p.click("#sc-pick-A"); await p.locator("#sc-overlay .sc-cand").nth(3).click({ force: true });
  await p.click("#sc-pick-B"); await p.locator("#sc-overlay .sc-cand").nth(8).click({ force: true });
  await p.click("#sc-compare"); await p.waitForTimeout(300);
  const before = await p.evaluate(() => ({ city: SCHOOL_UI.state.city, digest: SCHOOL_UI.state.digest, v: SCHOOL_UI.caseOf("astana").variants, title: document.querySelector("#sc-card h2").textContent,
    metrics: SCHOOL_UI.plan("B").metrics }));
  const [dl] = await Promise.all([p.waitForEvent("download", { timeout: 15000 }), p.click("#sc-export")]);
  const file = path.join(dir, dl.suggestedFilename()); await dl.saveAs(file);
  const text = fs.readFileSync(file, "utf8"), saved = JSON.parse(text);
  const out = { before, file: path.basename(file), bytes: text.length, sha256: crypto.createHash("sha256").update(text).digest("hex"), file_digest: saved.case_digest };
  // switch to Shymkent, then import the Astana file: city switches, same digest and metrics
  await p.click("#sc-strip [data-city=shymkent]"); await p.waitForTimeout(400);
  await p.setInputFiles("#sc-import-file", file); await p.waitForTimeout(800);
  out.after_import = await p.evaluate(() => ({ city: SCHOOL_UI.state.city, digest: SCHOOL_UI.state.digest, v: SCHOOL_UI.caseOf("astana").variants, metrics: SCHOOL_UI.plan("B").metrics, msg: document.getElementById("sc-msg").textContent }));
  // tampered copy: refused, nothing changes
  const bad = path.join(dir, "tampered.json"); fs.writeFileSync(bad, text.replace('"threshold_m": 500', '"threshold_m": 700'));
  await p.setInputFiles("#sc-import-file", bad); await p.waitForTimeout(600);
  out.tampered = await p.evaluate(() => ({ digest: SCHOOL_UI.state.digest, msg: document.getElementById("sc-msg").textContent }));
  // foreign snapshot: refused
  const foreign = JSON.parse(text); delete foreign.case_digest; foreign.snapshot_id = "overture-2025-01-01.0-astana";
  const fp = path.join(dir, "foreign.json"); fs.writeFileSync(fp, JSON.stringify(foreign));
  await p.setInputFiles("#sc-import-file", fp); await p.waitForTimeout(600);
  out.foreign = await p.evaluate(() => ({ digest: SCHOOL_UI.state.digest, msg: document.getElementById("sc-msg").textContent }));
  out.errs = errs;
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})();
