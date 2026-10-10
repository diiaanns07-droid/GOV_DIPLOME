/*
 * R11 · UX-разбор мастера жалобы R09: проходит 5 шагов + «Мои обращения» + ошибки на 1366 и 375, ru и kk,
 * снимает скриншоты и замеры. Код R09 берётся из его worktree (только читается), ui-kit/i18n — из этой ветки.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r09_shots.cjs <worktree R09> <папка> [streets.geojson]
 * Ответы API — подставные (CONTRACT §5, §7), сеть наружу закрыта.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const http = require("http");
const { chromium } = require("playwright");
const ROOT = path.resolve(__dirname, "../../../..");
const [WT, OUT, STREETS] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2" };

function serve() {
  return new Promise((ok) => {
    const s = http.createServer((req, res) => {
      const url = decodeURIComponent(req.url.split("?")[0]);
      let file;
      if (url === "/__stand.html") file = path.join(__dirname, "r09_stand.html");
      else if (url === "/__streets.json") file = STREETS;
      else if (url.startsWith("/civic/feedback/")) file = path.join(WT, "web", url);
      else file = path.join(ROOT, "web", url);
      if (!file || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    });
    s.listen(0, "127.0.0.1", () => ok(s));
  });
}

const NOW = Date.now();
const iso = (days) => new Date(NOW - days * 86400000).toISOString();
const STOP = { kind: "object", id: "osm-node-101", label_ru: "Остановка «Нура»", label_kk: "«Нұра» аялдамасы" };
const SEG = { kind: "segment", id: "osm-w123-4", label_ru: "Участок ул. Туран (ул. Сауран – пр. Мангилик Ел)", label_kk: "Тұран көшесінің бөлігі (Сауран көшесі – Мәңгілік Ел даңғылы)" };
const YARD = { kind: "area", id: "yard-77", label_ru: "Двор · ул. Сауран, 3", label_kk: "Аула · Сауран көшесі, 3" };

function mockApi(page, opts) {
  return page.route("**/api/civic/v2/**", async (route) => {
    const u = new URL(route.request().url());
    const p = u.pathname.replace("/api/civic/v2", "");
    const m = route.request().method();
    const json = (data, status) => route.fulfill({ status: status || 200, contentType: "application/json", body: JSON.stringify(status && status >= 400 ? { ok: false, error: data } : { ok: true, data }) });
    if (opts.down && opts.down.some((d) => p.startsWith(d))) return json({ code: "unavailable" }, 503);
    if (p === "/targets") return json({ candidates: [
      { target: STOP, distance_m: 38, geometry: { type: "Point", coordinates: [71.4296, 51.1719] } },
      { target: SEG, distance_m: 52, geometry: { type: "LineString", coordinates: [[71.4262, 51.1712], [71.4318, 51.1722]] } },
      { target: YARD, distance_m: 90, geometry: null } ] });
    if (p === "/classify") return json({ category: "snow_ice", score: 0.91, needs_review: false, model_version: "demo", top3: [] });
    if (p === "/similar") return json({ matches: opts.noSimilar ? [] : [{ complaint_id: "c-1", score: 0.82, target: STOP, metoo: 6 }] });
    if (p === "/complaints/c-1" && m === "GET") return json({ complaint: { id: "c-1", category: "snow_ice", target: STOP, reporters: 7, status: "accepted", created_at: iso(2), demo: true } });
    if (p === "/complaints/c-1/metoo") return json({ result: "added", complaint: { id: "c-1", code: "B-0412", category: "snow_ice", target: STOP, reporters: 8, status: "accepted", created_at: iso(2) } });
    if (p.startsWith("/complaints/summary")) return json({ top: null });
    if (p === "/complaints" && m === "POST") {
      if (opts.sendFails) return json({ code: "unavailable" }, 503);
      return json({ complaint: { id: "c-2", code: "B-0413", category: "snow_ice", target: STOP, reporters: 1, status: "new", created_at: iso(0), due_at: iso(-2) } });
    }
    if (p === "/complaints/mine") return json({ items: opts.mineEmpty ? [] : [
      { id: "c-2", code: "B-0413", category: "snow_ice", target: STOP, status: "new", created_at: iso(0), due_at: iso(-2), reporters: 1, demo: true },
      { id: "c-1", code: "B-0412", category: "transport", target: STOP, status: "in_progress", created_at: iso(5), reporters: 8, relation: "metoo", demo: true },
      { id: "c-0", code: "B-0398", category: "roads", target: SEG, status: "fixed", created_at: iso(20), reporters: 3, demo: true },
      { id: "c-9", code: "B-0371", category: "waste", target: YARD, status: "new", created_at: iso(9), due_at: iso(3), reporters: 2, demo: true } ] });
    if (p.startsWith("/complaints/place")) return json({ target: { kind: "area", id: "cell-5", label_ru: "Примерное место", label_kk: "Шамамен көрсетілген орын" }, geometry: null });
    return json({ code: "not_found" }, 404);
  });
}

async function measure(page) {
  return page.evaluate(() => {
    const vis = (el) => { const b = el.getBoundingClientRect(); const s = getComputedStyle(el); return b.width > 0 && b.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
    const out = { small: [], low: [], keys: [], clipped: [] };
    out.scroll = document.documentElement.scrollWidth - innerWidth;
    document.querySelectorAll(".bc-panel *, .bc-fab, .bc-toast *").forEach((el) => {
      if (!vis(el)) return;
      const own = Array.from(el.childNodes).some((c) => c.nodeType === 3 && c.textContent.trim());
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (own && fs < 14) out.small.push(fs + "px «" + el.textContent.trim().slice(0, 30) + "»");
      if (el.matches("button")) { const b = el.getBoundingClientRect(); if (b.height < 47.5) out.low.push(Math.round(b.height) + "px «" + (el.textContent.trim() || el.getAttribute("aria-label") || "").slice(0, 30) + "»"); }
      if (own && /^[a-z0-9_]+(\.[a-z0-9_]+)+$/.test(el.textContent.trim())) out.keys.push(el.textContent.trim());
      if (own && el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== "visible") out.clipped.push("«" + el.textContent.trim().slice(0, 30) + "»");
    });
    const p = document.querySelector(".bc-panel");
    if (p && !p.hidden) { const b = p.getBoundingClientRect(); out.panel = [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; }
    return out;
  });
}

async function run(browser, base, w, h, lang, opts, steps) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, permissions: [] });
  const page = await ctx.newPage();
  const logs = [];
  page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") logs.push(m.type() + ": " + m.text()); });
  page.on("pageerror", (e) => logs.push("pageerror: " + e.message));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await mockApi(page, opts);
  await page.goto(base + "/__stand.html?lang=" + lang);
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 20000 });
  const results = {};
  const shot = async (name) => {
    await page.waitForTimeout(450);
    const file = `r09-${w}-${lang}-${name}.png`;
    await page.screenshot({ path: path.join(OUT, file) });
    results[name] = await measure(page);
  };
  await steps(page, shot);
  results.console = [...new Set(logs)].slice(0, 15);
  await ctx.close();
  return results;
}

const clickMap = (page) => page.evaluate(() => { const c = window.__map.getCanvas().getBoundingClientRect(); return [c.left + c.width / 2, c.top + Math.min(c.height / 3, 200)]; }).then(([x, y]) => page.mouse.click(x, y));

(async () => {
  const server = await serve();
  const base = "http://127.0.0.1:" + server.address().port;
  const browser = await chromium.launch();
  const report = {};
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      report[`${w}-${lang}-main`] = await run(browser, base, w, h, lang, {}, async (page, shot) => {
        await shot("1-start");
        await page.click(".bc-fab");
        await shot("2-place");
        await clickMap(page);
        await page.waitForSelector(".bc-option", { timeout: 8000 }).catch(async () => {
          await page.screenshot({ path: path.join(OUT, "debug-after-click.png") });
          throw new Error("нет вариантов места после клика по карте; лог: " + JSON.stringify(await page.evaluate(() => ({ s: window.__ui.state() && window.__ui.state().candidatesLoading, p: window.__ui.state() && window.__ui.state().point }))));
        });
        await shot("2-candidates");
        await page.click(".bc-option--first");
        await page.fill("#bc-text", lang === "kk" ? "Аялдамада қар тазаланбаған, тұруға болмайды" : "На остановке не убран снег, стоять невозможно");
        await page.waitForTimeout(1200);
        await shot("3-text-suggest");
        await page.click(".bc-change");
        await shot("3-grid");
        await page.click(".bc-grid__chip[aria-pressed=true], .bc-grid__chip");
        await page.click(".bc-send");
        await page.waitForTimeout(600);
        await shot("4-similar");
        await page.click(".bc-panel .bk-btn--primary");
        await page.waitForTimeout(600);
        await shot("5-done-metoo");
        await page.click(".bc-panel .bk-btn--primary");
        await page.waitForTimeout(600);
        await shot("6-mine");
      });
    }
    report[`${w}-ru-errors`] = await run(browser, base, w, h, "ru", { down: ["/classify", "/similar"], sendFails: true }, async (page, shot) => {
      await page.click(".bc-fab");
      await page.waitForTimeout(500); // шторка выезжает 240 мс; клик раньше попадает мимо режима выбора места
      await clickMap(page);
      await page.waitForSelector(".bc-option");
      await page.click(".bc-option--first");
      await page.fill("#bc-text", "Яма на дороге у остановки, машины объезжают по тротуару");
      await page.waitForTimeout(3500);
      await shot("e1-no-ml-grid");
      const chip = await page.$(".bc-grid__chip");
      if (chip) await chip.click();
      await page.click(".bc-send");
      await page.waitForTimeout(3500);
      await shot("e2-send-failed");
    });
    report[`${w}-ru-mine-empty`] = await run(browser, base, w, h, "ru", { mineEmpty: true }, async (page, shot) => {
      await page.evaluate(() => window.__ui.openMine());
      await page.waitForTimeout(500);
      await shot("e3-mine-empty");
    });
  }
  await browser.close();
  server.close();
  fs.writeFileSync(path.join(OUT, "r09-measure.json"), JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1).slice(0, 6000));
})().catch((e) => { console.error(e); process.exit(1); });
