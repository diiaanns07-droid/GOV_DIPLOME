// R05 · раунд 15 · 3D-Астана в собранном приложении (оболочка R01): ориентиры при наклоне, ленивая загрузка,
// значки жалоб поверх моделей, строка «условные модели» в «?» легенды, ҚАЗ/РУС, 1366 / 1024 / 375.
//
// Нужен запущенный стенд (COMMON «КАК ПОДНЯТЬ СТЕНД»):  CIVIC_DB_PATH=… CIVIC_DEMO=1 python3 -B app.py --port 8655
// и в ui/web_server.py — пути build3d/build3d-landmarks.js, build3d/data/landmarks.json (patches/R01_web_server_assets.patch).
// Запуск:  NODE_PATH=$(npm root -g) node tests/civic/R05/round15/app_landmarks_check.mjs [--url http://127.0.0.1:8655] [--shots папка]
// Отчёт — research/round-15-results/R05/runs/app_landmarks_check.json. В облаке WebGL — SwiftShader (программная графика),
// подложки нет (упрощённый фон): так и записано в отчёте.
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { execSync } from "node:child_process";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const arg = (name, def) => {
  const i = process.argv.indexOf(name);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
};
const URL0 = arg("--url", "http://127.0.0.1:8655");
const SHOTS = arg("--shots", path.join(ROOT, "research/round-15-results/R05/screens"));
const ONLY = arg("--only", null);
const { chromium } = require("playwright");

const results = [];
function record(id, status, detail) {
  results.push({ id, status, detail });
  console.log(`${status}  ${id}${detail ? "  — " + (typeof detail === "string" ? detail : JSON.stringify(detail)) : ""}`);
}
async function check(id, fn) {
  if (ONLY && !new RegExp(ONLY).test(id)) return;
  try {
    const r = await fn();
    if (r && r.status) record(id, r.status, r.detail);
    else record(id, r === false ? "FAIL" : "PASS", r && r !== true ? r : undefined);
  } catch (e) {
    record(id, "FAIL", String(e.message || e).split("\n")[0]);
  }
}
const assert = (c, m) => {
  if (!c) throw new Error(m);
};

const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const pageErrors = [];
async function open(viewport, lang) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  await ctx.addInitScript((l) => {
    try {
      localStorage.setItem("birge.lang", l);
      localStorage.setItem("birge-lang", l);
    } catch (e) {}
  }, lang);
  const page = await ctx.newPage();
  page._requests = [];
  page.on("request", (r) => page._requests.push(r.url()));
  page.on("pageerror", (e) => pageErrors.push(`${viewport.width} ${lang}: ${e.message}`));
  await page.goto(URL0 + "/?lang=" + lang);
  await page.waitForFunction(() => window.CivicShell && window.CivicShell.build3d && typeof window.CivicShell.build3d.getState === "function", null, { timeout: 60000 });
  await page.waitForFunction(() => { const m = window.CivicShell.build3d.getState(); return m.phase !== "waiting_map"; }, null, { timeout: 60000 });
  return page;
}
const lm = (page) => page.evaluate(() => window.CivicShell.build3d.getState().landmarks);
// Карта — глобальная переменная web/map.js (window.map — это элемент #map).
const mapEval = (page, fn, arg) => page.evaluate(new Function("arg", "const m = map; return (" + fn + ")(m, arg);"), arg);
async function settle(page, extra = 0) {
  await page.waitForFunction(() => { try { return !map.isMoving() && map.loaded(); } catch (e) { return false; } }, null, { timeout: 60000 });
  await page.waitForTimeout(400 + extra);
}
async function shot(page, name) {
  await mkdir(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, name + ".png") });
}

const page = await open({ width: 1366, height: 768 }, "ru");

await check("flat_map_loads_nothing", async () => {
  await settle(page, 1500);
  const s = await lm(page);
  const req = page._requests.filter((u) => /landmarks|three\.module/.test(u));
  assert(s.phase === "idle" && !s.shown, "ориентиры на плоской карте: " + JSON.stringify(s));
  assert(!req.length, "запросы на плоской карте: " + req.join(", "));
  return { phase: s.phase, requests: req.length };
});

await check("tilt_city_center_shows_landmarks", async () => {
  await page.evaluate(() => window.CivicShell.build3d.flyToLandmarks());
  await page.waitForFunction(() => { const s = window.CivicShell.build3d.getState().landmarks; return s.shown && s.phase === "ready" && s.k === 1; }, null, { timeout: 90000 });
  await settle(page, 1200);
  const s = await lm(page);
  assert(s.count === 5 && s.visible >= 2, "видимых ориентиров: " + JSON.stringify(s));
  // Байтерек и Хан Шатыр — в кадре и вне панели слева (ноутбук 1366): «узнаются с первого взгляда».
  const scr = await page.evaluate(() => ["baiterek", "khan-shatyr"].map((id) => window.CivicShell.build3d._landmarkScreen(id, 0)));
  assert(scr.every((p) => p && p.x > 420 && p.x < 1290 && p.y > 80 && p.y < 740), "Байтерек / Хан Шатыр не в кадре: " + JSON.stringify(scr));
  assert(s.triangles > 0 && s.triangles <= 50000, "бюджет треугольников: " + s.triangles);
  const req = page._requests.filter((u) => /build3d-landmarks\.js|landmarks\.json|three\.module/.test(u)).map((u) => u.replace(URL0, ""));
  await shot(page, "landmarks_1366_ru");
  return { visible: s.visible, triangles: s.triangles, lazy: req };
});

await check("landmarks_on_screen_where_osm_says", async () => {
  const pts = await page.evaluate(() => ["baiterek", "khan-shatyr", "akorda"].map((id) => {
    const b = window.CivicShell.build3d;
    const top = b._landmarkScreen(id), base = b._landmarkScreen(id, 0);
    return { id, top, base };
  }));
  // Основание модели совпадает с точкой карты (map.project) — модель стоит на своих координатах.
  const data = await page.evaluate(() => fetch("/civic/build3d/data/landmarks.json").then((r) => r.json()));
  const out = [];
  const vw = page.viewportSize();
  for (const p of pts) {
    // Только ориентиры в кадре (за спиной камеры проекция теряет смысл).
    if (!p.base || !p.top || p.base.depth <= 0 || p.base.depth >= 1 || p.base.x < 0 || p.base.x > vw.width || p.base.y < 0 || p.base.y > vw.height) continue;
    const l = data.landmarks.find((x) => x.id === p.id);
    const q = await mapEval(page, "(m, ll) => m.project(ll)", [l.lon, l.lat]);
    const d = Math.hypot(q.x - p.base.x, q.y - p.base.y);
    out.push({ id: p.id, base_px_off: Math.round(d * 10) / 10, top_above_base_px: Math.round(p.base.y - p.top.y) });
    assert(d < 2, p.id + ": основание модели не на своей точке, " + d.toFixed(1) + " px");
    assert(p.base.y - p.top.y > 20, p.id + ": модель не поднялась над землёй");
  }
  assert(out.length >= 2, "в кадре меньше двух ориентиров: " + JSON.stringify(pts));
  return out;
});

await check("basemap_landmark_buildings_hidden_while_models_shown", async () => {
  const s = await lm(page);
  const layer = await mapEval(page, "(m) => m.getLayer('akim-3d-landmark') ? m.getLayoutProperty('akim-3d-landmark', 'visibility') || 'visible' : null");
  if (layer === null) return { status: "NOT_RUN", detail: "в облаке нет подложки со зданиями (слой akim-3d-landmark не создан) — проверить на ноутбуке (LOCAL)" };
  assert(layer === "none" && s.basemapHidden, "слой зданий-ориентиров подложки виден: " + layer);
  return { layer };
});

await check("legend_q_has_conditional_model_note", async () => {
  const has = await page.evaluate(() => !!document.querySelector("#birge-legend .birge-legend-q"));
  if (!has) return { status: "NOT_RUN", detail: "строки легенды нет на этом экране" };
  await page.click("#birge-legend .birge-legend-q");
  await page.waitForTimeout(300);
  const note = await page.evaluate(() => { const n = document.querySelector("#birge-legend .b3d-lm-note"); return n ? { text: n.textContent, hidden: n.hidden, visible: !!(n.offsetWidth && n.offsetHeight) } : null; });
  assert(note && !note.hidden && note.visible && /условн/i.test(note.text), "нет строки «условные модели»: " + JSON.stringify(note));
  await shot(page, "landmarks_legend_1366_ru");
  await page.click("#birge-legend .birge-legend-q");
  return note.text;
});

await check("complaint_badges_stay_above_models", async () => {
  // Значки жалоб R07 — HTML-маркеры (.r07-badge) поверх холста карты: по построению выше любой модели three.js.
  const r = await page.evaluate(() => {
    const canvas = document.querySelector(".maplibregl-canvas");
    const marker = document.querySelector(".maplibregl-marker.r07-badge");
    if (!marker) return null;
    const z = (el) => { let n = el, out = []; while (n && n !== document.body) { out.push(getComputedStyle(n).zIndex); n = n.parentElement; } return out; };
    return { markerAfterCanvas: !!(canvas.compareDocumentPosition(marker) & Node.DOCUMENT_POSITION_FOLLOWING), inMarkerPane: !!marker.closest(".maplibregl-canvas-container, .maplibregl-map") };
  });
  if (!r) return { status: "NOT_RUN", detail: "в кадре нет значков жалоб (демо-жалобы — в Нуре)" };
  assert(r.markerAfterCanvas, "маркер не поверх холста");
  return r;
});

await check("flat_again_hides_and_restores", async () => {
  await mapEval(page, "(m) => m.easeTo({ pitch: 0, bearing: 0, duration: 0 })");
  await settle(page, 300);
  const s = await lm(page);
  assert(!s.shown && s.visible === 0, "после «плоской» карты ориентиры видны: " + JSON.stringify(s));
  const note = await page.evaluate(() => { const n = document.querySelector(".b3d-lm-note"); return n ? n.hidden : null; });
  assert(note !== false, "строка легенды осталась видна");
  return s;
});

await check("tilted_far_zoom_hides_below_13", async () => {
  await mapEval(page, "(m) => m.easeTo({ zoom: 12.4, pitch: 50, duration: 0 })");
  await settle(page, 300);
  const s = await lm(page);
  assert(!s.shown || s.k === 0 || s.visible === 0, "на 12,4 масштабе ориентиры видны: " + JSON.stringify(s));
  await mapEval(page, "(m) => m.easeTo({ zoom: 14.2, duration: 0 })");
  await settle(page, 900);
  const s2 = await lm(page);
  assert(s2.shown && s2.visible > 0, "на 14,2 с наклоном ориентиров нет: " + JSON.stringify(s2));
  return { at12: s.visible, at14: s2.visible };
});

for (const [w, h, lang] of [[1366, 768, "kk"], [1024, 768, "ru"], [375, 812, "kk"], [375, 812, "ru"]]) {
  await check(`shot_${w}_${lang}`, async () => {
    const p = await open({ width: w, height: h }, lang);
    await settle(p, 800);
    await p.evaluate(() => window.CivicShell.build3d.flyToLandmarks());
    await p.waitForFunction(() => { const s = window.CivicShell.build3d.getState().landmarks; return s.shown && s.k === 1; }, null, { timeout: 90000 });
    await settle(p, 1200);
    await shot(p, `landmarks_${w}_${lang}`);
    const s = await lm(p);
    await p.context().close();
    return { visible: s.visible };
  });
}

let sha = "?";
try {
  sha = execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim();
} catch (e) {}
const report = { at: new Date().toISOString(), url: URL0, code_head: sha, env: "облако: Chromium headless + SwiftShader (программная графика), без подложки (упрощённый фон)", results, pageErrors };
await mkdir(path.join(ROOT, "research/round-15-results/R05/runs"), { recursive: true });
if (!ONLY) await writeFile(path.join(ROOT, "research/round-15-results/R05/runs/app_landmarks_check.json"), JSON.stringify(report, null, 1));
const fails = results.filter((r) => r.status === "FAIL").length;
console.log(`итог: ${results.filter((r) => r.status === "PASS").length} PASS / ${fails} FAIL / ${results.filter((r) => r.status === "NOT_RUN").length} NOT_RUN; ошибки страницы: ${pageErrors.length}`);
if (pageErrors.length) console.log(pageErrors.slice(0, 5).join("\n"));
await browser.close();
process.exit(fails ? 1 : 0);
