const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  await p.goto("http://127.0.0.1:8501/"); await p.waitForTimeout(4000);
  await p.click("#govtech-toggle"); await p.waitForTimeout(800); await p.click("#sc-strip .sc-adv"); await p.waitForTimeout(300);
  const show = async (t) => console.log(t, JSON.stringify(await p.evaluate(() => ({ city: CITY_APP.state.city, msg: CITY_PLAN_UI.state.msg }))));
  // variant 1: no points, invalid budget, fast click on city
  await p.fill("#plBudget", "-5"); await p.click('#gov-panel [data-city="astana"]'); await p.waitForTimeout(300); await show("v1 fast/no points:");
  // variant 2: demo, invalid cost, keyboard Tab then quick city click
  await p.click("#plDemo"); await p.evaluate(() => document.querySelectorAll("#gov-panel details").forEach((d) => d.open = true));
  const cid = await p.evaluate(() => CITY_PLAN_UI.state.cands[0].id);
  await p.locator("#plC_" + cid).scrollIntoViewIfNeeded(); await p.fill("#plC_" + cid, "0"); await p.click('#gov-panel [data-city="shymkent"]'); await p.waitForTimeout(300); await show("v2 fast/demo:");
  await p.click("#plDemo"); await p.evaluate(() => document.querySelectorAll("#gov-panel details").forEach((d) => d.open = true));
  await p.locator("#plC_" + cid).scrollIntoViewIfNeeded(); await p.fill("#plC_" + cid, "0"); await p.keyboard.press("Tab"); await p.click('#gov-panel [data-city="astana"]'); await p.waitForTimeout(300); await show("v3 tab+click:");
  await b.close();
})();
