// R05 · разбор R11 «День 3», пп. 20–26: по каждому пункту — проверка и скриншоты 1366 / 375 × ru / kk.
//   node tests/civic/R05/build3d/ux_day3_check.mjs [--kit <корень выгрузки R11 с web/civic/ui-kit и web/civic/i18n>]
// Демо-страница со своего статического сервера: API R06 нет (404) → заглушка этого устройства, ?reset=1 — 4 примера.
// Отчёт: research/round-14-results/R05/runs/ux_day3_check.json, скриншоты screens/d3_<пункт>_<ширина>_<язык>.png.
import http from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const WEB = path.join(ROOT, "web");
const OUT = path.join(ROOT, "research/round-14-results/R05");
const KIT = (() => {
  const i = process.argv.indexOf("--kit");
  return i > 0 && process.argv[i + 1] ? path.resolve(process.argv[i + 1], "web") : null;
})();
let chromium;
for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {
  try {
    ({ chromium } = require(id));
    break;
  } catch (e) {
    /* следующий */
  }
}
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".txt": "text/plain; charset=utf-8" };
const server = http.createServer(async (req, res) => {
  const rel = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
  if (rel.startsWith("/api/")) {
    res.writeHead(404, { "Content-Type": "application/json" });
    return res.end('{"error":{"code":"not_found"}}');
  }
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
    res.end("not found");
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}/civic/build3d/demo.html`;

const results = [];
const check = (id, ok, detail) => {
  results.push({ id, status: ok ? "PASS" : "FAIL", detail });
  console.log((ok ? "PASS " : "FAIL ") + id + " — " + JSON.stringify(detail));
};
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const errors = [];
const EXPECT = {
  ru: { title: "3D-превью", hint: "Нажмите на проект, чтобы проголосовать" },
  kk: { title: "3D-көрініс", hint: "Дауыс беру үшін жобаны басыңыз" },
};
const VIEWS = [
  { w: 1366, vp: { width: 1366, height: 768 }, extra: {} },
  { w: 375, vp: { width: 375, height: 812 }, extra: { hasTouch: true, isMobile: true } },
];
async function open(view, query) {
  const ctx = await browser.newContext(Object.assign({ viewport: view.vp }, view.extra));
  const p = await ctx.newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(BASE + query);
  await p.waitForFunction(() => window.__b3d && __b3d.getState().phase === "ready", null, { timeout: 60000 });
  await idle(p);
  return p;
}
const idle = (p) =>
  p.waitForFunction(() => __map.loaded() && !__map.isMoving() && !__b3d.getState().animating, null, { timeout: 60000 }).then(() => p.waitForTimeout(300));
const settle = (p) =>
  p.waitForFunction(() => !document.getAnimations().some((a) => a.playState === "running" || a.pending), null, { timeout: 5000 }).catch(() => {});
async function shot(p, name) {
  await settle(p);
  await p.screenshot({ path: path.join(OUT, "screens", name) });
}
// Ключи вместо текста (п. 26): «build3d.» / «proposal.» в видимом тексте.
const rawKeys = (p) => p.evaluate(() => (document.body.innerText.match(/\b(build3d|proposal|common)\.[a-z_.]+/g) || []).slice(0, 3));
// Проекты на экране: подпись «Проект · …» (она стоит над моделью, у освещения — над средней опорой) видна целиком,
// в пределах карты, не под шапкой (верхние 64 px) и не под панелью модуля.
const onScreen = (p) =>
  p.evaluate(() => {
    const c = __map.getCanvas().getBoundingClientRect(), d = document.querySelector(".b3d-dock").getBoundingClientRect();
    return [...document.querySelectorAll(".b3d-label:not(.b3d-label--hidden)")].map((b) => {
      const r = b.getBoundingClientRect();
      const free = r.width > 0 && r.left >= c.left && r.right <= c.right && r.top >= c.top + 64 && r.bottom <= c.bottom &&
        !(r.bottom > d.top && r.top < d.bottom && r.right > d.left && r.left < d.right);
      return free ? { id: b.getAttribute("data-id"), x: Math.round(r.left + r.width / 2), y: Math.round(r.bottom) } : null;
    }).filter(Boolean);
  });
await mkdir(path.join(OUT, "screens"), { recursive: true });

for (const view of VIEWS) {
  for (const lang of ["ru", "kk"]) {
    const tag = `${view.w}_${lang}`;
    try {
      // П. 20 + 22 + 23 + 25: стартовый вид — крупный план проектов, шапка «3D-превью», кнопка «3D», дворы OSM.
      let p = await open(view, `?reset=1&lang=${lang}`);
      const start = await p.evaluate(() => {
        const b3 = document.getElementById("demo-3d"), r = b3.getBoundingClientRect();
        const yards = __map.getLayer("yards") ? __map.queryRenderedFeatures({ layers: ["yards"] }).length : -1;
        return { zoom: +__map.getZoom().toFixed(2), title: document.getElementById("demo-title").textContent.trim(), btn3d: b3.innerText.trim(),
          btn: [Math.round(r.width), Math.round(r.height)], yards, headerTags: document.querySelectorAll(".demo-head .bk-tag, header .bk-tag").length };
      });
      const visible = await onScreen(p);
      // Ноутбук — несколько проектов в кадре; телефон 375 — хотя бы ближайший (UX_REVIEW: «~17,4 у ближайшего проекта»).
      const need = view.w >= 1024 ? 2 : 1;
      check(`r11_20_start_close_up_${tag}`, Math.abs(start.zoom - 17.4) < 0.06 && visible.length >= need, { zoom: start.zoom, projects_on_screen: visible.length, need });
      check(`r11_22_23_header_title_and_3d_label_${tag}`, start.title === EXPECT[lang].title && start.btn3d === "3D" && start.btn[0] >= 44 && start.btn[1] >= 44 && start.headerTags === 0,
        { title: start.title, btn3d: start.btn3d, size: start.btn, tags_in_header: start.headerTags });
      check(`r11_25_offline_basemap_osm_yards_${tag}`, start.yards > 0, { yards_rendered: start.yards });
      const keys0 = await rawKeys(p);
      await shot(p, `d3_20_start_${tag}.png`);

      // П. 20: выбор в каталоге с дальнего вида → плавно к 17.5, призрак виден.
      await p.evaluate(() => __map.jumpTo({ zoom: 16.4 }));
      await idle(p);
      await (view.extra.hasTouch ? p.tap(".b3d-card[data-kind=square]") : p.click(".b3d-card[data-kind=square]"));
      await p.waitForTimeout(200);
      await idle(p);
      const pick = await p.evaluate(() => ({ zoom: +__map.getZoom().toFixed(2), mode: __b3d.getState().mode }));
      check(`r11_20_catalog_pick_zooms_to_17_5_${tag}`, Math.abs(pick.zoom - 17.5) < 0.06 && pick.mode === "placing", pick);
      await shot(p, `d3_20_pick_${tag}.png`);
      await p.keyboard.press("Escape");
      if (view.extra.hasTouch) await p.evaluate(() => __b3d.cancel());
      await p.evaluate(() => __b3d.flyToProposals({ duration: 0 }));
      await idle(p);

      // П. 21: нажать на САМУ модель (не на подпись) → карточка; объект — на экране и не под карточкой; зона подписи 48.
      // Человек сначала двигает карту к объекту: ставим в центр карты ближайший к центру проект-точку (не освещение).
      const target = await p.evaluate(() => {
        const c = __map.getCenter();
        const pts = __b3d.getState().proposals.filter((q) => q.kind !== "lighting");
        pts.sort((a, b) => Math.hypot(a.geometry.coordinates[0] - c.lng, a.geometry.coordinates[1] - c.lat) - Math.hypot(b.geometry.coordinates[0] - c.lng, b.geometry.coordinates[1] - c.lat));
        return { id: pts[0].id, kind: pts[0].kind, ll: pts[0].geometry.coordinates };
      });
      await p.evaluate((ll) => __map.jumpTo({ center: ll }), target.ll);
      await idle(p);
      Object.assign(target, await p.evaluate((id) => { const g = __b3d._project(id, [0, 0, 1]), c = __map.getCanvas().getBoundingClientRect(); return { x: c.left + g.x, y: c.top + g.y }; }, target.id));
      const lab = await p.evaluate(() => {
        const b = document.querySelector(".b3d-label:not(.b3d-label--dot)"), pill = b && b.querySelector(".b3d-label__pill");
        return b ? { zone: Math.round(b.getBoundingClientRect().height), pill: Math.round(pill.getBoundingClientRect().height) } : null;
      });
      let cursor = "n/a";
      if (!view.extra.hasTouch) {
        await p.mouse.move(target.x, target.y + 6);
        await p.waitForTimeout(150);
        cursor = await p.evaluate(() => __map.getCanvas().style.cursor);
        await p.mouse.click(target.x, target.y + 6);
      } else {
        await p.touchscreen.tap(target.x, target.y + 6);
      }
      await p.waitForFunction(() => document.querySelector(".b3d-dock[data-state=card]"), null, { timeout: 10000 });
      await idle(p);
      const card = await p.evaluate((id) => {
        const g = __b3d._project(id, [0, 0, 0]), c = __map.getCanvas().getBoundingClientRect(), d = document.querySelector(".b3d-dock").getBoundingClientRect();
        const x = c.left + g.x, y = c.top + g.y;
        return { selected: __b3d.getState().selected, x: Math.round(x), y: Math.round(y), under: x >= d.left && x <= d.right && y >= d.top && y <= d.bottom,
          onScreen: x > c.left && x < c.right && y > c.top && y < c.bottom };
      }, target.id);
      check(`r11_21_model_click_opens_card_object_visible_${tag}`,
        card.selected === target.id && !card.under && card.onScreen && lab && lab.zone >= 48 && lab.pill >= 40 && (view.extra.hasTouch || cursor === "pointer"),
        { clicked: target.kind, cursor, label: lab, object: { x: card.x, y: card.y, under_card: card.under } });
      const keys1 = await rawKeys(p);
      await shot(p, `d3_21_card_${tag}.png`);
      await p.context().close();

      // П. 24: житель — подсказка про голос, каталога нет.
      p = await open(view, `?reset=1&lang=${lang}&role=resident`);
      const res = await p.evaluate(() => ({ hint: (document.querySelector(".b3d-dock") || {}).innerText || "", cards: document.querySelectorAll(".b3d-card").length }));
      check(`r11_24_resident_hint_${tag}`, res.hint.trim() === EXPECT[lang].hint && res.cards === 0, { hint: res.hint.trim(), catalog_cards: res.cards });
      const keys2 = await rawKeys(p);
      await shot(p, `d3_24_resident_${tag}.png`);
      await p.context().close();

      // П. 26: ни одного ключа вместо текста на этих экранах.
      const keys = keys0.concat(keys1, keys2);
      check(`r11_26_no_raw_keys_${tag}`, keys.length === 0, keys);
    } catch (e) {
      check(`run_${tag}`, false, e.message.split("\n")[0]);
    }
  }
}
check("no_page_errors", errors.length === 0, errors.slice(0, 3));
await browser.close();
server.close();
await mkdir(path.join(OUT, "runs"), { recursive: true });
await writeFile(path.join(OUT, "runs", "ux_day3_check.json"), JSON.stringify({ generated_at: new Date().toISOString(),
  ui_kit_i18n: KIT ? "выгрузка --kit" : "web/civic этой ветки", checks: results }, null, 1) + "\n");
const failed = results.filter((r) => r.status !== "PASS").length;
console.log(`Итого: ${results.length - failed} PASS, ${failed} FAIL`);
process.exit(failed ? 1 : 0);
