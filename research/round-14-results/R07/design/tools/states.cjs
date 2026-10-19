// R07 · дизайн-марафон: кадры всех состояний тепловой карты на сборке R01 со стеклом.
//   node states.cjs <url> <outdir> [sizes] [langs] [only-states]
// Состояния: list (первый кадр, акимат), legend (открыта «?»), card-new, card-work, card-reported, card-verified,
// card-reopened (акимат), card-resident (житель), focus16 (крупный план с выбранной), cluster13 (средний масштаб),
// skeleton (ответ /heat задержан), empty (фильтр без жалоб), error (нет связи), glassoff (?glass=off).
// Пишет <outdir>/<state>-<w>-<lang>.jpg и metrics.json (контраст текста не меряет — это glass_contrast R11).
"use strict";
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const fs = require("fs"), path = require("path");
const BASE = process.argv[2] || "http://127.0.0.1:8614/";
const OUT = process.argv[3] || "/tmp/r07states";
const SIZES = String(process.argv[4] || "1366x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = String(process.argv[5] || "ru,kk").split(",");
const ONLY = process.argv[6] ? String(process.argv[6]).split(",") : null;
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const want = (s) => !ONLY || ONLY.includes(s);

const TARGETS = {
  "card-new": (it) => /Хан Шатыр/.test(it.target.label_ru || ""),
  "card-work": (it) => it.state === "active" && it.status === "in_progress" && !it.reopened,
  "card-reported": (it) => it.state === "fixed" && it.fixed_kind === "reported" && it.target.kind === "object",
  "card-verified": (it) => it.state === "fixed" && it.fixed_kind === "verified" && it.target.kind === "segment",
  "card-reopened": (it) => it.reopened,
};

async function openPage(browser, w, h, lang, mode, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: w < 500, hasTouch: w < 500 });
  await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) {} }, [mode, lang]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 160)));
  page.on("console", (m) => { if (m.type() === "error" && !/TUNNEL|403|Failed to load resource/.test(m.text())) errors.push(m.text().slice(0, 160)); });
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  if (opts.route) await opts.route(page);
  await page.goto(BASE + (opts.query || ""), { waitUntil: "domcontentloaded" });
  if (!opts.noWait) {
    await page.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => {});
    await sleep(2200);
  }
  return { ctx, page, errors };
}

const metrics = (page) => page.evaluate(() => {
  const root = document.getElementById("birge-heat-root");
  const fonts = new Set(), weights = new Set();
  if (root) root.querySelectorAll("*").forEach((e) => {
    if ([...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && e.getClientRects().length) {
      const cs = getComputedStyle(e); fonts.add(cs.fontSize); weights.add(cs.fontWeight);
    }
  });
  const opaque = [];
  if (root) root.querySelectorAll("*").forEach((e) => {
    const bg = getComputedStyle(e).backgroundColor;
    const m = /rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)/.exec(bg);
    if (m && (m[4] === undefined || Number(m[4]) > 0.5) && e.getClientRects().length && e.getBoundingClientRect().width > 30)
      opaque.push((e.className && String(e.className).split(" ")[0]) + " " + bg);
  });
  const badges = [...document.querySelectorAll(".r07-badge")].filter((b) => !b.hidden && b.getClientRects().length).map((b) => Math.round(b.getBoundingClientRect().height));
  return { fonts: [...fonts].sort(), weights: [...weights].sort(), opaque: [...new Set(opaque)].slice(0, 12), badgeMinH: badges.length ? Math.min(...badges) : null, badges: badges.length,
    statuses: root ? root.querySelectorAll(".bk-status").length : 0 };
});

(async () => {
  const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const report = [];
  const items = await (await fetch(BASE + "api/civic/v2/heat?days=30&zoom=14")).json().then((d) => (d.data || d).items);
  for (const [w, h] of SIZES) for (const lang of LANGS) {
    const tag = `${w}-${lang}`;
    const shot = async (page, name, errors, extra) => {
      const file = path.join(OUT, `${name}-${tag}.jpg`);
      await page.screenshot({ path: file, type: "jpeg", quality: 80 });
      const m = await metrics(page);
      report.push({ name, tag, ...m, ...(extra || {}), errors: errors.slice(0, 4) });
      console.log(name, tag, JSON.stringify({ f: m.fonts, w: m.weights, op: m.opaque.length, bmin: m.badgeMinH, st: m.statuses, err: errors.length }));
    };
    // список + легенда + карточки (акимат)
    if (["list", "cats", "legend", ...Object.keys(TARGETS)].some(want)) {
      const { ctx, page, errors } = await openPage(browser, w, h, lang, "akimat");
      if (want("list")) await shot(page, "list", errors);
      if (want("cats")) {
        await page.evaluate(() => document.querySelector("[data-cats-toggle]")?.click());
        await sleep(700);
        await shot(page, "cats", errors);
        await page.evaluate(() => document.querySelector("[data-cats-toggle]")?.click());
        await sleep(400);
      }
      if (want("legend")) {
        await page.click(".birge-legend-q").catch(() => {});
        await sleep(1500);
        await shot(page, "legend", errors);
        await page.click(".birge-legend-q").catch(() => {});
        await sleep(600);
      }
      for (const [name, pick] of Object.entries(TARGETS)) {
        if (!want(name)) continue;
        const it = items.find(pick);
        if (!it) { console.log(name, tag, "нет цели"); continue; }
        await page.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), it.target);
        await sleep(3000);
        await shot(page, name, errors, { label: it.target.label_ru });
        await page.keyboard.press("Escape"); await sleep(500);
      }
      await ctx.close();
    }
    if (want("card-resident")) {
      const { ctx, page, errors } = await openPage(browser, w, h, lang, "resident");
      const it = items.find(TARGETS["card-new"]);
      await page.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), it.target);
      await sleep(3000);
      await shot(page, "card-resident", errors);
      await ctx.close();
    }
    if (want("focus16") || want("cluster13")) {
      const { ctx, page, errors } = await openPage(browser, w, h, lang, "akimat");
      if (want("cluster13")) {
        await page.evaluate(() => map.jumpTo({ center: [71.41, 51.125], zoom: 13.2 }));
        await sleep(2500);
        await shot(page, "cluster13", errors);
      }
      if (want("focus16")) {
        const it = items.find(TARGETS["card-new"]);
        await page.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), it.target);
        await sleep(1500);
        await page.evaluate(() => map.easeTo({ zoom: 16.3, duration: 0 }));
        await sleep(2000);
        await shot(page, "focus16", errors);
      }
      await ctx.close();
    }
    if (want("skeleton")) {
      const { ctx, page, errors } = await openPage(browser, w, h, lang, "akimat", { noWait: true,
        route: (p) => p.route(/\/api\/civic\/v2\/heat/, async (r) => { await sleep(20000); r.continue().catch(() => {}); }) });
      await page.waitForSelector(".r07-skeleton", { timeout: 20000 }).catch(() => {});
      await sleep(2500);
      await shot(page, "skeleton", errors);
      await ctx.close();
    }
    if (want("error")) {
      const { ctx, page, errors } = await openPage(browser, w, h, lang, "akimat", { noWait: true,
        route: (p) => p.route(/\/api\/civic\/v2\/heat/, (r) => r.fulfill({ status: 502, contentType: "application/json", body: "{}" })) });
      await page.waitForSelector(".r07-error", { timeout: 20000 }).catch(() => {});
      await sleep(2000);
      await shot(page, "error", errors.filter((e) => !/502/.test(e)));
      await ctx.close();
    }
    if (want("empty")) {
      const { ctx, page, errors } = await openPage(browser, w, h, lang, "akimat", {
        route: (p) => p.route(/\/api\/civic\/v2\/heat\?.*category=/, async (r) => {
          const res = await r.fetch(); const d = await res.json(); const x = d.data || d; x.items = []; await r.fulfill({ response: res, json: d });
        }) });
      await page.evaluate(() => document.querySelector("[data-cats-toggle]")?.click());
      await sleep(400);
      await page.evaluate(() => document.querySelector('[data-cat]:not([data-cat=""])')?.click());
      await page.waitForSelector(".r07-empty", { timeout: 10000 }).catch(() => {});
      await sleep(1500);
      await shot(page, "empty", errors);
      await ctx.close();
    }
    if (want("glassoff")) {
      const { ctx, page, errors } = await openPage(browser, w, h, lang, "akimat", { query: "?glass=off" });
      const it = items.find(TARGETS["card-new"]);
      await page.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), it.target);
      await sleep(3000);
      await shot(page, "glassoff", errors);
      await ctx.close();
    }
  }
  fs.writeFileSync(path.join(OUT, "metrics.json"), JSON.stringify(report, null, 1));
  await browser.close();
})();
