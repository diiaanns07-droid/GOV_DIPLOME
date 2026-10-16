/*
 * R11 · кадры сцен 7–9 для книги экранов (DESIGN_BOOK_R15 v1) на сборке R01 с демо-миром R02.
 *
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r15_scenes.cjs <BASE> <OUT> <файл-пароля> [--only kk] [--sizes 1366,375]
 *     BASE — сервер сборки (CIVIC_DEMO=1, CIVIC_DEMO_WORLD=1, сотрудник operator создан); пароль читается из файла, не печатается.
 *
 * Ничего не нажимает и не меняет демо-данные: открывает состояния сцен по адресам разделов (IA_ROUND15 §7.3) с id сцен из
 * GET /api/civic/v2/demo/scenes. Кадры: <OUT>/<сцена>-<шаг>-<ширина>-<язык>.jpg; ситуационный центр — 1920 × 1080.
 * Итог: <OUT>/scenes.json (что открыто, раздел и путь оболочки, ошибки JS) — подписи к кадрам для R14.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const [BASE, OUT, PWFILE] = process.argv.slice(2);
if (!BASE || !OUT || !PWFILE) { console.error("node r15_scenes.cjs <BASE> <OUT> <файл-пароля> [--only kk] [--sizes 1366,375]"); process.exit(2); }
const args = process.argv.slice(5);
const ONLY = args.includes("--only") ? args[args.indexOf("--only") + 1] : null;
const SIZES = (args.includes("--sizes") ? args[args.indexOf("--sizes") + 1] : "1366,375").split(",").map(Number);
const PASSWORD = fs.readFileSync(PWFILE, "utf8").trim();
fs.mkdirSync(OUT, { recursive: true });
const LANGS = ONLY ? [ONLY] : ["ru", "kk"];
const VIEW = { 1920: [1920, 1080, 1], 1366: [1366, 768, 1], 1024: [1024, 768, 1], 375: [375, 812, 2] };

// Шаги сцен: вид, адрес (#раздел/путь или страница), что ждать. id — из мира (sc).
const STEPS = (sc) => [
  ["s7", "1-yard", "resident", "#yard/" + sc.scene7.yard],
  ["s7", "2-initiative", "resident", "#together/" + sc.scene7.initiative],
  ["s7", "3-done", "resident", "#together/" + sc.scene7.initiative_done],
  ["s7", "4-staff-queue", "akimat", "#together"],
  ["s8", "1-board", "akimat", "#agencies"],
  ["s8", "2-complaint", "akimat", "#inbox/" + sc.scene8.complaint],
  ["s8", "3-handoffs", "akimat", "#agencies/handoffs"],
  ["s8", "4-calendar", "akimat", "#agencies/calendar"],
  ["s9", "1-day", "akimat", "#day"],
  ["s9", "2-hq", "akimat", "#agencies/crisis/" + sc.scene9.incident],
  ["s9", "3-public", "resident", "#crisis/" + sc.scene9.incident],
  ["s9", "4-chronicle", "resident", "?replay=7"],
  ["s9", "5-board", "akimat", "/civic/board/", 1920],
];

(async () => {
  // поле даты <input type=date> рисуется в формате языка системы, а не контекста: в облаке LANG пустой → 10/16/2026;
  // с ru_RU — 16.10.2026, как на ноутбуке акимата (для ҚАЗ формат тот же — дд.мм.гггг)
  const browser = await chromium.launch({ env: { ...process.env, LANG: "ru_RU.UTF-8", LC_ALL: "ru_RU.UTF-8" } });
  const probe = await browser.newPage();
  await probe.goto(BASE + "/");
  const scenes = await probe.evaluate(async () => (await fetch("/api/civic/v2/demo/scenes", { headers: { Accept: "application/json" } })).json());
  await probe.close();
  if (!scenes || !scenes.world || !scenes.scenes) { console.error("нет демо-мира (CIVIC_DEMO_WORLD=1)"); process.exit(1); }
  const sc = scenes.scenes;
  const report = { base: BASE, when: new Date().toISOString(), frames: [] };
  for (const [scene, step, mode, where, only] of STEPS(sc)) {
    for (const w of only ? [only] : SIZES) for (const lang of LANGS) {
      const [vw, vh, dpr] = VIEW[w];
      // язык браузера как у жителя (navigator.language, Intl); формат поля даты — от LANG процесса браузера (выше)
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, deviceScaleFactor: dpr, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
      await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); localStorage.setItem("birge.i18n.lang", l); } catch (e) { /* приватный режим */ } }, [mode, lang]);
      const page = await ctx.newPage();
      const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));
      if (mode === "akimat") {
        await page.goto(BASE + "/");
        await page.evaluate(async (pw) => { await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "operator", password: pw }) }); }, PASSWORD);
      }
      const url = where.startsWith("#") ? BASE + "/" + where : where.startsWith("?") ? BASE + "/" + where : BASE + where;
      await page.goto(url);
      await page.waitForTimeout(where.startsWith("/civic/board") ? 3500 : 2500);
      const file = `${scene}-${step}-${w}-${lang}.jpg`;
      await page.screenshot({ path: path.join(OUT, file), type: "jpeg", quality: 82 });
      const state = await page.evaluate(() => ({ section: window.BirgeShell ? BirgeShell.section : null, path: window.BirgeShell ? BirgeShell.path : null,
        // заголовок раздела оболочки (у экранов модулей он скрыт визуально, но это имя экрана); иначе — заголовок страницы
        title: (document.querySelector("#birge-screen:not([hidden]) #birge-screen-title") || document.querySelector("#birge-day:not([hidden]) #birge-day-title") || {}).textContent || document.title || "" }));
      report.frames.push({ file, scene, step, mode, where, width: w, lang, ...state, errors });
      console.log(`${file} · ${state.section || "—"}${state.path ? "/" + state.path : ""} · «${(state.title || "").trim().slice(0, 40)}»` + (errors.length ? ` · ошибки JS: ${errors.length}` : ""));
      await ctx.close();
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "scenes.json"), JSON.stringify(report, null, 1));
  const bad = report.frames.filter((f) => f.errors.length);
  console.log(`кадров ${report.frames.length}, с ошибками JS: ${bad.length}`);
  process.exit(bad.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
