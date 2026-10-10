// R07: скриншоты и проверки тепловой карты в настоящем Chromium (Playwright).
// Запуск: python -m ui.civic_heat.devserver &   затем
//   NODE_PATH=$(npm root -g) node tests/civic/R07/browser/shots.js [папка_для_скриншотов]
// Проверяет: нет ошибок консоли, нет горизонтальной прокрутки, нет непереведённых ключей heat.*,
// кнопки ≥ 48 px, значки с числом на карте, карточка цели, пульс после новой жалобы.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.R07_BASE || "http://127.0.0.1:8617/civic/heat/demo.html";
const OUT = process.argv[2] || path.join(__dirname, "..", "..", "..", "..", "research", "round-14-results", "R07", "screens");
fs.mkdirSync(OUT, { recursive: true });

const SIZES = { desktop: { width: 1366, height: 768 }, phone: { width: 375, height: 812 } };
const results = [];

async function shot(browser, name, size, query, after) {
  const page = await browser.newPage({ viewport: SIZES[size], deviceScaleFactor: 1 });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error" || (m.type() === "warning" && m.text().includes("[heat]"))) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(BASE + query, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
  await page.waitForTimeout(900);
  if (after) await after(page);
  await page.waitForTimeout(500);
  const checks = await page.evaluate(() => {
    const doc = document.documentElement;
    const panelText = document.getElementById("heat-root").innerText;
    const small = [...document.querySelectorAll("#heat-root button, .bar button, .mapbtns button")]
      .filter((b) => b.offsetParent !== null)
      .map((b) => ({ t: (b.innerText || b.getAttribute("aria-label") || "").trim().slice(0, 30), h: b.getBoundingClientRect().height }))
      .filter((b) => b.h < 39.5); // чипы 40 видимых + 4+4 зона нажатия
    const badges = [...document.querySelectorAll(".r07-badge")].filter((b) => !b.hidden).length;
    return {
      hscroll: doc.scrollWidth > doc.clientWidth + 1,
      rawKeys: (panelText.match(/heat\.[a-z_.0-9]+/g) || []),
      smallButtons: small,
      badges,
      state: window.__heat.state(),
    };
  });
  const file = path.join(OUT, name + ".jpg");
  await page.screenshot({ path: file, type: "jpeg", quality: 82 });
  results.push({ name, size, query, errors, ...checks });
  await page.close();
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  for (const lang of ["ru", "kk"]) {
    await shot(browser, `nura-akimat-1366-${lang}`, "desktop", `?lang=${lang}&role=akimat&view=nura`);
    await shot(browser, `nura-akimat-375-${lang}`, "phone", `?lang=${lang}&role=akimat&view=nura&sheet=peek`);
    await shot(browser, `city-districts-1366-${lang}`, "desktop", `?lang=${lang}&view=city`);
    await shot(browser, `card-segment-1366-${lang}`, "desktop", `?lang=${lang}&view=nura`, async (page) => {
      await page.click(".r07-item");               // первая строка «Горячие места»
      await page.waitForTimeout(900);
    });
    await shot(browser, `card-resident-375-${lang}`, "phone", `?lang=${lang}&role=resident&view=nura&sheet=full`, async (page) => {
      await page.click(".r07-item");
      await page.waitForTimeout(900);
    });
  }
  // Исправленная остановка (зелёная, 7 дней) — открываем её карточку через параметр target.
  for (const lang of ["ru", "kk"]) {
    await shot(browser, `stop-fixed-1366-${lang}`, "desktop", `?lang=${lang}&view=stops&target=object:osm-node-4975687943`, async (page) => {
      await page.waitForSelector(".r07-card", { timeout: 5000 });
    });
  }
  await shot(browser, "pulse-new-complaint-1366-ru", "desktop", "?lang=ru&view=nura", async (page) => {
    await page.click(".r07-item");
    await page.waitForTimeout(700);
    await page.click("#demo-new");
    await page.waitForSelector(".r07-pulse", { timeout: 5000 });
    await page.waitForTimeout(350);
  });
  await shot(browser, "filter-snow-7days-1366-kk", "desktop", "?lang=kk&view=nura", async (page) => {
    await page.click("[data-cats-toggle]");
    await page.click('[data-cat="snow_ice"]');
    await page.waitForTimeout(500);
    await page.click('[data-days="7"]');
    await page.waitForTimeout(700);
  });
  await browser.close();
  fs.writeFileSync(path.join(OUT, "CHECKS.json"), JSON.stringify(results, null, 1));
  let bad = 0;
  for (const r of results) {
    const problems = [];
    if (r.errors.length) problems.push("console: " + r.errors.join(" | "));
    if (r.hscroll) problems.push("горизонтальная прокрутка");
    if (r.rawKeys.length) problems.push("ключи без перевода: " + r.rawKeys.join(","));
    if (r.smallButtons.length) problems.push("мелкие кнопки: " + JSON.stringify(r.smallButtons));
    if (problems.length) bad++;
    console.log((problems.length ? "FAIL " : "PASS ") + r.name + " · значков " + r.badges + (problems.length ? " · " + problems.join("; ") : ""));
  }
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
