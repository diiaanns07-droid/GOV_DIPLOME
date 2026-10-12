/*
 * R11 · дизайн-марафон, п. 8 чек-листа: состояния «загрузка» и «нет связи» у каждого экрана.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/state_shots.cjs http://127.0.0.1:<порт>/ <папка>
 * Загрузка — ответ API раздела задержан на 20 с, кадр через 0,9 с; ошибка — запрос API раздела оборван (как без сети),
 * кадр через 3 с. Карта (панель «Карта жалоб») — то же для /api/civic/v2/heat с самого начала.
 * Кадры: <экран>-<режим>-<ширина>-<язык>-<loading|error>.png; в консоль — что видно (скелетон, текст, кнопка).
 */
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const [BASE = "http://127.0.0.1:8752/", OUT = "states"] = process.argv.slice(2);
const SCREENS = [
  ["map", "akimat", /\/api\/civic\/v2\/heat(\?|$)/],
  ["day", "akimat", /\/api\/civic\/v2\/akim\/summary/],
  ["inbox", "akimat", /\/api\/civic\/v2\/complaints\/inbox/],
  ["projects", "akimat", /\/api\/civic\/v2\/(proposals|staff\/ideas)/],
  ["nearby", "resident", /\/api\/civic\/v2\/nearby/],
  ["ideas", "resident", /\/api\/civic\/v2\/ideas/],
  ["questions", "resident", /\/api\/civic\/v2\/questions/],
];
const SIZES = [[1366, 768, "ru"], [375, 812, "kk"]];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  for (const [w, h, lang] of SIZES) for (const [screen, mode, api] of SCREENS) for (const kind of ["loading", "error"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    await ctx.addInitScript(([l, m]) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); } catch (e) {} }, [lang, mode]);
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    let armed = screen === "map";
    await p.route(api, async (r) => {
      if (!armed) return r.continue();
      if (kind === "error") return r.abort("internetdisconnected");
      await new Promise((res) => setTimeout(res, 20000));
      return r.continue().catch(() => {});
    });
    await p.goto(BASE, { waitUntil: "domcontentloaded" });
    if (screen === "map") {
      await p.waitForTimeout(kind === "loading" ? 2500 : 5000);
    } else {
      await p.waitForFunction(() => window.CivicShell?.mode === "civic" && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => {});
      await p.waitForTimeout(800);
      armed = true;
      await p.evaluate((s) => window.BirgeShell.setSection(s), screen);
      await p.waitForTimeout(kind === "loading" ? 900 : 3000);
    }
    await p.addStyleTag({ content: "#map-status { visibility: hidden !important; }" });
    const name = `${screen}-${mode}-${w}-${lang}-${kind}`;
    await p.screenshot({ path: path.join(OUT, name + ".png") });
    const seen = await p.evaluate((scr) => {
      const root = scr === "map" ? document.querySelector(".civic-panel") : document.querySelector("#birge-screen:not([hidden]), #birge-day:not([hidden])");
      if (!root) return "нет корня";
      const skel = root.querySelectorAll(".bk-skel").length, ill = root.querySelectorAll(".bk-ill, .ic--48").length;
      const btn = [...root.querySelectorAll("button")].filter((b) => b.offsetWidth && /повтор|қайта|обнов|retry/i.test(b.textContent)).length;
      const txt = (root.querySelector(".bk-error, .bk-empty, [role=alert], [role=status]") || {}).textContent || "";
      return `скелетон ${skel} · рисунок ${ill} · «Повторить» ${btn} · ${txt.trim().replace(/\s+/g, " ").slice(0, 90)}`;
    }, screen);
    console.log(`${name}: ${seen}`);
    await ctx.close();
  }
  await browser.close();
})();
