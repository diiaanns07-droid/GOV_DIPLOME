// R16 · быстрый осмотр экранов на стенде: ошибки консоли, «Мой двор», «Сделаем вместе», карточка дела.
// NODE_PATH=$(npm root -g) node tests/civic/R16/browser/r16_smoke.cjs http://127.0.0.1:8655 <папка кадров>
const { chromium } = require("playwright");
const base = process.argv[2] || "http://127.0.0.1:8655";
const out = process.argv[3] || "research/round-15-results/R16/screens";
(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  await page.addInitScript(() => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", "ru"); } catch (e) {} });
  await page.goto(base + "/#yard", { waitUntil: "load" });
  await page.waitForSelector(".tg", { timeout: 15000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: out + "/smoke_yard_picker_1366_ru.png" });
  const rows = await page.$$(".tg-yardrow");
  console.log("yard rows", rows.length);
  if (rows.length) { await rows[0].click(); await page.waitForSelector(".tg-yardhead", { timeout: 10000 }); await page.waitForTimeout(600); }
  await page.screenshot({ path: out + "/smoke_yard_page_1366_ru.png" });
  console.log("kpis", await page.$$eval(".tg-kpi .bk-kpi__value", (n) => n.map((x) => x.textContent)));
  await page.goto(base + "/#together", { waitUntil: "load" });
  await page.waitForSelector(".tg-card", { timeout: 15000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: out + "/smoke_list_1366_ru.png" });
  console.log("cards", (await page.$$(".tg-card")).length);
  console.log("errors", JSON.stringify(errors.slice(0, 10), null, 1));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
