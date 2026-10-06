const { chromium } = require("playwright");
async function hold(p, sel, ms) { await p.locator(sel).scrollIntoViewIfNeeded(); const bb = await p.locator(sel).boundingBox(); await p.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await p.mouse.down(); await p.waitForTimeout(ms); await p.mouse.up(); }
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader"] });
  const p = await (await b.newContext({ viewport: { width: +(process.argv[2] || 1440), height: +(process.argv[3] || 900) } })).newPage();
  await p.goto("http://127.0.0.1:8501/"); await p.waitForFunction(() => window.SCHOOL_UI && SCHOOL_UI.ready(), null, { timeout: 20000 });
  await p.evaluate(() => localStorage.clear());
  await p.click("#govtech-toggle"); await p.waitForTimeout(600);
  await p.click("#sc-pick-A"); await p.locator("#sc-overlay .sc-cand").nth(1).click({ force: true }); await p.waitForTimeout(300);
  await p.click("#sc-view-current"); await p.waitForTimeout(200);
  await p.click("#sc-card .sc-back").catch(() => {}); await p.waitForTimeout(200);
  await p.locator("#sc-threshold").scrollIntoViewIfNeeded();
  await p.fill("#sc-threshold", "700");
  await hold(p, "#sc-compare", 110); await p.waitForTimeout(400);
  console.log(JSON.stringify(await p.evaluate(() => ({ thr: SCHOOL_UI.caseOf("shymkent").parameters.threshold_m, compared: SCHOOL_UI.state.compared, title: document.querySelector("#sc-card h2").textContent }))));
  await b.close();
})();
