/*
 * R11 · UX-разбор 3D-превью R05 (день 3). Код R05 — из его worktree (только читается), ui-kit/i18n — из ветки R11
 * (копия кладётся в worktree в scratchpad). Хранилище — ?store=local (без API).
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r05_build3d_shots.cjs <worktree R05> <папка>
 */
"use strict";
const fs = require("fs"), path = require("path"), http = require("http");
const { chromium } = require("playwright");
const { measure, brief, consoleCollector } = require("./measure.cjs");
const [WT, OUT] = process.argv.slice(2);
const WEB = path.join(WT, "web");
fs.mkdirSync(OUT, { recursive: true });
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
const STREETS = JSON.parse(fs.readFileSync(path.join(WEB, "civic/build3d/data/nura-streets.json"), "utf8"));
const edge = (id) => STREETS.edges.find((e) => e[0] === id)[5];
const LIGHT = edge("osm-w1189551423-3");

async function ready(p) {
  await p.waitForFunction(() => window.__b3d && window.__b3d.getState().phase === "ready", null, { timeout: 60000 });
  await p.waitForFunction(() => __map.loaded() && !__b3d.getState().animating, null, { timeout: 60000 });
}
async function screenOf(p, ll) {
  return p.evaluate((ll) => { const q = __map.project(ll); const r = __map.getCanvas().getBoundingClientRect(); return [q.x + r.left, q.y + r.top]; }, ll);
}
async function place(p, kind, ll) {
  await p.click(`.b3d-card[data-kind=${kind}]`);
  const [x, y] = await screenOf(p, ll);
  await p.mouse.move(x, y, { steps: 2 }); await p.mouse.click(x, y);
}

const SCENARIOS = [
  ["start", "", null],
  ["ghost", "", async (p) => { await place(p, "square", [71.3995, 51.1282]); await p.waitForTimeout(400); }],
  ["built", "", async (p) => {
    await place(p, "square", [71.3995, 51.1282]); await p.click("[data-action=place]"); await ready(p);
    await place(p, "playground", [71.4022, 51.1283]); await p.click("[data-action=place]"); await ready(p);
    await p.waitForTimeout(300);
  }],
  ["lighting", "", async (p) => {
    await p.click(".b3d-card[data-kind=lighting]");
    let [x, y] = await screenOf(p, LIGHT[0]); await p.mouse.move(x, y); await p.mouse.click(x, y);
    [x, y] = await screenOf(p, LIGHT[LIGHT.length - 1]); await p.mouse.move(x, y, { steps: 4 }); await p.mouse.click(x, y);
    await p.waitForTimeout(400);
  }],
  ["card", "", async (p) => {
    await place(p, "sports", [71.3985, 51.1263]); await p.click("[data-action=place]"); await ready(p);
    const id = await p.evaluate(() => { const s = __b3d.getState(); return (s.items && s.items[s.items.length - 1] && s.items[s.items.length - 1].id) || null; });
    if (id) await p.evaluate((i) => __b3d.select(i), id);
    await p.waitForTimeout(500);
  }],
  ["resident", "&role=resident", null],
  ["pitch0", "&pitch=0", null],
];

(async () => {
  const server = http.createServer((req, res) => {
    const f = path.normalize(path.join(WEB, decodeURIComponent(req.url.split("?")[0])));
    if (!f.startsWith(WEB) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "Content-Type": MIME[path.extname(f)] || "application/octet-stream" }); fs.createReadStream(f).pipe(res);
  });
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  const BASE = "http://127.0.0.1:" + server.address().port + "/civic/build3d/demo.html?store=local&reset=1";
  const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const report = {};
  for (const [name, query, act] of SCENARIOS) {
    for (const size of [1366, 375]) {
      for (const lang of ["ru", "kk"]) {
        if (["pitch0", "lighting"].includes(name) && lang === "kk") continue;
        const ctx = await browser.newContext({ viewport: size === 1366 ? { width: 1366, height: 768 } : { width: 375, height: 812 } });
        const p = await ctx.newPage();
        const logs = consoleCollector(p);
        await p.goto(BASE + "&lang=" + lang + query);
        try { await ready(p); } catch (e) { logs.push("не дождались ready"); }
        if (act) { try { await act(p); } catch (e) { logs.push("действие: " + e.message.split("\n")[0]); } }
        await p.waitForTimeout(300);
        const tag = `${name}-${size}-${lang}`;
        await p.screenshot({ path: path.join(OUT, `r05-${tag}.png`) });
        const m = await measure(p, null);
        report[tag] = { m, brief: brief(m), console: [...new Set(logs)].slice(0, 6), state: await p.evaluate(() => { try { const s = __b3d.getState(); return { phase: s.phase, count: s.count, mode: s.mode }; } catch (e) { return null; } }) };
        await ctx.close();
      }
    }
  }
  await browser.close(); server.close();
  fs.writeFileSync(path.join(OUT, "r05-measure.json"), JSON.stringify(report, null, 1));
  for (const [k, v] of Object.entries(report)) console.log(k.padEnd(20), JSON.stringify(v.state), v.brief, v.console.length ? " | консоль: " + v.console.join(" ; ").slice(0, 300) : "");
})().catch((e) => { console.error(e); process.exit(1); });
