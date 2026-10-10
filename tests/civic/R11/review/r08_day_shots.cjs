/*
 * R11 · UX-разбор «Картины дня» R08 (день 3). Стенд — demo_server.py R08 из его ветки (только читается):
 *   (в worktree R08, с ui/civic_heat из ветки R07) python3 tests/civic/R08/demo_server.py --port 8508 &
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r08_day_shots.cjs http://127.0.0.1:8508 <папка> <метка: as|kit>
 */
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const { measure, brief, consoleCollector } = require("./measure.cjs");
const [BASE, OUT, TAG] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const API = "**/api/civic/v2/akim/summary**";

const SCENARIOS = [
  ["today", "", null, null],
  ["nura", "district=nura", null, null],
  ["pastday", "date=2026-10-09", null, null],
  ["network", "", (r) => r.abort("internetdisconnected"), null],
  ["hot-click", "", null, async (p) => { await p.click(".akim-hot__item"); await p.waitForTimeout(800); }],
];

(async () => {
  const browser = await chromium.launch();
  const report = {};
  for (const [name, query, route, act] of SCENARIOS) {
    for (const size of [1366, 375]) {
      for (const lang of ["ru", "kk"]) {
        if (["network", "hot-click", "pastday"].includes(name) && lang === "kk" && size === 375) continue;
        const ctx = await browser.newContext({ viewport: size === 1366 ? { width: 1366, height: 768 } : { width: 375, height: 812 } });
        const p = await ctx.newPage();
        const logs = consoleCollector(p);
        if (route) await p.route(API, route);
        await p.goto(BASE + "/civic/akim/?lang=" + lang + (query ? "&" + query : ""));
        try { await p.waitForSelector("#akim:not([data-state=loading])", { timeout: 15000 }); } catch (e) { logs.push("не дождались загрузки"); }
        await p.waitForTimeout(700);
        let url = null;
        if (act) { try { await act(p); url = p.url(); } catch (e) { logs.push("действие: " + e.message.split("\n")[0]); } }
        const tag = `${TAG}-${name}-${size}-${lang}`;
        await p.screenshot({ path: path.join(OUT, `r08-${tag}.png`), fullPage: !act });
        // замер — по всей странице: прокрутим и посмотрим весь DOM (measure берёт только видимое в окне)
        await p.setViewportSize({ width: size === 1366 ? 1366 : 375, height: Math.min(6000, await p.evaluate(() => document.documentElement.scrollHeight)) });
        const m = await measure(p, null);
        report[tag] = { m, brief: brief(m), console: [...new Set(logs)].slice(0, 6), state: await p.evaluate(() => document.querySelector("#akim") && document.querySelector("#akim").dataset.state), url };
        await ctx.close();
      }
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, `r08-${TAG}-measure.json`), JSON.stringify(report, null, 1));
  for (const [k, v] of Object.entries(report)) console.log(k.padEnd(28), "[" + v.state + "]", v.brief, v.url ? " → " + v.url.replace(BASE, "") : "", v.console.length ? " | консоль: " + v.console.join(" ; ").slice(0, 300) : "");
})().catch((e) => { console.error(e); process.exit(1); });
