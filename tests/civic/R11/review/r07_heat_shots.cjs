/*
 * R11 · UX-разбор тепловой карты R07 (день 3). Стенд — devserver R07 из его ветки (только читается):
 *   (в worktree R07) python3 -m ui.civic_heat.devserver --port 8617 &
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r07_heat_shots.cjs http://127.0.0.1:8617 <папка>
 * Две страницы: demo.html (как поставлено) и demo-r11.html (та же + ui-kit/i18n R11, как в сборке R01;
 * копия кладётся в worktree R07 в scratchpad, в Git не попадает).
 */
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const { measure, brief, consoleCollector } = require("./measure.cjs");
const [BASE, OUT] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const SIZES = { 1366: { width: 1366, height: 768 }, 375: { width: 375, height: 812 } };

const SCENARIOS = [
  ["start", "?view=nura", null],
  ["card", "?view=nura", async (p) => { await p.click(".r07-item"); await p.waitForTimeout(1000); }],
  ["city", "?view=city", null],
  ["resident-card", "?view=nura&role=resident&sheet=full", async (p) => { await p.click(".r07-item"); await p.waitForTimeout(1000); }],
  ["fixed", "?view=nura", async (p) => {
    await p.evaluate(async () => {
      const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=15")).json();
      const it = d.items.find((x) => x.state === "fixed");
      if (it) window.__heat.focusTarget(it.target.kind, it.target.id);
    });
    await p.waitForTimeout(1200);
  }],
  ["pulse", "?view=nura", async (p) => { await p.click("#demo-new"); await p.waitForTimeout(450); }],
  ["cats-open", "?view=nura", async (p) => { await p.click("[data-cats-toggle]"); await p.waitForTimeout(500); }],
  ["filter-empty", "?view=nura", async (p) => {
    // редкое сочетание: категория «Другое» + 7 дней → ждём пустое состояние с подсказкой
    await p.click("[data-cats-toggle]"); await p.waitForTimeout(300);
    await p.click("[data-cat='other']"); await p.waitForTimeout(700);
    await p.click("[data-days='7']"); await p.waitForTimeout(1000);
  }],
];

(async () => {
  const browser = await chromium.launch();
  const report = {};
  for (const page of ["demo.html", "demo-r11.html"]) {
    for (const [name, query, act] of SCENARIOS) {
      for (const size of [1366, 375]) {
        for (const lang of ["ru", "kk"]) {
          if (page === "demo.html" && lang === "kk" && !["start", "card"].includes(name)) continue; // «как поставлено» — выборочно
          const p = await browser.newPage({ viewport: SIZES[size] });
          const logs = consoleCollector(p);
          await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
          const sheet = size === 375 && !query.includes("sheet=") ? "&sheet=half" : "";
          await p.goto(BASE + "/civic/heat/" + page + query + sheet + "&lang=" + lang, { waitUntil: "networkidle" });
          try { await p.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 }); } catch (e) { logs.push("не дождались ready"); }
          await p.waitForTimeout(900);
          if (act) { try { await act(p); } catch (e) { logs.push("действие: " + e.message.split("\n")[0]); } }
          await p.waitForTimeout(400);
          const tag = (page === "demo.html" ? "as" : "kit") + `-${name}-${size}-${lang}`;
          await p.screenshot({ path: path.join(OUT, `r07-${tag}.png`) });
          const m = await measure(p, null);
          report[tag] = { m, brief: brief(m), console: [...new Set(logs)].slice(0, 8), state: await p.evaluate(() => window.__heat && window.__heat.state && JSON.stringify(window.__heat.state()).slice(0, 300)) };
          await p.close();
        }
      }
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "r07-measure.json"), JSON.stringify(report, null, 1));
  for (const [k, v] of Object.entries(report)) console.log(k.padEnd(34), v.brief, v.console.length ? " | консоль: " + v.console.join(" ; ").slice(0, 300) : "");
})().catch((e) => { console.error(e); process.exit(1); });
