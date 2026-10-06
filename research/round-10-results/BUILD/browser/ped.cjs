const { chromium } = require("playwright");
(async () => {
  const out = process.argv[2], w = +(process.argv[3] || 1440), h = +(process.argv[4] || 900);
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const p = await (await b.newContext({ viewport: { width: w, height: h } })).newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(e.message));
  await p.goto("http://127.0.0.1:8501/"); await p.waitForFunction(() => window.SCHOOL_UI && SCHOOL_UI.ready(), null, { timeout: 20000 });
  await p.evaluate(() => localStorage.clear());
  await p.click("#govtech-toggle"); await p.waitForTimeout(800);
  await p.click("#sc-pick-A"); await p.locator("#sc-overlay .sc-cand").nth(1).click({ force: true });
  await p.click("#sc-pick-B"); await p.locator("#sc-overlay .sc-cand").nth(0).click({ force: true });
  await p.click("#sc-compare"); await p.waitForTimeout(300);
  const res = {};
  for (const k of ["pedestrian-v1-exploratory", "pedestrian-v1-strict", "geodesic"]) {
    const t0 = Date.now();
    await p.click("#sc-method-" + k);
    await p.waitForFunction((k) => { const c = SCHOOL_UI.caseOf(SCHOOL_UI.state.city); return SCHOOL_UI.state.cmp && (c.parameters.routing_policy_id || "geodesic") === k; }, k, { timeout: 20000 });
    await p.waitForTimeout(500);
    res[k] = await p.evaluate(() => ({ method: SCHOOL_UI.state.cmp.method, policy: SCHOOL_UI.state.cmp.policy_id, digest: SCHOOL_UI.state.digest.slice(7, 19),
      cur: SCHOOL_UI.plan("current").metrics, A: SCHOOL_UI.plan("A").metrics, B: SCHOOL_UI.plan("B").metrics, title: document.querySelector("#sc-card h2").textContent,
      lines: map.querySourceFeatures("sc-links").length }));
    res[k].ms = Date.now() - t0;
    await p.screenshot({ path: `${out}-${k}.png` });
  }
  // origin card under strict
  await p.click("#sc-method-pedestrian-v1-strict"); await p.waitForTimeout(800);
  await p.evaluate(() => SCHOOL_UI.select("origin", SCHOOL_UI.caseOf("shymkent").origins[3].id)); await p.waitForTimeout(300);
  res.origin_card = await p.evaluate(() => [...document.querySelectorAll("#sc-card p")].map((x) => x.textContent).join(" | "));
  await p.screenshot({ path: `${out}-origin-strict.png` });
  await p.reload(); await p.waitForFunction(() => window.SCHOOL_UI && SCHOOL_UI.ready(), null, { timeout: 20000 });
  await p.click("#govtech-toggle"); await p.waitForTimeout(2500);
  res.f5 = await p.evaluate(() => ({ policy: SCHOOL_UI.caseOf("shymkent").parameters.routing_policy_id, cmp: !!SCHOOL_UI.state.cmp, digest: SCHOOL_UI.state.digest && SCHOOL_UI.state.digest.slice(7, 19) }));
  res.errs = errs;
  console.log(JSON.stringify(res, null, 1));
  await b.close();
})();
