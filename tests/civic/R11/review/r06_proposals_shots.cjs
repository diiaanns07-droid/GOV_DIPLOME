/*
 * R11 · UX-разбор карточек предложений и этапов R06 (день 3). Стенд — serve_r14.py R06 из его ветки (только читается):
 *   (в worktree R06) python3 tests/civic/R06/round14/serve_r14.py --port 8616 --age-days 16 --kit-dir <корень R11> > stand.json &
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r06_proposals_shots.cjs stand.json <папка>
 * Логин сотрудника берётся из stand.json и нигде не печатается.
 */
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const { measure, brief, consoleCollector } = require("./measure.cjs");
const [STAND, OUT] = process.argv.slice(2);
const stand = JSON.parse(fs.readFileSync(STAND, "utf8").split("\n")[0]);
const URL = stand.url;
const ORIGIN = new globalThis.URL(URL).origin;
fs.mkdirSync(OUT, { recursive: true });

const SCENARIOS = [
  ["resident", "", null, null],
  ["voted", "", null, async (p) => { const b = await p.$("[data-vote='1'], [data-value='1'], .r06-vote--up, button[data-action='vote-up']"); if (b) { await b.click(); await p.waitForTimeout(900); } else throw new Error("нет кнопки «За»"); }],
  ["akimat", "role=akimat", "login", null],
  ["network", "", null, null, true],
];

(async () => {
  const browser = await chromium.launch();
  const report = {};
  for (const [name, query, login, act, offline] of SCENARIOS) {
    for (const size of [1366, 375]) {
      for (const lang of ["ru", "kk"]) {
        if (["network", "voted"].includes(name) && lang === "kk") continue;
        const ctx = await browser.newContext({ viewport: size === 1366 ? { width: 1366, height: 768 } : { width: 375, height: 812 } });
        const p = await ctx.newPage();
        const logs = consoleCollector(p);
        if (login) {
          await p.goto(URL + "?lang=" + lang);
          const st = await p.evaluate(async (cred) => (await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cred) })).status, { username: stand.username, password: stand.password });
          if (st !== 200) logs.push("вход сотрудника: " + st);
        }
        if (offline) await p.route("**/api/civic/**", (r) => r.abort("internetdisconnected"));
        await p.goto(URL + "?lang=" + lang + (query ? "&" + query : ""));
        await p.waitForTimeout(1500);
        if (act) { try { await act(p); } catch (e) { logs.push("действие: " + e.message.split("\n")[0]); } }
        const tag = `${name}-${size}-${lang}`;
        await p.screenshot({ path: path.join(OUT, `r06-${tag}.png`), fullPage: true });
        await p.setViewportSize({ width: size, height: Math.min(6000, await p.evaluate(() => document.documentElement.scrollHeight)) });
        const m = await measure(p, null);
        report[tag] = { m, brief: brief(m), console: [...new Set(logs)].slice(0, 6) };
        await ctx.close();
      }
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "r06-measure.json"), JSON.stringify(report, null, 1));
  for (const [k, v] of Object.entries(report)) console.log(k.padEnd(22), v.brief, v.console.length ? " | консоль: " + v.console.join(" ; ").slice(0, 300) : "");
})().catch((e) => { console.error(e); process.exit(1); });
