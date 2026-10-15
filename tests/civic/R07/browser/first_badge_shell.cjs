// R07 раунд 15 (R10 B-113): первый значок с числом в сборке R01 — хроника не подключена (none), подключена целиком
// (full: replay.js + replay.css в index.html) и лёгким входом (lazy: replay-attach.js). Ассеты хроники берутся из этой
// рабочей копии (подстановка запросом — пока их нет в списке шлюза R01). В режиме lazy первый прогон ещё открывает
// хронику кнопкой и проверяет, что полная хроника загрузилась только по нажатию.
// Запуск: сборка R01 с демо-миром на R07_SHELL (по умолчанию http://127.0.0.1:8655/), затем
//   NODE_PATH=$(npm root -g) node tests/civic/R07/browser/first_badge_shell.cjs [прогонов=5]
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const SHELL = (process.env.R07_SHELL || "http://127.0.0.1:8655/").replace(/\/?$/, "/");
const DIR = path.join(__dirname, "..", "..", "..", "..", "web", "civic", "replay") + "/";
const FILES = { "replay.css": "text/css", "replay.js": "application/javascript", "replay-attach.js": "application/javascript" };
const RUNS = Number(process.argv[2] || 5);
(async () => {
  const browser = await chromium.launch();
  const out = { full: [], lazy: [], none: [] };
  const extra = { lazy: [] };
  for (let i = 0; i < RUNS; i++) {
    for (const mode of ["none", "full", "lazy"]) {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      const page = await ctx.newPage();
      const asked = [];
      page.on("request", (r) => { if (/\/civic\/replay\//.test(r.url())) asked.push(r.url().replace(/^.*\/civic\/replay\//, "")); });
      for (const [f, type] of Object.entries(FILES)) {
        await page.route("**/civic/replay/" + f, (r) => r.fulfill({ status: 200, contentType: type + "; charset=utf-8", body: fs.readFileSync(DIR + f, "utf8") }));
      }
      await page.route((url) => url.href.split("?")[0] === SHELL, async (route) => {
        const res = await route.fetch();
        let html = await res.text();
        if (mode === "full") html = html.replace('<link rel="stylesheet" href="/civic/heat/heat.css" />', '<link rel="stylesheet" href="/civic/heat/heat.css" />\n    <link rel="stylesheet" href="/civic/replay/replay.css" />')
          .replace('<script defer src="/civic/heat/heat.js"></script>', '<script defer src="/civic/heat/heat.js"></script>\n    <script defer src="/civic/replay/replay.js"></script>');
        if (mode === "lazy") html = html.replace('<script defer src="/civic/heat/heat.js"></script>', '<script defer src="/civic/heat/heat.js"></script>\n    <script defer src="/civic/replay/replay-attach.js"></script>');
        await route.fulfill({ response: res, body: html, headers: Object.assign({}, res.headers(), { "content-security-policy": "" }) });
      });
      await page.addInitScript(() => {
        window.__fb = null;
        const tick = () => {
          const b = [...document.querySelectorAll(".r07-badge")].find((x) => /\d/.test(x.textContent || "") && x.getBoundingClientRect().width > 0);
          if (b) { window.__fb = performance.now(); return; }
          requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
      await page.goto(SHELL + "?lang=ru", { waitUntil: "load" });
      await page.waitForFunction(() => window.__fb !== null, null, { timeout: 60000 });
      const fb = await page.evaluate(() => window.__fb);
      out[mode].push(Math.round(fb));
      if (mode === "lazy" && i === 0) {
        const atBadge = asked.slice();
        await page.evaluate(() => window.BirgeReplay.attach({ map, heat: window.CivicShell.heat, tools: document.querySelector(".map-tools") }));  // eslint-disable-line no-undef
        await page.click(".map-tools .rp-open");
        await page.waitForFunction(() => window.BirgeReplay.active && window.BirgeReplay.active.state().status === "ready", null, { timeout: 30000 });
        const st = await page.evaluate(() => ({ full: typeof window.BirgeReplay.mount === "function", days: window.BirgeReplay.active.state().days.length,
          play: document.querySelector(".rp-play").innerHTML.includes("#i-") }));
        extra.lazy.push({ requested_before_click: atBadge, requested_after: asked.slice(), opened: st });
      }
      await ctx.close();
    }
  }
  const med = (a) => { const s = a.slice().sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
  console.log(JSON.stringify({ runs: RUNS, first_badge_ms: out, median: { none: med(out.none), full: med(out.full), lazy: med(out.lazy) }, lazy_check: extra.lazy }, null, 1));
  await browser.close();
})();
