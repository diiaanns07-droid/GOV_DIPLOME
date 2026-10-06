// K07 r10: повторная проверка D1/D2 (найдены r9 на доноре d18847f) на ОСНОВНОЙ странице (корневой web/, app.py :8501).
// Usage: NODE_PATH=$(npm root -g) node k07r10_d1d2.cjs --url http://127.0.0.1:8501/ [--out DIR]
// D1: ввод бюджета и клик человека (удержание ~100 мс) по «Найти точные оптимумы» — поиск должен стартовать с первой попытки.
// D2: ввод неверной стоимости и сразу касание другого города (390 px, touch) — сообщение должно относиться к смене города.
"use strict";
const { chromium } = require("playwright");
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const URL = arg("--url", "http://127.0.0.1:8501/");
const results = []; const check = (id, ok, info) => { results.push({ id, ok: !!ok, info }); console.log(`${ok ? "PASS" : "FAIL"} ${id} ${info ? JSON.stringify(info).slice(0, 220) : ""}`); };
async function open(b, opts) {
  const pg = await b.newPage(opts); const errs = [];
  pg.on("pageerror", (e) => errs.push(String(e)));
  await pg.goto(URL, { waitUntil: "load" }); await pg.waitForTimeout(800);
  await pg.click("#govtech-toggle"); await pg.waitForTimeout(400);
  return { pg, errs };
}
(async () => {
  const b = await chromium.launch();
  // ---------- D1 ----------
  for (const hold of [0, 100]) {
    const { pg, errs } = await open(b, { viewport: { width: 1440, height: 900 } });
    await pg.evaluate(() => window.GOVTECH.setPage("plan"));
    await pg.click("#plDemo"); await pg.waitForTimeout(200);
    await pg.fill("#plBudget", "660");  // без Tab/Enter
    await pg.evaluate(() => document.getElementById("plRun").scrollIntoView({ block: "center" }));  // r10: кнопка ниже экрана
    await pg.waitForTimeout(100);
    const box = await (await pg.$("#plRun")).boundingBox();
    const hit = await pg.evaluate(([x, y]) => document.elementFromPoint(x, y)?.id || null, [box.x + box.width / 2, box.y + box.height / 2]);
    if (hit !== "plRun") { check(`D1_hold${hold}ms`, false, { error: "plRun не под курсором", hit }); await pg.close(); continue; }
    await pg.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await pg.mouse.down(); await pg.waitForTimeout(hold); await pg.mouse.up();
    await pg.waitForTimeout(600);
    const s = await pg.evaluate(() => ({ budget: CITY_PLAN_UI.state.budget, status: CITY_PLAN_UI.opt.status, msg: document.getElementById("plMsg")?.textContent }));
    check(`D1_hold${hold}ms`, s.budget === 660 && ["running", "done"].includes(s.status), { ...s, errs });
    await pg.close();
  }
  // ---------- D2 ----------
  {
    const { pg, errs } = await open(b, { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    await pg.evaluate(() => window.GOVTECH.setPage("plan"));
    await pg.tap("#plDemo"); await pg.waitForTimeout(200);
    await pg.evaluate(() => { const d = document.getElementById("plSecCands"); if (d && !d.open) d.querySelector("summary").click(); });
    await pg.waitForTimeout(100);
    await pg.fill("#plC_K1", "0");
    await pg.tap('#gov-panel [data-city="astana"]'); await pg.waitForTimeout(400);
    const s = await pg.evaluate(() => ({ city: CITY_APP.state.city, msg: document.getElementById("plMsg")?.textContent, pts: CITY_PLAN_UI.state.points.length }));
    check("D2_city_message", s.city === "astana" && /Город изменён/.test(s.msg || "") && s.pts === 0, { ...s, errs });
    await pg.close();
  }
  await b.close();
  const out = arg("--out", null);
  if (out) require("fs").writeFileSync(out, JSON.stringify({ url: URL, results }, null, 1));
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})();
