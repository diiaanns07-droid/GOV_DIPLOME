// R05 · дизайн-марафон · чек-лист п. 7 «Движение» для панели 3D-модуля — по тем же правилам, что R10 motion_check.cjs
// (claude/r14-R10 b84d46ff): сразу после смены состояния читаем document.getAnimations() — длительность, кривая, свойства;
// панель должна выезжать (transform/translate), а не только проявляться; 200–350 мс (±30); ease-out; с «уменьшить
// движение» анимаций нет. Анимация постройки 3D (WebGL, 1,1 с) сюда не попадает — она не CSS и описана в CHECKLIST.md.
// Отличие от R10: кривую CSS-анимации берём из ключевых кадров (у R10 она читается как «linear» — так по спецификации
// возвращает getTiming(); R10 пропускает «linear» только вместе с opacity).
//
//   NODE_PATH="$(npm root -g)" node tests/civic/R05/build3d/motion_check.mjs [--kit <выгрузка ui-kit R11>] [--out <файл.json>]
//
// Состояния (демо web/civic/build3d/demo.html, 1366×768 и 375×812): каталог → размещение, размещение → каталог («Отменить»),
// табличка → карточка проекта, наведение на табличку (только 1366). Итог — runs/motion_check.json, код 1 при FAIL.
import http from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const WEB = path.join(ROOT, "web");
const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : null;
};
const KIT = arg("--kit") ? path.resolve(arg("--kit"), "web") : null;
const OUT = arg("--out") ? path.resolve(arg("--out")) : path.join(ROOT, "research/round-14-results/R05/runs/motion_check.json");
const { chromium } = (() => {
  for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {
    try {
      return require(id);
    } catch (e) {
      /* следующий */
    }
  }
  throw new Error("нужен playwright");
})();

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png" };
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname.startsWith("/api/")) {
    res.writeHead(404, { "Content-Type": "application/json" });
    return res.end('{"error":{"code":"not_found"}}');
  }
  const rel = decodeURIComponent(url.pathname);
  const base = KIT && (rel.startsWith("/civic/ui-kit/") || rel.startsWith("/civic/i18n/")) ? KIT : WEB;
  const file = path.normalize(path.join(base, rel));
  if (!file.startsWith(base)) {
    res.writeHead(403);
    return res.end();
  }
  try {
    const data = await readFile(file);
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  } catch (e) {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}/civic/build3d/demo.html`;

// Анимации модуля, идущие сейчас (панель .b3d и таблички .b3d-labels), — как RUNNING у R10.
const RUNNING = () =>
  document
    .getAnimations()
    .map((a) => {
      const t = a.effect && a.effect.target,
        tm = a.effect ? a.effect.getTiming() : {};
      const kf = a.effect && a.effect.getKeyframes ? a.effect.getKeyframes() : [];
      const props = a.transitionProperty || [...new Set(kf.flatMap((k) => Object.keys(k).filter((x) => !["offset", "easing", "composite", "computedOffset"].includes(x))))].join(",");
      const el = t && t.nodeType === 1 ? t : t && t.element;
      const mine = !!(el && el.closest && el.closest(".b3d, .b3d-labels"));
      // У CSS-анимации (@keyframes) кривая по спецификации лежит в ключевых кадрах (animation-timing-function), а
      // getTiming().easing всегда «linear» — берём кривую первого кадра. У переходов и Web Animations — из getTiming().
      const kfEase = a.constructor.name === "CSSAnimation" && kf.length && kf[0].easing && kf[0].easing !== "linear" ? kf[0].easing : "";
      return { mine, type: a.constructor.name, name: a.animationName || "", props, duration: Math.round(Number(tm.duration) || 0), easing: kfEase || tm.easing || "", iterations: tm.iterations,
        target: el ? "." + String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className).trim().split(/\s+/).slice(0, 2).join(".") : "?" };
    })
    .filter((x) => x.mine && x.iterations !== Infinity);
const EASE_OUT = /ease-out|cubic-bezier\(0\.(1|2|3)\d*, ?1|cubic-bezier\(0, ?0, ?0\.\d+, ?1\)|cubic-bezier\(0\.\d+, ?0\.\d+, ?0\.\d+, ?1\)/;

const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const results = [];
const add = (scope, name, status, detail) => {
  results.push({ scope, name, status, detail });
  console.log(`${status.padEnd(8)} ${scope} ${name}` + (detail ? " — " + JSON.stringify(detail).slice(0, 220) : ""));
};
async function open(w, h, role, reduce) {
  const phone = w < 700;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: phone, hasTouch: phone, reducedMotion: reduce ? "reduce" : "no-preference" });
  const page = await ctx.newPage();
  await page.goto(`${BASE}?reset=1&store=local&lang=ru&role=${role}&center=71.4008,51.1272&zoom=17.4&pitch=60&bearing=-30`);
  await page.waitForFunction(() => { const s = window.__b3d && __b3d.getState(); return s && s.phase === "ready" && (s.view !== "3d" || s.three === "ready"); }, null, { timeout: 60000 });
  await page.waitForFunction(() => { const s = __b3d.getState(); return __map.loaded() && !__map.isMoving() && !s.animating && !s.shadowsPending; }, null, { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.evaluate(() => document.getAnimations().forEach((a) => { try { if (a.effect && a.effect.getTiming().iterations !== Infinity) a.finish(); } catch (e) { /* пусто */ } }));
  return page;
}
const click = (page, sel) => page.evaluate((s) => document.querySelector(s).click(), sel); // без наведения мыши: только смена состояния
const SCEN = [
  ["каталог → размещение", "akimat", async (p) => click(p, ".b3d-card[data-kind=square]")],
  ["размещение → каталог («Отменить»)", "akimat", async (p) => { await click(p, ".b3d-card[data-kind=square]"); await p.waitForSelector("[data-action=cancel]"); await p.waitForTimeout(500); await click(p, "[data-action=cancel]"); }],
  ["табличка → карточка проекта", "resident", async (p) => click(p, '.b3d-label[data-id="p-demo-stop-syganak"]')],
  ["наведение на табличку", "resident", async (p) => p.hover('.b3d-label[data-id="p-demo-stop-syganak"]'), 1366],
];
for (const [w, h] of [[1366, 768], [375, 812]]) {
  for (const [name, role, act, only] of SCEN) {
    if (only && only !== w) continue;
    const tag = `${w}x${h}`;
    const got = {};
    for (const reduce of [false, true]) {
      const p = await open(w, h, role, reduce);
      await act(p);
      await p.waitForTimeout(40);
      got[reduce ? "reduce" : "normal"] = await p.evaluate(RUNNING);
      await p.context().close();
    }
    const main = got.normal.filter((a) => a.duration >= 60);
    const moves = main.some((a) => /transform|translate|scale|slide|up|enter/i.test(a.props + " " + a.name));
    const durOk = main.every((a) => (a.duration >= 170 && a.duration <= 380) || (a.duration >= 100 && a.duration < 170 && !/transform|translate/.test(a.props)));
    const easeOk = main.every((a) => EASE_OUT.test(a.easing) || (a.easing === "linear" && /opacity/.test(a.props)));
    const list = main.map((a) => `${a.target} ${a.props || a.name} ${a.duration} мс ${a.easing}`).slice(0, 5);
    add(tag, `${name}: есть движение`, main.length ? "PASS" : "СМОТРЕТЬ", { anims: list });
    if (main.length) {
      add(tag, `${name}: выезжает/приподнимается (transform), а не только проявляется`, moves ? "PASS" : "СМОТРЕТЬ", null);
      add(tag, `${name}: длительность 200–350 мс (±30)`, durOk ? "PASS" : "FAIL", { anims: list });
      add(tag, `${name}: кривая ease-out`, easeOk ? "PASS" : "СМОТРЕТЬ", { easing: [...new Set(main.map((a) => a.easing))] });
    }
    const left = got.reduce.filter((a) => a.duration > 20);
    add(tag, `${name}: «уменьшить движение» — анимаций нет (≤ 20 мс)`, left.length ? "FAIL" : "PASS", { left: left.map((a) => `${a.target} ${a.props || a.name} ${a.duration} мс`).slice(0, 4) });
  }
}
await browser.close();
server.close();
const counts = {};
results.forEach((r) => (counts[r.status] = (counts[r.status] || 0) + 1));
await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify({ kit: KIT ? path.basename(path.dirname(KIT)) : "web/", when: new Date().toISOString(), counts, results }, null, 1) + "\n");
console.log("Итого:", counts, "→", path.relative(ROOT, OUT));
process.exit(counts.FAIL ? 1 : 0);
