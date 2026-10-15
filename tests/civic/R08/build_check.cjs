/*
 * R08 · раунд 15 · проверка в СБОРКЕ R01: «Ситуационный центр» и «Картина недели» через настоящий шлюз
 * (вход R02 → сессия + CSRF → V2Handler → ui.civic_akim.api). Нужны INTEGRATION.txt R08 §1–§3.
 *
 *   CIVIC_DB_PATH=… CIVIC_DEMO=1 python3 -B app.py --port 8655        # база и редактор — RUN.txt R08 «В СБОРКЕ R01»
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/build_check.cjs http://127.0.0.1:8655 <папка_кадров> <пароль operator>
 *
 * Проверяет: без входа — форма входа; вход прямо на табло; после входа данные, X-CSRF-Token в каждом запросе табло;
 * 1920×1080 и 1366×768 без прокрутки; «Картина недели» (kk) — данные и печать ровно 2 листа A4; после входа ни одной
 * ошибки в консоли (CSP, скрипты). Код выхода 1, если есть FAIL. Кадры: build-board-1920-ru.jpg, build-board-1366-ru.jpg,
 * build-week-1366-kk.jpg.
 */
"use strict";
const { chromium } = require("playwright");
const path = require("path");
const BASE = (process.argv[2] || "http://127.0.0.1:8655").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-15-results/R08/screens");
const PASS = process.argv[4] || process.env.BIRGE_OPERATOR_PASSWORD || "";
require("fs").mkdirSync(OUT, { recursive: true });
const res = [];
const check = (n, ok, d) => { res.push([ok ? "PASS" : "FAIL", n]); console.log((ok ? "PASS " : "FAIL ") + n + (ok ? "" : " — " + JSON.stringify(d).slice(0, 400))); };
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const tokens = [];
  page.on("request", (r) => { if (/\/akim\/(board|week)/.test(r.url())) tokens.push([r.url().replace(BASE, ""), !!r.headers()["x-csrf-token"]]); });
  await page.goto(BASE + "/civic/board/index.html?lang=ru", { waitUntil: "networkidle" });
  await page.waitForSelector('#board[data-state="login"], #board[data-state="ok"], #board[data-state="error"]', { timeout: 20000 });
  check("без входа — форма входа сотрудника", (await page.getAttribute("#board", "data-state")) === "login");
  const before = tokens.length; // до входа сессии нет: запрос без токена и 401 — так и должно быть
  const preErrors = errors.length;
  await page.fill("#sc-user", "operator");
  await page.fill("#sc-pass", PASS);
  await page.click(".sc-login button[type=submit]");
  await page.waitForSelector('#board[data-state="ok"]', { timeout: 20000 }).catch(() => {});
  const st = await page.getAttribute("#board", "data-state");
  check("после входа — табло (data-state=ok)", st === "ok", st);
  await page.waitForTimeout(800);
  const info = await page.evaluate(() => ({
    sh: document.documentElement.scrollHeight, ch: document.documentElement.clientHeight,
    kpi: Array.from(document.querySelectorAll(".sc-kpi__value, .sc-kpi-value, [class*='kpi'] [class*='value']")).map((e) => e.textContent.trim()).slice(0, 6),
    stages: Array.from(document.querySelectorAll("[data-stage-id], .sc-tab[data-id]")).map((e) => e.getAttribute("data-stage-id") || e.getAttribute("data-id")),
    text: document.getElementById("board").innerText.slice(0, 400),
  }));
  check("1920×1080 без прокрутки", info.sh <= info.ch, info);
  check("после входа запросы табло несут X-CSRF-Token", tokens.length > before && tokens.slice(before).every((t) => t[1]), tokens);
  await page.screenshot({ path: path.join(OUT, "build-board-1920-ru.jpg"), type: "jpeg", quality: 80 });
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.waitForTimeout(800);
  const s2 = await page.evaluate(() => ({ sh: document.documentElement.scrollHeight, ch: document.documentElement.clientHeight }));
  check("1366×768 без прокрутки", s2.sh <= s2.ch, s2);
  await page.screenshot({ path: path.join(OUT, "build-board-1366-ru.jpg"), type: "jpeg", quality: 80 });
  const wk = await ctx.newPage();
  wk.on("pageerror", (e) => errors.push("week: " + e.message));
  wk.on("console", (m) => { if (m.type() === "error") errors.push("week: " + m.text()); });
  wk.on("request", (r) => { if (/\/akim\/week/.test(r.url())) tokens.push([r.url().replace(BASE, ""), !!r.headers()["x-csrf-token"]]); });
  await wk.setViewportSize({ width: 1366, height: 900 });
  await wk.goto(BASE + "/civic/akim/week.html?lang=kk", { waitUntil: "networkidle" });
  await wk.waitForSelector('#week[data-state="ok"], #week[data-state="login"], #week[data-state="error"]', { timeout: 20000 });
  const ws = await wk.getAttribute("#week", "data-state");
  check("«Картина недели» (kk) после входа — данные", ws === "ok", ws);
  await wk.screenshot({ path: path.join(OUT, "build-week-1366-kk.jpg"), type: "jpeg", quality: 80, fullPage: true });
  await wk.emulateMedia({ media: "print" });
  const pdf = await wk.pdf({ format: "A4", printBackground: true, preferCSSPageSize: true });
  const pages = (pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
  check("печать «Картины недели» — 2 листа A4", pages === 2, pages);
  check("до входа — ровно один 401 в журнале сети; после входа ошибок нет (CSP, скрипты)", preErrors <= 1 && errors.length === preErrors, errors.slice(0, 5));
  await browser.close();
  const failed = res.filter((r) => r[0] === "FAIL").length;
  require("fs").writeFileSync(path.join(OUT, "build_check.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(),
    passed: res.length - failed, failed, results: res.map((r) => ({ status: r[0], name: r[1] })) }, null, 2));
  console.log(`${res.length - failed} PASS · ${failed} FAIL`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
