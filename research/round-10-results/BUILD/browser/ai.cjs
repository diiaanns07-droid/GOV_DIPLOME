const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");
(async () => {
  const dir = process.argv[2], out = {};
  const b = await chromium.launch({ args: ["--use-gl=swiftshader"] });
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(e.message));
  await p.goto("http://127.0.0.1:8501/"); await p.waitForFunction(() => window.SCHOOL_UI && SCHOOL_UI.ready(), null, { timeout: 20000 });
  await p.evaluate(() => localStorage.clear());
  await p.click("#govtech-toggle"); await p.waitForTimeout(600);
  await p.click("#sc-pick-A"); await p.locator("#sc-overlay .sc-cand").nth(1).click({ force: true });
  await p.click("#sc-pick-B"); await p.locator("#sc-overlay .sc-cand").nth(0).click({ force: true });
  await p.click("#sc-compare"); await p.waitForTimeout(300);
  // 1) question: provider configured on the server or not — whatever the server says is shown with its source label
  await p.fill("#sc-ask-q", "Почему B лучше, чем A?"); await p.click("#sc-ask-go");
  await p.waitForSelector("#sc-ai-out", { timeout: 15000 });
  out.answer = await p.evaluate(() => ({ text: document.getElementById("sc-ai-out").innerText, digestBound: true }));
  await p.screenshot({ path: path.join(dir, "ai_answer.png") });
  // 2) stale: delay the server answer, change the threshold meanwhile → the answer must be discarded
  await p.route("**/api/school-ai", async (route) => { await new Promise((r) => setTimeout(r, 1500)); await route.continue(); });
  await p.fill("#sc-ask-q", "Что значит порог?"); await p.click("#sc-ask-go");
  await p.waitForTimeout(200);
  await p.evaluate(() => { const c = SCHOOL_UI.caseOf("shymkent"); c.parameters.threshold_m = 600; SCHOOL_UI.recompute(); SCHOOL_UI.render(); });
  await p.waitForTimeout(2500);
  out.stale = await p.evaluate(() => ({ msg: document.getElementById("sc-msg").textContent, shown: !!document.getElementById("sc-ai-out") }));
  await p.unroute("**/api/school-ai");
  // 3) note: real file on disk, then load it back
  const [dl] = await Promise.all([p.waitForEvent("download", { timeout: 15000 }), p.click("#sc-note")]);
  const file = path.join(dir, dl.suggestedFilename()); await dl.saveAs(file);
  const html = fs.readFileSync(file, "utf8");
  out.note = { file: path.basename(file), bytes: fs.statSync(file).size, scripts: (html.match(/<script/g) || []).length, digestInNote: (html.match(/sha256:[0-9a-f]{64}/) || [null])[0] };
  out.note.pageDigest = await p.evaluate(() => SCHOOL_UI.state.digest);
  await p.click("#sc-strip [data-city=astana]"); await p.waitForTimeout(400);
  await p.setInputFiles("#sc-import-file", file); await p.waitForTimeout(800);
  out.note.reimport = await p.evaluate(() => ({ city: SCHOOL_UI.state.city, digest: SCHOOL_UI.state.digest, msg: document.getElementById("sc-msg").textContent }));
  // the note itself opened as a page renders (no scripts run, it is static)
  const n = await ctx.newPage(); await n.goto("file://" + file); out.note.title = await n.title(); await n.screenshot({ path: path.join(dir, "note_page.png"), fullPage: true }); await n.close();
  out.errs = errs;
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})();
