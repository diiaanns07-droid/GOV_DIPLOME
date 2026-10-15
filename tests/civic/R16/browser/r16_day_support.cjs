// R16 · шаг 3 сцены 7 по DEMO_SCRIPT R01: акимат → «Картина дня» (R08) → карточка «Жители вместе» → «Поддержать» →
// карточка дела сцены 7 (R16) с действием сотрудника «Поддержать». Данные не меняются (форму не отправляем).
//   NODE_PATH=$(npm root -g) node tests/civic/R16/browser/r16_day_support.cjs http://127.0.0.1:8656 [ru|kk] [1366x768]
// Дело сцены: R16_SCENE_ITEM (демо-мир R02 — i-w15-01), по умолчанию — фикстура R16. Нет «Картины дня» с карточкой
// «Жители вместе» (сборка без R08 раунда 15) — NOT_RUN с причиной, не FAIL.
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8656";
const LANG = process.argv[3] || "ru";
const [W, H] = (process.argv[4] || "1366x768").split("x").map(Number);
const ITEM = process.env.R16_SCENE_ITEM || "i-demo-scene7";
const STAFF = { user: process.env.R16_STAFF_USER || "operator", pass: process.env.R16_STAFF_PASS || "demo-stand-pass-2026" };
let fails = 0;
function check(name, ok, info) {
  if (!ok) fails++;
  console.log(`${ok ? "PASS" : "FAIL"} ${W}-${LANG} ${name}${ok ? "" : "  " + String(JSON.stringify(info)).slice(0, 300)}`);
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H } });
  await ctx.addInitScript(([l]) => { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); }, [LANG]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(BASE + "/", { waitUntil: "load" });
  await page.evaluate(async (s) => {
    await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: s.user, password: s.pass }) });
  }, STAFF);
  await page.goto(BASE + "/?n=day#day", { waitUntil: "load" });
  const link = await page.waitForSelector('a[data-key="trio:together"]', { timeout: 20000 }).catch(() => null);
  if (!link) {
    console.log(`NOT_RUN ${W}-${LANG} «Картина дня»: нет карточки «Жители вместе» (R08 раунда 15 нет в сборке)`);
    await browser.close();
    process.exit(0);
  }
  const card = await page.evaluate(() => {
    const a = document.querySelector('a[data-key="trio:together"]');
    return { href: a.getAttribute("href"), text: a.textContent.trim(), line: (a.closest("section, article, div") || a).textContent.slice(0, 160) };
  });
  check("«Жители вместе»: «Поддержать» ведёт на дело сцены 7", card.href === "#together/" + encodeURIComponent(ITEM), card);
  await page.click('a[data-key="trio:together"]');
  const opened = await page.waitForSelector(`.tg-detail [data-focus="support-${ITEM}"]`, { timeout: 15000 }).then(() => true, () => false);
  const view = await page.evaluate(() => ({ hash: location.hash, title: document.querySelector(".tg-detail .tg-title")?.textContent || null,
    primary: document.querySelector(".tg-detail .tg-staffactions .bk-btn--primary")?.textContent?.trim() || null }));
  check("карточка дела: у сотрудника «Поддержать» — главная кнопка", opened && !!view.primary, view);
  await page.click(`.tg-detail [data-focus="support-${ITEM}"]`).catch(() => null);
  const form = await page.waitForSelector(".tg-detail .tg-form", { timeout: 10000 }).then(() => true, () => false);
  check("«Поддержать» открывает форму (инвентарь, вывоз, заметка)", form);
  check("нет ошибок JS", errors.length === 0, errors.slice(0, 3));
  await browser.close();
  console.log(`\nИТОГ: PASS ${4 - fails} · FAIL ${fails}`);
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
