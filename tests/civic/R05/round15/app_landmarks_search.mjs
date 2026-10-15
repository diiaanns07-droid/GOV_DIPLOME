// R05 · раунд 15 · «Настоящий город» (поправка П1): поиск ориентира в шапке → перелёт камеры к настоящему зданию
// подложки с наклоном 3D. Моделей зданий нет — проверяем данные, подсказку, камеру и «уменьшить движение».
//
// Нужен стенд (COMMON «КАК ПОДНЯТЬ СТЕНД») с патчем R05 для R01:
//   research/round-15-results/R05/patches/R01_landmarks_search_basemap.patch (+ R01_web_server_assets.patch).
// Запуск:  NODE_PATH=$(npm root -g) node tests/civic/R05/round15/app_landmarks_search.mjs [--url http://127.0.0.1:8655] [--shots папка]
// Отчёт — research/round-15-results/R05/runs/app_landmarks_search.json. В облаке нет подложки со зданиями (упрощённый
// фон): вид здания и подписи — NOT_RUN, проверка на ноутбуке (LOCAL-12).
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const URL0 = arg("--url", "http://127.0.0.1:8655");
const SHOTS = arg("--shots", path.join(ROOT, "research/round-15-results/R05/screens"));
const { chromium } = require("playwright");
const DATA = JSON.parse(await readFile(path.join(ROOT, "web/civic/build3d/data/landmarks.json"), "utf8"));
const byId = Object.fromEntries(DATA.landmarks.map((l) => [l.id, l]));

const results = [];
const record = (id, status, detail) => { results.push({ id, status, detail }); console.log(`${status}  ${id}${detail ? "  — " + (typeof detail === "string" ? detail : JSON.stringify(detail)) : ""}`); };
async function check(id, fn) {
  try { const r = await fn(); if (r && r.status) record(id, r.status, r.detail); else record(id, r === false ? "FAIL" : "PASS", r && r !== true ? r : undefined); }
  catch (e) { record(id, "FAIL", String(e.message || e).split("\n")[0]); }
}
const assert = (c, m) => { if (!c) throw new Error(m); };
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const pageErrors = [];
async function open(viewport, lang, extra = {}) {
  const ctx = await browser.newContext(Object.assign({ viewport, deviceScaleFactor: 1 }, extra));
  const page = await ctx.newPage();
  page.on("pageerror", (e) => pageErrors.push(`${viewport.width} ${lang}: ${e.message}`));
  await page.goto(URL0 + "/?lang=" + lang);
  await page.waitForFunction(() => window.BirgeLandmarks && document.querySelector(".civic-explore-search input"), null, { timeout: 60000 });
  await page.waitForFunction(() => { try { return map.loaded() && !map.isMoving(); } catch (e) { return false; } }, null, { timeout: 60000 });
  if (lang === "kk") await page.evaluate(() => window.BirgeI18n?.setLang?.("kk"));
  await page.waitForTimeout(600);
  return page;
}
async function typeAndPick(page, text) {
  const input = page.locator(".civic-explore-search input");
  await input.click();
  await input.fill("");
  await input.type(text, { delay: 30 });
  await page.waitForSelector('.civic-explore-list [role="option"][data-kind="landmark"]', { timeout: 15000 });
  return page.evaluate(() => [...document.querySelectorAll('.civic-explore-list [role="option"]')].map((li) => ({ kind: li.dataset.kind, name: li.querySelector(".civic-explore-opt-name")?.textContent, place: li.querySelector(".civic-explore-opt-place")?.textContent })));
}
async function shot(page, name) { await mkdir(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + ".png") }); }
// Где на экране центр ориентира и где центр свободной части карты (как считает оболочка).
const cameraState = (page, id) => page.evaluate((l) => {
  const p = map.project([l.lon, l.lat]);
  return { x: Math.round(p.x), y: Math.round(p.y), zoom: +map.getZoom().toFixed(2), pitch: +map.getPitch().toFixed(1), bearing: +map.getBearing().toFixed(1),
    w: map.getCanvas().clientWidth, h: map.getCanvas().clientHeight };
}, byId[id]);

for (const [w, h, lang, q, id] of [[1366, 768, "ru", "Байтерек", "baiterek"], [1366, 768, "kk", "ақорда", "akorda"], [1024, 768, "ru", "пирамида", "palace-peace"], [375, 812, "kk", "хан шатыр", "khan-shatyr"], [375, 812, "ru", "экспо", "nur-alem"]]) {
  await check(`search_${q}_${w}_${lang}`, async () => {
    const page = await open({ width: w, height: h }, lang);
    const opts = await typeAndPick(page, q);
    const first = opts.find((o) => o.kind === "landmark");
    const want = byId[id].name[lang];
    assert(first && first.name === want, `подсказка ориентира: ${JSON.stringify(first)} (ждали «${want}»)`);
    assert(opts.findIndex((o) => o.kind === "landmark") <= 2, "ориентир не в первых строках: " + JSON.stringify(opts.slice(0, 4)));
    await shot(page, `search_${id}_${w}_${lang}`);
    const t0 = Date.now();
    await page.locator('.civic-explore-list [role="option"][data-kind="landmark"]').first().click();
    await page.waitForFunction(() => map.isMoving(), null, { timeout: 3000 }).catch(() => {});
    await page.waitForFunction(() => !map.isMoving(), null, { timeout: 15000 });
    const flightMs = Date.now() - t0;
    await page.waitForTimeout(1200); // автонаклон R01 (moveend) не должен доворачивать камеру
    const c = await cameraState(page, id);
    const cam = byId[id].camera;
    assert(Math.abs(c.pitch - cam.pitch) < 1.5, `наклон ${c.pitch} (ждали ${cam.pitch})`);
    assert(Math.abs(c.zoom - cam.zoom) < 0.05, `масштаб ${c.zoom} (ждали ${cam.zoom})`);
    assert(c.x > 0 && c.x < c.w && c.y > 60 && c.y < c.h, `здание вне экрана: ${JSON.stringify(c)}`);
    await shot(page, `flight_${id}_${w}_${lang}`);
    await page.context().close();
    return { suggestion: first, camera: c, flight_ms: flightMs };
  });
}

await check("reduced_motion_jumps_without_flight", async () => {
  const page = await open({ width: 1366, height: 768 }, "ru", { reducedMotion: "reduce" });
  await typeAndPick(page, "Хан");
  const t0 = Date.now();
  let moves = 0;
  await page.evaluate(() => { window.__moves = 0; map.on("move", () => window.__moves++); });
  await page.locator('.civic-explore-list [role="option"][data-kind="landmark"]').first().click();
  await page.waitForTimeout(400);
  moves = await page.evaluate(() => window.__moves);
  const c = await cameraState(page, "khan-shatyr");
  await page.context().close();
  assert(Math.abs(c.zoom - byId["khan-shatyr"].camera.zoom) < 0.05, "камера не у здания сразу: " + JSON.stringify(c));
  assert(moves <= 3, "есть полёт по кадрам: " + moves);
  return { moves, ms: Date.now() - t0 };
});

await check("basemap_landmark_lighter_and_labelled", async () => {
  const page = await open({ width: 1366, height: 768 }, "ru");
  const r = await page.evaluate(() => ({ landmarkLayer: !!map.getLayer("akim-3d-landmark"), label: !!map.getLayer("birge-landmark-label"),
    color: map.getLayer("akim-3d-landmark") ? map.getPaintProperty("akim-3d-landmark", "fill-extrusion-color") : null,
    centers: (window.BirgeBasemapStyle?.landmarks || []).map((l) => [l.id, l.center, l.radius]) }));
  await page.context().close();
  const fromFile = r.centers.every(([id, c]) => byId[id] && Math.abs(c[0] - byId[id].lon) < 1e-6 && Math.abs(c[1] - byId[id].lat) < 1e-6);
  if (!r.landmarkLayer) return { status: "NOT_RUN", detail: { why: "в облаке нет подложки со зданиями (OpenFreeMap недоступен) — вид проверяет LOCAL-12", centers_from_landmarks_json: fromFile } };
  assert(fromFile, "центры R01 не из landmarks.json: " + JSON.stringify(r.centers));
  assert(r.color === "#F6F4EF", "цвет ориентира: " + JSON.stringify(r.color));
  return r;
});

let sha = "?";
try { sha = execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim(); } catch (e) {}
const report = { at: new Date().toISOString(), url: URL0, code_head: sha, env: "облако: Chromium headless + SwiftShader, без подложки со зданиями (упрощённый фон)", results, pageErrors };
await mkdir(path.join(ROOT, "research/round-15-results/R05/runs"), { recursive: true });
await writeFile(path.join(ROOT, "research/round-15-results/R05/runs/app_landmarks_search.json"), JSON.stringify(report, null, 1));
const fails = results.filter((r) => r.status === "FAIL").length;
console.log(`итог: ${results.filter((r) => r.status === "PASS").length} PASS / ${fails} FAIL / ${results.filter((r) => r.status === "NOT_RUN").length} NOT_RUN; ошибки страницы: ${pageErrors.length}`);
if (pageErrors.length) console.log(pageErrors.slice(0, 5).join("\n"));
await browser.close();
process.exit(fails ? 1 : 0);
