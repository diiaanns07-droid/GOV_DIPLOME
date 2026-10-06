const { chromium } = require("playwright");
async function hold(p, sel, ms) { await p.locator(sel).scrollIntoViewIfNeeded(); const bb = await p.locator(sel).boundingBox(); await p.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await p.mouse.down(); await p.waitForTimeout(ms); await p.mouse.up(); }
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  await p.goto("http://127.0.0.1:8501/"); await p.waitForTimeout(4000);
  await p.click("#govtech-toggle"); await p.waitForTimeout(800); await p.click("#sc-strip .sc-adv"); await p.waitForTimeout(300);
  await p.click("#plDemo"); await p.waitForTimeout(300);
  // D1: type budget, then human-speed click on «Найти»
  await p.locator("#plRun").scrollIntoViewIfNeeded(); await p.fill("#plBudget", "400");
  await hold(p, "#plRun", 110);
  await p.waitForTimeout(400);
  const d1 = await p.evaluate(() => ({ status: CITY_PLAN_UI.opt.status, rid: CITY_PLAN_UI.opt.request_id, budget: CITY_PLAN_UI.state.budget }));
  console.log("D1 after one click:", JSON.stringify(d1));
  await p.waitForTimeout(3000);
  await hold(p, "#plRun", 110); await p.waitForTimeout(400);
  console.log("D1 control (second click):", JSON.stringify(await p.evaluate(() => ({ status: CITY_PLAN_UI.opt.status, rid: CITY_PLAN_UI.opt.request_id }))));
  await p.waitForTimeout(3000);
  await p.evaluate(() => document.querySelectorAll("#gov-panel details").forEach((d) => d.open = true));
  // D2: invalid candidate cost then switch city
  const cid = await p.evaluate(() => CITY_PLAN_UI.state.cands[0].id);
  await p.fill("#plC_" + cid, "0");
  await hold(p, '#gov-panel [data-city="astana"]', 110);
  await p.waitForTimeout(500);
  const d2 = await p.evaluate(() => ({ city: CITY_APP.state.city, msg: CITY_PLAN_UI.state.msg, shown: document.getElementById("plMsg")?.textContent }));
  console.log("D2:", JSON.stringify(d2));
  await b.close();
})();
