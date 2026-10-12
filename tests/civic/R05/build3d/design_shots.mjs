// R05 · дизайн-марафон: кадры «до/после» для внешнего вида 3D (DESIGN_MARATHON.md, задачи R05).
//
//   NODE_PATH="$(npm root -g)" node tests/civic/R05/build3d/design_shots.mjs <метка> [--kit <выгрузка ui-kit R11>]
//
// Кадры — research/round-14-results/R05/design/<метка>/:
//   obj_<вид>_1366.png  — крупный план каждого из пяти объектов (панель модуля скрыта, табличка видна);
//   obj_<вид>_375.png   — то же на телефоне (×2);
//   all_<ширина>_<язык>.png — все объекты с панелью и каталогом «Что построить?», как в демо;
//   build_<доля>.png    — постройка сквера (замедлена до 6 с): доли 0.1 … 1.0;
// Набор как в browser_check (SHOWCASE: спортплощадка + примеры), без ?reset — иначе демо стирает набор.
// Ничего не проверяет — только снимает (проверки остаются в browser_check.mjs). Сервер — статический web/ (+ ui-kit/i18n из --kit).
import http from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const WEB = path.join(ROOT, "web");
const TAG = process.argv[2] && !process.argv[2].startsWith("--") ? process.argv[2] : "now";
const OUT = path.join(ROOT, "research/round-14-results/R05/design", TAG);
const KIT = (() => {
  const i = process.argv.indexOf("--kit");
  return i > 0 && process.argv[i + 1] ? path.resolve(process.argv[i + 1], "web") : null;
})();
const ONLY = (() => {
  const i = process.argv.indexOf("--only");
  return i > 0 && process.argv[i + 1] ? new RegExp(process.argv[i + 1]) : null;
})();
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

const FIXTURE = JSON.parse(await readFile(path.join(WEB, "civic/build3d/data/proposals.fixture.json"), "utf8"));
const SHOWCASE = [{ id: "s-sports", kind: "sports", geometry: { type: "Point", coordinates: [71.3998, 51.1268] }, rotation_deg: 8 }]
  .map((p) => Object.assign({ status: "proposal", votes_up: 0, votes_down: 0, year: 2027, district: "nura" }, p))
  .concat(FIXTURE.proposals);
// Крупный план: центр, масштаб (ноутбук; телефон — на 0.6 меньше).
const CLOSE = {
  square: { c: [71.402378, 51.12881], z: 19.5 },
  playground: { c: [71.398021, 51.129789], z: 20.0 },
  sports: { c: [71.3998, 51.1268], z: 19.6 },
  stop: { c: [71.401473, 51.127621], z: 20.8 },
  lighting: { c: [71.39915, 51.127675], z: 18.9 },
};

const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
await mkdir(OUT, { recursive: true });
const made = [];
async function open(viewport, query, seed) {
  const phone = viewport.width < 700;
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: phone ? 2 : 1, hasTouch: phone, isMobile: phone });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log("pageerror", query, e.message));
  if (seed)
    await page.addInitScript((items) => {
      if (!sessionStorage.getItem("seeded")) {
        localStorage.setItem("birge.build3d.proposals.v1", JSON.stringify({ items, votes: {} }));
        sessionStorage.setItem("seeded", "1");
      }
    }, seed);
  await page.goto(BASE + query);
  await page.waitForFunction(() => { const s = window.__b3d && __b3d.getState(); return s && s.phase === "ready" && (s.view !== "3d" || s.three === "ready"); }, null, { timeout: 60000 });
  await settle(page);
  return page;
}
async function settle(page) {
  await page.waitForFunction(() => __map.loaded() && __map.areTilesLoaded() && !__map.isMoving() && !__b3d.getState().animating, null, { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(350);
}
async function shot(page, name) {
  if (ONLY && !ONLY.test(name)) return;
  await page.screenshot({ path: path.join(OUT, name) });
  made.push(name);
}
const want = (re) => !ONLY || ONLY.test(re);

// 1. Крупные планы пяти объектов (панель скрыта: смотрим на сам объект и табличку).
for (const [w, h] of [[1366, 768], [375, 812]]) {
  if (!want(`obj_.*_${w}`)) continue;
  const p = await open({ width: w, height: h }, "?store=local&lang=ru&role=resident&center=71.4008,51.1272&zoom=17.4&pitch=60&bearing=-30", SHOWCASE);
  await p.addStyleTag({ content: ".b3d-dock,.b3d-toasts,.demo-head,.bk-header,header{visibility:hidden!important}" });
  for (const [kind, v] of Object.entries(CLOSE)) {
    await p.evaluate(([c, z]) => __map.jumpTo({ center: c, zoom: z, pitch: 60, bearing: -30 }), [v.c, w < 700 ? v.z - 0.6 : v.z]);
    await settle(p);
    await shot(p, `obj_${kind}_${w}.png`);
  }
  await p.context().close();
}
// 2. Все объекты с панелью (как в демо, каталог открыт) — 1366/375, ru/kk.
for (const lang of ["ru", "kk"]) {
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    if (!want(`all_${w}_${lang}`)) continue;
    const p = await open({ width: w, height: h }, `?store=local&lang=${lang}&center=71.4008,51.1278&zoom=${w < 700 ? 16.9 : 17.5}&pitch=60&bearing=-30`, SHOWCASE);
    await shot(p, `all_${w}_${lang}.png`); // у акимата в демо каталог открыт сразу — это и есть кадр каталога
    await p.context().close();
  }
}
// 3. Постройка сквера, замедленная до 6 с: кадры по долям времени.
if (want("build_")) {
  const BUILD = 6000;
  const p = await open({ width: 1366, height: 768 }, `?reset=1&store=local&lang=ru&build_ms=${BUILD}&center=71.4006,51.1276&zoom=18.6&pitch=60&bearing=-30`);
  await p.addStyleTag({ content: ".b3d-toasts{visibility:hidden!important}" });
  await p.click(".b3d-card[data-kind=square]");
  const [x, y] = await p.evaluate((ll) => { const q = __map.project(ll), r = __map.getCanvas().getBoundingClientRect(); return [q.x + r.left, q.y + r.top]; }, [71.4004, 51.1278]);
  await p.mouse.move(x, y, { steps: 2 });
  await p.mouse.click(x, y);
  await p.click("[data-action=place]", { timeout: 5000 });
  const t0 = Date.now();
  for (const f of [0.1, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0]) {
    const wait = t0 + f * BUILD - Date.now();
    if (wait > 0) await p.waitForTimeout(wait);
    if (f >= 1) await settle(p);
    await shot(p, `build_${f.toFixed(2)}.png`);
  }
  await p.context().close();
}
await browser.close();
server.close();
console.log(`кадров ${made.length} → ${path.relative(ROOT, OUT)}`);
