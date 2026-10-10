// R06 раунд 14 · R10 B-006: страница и карточки R06, если не загрузились ui-kit.js и/или i18n.js; медленная сеть.
//
//   python3 tests/civic/R06/round14/serve_r14.py --port 8616 --kit-dir <R11> > stand.json &
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/browser_nokit.cjs stand.json [папка-скриншотов]
//
// Браузер (Playwright) отвечает 404 на ui-kit.js (и i18n.js) — как стенд без --kit-dir. Ожидается: нет ошибок
// JavaScript, ни одного пустого блока (UX_BRIEF, правило 7): понятное сообщение ru/kk и кнопка «Обновить»;
// карточки R06 без ui-kit (словарь есть) показывают состояние простым текстом, а не пустоту.
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const stand = JSON.parse(fs.readFileSync(process.argv[2], "utf8").trim().split("\n")[0]);
const shots = process.argv[3] || null;
const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
};

async function open(browser, width, block) {
  const page = await browser.newPage({ viewport: { width, height: width < 600 ? 812 : 768 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.route(/\/civic\/(ui-kit\/ui-kit\.js|i18n\/i18n\.js)$/, (route) => {
    const url = route.request().url();
    if (block.some((b) => url.endsWith(b))) return route.fulfill({ status: 404, body: "not found" });
    return route.continue();
  });
  await page.goto(stand.url, { waitUntil: "load" });
  await page.waitForTimeout(800);
  return { page, errors };
}

(async () => {
  const browser = await chromium.launch();
  for (const width of [375, 1366]) {
    // 1. Нет ни ui-kit, ни словаря — как стенд без --kit-dir (B-006).
    const a = await open(browser, width, ["ui-kit.js", "i18n.js"]);
    const m = await a.page.evaluate(() => ({
      blocks: ["proposals", "objects"].map((id) => {
        const box = document.getElementById(id);
        const alert = box.querySelector("[role=alert]");
        const btn = box.querySelector("button");
        return { text: alert ? alert.textContent : "", btn: btn ? btn.textContent : "", h: btn ? btn.getBoundingClientRect().height : 0 };
      }),
      h1: document.querySelector("h1").textContent,
      scroll: document.documentElement.scrollWidth - window.innerWidth,
    }));
    check(width + ": без ui-kit и словаря — нет ошибок JavaScript", a.errors.length === 0, a.errors.join(" | "));
    check(width + ": оба блока — сообщение ru/kk и «Обновить» (≥ 48 px)",
          m.blocks.every((b) => /Обновите страницу/.test(b.text) && /Бетті жаңартыңыз/.test(b.text) && /Обновить/.test(b.btn) && b.h >= 48),
          JSON.stringify(m.blocks));
    check(width + ": заголовок страницы не пустой", m.h1.trim().length > 0, m.h1);
    check(width + ": нет горизонтальной прокрутки", m.scroll <= 0, String(m.scroll));
    if (shots) await a.page.screenshot({ path: path.join(shots, "r06-" + width + "-nokit.png"), fullPage: true });
    await a.page.close();

    // 2. Словарь есть, ui-kit нет: карточки R06 рисуют состояние простым текстом.
    const b = await open(browser, width, ["ui-kit.js"]);
    const n = await b.page.evaluate(async () => {
      const box = document.createElement("div");
      document.body.appendChild(box);
      await window.BirgeProposals.mountObject(box, "no-such-object");
      const errBox = document.createElement("div");
      document.body.appendChild(errBox);
      let retried = 0;
      window.BirgeProposals.stateBox(errBox, "error", { action: { onClick: () => { retried += 1; } } });
      errBox.querySelector("button").click();
      return { notFound: box.textContent, error: errBox.textContent, retried, pageAlert: document.querySelector("#proposals [role=alert]") ? 1 : 0 };
    });
    check(width + ": без ui-kit — нет ошибок JavaScript", b.errors.length === 0, b.errors.join(" | "));
    check(width + ": без ui-kit — страница говорит, что интерфейс не загрузился", n.pageAlert === 1);
    check(width + ": карточка объекта без ui-kit — «не найден» текстом", /не найден/.test(n.notFound), n.notFound);
    check(width + ": ошибка без ui-kit — текст и рабочая «Повторить»", /Не получилось загрузить/.test(n.error) && /Повторить/.test(n.error) && n.retried === 1,
          n.error + " retried=" + n.retried);
    await b.page.close();

    // 3. Медленная сеть (ui-kit на месте): пока API отвечает, в блоках видна загрузка, а не пустота (UX_BRIEF, правило 7).
    const c = await browser.newPage({ viewport: { width, height: width < 600 ? 812 : 768 } });
    const cErrors = [];
    c.on("pageerror", (e) => cErrors.push(String(e)));
    await c.route(/\/api\/civic\/v2\/(proposals|objects)(\?|$)/, async (route) => { await new Promise((r) => setTimeout(r, 1500)); return route.continue(); });
    await c.goto(stand.url, { waitUntil: "domcontentloaded" });
    await c.waitForTimeout(500);
    const loading = await c.evaluate(() => ["proposals", "objects"].map((id) => {
      const box = document.getElementById(id);
      const st = box.querySelector("[role=status], [aria-busy=true], .bk-skeleton");
      return st ? (st.textContent || "").trim() || "skeleton" : "";
    }));
    check(width + ": медленная сеть — в обоих блоках загрузка", loading.every(Boolean), JSON.stringify(loading));
    await c.waitForSelector(".r06-card[data-proposal]", { timeout: 10000 });
    check(width + ": медленная сеть — после ответа карточки на месте, без ошибок", cErrors.length === 0, cErrors.join(" | "));
    await c.close();
  }

  // 4. Лимит голосов с адреса (R15 S08): сервер отвечает 429 — понятный текст ru/kk, без «Повторить», без [i18n].
  for (const lang of ["ru", "kk"]) {
    const d = await browser.newPage({ viewport: { width: 375, height: 812 } });
    const warns = [];
    d.on("console", (m) => { if (/\[i18n\]/.test(m.text())) warns.push(m.text()); });
    await d.route(/\/api\/civic\/v2\/proposals\/[^/]+\/vote$/, (route) => route.fulfill({
      status: 429, headers: { "Content-Type": "application/json", "Retry-After": "86000" },
      body: JSON.stringify({ ok: false, error: { code: "rate_limited", message: "С этого адреса уже много голосов за этот проект. Повторите завтра." } }),
    }));
    await d.goto(stand.url + "?lang=" + lang, { waitUntil: "load" });
    await d.waitForSelector(".r06-vote__btn:not([disabled])");
    await d.click(".r06-vote__btn:not([disabled])");
    await d.waitForTimeout(700);
    const toast = await d.evaluate(() => {
      const el = document.querySelector(".bk-toast");
      return el ? { text: (el.querySelector(".bk-toast__text") || el).textContent.trim(), retry: !!el.querySelector(".bk-btn") } : null;
    });
    const want = lang === "kk" ? /дауыс көп берілді/ : /много голосов/;
    check("лимит голосов " + lang + ": понятный текст без «Повторить», без [i18n]", toast && want.test(toast.text) && !toast.retry && warns.length === 0,
          JSON.stringify({ toast, warns }));
    await d.close();
  }
  await browser.close();
  const failed = results.filter((r) => !r.ok).length;
  console.log(JSON.stringify({ total: results.length, failed }));
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
