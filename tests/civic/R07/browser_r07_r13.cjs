/* R07 round 13 — браузерная приёмка пользовательского пути в собранном приложении (Chromium/Playwright).
 *
 *   node tests/civic/R07/browser_r07_r13.cjs http://127.0.0.1:8631 [--screenshots DIR] [--restart-cmd "..."]
 *
 * Нужен запущенный app.py (R01 shell + R07 + R09 с кэшем результатов на сервере). Сценарий:
 * места кликами по карте (без node ID) -> привязка с порогом и отказом -> участки A/B явным выбором ->
 * сравнение (длины = пример движка) -> объяснение R09 своего расчёта -> изменение входа -> устаревание ->
 * второй расчёт = второе объяснение -> отмена/поздний ответ -> нет пути != 0 -> Esc/destroy.
 * Ожидаемые числа берутся из engine/civic_scenarios/cases/astana-baiterek-khanshatyr-v1.case.json.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");
const { chromium } = require(path.join(execSync("npm root -g").toString().trim(), "playwright"));

const ROOT = path.resolve(__dirname, "..", "..", "..");
const BASE = process.argv[2] || "http://127.0.0.1:8631";
const shotArg = process.argv.indexOf("--screenshots");
const SHOTS = shotArg > 0 ? process.argv[shotArg + 1] : null;
const CASE = JSON.parse(fs.readFileSync(path.join(ROOT, "engine/civic_scenarios/cases/astana-baiterek-khanshatyr-v1.case.json"), "utf8"));
const EXP = CASE.expected;
const GRAPH = JSON.parse(fs.readFileSync(path.join(ROOT, "engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json"), "utf8"));
const EDGES = new Map(GRAPH.edges.map((e) => [e.id, e]));
const results = [];
const check = (name, ok, detail) => { results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail === undefined ? null : detail }); if (!ok) console.error("FAIL", name, detail || ""); };
const PANEL = ".civic-r07-panel";

function edgeMid(id) {   // вершина ломаной ближе всего к середине длины — точно лежит на линии
  const g = EDGES.get(id).geometry;
  if (g.length === 2) return [(g[0][0] + g[1][0]) / 2, (g[0][1] + g[1][1]) / 2];
  return g[Math.floor(g.length / 2)];
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = [], toolEvents = [], compareBodies = [], assistantBodies = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("request", (r) => {
    if (r.url().endsWith("/scenarios/compare") && r.method() === "POST") compareBodies.push(JSON.parse(r.postData()));
    if (r.url().endsWith("/assistant") && r.method() === "POST") assistantBodies.push(JSON.parse(r.postData()));
  });
  const lastCompare = () => page.waitForResponse((r) => r.url().endsWith("/scenarios/compare") && r.request().method() === "POST", { timeout: 60000 });
  const lastAnswer = () => page.waitForResponse((r) => r.url().endsWith("/assistant") && r.request().method() === "POST", { timeout: 30000 });

  async function clickMapAt(lon, lat, zoom) {
    // Точку ставим в свободную от панели часть экрана и щёлкаем НАСТОЯЩЕЙ мышью по канве карты.
    const pt = await page.evaluate(([lo, la, z]) => {
      map.jumpTo({ center: [lo, la], zoom: z, pitch: 0, bearing: 0 });
      const p = map.project([lo, la]);
      map.panBy([p.x - 340, p.y - 520], { duration: 0 });
      const q = map.project([lo, la]); const r = map.getCanvas().getBoundingClientRect();
      return { x: r.left + q.x, y: r.top + q.y };
    }, [lon, lat, zoom || 16]);
    await page.waitForTimeout(500);
    await page.mouse.click(pt.x, pt.y);
    await page.waitForTimeout(300);
  }
  const block = (title) => page.locator(PANEL + " .civic-r07-placeblock[data-role=" + (title === "Откуда" ? "origins" : "dests") + "]");

  try {
    await page.goto(BASE + "/");
    await page.waitForFunction(() => window.CivicShell && CivicShell.modules && CivicShell.modules.scenarios && typeof mapReady !== "undefined" && mapReady === true, null, { timeout: 40000 });
    await page.evaluate(() => document.addEventListener("civic-scenarios:tool", (e) => (window.__r07tool = (window.__r07tool || []).concat([e.detail.active]))));
    await page.click("#civic-scenarios-button");
    const t0 = Date.now();
    await page.waitForFunction(() => /участков/.test(document.querySelector(".civic-r07-graphinfo")?.textContent || "") && !/Загружаем/.test(document.querySelector(".civic-r07-graphinfo").textContent), null, { timeout: 90000 });
    check("city graph loaded in browser", true, (Date.now() - t0) + " ms (31 МБ JSON)");
    const notice = await page.textContent(PANEL + " .civic-r07-notice");
    check("hypothesis + snapshot + no travel time stated", /Гипотетический/.test(notice) && /снимок/.test(notice) && /время в пути/.test(notice) && /Фон карты/.test(notice));
    check("compare disabled before places", await page.locator(PANEL + " .civic-r07-primary").isDisabled());

    // 1. Места кликом по карте, без node ID.
    await block("Откуда").locator("button", { hasText: "Указать на карте" }).click();
    check("pick mode announced", (await page.isVisible(PANEL + " .civic-r07-toolbar")) && (await page.evaluate(() => (window.__r07tool || []).slice(-1)[0])) === true);
    await clickMapAt(...CASE.places.origin.input);
    const origin = await block("Откуда").innerText();
    check("origin snapped with distance and threshold shown", /Привязано к узлу сети в 5,3 м \(порог 150 м\)/.test(origin), origin);
    check("pick mode ends after a valid place", !(await page.isVisible(PANEL + " .civic-r07-toolbar")) && (await page.evaluate(() => window.__r07tool.slice(-1)[0])) === false);
    await block("Куда").locator("button", { hasText: "Указать на карте" }).click();
    await clickMapAt(...CASE.places.destination.input);
    const dest = await block("Куда").innerText();
    check("destination snapped (88 м) and nearer unverified line reported", /88,2 м/.test(dest) && /не подтверждён/.test(dest), dest);

    // Слишком далёкая точка: отказ, место не переносится; Esc выходит из режима, панель не закрывается.
    await block("Куда").locator("button", { hasText: "+ ещё" }).click();
    await clickMapAt(71.30, 51.30, 14);
    const refusal = await page.textContent(PANEL + " .civic-r07-toolbar");
    check("far click refused, not moved", /Рядом нет участка/.test(refusal) && /Точку не переносим/.test(refusal), refusal);
    check("refused click did not add a place", (await block("Куда").locator(".civic-r07-place").count()) === 1);
    await page.keyboard.press("Escape");
    check("Escape ends pick mode but keeps the drawer", !(await page.isVisible(PANEL + " .civic-r07-toolbar")) && !(await page.isHidden("#civic-scenarios")));

    // 2. Варианты: явный выбор участков (A — один участок, B — три).
    const pick = async (plan, ids) => {
      await page.locator(PANEL + " .civic-r07-tab", { hasText: "Вариант " + plan }).click();
      await page.locator(PANEL + " .civic-r07-plan button", { hasText: "Выбрать участки на карте" }).click();
      for (const id of ids) {
        await clickMapAt(...edgeMid(id), 17.5);
        if (await page.isVisible(PANEL + " .civic-r07-chooser")) {   // наложение линий — выбор из списка
          await page.locator(PANEL + " .civic-r07-chooser button", { hasText: "OSM way " + EDGES.get(id).osm_way_id }).first().click();
        }
      }
      await page.locator(PANEL + " .civic-r07-plan button", { hasText: "Готово" }).click();
    };
    const planA = CASE.payload.plans[0].closures[0].edge_ids, planB = CASE.payload.plans[1].closures[0].edge_ids;
    await pick("A", planA);
    await pick("B", planB);
    const tabs = await page.locator(PANEL + " .civic-r07-tab").allInnerTexts();
    check("segments selected explicitly", tabs[0].includes("участков: 1") && tabs[1].includes("участков: 3"), tabs.join(" | "));
    check("period and analysis moment shown", /действует/.test(await page.textContent(PANEL + " .civic-r07-plan")) && /закрыто участков/.test(await page.textContent(PANEL + " .civic-r07-hint >> nth=0").catch(() => "")) || /закрыто участков/.test(await page.textContent(PANEL)));

    // 3. Сравнение: числа = пример движка.
    let resp = lastCompare();
    await page.click(PANEL + " .civic-r07-primary");
    const r1 = (await (await resp).json()).data;
    const body1 = compareBodies[compareBodies.length - 1];
    check("UI payload uses snapped nodes, not raw coordinates", body1.origin_node_ids[0] === EXP.snap.origin.node_id && body1.destination_node_ids[0] === EXP.snap.destination.node_id && !("coordinates" in body1));
    const len = (p) => (p === "base" ? r1.baseline : r1.plans.find((x) => x.id === p)).routes[0].length_m;
    check("baseline/A/B lengths match engine example", len("base") === EXP.baseline_length_m && len("A") === EXP.plan_length_m.A && len("B") === EXP.plan_length_m.B, [len("base"), len("A"), len("B")]);
    await page.waitForSelector(PANEL + " .civic-r07-table tbody tr");
    const row = await page.textContent(PANEL + " .civic-r07-table tbody tr");
    check("table shows lengths and deltas in metres", /2\s?230,2 м/.test(row) && /\+60,4 м/.test(row) && /\+156,8 м/.test(row) && /\+96,4 м/.test(row), row);
    check("no travel time in result", !/мин\b|минут|км\/ч/.test(await page.textContent(PANEL + " .civic-r07-result")));

    // 4. Объяснение R09 именно этого расчёта.
    await page.waitForSelector(PANEL + " .civic-r07-assistant .civic-r09", { timeout: 10000 });
    const ask = async (q) => {
      const a = lastAnswer();
      await page.fill(PANEL + " .civic-r07-assistant .civic-r09 textarea, " + PANEL + " .civic-r07-assistant .civic-r09 input[type=text]", q);
      await page.locator(PANEL + " .civic-r07-assistant .civic-r09 button[type=submit]").click();
      return (await (await a).json()).data;
    };
    const ans1 = await ask("Почему вариант B длиннее варианта A?");
    const sid1 = assistantBodies[assistantBodies.length - 1].scenario_id;
    check("assistant asked about THIS result", sid1 === "result:" + r1.result_digest && Object.keys(assistantBodies.slice(-1)[0]).sort().join() === "object_id,question,scenario_id", sid1);
    check("assistant answer from server facts (not unavailable)", ans1.source !== "unavailable" && !(ans1.warnings || []).includes("scenario_not_found"), ans1.source);
    const text1 = (ans1.statements || []).map((s) => s.text).join(" ");
    check("explanation cites engine numbers", /2\s?387|2\s?290|156|96/.test(text1.replace(/ /g, " ")), text1.slice(0, 300));
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "r07_r13_result_assistant.png") });

    // 5. Изменение входа -> результат и объяснение устарели.
    await page.fill(PANEL + " input[aria-label='Момент анализа']", "2026-10-10T21:00");
    await page.dispatchEvent(PANEL + " input[aria-label='Момент анализа']", "change");
    check("stale banner after input change", await page.isVisible(PANEL + " .civic-r07-stale"));
    check("old explanation detached", (await page.locator(PANEL + " .civic-r07-assistant .civic-r09").count()) === 0 && /прежнему расчёту/.test(await page.textContent(PANEL + " .civic-r07-assistant")));
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "r07_r13_stale.png") });

    // 6. Второй расчёт -> другое объяснение.
    resp = lastCompare();
    await page.click(PANEL + " .civic-r07-primary");
    const r2 = (await (await resp).json()).data;
    check("second result differs (A inactive at 21:00)", r2.result_digest !== r1.result_digest && r2.plans[0].active_closed_edge_ids.length === 0 && r2.plans[0].routes[0].length_m === EXP.late.plan_length_m.A);
    check("stale banner cleared", !(await page.isVisible(PANEL + " .civic-r07-stale")));
    await page.waitForSelector(PANEL + " .civic-r07-assistant .civic-r09");
    const ans2 = await ask("Почему вариант B длиннее варианта A?");
    const sid2 = assistantBodies[assistantBodies.length - 1].scenario_id;
    const text2 = (ans2.statements || []).map((s) => s.text).join(" ");
    check("two calculations -> two explanations", sid2 === "result:" + r2.result_digest && sid2 !== sid1 && text2 !== text1, { sid1, sid2 });

    // 7. Отмена и поздний ответ.
    await page.route("**/scenarios/compare", async (route) => { await new Promise((r) => setTimeout(r, 2500)); await route.continue().catch(() => {}); });
    await page.fill(PANEL + " input[aria-label='Момент анализа']", "2026-10-10T13:00");
    await page.dispatchEvent(PANEL + " input[aria-label='Момент анализа']", "change");
    await page.click(PANEL + " .civic-r07-primary");
    await page.waitForSelector(PANEL + " button:has-text('Отменить расчёт')");
    await page.click(PANEL + " button:has-text('Отменить расчёт')");
    await page.waitForTimeout(3500);
    check("cancelled request never rendered", (await page.textContent(PANEL + " .civic-r07-result")).includes(r2.result_digest.slice(0, 8)) && await page.isVisible(PANEL + " .civic-r07-stale"));
    await page.click(PANEL + " .civic-r07-primary");
    await page.waitForTimeout(400);
    await page.fill(PANEL + " input[aria-label='Момент анализа']", "2026-10-10T14:00");
    await page.dispatchEvent(PANEL + " input[aria-label='Момент анализа']", "change");
    await page.waitForTimeout(3500);
    const runInfo = await page.textContent(PANEL + " .civic-r07-hint[role=status]");
    check("input change during pending cancels; late answer not drawn", /Вход изменён во время расчёта/.test(runInfo) && (await page.textContent(PANEL + " .civic-r07-result")).includes(r2.result_digest.slice(0, 8)), runInfo);
    await page.unroute("**/scenarios/compare");

    // 8. Нет пути != 0: цель во фрагменте сети у вокзала.
    await block("Куда").locator("button", { hasText: "Указать заново" }).click();
    await clickMapAt(71.5330, 51.1105, 16);
    const frag = await block("Куда").innerText();
    check("fragment warning shown", /фрагменте сети из \d+ участков/.test(frag), frag);
    resp = lastCompare();
    await page.click(PANEL + " .civic-r07-primary");
    const r3 = (await (await resp).json()).data;
    const b3 = r3.baseline.routes[0];
    const row3 = await page.textContent(PANEL + " .civic-r07-table tbody tr");
    check("no route shown as 'нет пути', length null not 0", b3.length_m === null && /нет пути в модели|доступ не подтверждён/.test(row3) && !/\b0 м\b/.test(row3), row3);
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "r07_r13_no_route.png") });

    // 9. Мобильная ширина и destroy.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(400);
    const overflow = await page.evaluate(() => { const p = document.querySelector(".civic-r07-panel"); return p.scrollWidth - p.clientWidth; });
    check("panel fits mobile width", overflow <= 1, overflow);
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.locator(PANEL + " .civic-r07-tab", { hasText: "Вариант A" }).click();
    await page.locator(PANEL + " .civic-r07-plan button", { hasText: "Выбрать участки на карте" }).click();
    await page.click("#civic-scenarios [data-close=scenarios]");
    const after = await page.evaluate(() => ({ layers: (map.getStyle().layers || []).filter((l) => l.id.startsWith("civic-r07-")).length,
      sources: Object.keys(map.getStyle().sources || {}).filter((s) => s.startsWith("civic-r07-")).length, cursor: map.getCanvas().style.cursor, lastTool: (window.__r07tool || []).slice(-1)[0] }));
    check("destroy removes layers/sources, resets cursor, ends tool", after.layers === 0 && after.sources === 0 && after.cursor === "" && after.lastTool === false, after);
    check("no page errors", errors.length === 0, errors);
  } catch (error) {
    check("run completed", false, String((error && error.stack) || error));
  } finally {
    await browser.close();
  }
  const failed = results.filter((r) => r.status !== "PASS");
  console.log(JSON.stringify({ base: BASE, passed: results.length - failed.length, failed: failed.length, results }, null, 1));
  process.exit(failed.length ? 1 : 0);
})();
