/*
 * R11 · браузерная проверка витрины ui-kit (и любой страницы web/ по пути из аргумента).
 * Запуск (нужен Playwright с Chromium):
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/browser_check.cjs [--shots DIR] [--page /civic/ui-kit/index.html]
 * Проверяет на 375×812 и 1366×768, в ru и kk:
 *   - нет горизонтальной прокрутки страницы;
 *   - нет предупреждений [i18n] и ошибок в консоли;
 *   - на экране нет «сырых» ключей вида common.action.close;
 *   - видимые кнопки .bk-btn / .bk-mapbtn / .bk-iconbtn не ниже 48 px;
 *   - видимый основной текст не меньше 14 px (подписи), у .bk-btn ≥ 16 px.
 * Сервер статики свой (web/ как корень), без зависимостей; сеть наружу не нужна.
 */
"use strict";
const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "../../..");
const WEB = path.join(ROOT, "web");
const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : def;
};
const SHOTS = opt("--shots", null);
const PAGE = opt("--page", "/civic/ui-kit/index.html");
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2" };

function serve() {
  const server = http.createServer((req, res) => {
    const url = decodeURIComponent(req.url.split("?")[0]);
    const file = path.join(WEB, url);
    if (!file.startsWith(WEB) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404);
      return res.end("not found");
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

async function check(browser, base, width, height, lang) {
  const page = await browser.newPage({ viewport: { width, height } });
  const problems = [];
  page.on("console", (m) => {
    if (m.type() === "error" || /\[i18n\]/.test(m.text())) problems.push("консоль: " + m.text());
  });
  page.on("pageerror", (e) => problems.push("ошибка JS: " + e.message));
  await page.goto(base + PAGE + "?lang=" + lang, { waitUntil: "networkidle" });
  await page.waitForTimeout(300);
  const r = await page.evaluate(() => {
    const out = { keys: [], small: [], lowButtons: [], tinyText: [] };
    const doc = document.documentElement;
    out.scroll = doc.scrollWidth - window.innerWidth;
    out.lang = doc.lang;
    const visible = (el) => {
      const b = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return b.width > 0 && b.height > 0 && s.visibility !== "hidden" && s.display !== "none";
    };
    // Сырые ключи: текстовый узел целиком вида a.b.c (латиница, точки, подчёркивания)
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const txt = n.textContent.trim();
      if (/^[a-z0-9_]+(\.[a-z0-9_]+){1,}$/.test(txt) && !n.parentElement.closest("code")) out.keys.push(txt);
    }
    document.querySelectorAll("[placeholder],[aria-label],[title]").forEach((el) => {
      ["placeholder", "aria-label", "title"].forEach((a) => {
        const v = el.getAttribute(a);
        if (v && /^[a-z0-9_]+(\.[a-z0-9_]+){1,}$/.test(v)) out.keys.push(a + "=" + v);
      });
    });
    document.querySelectorAll(".bk-btn,.bk-mapbtn,.bk-iconbtn,.bk-option,.bk-list__item").forEach((el) => {
      if (!visible(el)) return;
      const h = el.getBoundingClientRect().height;
      if (h < 47.5) out.lowButtons.push((el.textContent.trim() || el.getAttribute("aria-label") || el.className) + " " + Math.round(h) + "px");
      if (el.classList.contains("bk-btn") && parseFloat(getComputedStyle(el).fontSize) < 16) out.small.push(el.textContent.trim());
    });
    document.querySelectorAll("body *").forEach((el) => {
      if (!visible(el) || el.closest("code,figcaption,svg")) return;
      const own = Array.from(el.childNodes).some((c) => c.nodeType === 3 && c.textContent.trim());
      if (own && parseFloat(getComputedStyle(el).fontSize) < 14) out.tinyText.push(el.className + ": " + el.textContent.trim().slice(0, 30));
    });
    return out;
  });
  if (r.scroll > 0) problems.push("горизонтальная прокрутка на " + r.scroll + " px");
  if (r.lang !== lang) problems.push("html lang=" + r.lang + ", ожидали " + lang);
  r.keys.forEach((k) => problems.push("ключ вместо текста: " + k));
  r.lowButtons.forEach((k) => problems.push("кнопка ниже 48 px: " + k));
  r.small.forEach((k) => problems.push("текст кнопки < 16 px: " + k));
  r.tinyText.forEach((k) => problems.push("текст < 14 px: " + k));
  if (SHOTS) {
    fs.mkdirSync(SHOTS, { recursive: true });
    const name = path.basename(PAGE, ".html").replace("index", "ui-kit") + `-${width}-${lang}`;
    await page.screenshot({ path: path.join(SHOTS, name + ".png"), fullPage: width > 400 ? false : false });
    await page.screenshot({ path: path.join(SHOTS, name + "-full.png"), fullPage: true });
  }
  await page.close();
  return problems;
}

(async () => {
  const server = await serve();
  const base = "http://127.0.0.1:" + server.address().port;
  const browser = await chromium.launch();
  let failed = 0;
  for (const [w, h] of [[375, 812], [1366, 768]]) {
    for (const lang of ["ru", "kk"]) {
      const problems = await check(browser, base, w, h, lang);
      const uniq = [...new Set(problems)];
      console.log((uniq.length ? "FAIL" : "PASS") + ` ${w}px ${lang}` + (uniq.length ? "\n  - " + uniq.join("\n  - ") : ""));
      if (uniq.length) failed++;
    }
  }
  await browser.close();
  server.close();
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
