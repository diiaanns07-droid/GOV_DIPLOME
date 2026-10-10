/* R07 round 13 — стык с оболочкой R01/картой R03 и истёкший кэш объяснения (Chromium/Playwright).
 *
 *   R07_RESTART_CMD="bash restart.sh" node tests/civic/R07/browser_r07_r13_shell.cjs http://127.0.0.1:8631
 *
 * 1) Без режима выбора клик по объекту открывает карточку R03; в режиме выбора — нет (нужен
 *    proposed_patches/r03_pause_map_input.patch + r01_scenarios_tool.patch; без них проверка FAIL — это ожидаемо).
 * 2) Пример из списка: места проходят ту же привязку, узлы = ожидания движка; расчёт.
 * 3) Истёкший кэш: R07_RESTART_CMD перезапускает сервер на той же временной БД (кэш R09 в памяти
 *    теряется); вопрос -> просьба пересчитать; после «Сравнить» объяснение снова есть.
 *    Без R07_RESTART_CMD шаг 3 — NOT_RUN.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");
const { chromium } = require(path.join(execSync("npm root -g").toString().trim(), "playwright"));

const ROOT = path.resolve(__dirname, "..", "..", "..");
const BASE = process.argv[2] || "http://127.0.0.1:8631";
const RESTART = process.env.R07_RESTART_CMD || null;
const CASE = JSON.parse(fs.readFileSync(path.join(ROOT, "engine/civic_scenarios/cases/astana-baiterek-khanshatyr-v1.case.json"), "utf8"));
const PANEL = ".civic-r07-panel";
const results = [];
const check = (name, ok, detail) => { results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail === undefined ? null : detail }); if (!ok) console.error("FAIL", name, detail || ""); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  async function clickMapAt(lon, lat, zoom) {
    const pt = await page.evaluate(([lo, la, z]) => {
      map.jumpTo({ center: [lo, la], zoom: z, pitch: 0, bearing: 0 });
      // свободная полоса между левой панелью R03 (до ~440 px) и панелью сценариев (от ~760 px)
      const p = map.project([lo, la]); map.panBy([p.x - 600, p.y - 560], { duration: 0 });
      const q = map.project([lo, la]); const r = map.getCanvas().getBoundingClientRect();
      return { x: r.left + q.x, y: r.top + q.y };
    }, [lon, lat, zoom]);
    await page.waitForTimeout(700);
    await page.mouse.click(pt.x, pt.y);
    await page.waitForTimeout(500);
  }
  try {
    await page.goto(BASE + "/");
    await page.waitForFunction(() => window.CivicShell && CivicShell.modules && CivicShell.modules.scenarios && typeof mapReady !== "undefined" && mapReady === true, null, { timeout: 40000 });
    // Объект, который карта R03 действительно рисует сейчас (фильтры по умолчанию могут скрывать часть записей).
    await page.waitForTimeout(2500);
    const obj = await page.evaluate(() => {
      const layers = (map.getStyle().layers || []).filter((l) => l.id.startsWith("civic-r03-") && l.type === "circle").map((l) => l.id);
      const f = map.queryRenderedFeatures({ layers: ["civic-r03-point"].filter((l) => layers.includes(l)) }).find((x) => x.geometry && x.geometry.type === "Point");
      return f ? { cid: f.properties.cid, c: f.geometry.coordinates } : null;
    });
    check("rendered R03 object found", !!obj, obj);

    // 1. Контроль: без режима выбора клик открывает карточку объекта.
    await page.waitForTimeout(1500);
    await clickMapAt(obj.c[0], obj.c[1], 15);
    const opened = await page.evaluate(() => CivicShell.selected);
    check("control: public map click opens the object (no tool)", typeof opened === "string" && opened.length > 0, opened);
    await page.evaluate(() => CivicShell.selectObject(null));
    await page.keyboard.press("Escape");

    await page.click("#civic-scenarios-button");
    await page.waitForFunction(() => /участков/.test(document.querySelector(".civic-r07-graphinfo")?.textContent || "") && !/Загружаем/.test(document.querySelector(".civic-r07-graphinfo").textContent), null, { timeout: 90000 });
    await page.evaluate(() => CivicShell.selectObject(null));
    await page.locator(PANEL + " .civic-r07-placeblock[data-role=origins] button", { hasText: "Указать на карте" }).click();
    await clickMapAt(obj.c[0], obj.c[1], 15);
    const during = await page.evaluate(() => CivicShell.selected);
    check("pick mode: same click does NOT open the object card", during === null || during === undefined, during);
    // Удачный клик сам завершает режим; Escape без режима закрыл бы панель (это поведение оболочки).
    if (await page.isVisible(PANEL + " .civic-r07-toolbar")) await page.keyboard.press("Escape");

    // 2. Пример из списка.
    await page.selectOption(PANEL + " select[aria-label='Пример']", CASE.case_id);
    await page.waitForTimeout(500);
    const placeText = await page.textContent(PANEL + " .civic-r07-places");
    check("example places go through the same snapping (shown distance)", /5,3 м/.test(placeText) && /88,2 м/.test(placeText), placeText.slice(0, 200));
    const wait = page.waitForResponse((r) => r.url().endsWith("/scenarios/compare"), { timeout: 60000 });
    await page.click(PANEL + " .civic-r07-primary");
    const res = (await (await wait).json()).data;
    check("example via UI = engine expected", res.baseline.routes[0].length_m === CASE.expected.baseline_length_m && res.input.origin_node_ids[0] === CASE.expected.snap.origin.node_id);
    await page.waitForSelector(PANEL + " .civic-r07-assistant .civic-r09");

    // 3. Истёкший/потерянный кэш сервера.
    if (!RESTART) { results.push({ name: "expired cache after server restart", status: "NOT_RUN", detail: "R07_RESTART_CMD не задан" }); throw new Error("skip-restart"); }
    execSync(RESTART, { stdio: "ignore", timeout: 60000 });
    const ask = async () => {
      const a = page.waitForResponse((r) => r.url().endsWith("/assistant"), { timeout: 30000 });
      await page.fill(PANEL + " .civic-r07-assistant .civic-r09 textarea", "Почему вариант B длиннее?");
      await page.locator(PANEL + " .civic-r07-assistant .civic-r09 button[type=submit]").click();
      return (await (await a).json()).data;
    };
    const lost = await ask();
    await page.waitForTimeout(300);
    const note = await page.textContent(PANEL + " .civic-r07-assistant");
    check("expired cache: unavailable + ask to recompute (no substitute case)", lost.source === "unavailable" && (lost.warnings || []).includes("scenario_not_found") && /Сервер не нашёл расчёт/.test(note), { source: lost.source, warnings: lost.warnings });
    const again = page.waitForResponse((r) => r.url().endsWith("/scenarios/compare"), { timeout: 60000 });
    await page.click(PANEL + " .civic-r07-primary");
    const res2 = (await (await again).json()).data;
    await page.waitForTimeout(300);
    const back = await ask();
    check("after recompute the explanation is available again", res2.result_digest === res.result_digest && back.source !== "unavailable", back.source);
    check("no page errors", errors.length === 0, errors);
  } catch (error) {
    if (!(error && error.message === "skip-restart")) check("run completed", false, String((error && error.stack) || error));
  } finally {
    await browser.close();
  }
  const failed = results.filter((r) => r.status === "FAIL");
  console.log(JSON.stringify({ base: BASE, passed: results.length - failed.length, failed: failed.length, results }, null, 1));
  process.exit(failed.length ? 1 : 0);
})();
