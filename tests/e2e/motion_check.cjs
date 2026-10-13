#!/usr/bin/env node
// R10 · дизайн-марафон · чек-лист п. 7 «Движение»: ease-out, без рывков; панели выезжают, а не появляются;
// длительность (13 окт, эталон A + правило Linear 6): 150–250 мс (±30 → 120–280) — PASS; 281–330 — СМОТРЕТЬ (эталон: «карточки
// выезжают за 300 мс», Linear — до 250); вне — FAIL. Микро-отклик цвета/тени 80–120 мс — норма. Старая норма марафона 200–350 —
// флаг --norm marathon.
// prefers-reduced-motion отключает анимацию. Сразу после открытия меню / листа раздела / карточки места / мастера жалобы /
// легенды читает document.getAnimations() — настоящие длительность, кривая, задержка и свойства (без замера по кадрам:
// в облаке программный WebGL, 3–7 к/с). То же с «уменьшить движение» — анимаций быть не должно.
//   NODE_PATH="$(npm root -g)" node tests/e2e/motion_check.cjs --root <сборка> --out <папка> [--sizes 1366x768,375x812]
// Итог: <out>/MOTION.json, MOTION.md; код 1 — при FAIL.
"use strict";
const fs = require("fs"), path = require("path"), os = require("os");
const { chromium } = require("playwright");
const L = require("./r10_lib.cjs");
const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(String(args.root || path.join(__dirname, "../..")));
const OUT = path.resolve(String(args.out || path.join(os.tmpdir(), "r10-motion")));
const SIZES = String(args.sizes || "1366x768,375x812").split(",").map((s) => s.split("x").map(Number));
const KHAN = [71.406553, 51.131155];
const MARATHON = String(args.norm || "") === "marathon";
const durClass = (a) => { const t = /transform|translate|scale/.test(a.props);
  if (MARATHON) return (a.duration >= 170 && a.duration <= 380) || (a.duration >= 100 && a.duration < 170 && !t) ? "ok" : "bad";
  if (a.duration >= 120 && a.duration <= 280) return "ok";
  if (a.duration >= 80 && a.duration < 120 && !t) return "ok";
  if (a.duration > 280 && a.duration <= 330) return "look";
  return "bad"; };
const results = [];
const add = (scope, name, status, detail) => { results.push({ scope, name, status, detail }); console.log(`${status.padEnd(8)} ${scope} ${name}` + (detail ? " — " + JSON.stringify(detail).slice(0, 300) : "")); };

// Анимации, идущие сейчас: цель, тип, свойство/имя, длительность, кривая, задержка.
const RUNNING = () => document.getAnimations().map((a) => {
  const t = a.effect && a.effect.target, tm = a.effect ? a.effect.getTiming() : {};
  const kf = a.effect && a.effect.getKeyframes ? a.effect.getKeyframes() : [];
  const props = a.transitionProperty || [...new Set(kf.flatMap((k) => Object.keys(k).filter((x) => !["offset", "easing", "composite", "computedOffset"].includes(x))))].join(",");
  const el = t && t.nodeType === 1 ? t : t && t.element;
  const r = el ? el.getBoundingClientRect() : { width: 0, height: 0 };
  return { type: a.constructor.name, name: a.animationName || a.transitionProperty || "", props, duration: Math.round(Number(tm.duration) || 0), delay: Math.round(Number(tm.delay) || 0),
    easing: tm.easing || "", iterations: tm.iterations, target: el ? (el.id ? "#" + el.id : "") + "." + String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className).trim().split(/\s+/).slice(0, 2).join(".") : "?", area: Math.round(r.width * r.height) };
}).filter((x) => x.iterations !== Infinity);
const EASE_OUT = /ease-out|cubic-bezier\(0\.(1|2|3)\d*, ?1|cubic-bezier\(0, ?0, ?0\.\d+, ?1\)|cubic-bezier\(0\.\d+, ?0\.\d+, ?0\.\d+, ?1\)/;

async function scenario(browser, size, reduce, name, mode, open) {
  const mobile = size[0] < 761;
  const ctx = await browser.newContext({ viewport: { width: size[0], height: size[1] }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1, reducedMotion: reduce ? "reduce" : "no-preference" });
  await ctx.addInitScript((m) => { try { localStorage.setItem("birge.lang", "ru"); localStorage.setItem("birge.mode", m); } catch (e) { /* пусто */ } }, mode);
  await L.glassMode(ctx, "keep");
  const page = await ctx.newPage();
  try {
    await page.goto(SERVER.base); await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 40, null, { timeout: 40000 }).catch(() => null);
    await L.sleep(4000);
    await page.evaluate(() => document.getAnimations().forEach((a) => { try { if (a.effect && a.effect.getTiming().iterations !== Infinity) a.finish(); } catch (e) { /* пусто */ } }));
    const ok = await open(page);
    if (!ok) return { name, reached: false };
    const anims = await page.evaluate(RUNNING);
    return { name, reached: true, anims: anims.filter((a) => a.area >= 2000 || /panel|sheet|menu|account|day|screen|card|dialog|legend|bc-|r07-/i.test(a.target)).slice(0, 12), all: anims.length };
  } finally { await ctx.close(); }
}
let SERVER = null;
const tapCard = async (page) => { const p = await L.showPoint(page, KHAN, 17); if (!p) return false; await L.tap(page, p.x, p.y); await L.sleep(60); return true; };
const SCEN = [
  ["меню аватара", "resident", async (page) => { const a = await L.firstVisible(page.locator(".birge-avatar")); if (!a) return false; await a.click(); await L.sleep(40); return true; }],
  ["лист «Картина дня»", "akimat", async (page) => L.headerClick(page, /^\s*Картина дня\s*$/i, { wait: 40, menuRe: /^\s*Меню\s*$/i })],
  ["карточка места", "resident", tapCard],
  ["мастер жалобы", "resident", async (page) => { const b = await L.firstVisible(page.getByRole("button", { name: /Сообщить о проблеме/i })); if (!b) return false; await b.click(); await L.sleep(40); return true; }],
  ["легенда «?»", "resident", async (page) => { const b = await L.firstVisible(page.getByRole("button", { name: /Что значат цвета/i })); if (!b) return false; await b.click(); await L.sleep(40); return true; }],
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  SERVER = await L.startServer(ROOT);
  const browser = await chromium.launch();
  const raw = [];
  try {
    for (const size of SIZES) for (const [name, mode, open] of SCEN) {
      const tag = size.join("x");
      const n = await scenario(browser, size, false, name, mode, open), r = await scenario(browser, size, true, name, mode, open);
      raw.push({ size: tag, normal: n, reduce: r });
      if (!n.reached) { add(tag, `${name}: открыть`, "NOT_RUN", null); continue; }
      const main = n.anims.filter((a) => a.duration >= 60);
      const moves = main.some((a) => /transform|translate|scale|^bk-|enter|slide|up|right|pop/i.test(a.props + " " + a.name));
      const dc = main.map(durClass), durOk = main.length ? dc.every((c) => c === "ok") : null, durLook = dc.includes("look") && !dc.includes("bad");
      const easeOk = main.length ? main.every((a) => EASE_OUT.test(a.easing) || a.easing === "linear" && /opacity/.test(a.props)) : null;
      add(tag, `${name}: есть движение (не «появляется» мгновенно)`, main.length ? "PASS" : "СМОТРЕТЬ", { anims: main.map((a) => `${a.target} ${a.props || a.name} ${a.duration} мс ${a.easing}`).slice(0, 5) });
      if (main.length) {
        add(tag, `${name}: панель выезжает (transform), а не только проявляется`, moves ? "PASS" : "СМОТРЕТЬ", null);
        add(tag, MARATHON ? `${name}: длительность 200–350 мс (±30)` : `${name}: длительность 150–250 мс (±30; эталон — до 300)`, durOk ? "PASS" : durLook ? "СМОТРЕТЬ" : "FAIL",
          { off: main.filter((a) => durClass(a) !== "ok").map((a) => `${a.target} ${a.duration} мс`).slice(0, 4) });
        add(tag, `${name}: кривая ease-out`, easeOk ? "PASS" : "СМОТРЕТЬ", { easing: [...new Set(main.map((a) => a.easing))].slice(0, 4) });
      }
      if (r.reached) {
        const left = r.anims.filter((a) => a.duration > 20);
        add(tag, `${name}: «уменьшить движение» — анимаций нет (≤ 20 мс)`, left.length ? "FAIL" : "PASS", { left: left.map((a) => `${a.target} ${a.props || a.name} ${a.duration} мс`).slice(0, 4) });
      }
    }
  } finally { await browser.close(); await SERVER.stop(); }
  const counts = {}; results.forEach((r) => (counts[r.status] = (counts[r.status] || 0) + 1));
  const sha = L.buildSha(ROOT);
  fs.writeFileSync(path.join(OUT, "MOTION.json"), JSON.stringify({ sha, when: new Date().toISOString(), counts, results, raw }, null, 1));
  fs.writeFileSync(path.join(OUT, "MOTION.md"), [`# R10 · движение (чек-лист п. 7) · ${sha}`, "", `Итого: ${Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(" · ")}`, "",
    "| Где | Проверка | Итог | Подробно |", "|---|---|---|---|", ...results.map((r) => `| ${r.scope} | ${r.name} | **${r.status}** | ${r.detail ? JSON.stringify(r.detail).replace(/\|/g, "/").slice(0, 260) : ""} |`)].join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
  process.exit(counts.FAIL ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
