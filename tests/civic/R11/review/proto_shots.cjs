/*
 * R11 · скриншоты макетов web/civic/ui-kit/prototypes/ в разных состояниях (1366 и 375, ru и kk).
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/proto_shots.cjs <папка> [фильтр-имени]
 */
"use strict";
const fs = require("fs"), path = require("path"), http = require("http");
const { chromium } = require("playwright");
const ROOT = path.resolve(__dirname, "../../../..");
const [OUT, ONLY] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
const P = "/civic/ui-kit/prototypes/";
// [имя, страница, действия]
const SHOTS = [
  ["map-list", P + "akimat-map.html", async () => {}],
  ["map-card", P + "akimat-map.html?target=t-stop-sauran", async (p) => p.waitForTimeout(600)],
  ["map-card-segment", P + "akimat-map.html?target=t-seg-kabanbay", async (p) => p.waitForTimeout(600)],
  ["map-card-full", P + "akimat-map.html?target=t-stop-sauran", async (p) => { await p.waitForTimeout(600); await p.evaluate(() => { const s = document.querySelector(".bk-sheet"); if (s) s.dataset.snap = "full"; }); }],
  ["map-resident", P + "akimat-map.html?role=resident&target=t-seg-orynbor", async (p) => p.waitForTimeout(600)],
  ["map-empty", P + "akimat-map.html?state=empty", async () => {}],
  ["map-error", P + "akimat-map.html?state=error", async () => {}],
  ["map-loading", P + "akimat-map.html?state=loading", async () => {}],
  ["day", P + "day.html", async (p) => p.waitForTimeout(600)],
  ["day-empty", P + "day.html?date=2026-10-05", async (p) => p.waitForTimeout(600)],
  ["complaint-start", P + "complaint.html", async () => {}],
  ["complaint-2", P + "complaint.html", async (p) => { await p.click("#pc-fab"); await p.waitForTimeout(400); await p.evaluate(() => window.__proto.pickAt("stop_orynbor")); await p.waitForTimeout(700); }],
  ["complaint-3", P + "complaint.html", async (p) => { await p.click("#pc-fab"); await p.waitForTimeout(400); await p.evaluate(() => window.__proto.pickAt("stop_orynbor")); await p.waitForTimeout(700); await p.click("[data-cand='0']"); await p.fill("#pc-text", (await p.evaluate(() => document.documentElement.lang)) === "kk" ? "Аялдамада қар тазаланбаған" : "На остановке не убран снег"); await p.waitForTimeout(1200); }],
  ["complaint-3-grid", P + "complaint.html", async (p) => { await p.click("#pc-fab"); await p.waitForTimeout(400); await p.evaluate(() => window.__proto.pickAt("stop_orynbor")); await p.waitForTimeout(700); await p.click("[data-cand='0']"); await p.fill("#pc-text", "яма"); await p.waitForTimeout(1200); await p.click("#pc-change"); await p.waitForTimeout(200); }],
  ["complaint-4", P + "complaint.html", async (p) => { await p.click("#pc-fab"); await p.waitForTimeout(400); await p.evaluate(() => window.__proto.pickAt("stop_orynbor")); await p.waitForTimeout(700); await p.click("[data-cand='0']"); await p.fill("#pc-text", "Аялдамада қар / снег"); await p.waitForTimeout(1200); await p.click("#pc-send"); await p.waitForTimeout(900); }],
  ["complaint-5", P + "complaint.html", async (p) => { await p.click("#pc-fab"); await p.waitForTimeout(400); await p.evaluate(() => window.__proto.pickAt("stop_orynbor")); await p.waitForTimeout(700); await p.click("[data-cand='0']"); await p.fill("#pc-text", "Аялдамада қар / снег"); await p.waitForTimeout(1200); await p.click("#pc-send"); await p.waitForTimeout(900); await p.click("#pc-metoo"); await p.waitForTimeout(900); }],
  ["complaint-mine", P + "complaint.html?view=mine", async (p) => p.waitForTimeout(700)],
  ["complaint-send-error", P + "complaint.html?fail=send", async (p) => { await p.click("#pc-fab"); await p.waitForTimeout(400); await p.evaluate(() => window.__proto.pickAt("stop_bukhar")); await p.waitForTimeout(700); await p.click("[data-cand='approx']"); await p.fill("#pc-text", "Шумят ночью / түнде шу"); await p.waitForTimeout(1200); await p.click("#pc-send"); await p.waitForTimeout(1200); }],
];

(async () => {
  const server = http.createServer((req, res) => {
    const f = path.join(ROOT, "web", decodeURIComponent(req.url.split("?")[0]));
    if (!f.startsWith(path.join(ROOT, "web")) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "Content-Type": MIME[path.extname(f)] || "application/octet-stream" }); fs.createReadStream(f).pipe(res);
  });
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  const base = "http://127.0.0.1:" + server.address().port;
  const browser = await chromium.launch();
  const problems = [];
  for (const [name, url, act] of SHOTS) {
    if (ONLY && !name.includes(ONLY)) continue;
    for (const [w, h] of [[1366, 768], [375, 812]]) {
      for (const lang of ["ru", "kk"]) {
        const page = await browser.newPage({ viewport: { width: w, height: h } });
        page.on("console", (m) => { if (m.type() === "error" || /\[i18n\]/.test(m.text())) problems.push(`${name} ${w} ${lang}: ${m.text()}`); });
        page.on("pageerror", (e) => problems.push(`${name} ${w} ${lang}: ${e.message}`));
        await page.goto(base + url + (url.includes("?") ? "&" : "?") + "lang=" + lang, { waitUntil: "networkidle" });
        await page.waitForTimeout(300);
        try { await act(page); } catch (e) { problems.push(`${name} ${w} ${lang}: действие не прошло: ${e.message.split("\n")[0]}`); }
        await page.waitForTimeout(350);
        const scroll = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
        if (scroll > 0) problems.push(`${name} ${w} ${lang}: прокрутка вбок ${scroll}px`);
        await page.screenshot({ path: path.join(OUT, `${name}-${w}-${lang}.png`), fullPage: name.startsWith("day") });
        await page.close();
      }
    }
  }
  await browser.close(); server.close();
  console.log(problems.length ? problems.join("\n") : "без ошибок в консоли и без прокрутки вбок");
})().catch((e) => { console.error(e); process.exit(1); });
