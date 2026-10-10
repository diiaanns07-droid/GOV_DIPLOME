// R12 round 14 × офлайн-подложка (ветка claude/r14-offline, web/civic/offline/): подпись улицы R12 на локальных глифах.
//   node --test --test-concurrency=1 tests/civic/R12/map/r12_offline_glyphs.test.mjs
//   R12_SHOTS=research/round-14-results/R12/screenshots node --test tests/civic/R12/map/r12_offline_glyphs.test.mjs
// Нужны шрифты офлайн-подложки web/civic/offline/fonts/Noto Sans Regular/*.pbf (после того как R01 возьмёт офлайн-ветку);
// без них тест NOT_RUN. Сеть закрыта: любой запрос не к 127.0.0.1 обрывается — проверяется именно работа без интернета.
// Проверяет: подпись улицы R12 появляется со шрифтом подложки, в ҚАЗ — казахское имя (ә, ғ, қ, ң, ө, ұ, ү, һ, і),
// без предупреждений о глифах; плоские слои R12 — под 3D-зданиями «akim-3d» (как BirgeOffline.buildingLayer), значки — над ними.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { mkdirSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "./serve.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../../../..");
const FONT = "web/civic/offline/fonts/Noto Sans Regular/1024-1279.pbf";   // кириллица с казахскими буквами
function loadPlaywright() {
  try { return createRequire(import.meta.url)("playwright"); } catch (e) { /* fall through */ }
  try { return createRequire(path.join(execSync("npm root -g", { encoding: "utf8" }).trim(), "x.js"))("playwright"); } catch (e) { return null; }
}
const pw = loadPlaywright();
const SKIP = !pw ? "playwright is not installed (NOT_RUN)"
  : !existsSync(path.join(ROOT, FONT)) ? "нет глифов офлайн-подложки " + FONT + " (NOT_RUN до слияния claude/r14-offline)" : false;
const SHOTS = process.env.R12_SHOTS ? path.resolve(ROOT, process.env.R12_SHOTS) : null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const STREETS = "/tests/civic/R12/map/fixtures/.generated/streets_demo_area.json";

let server, base, browser;
before(async () => {
  if (SKIP) return;
  if (!existsSync(path.join(ROOT, STREETS.slice(1)))) execSync("python3 -B " + path.join(HERE, "make_streets_fixture.py"), { cwd: ROOT, stdio: "ignore" });
  server = createServer();
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  base = "http://127.0.0.1:" + server.address().port;
  browser = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
});
after(async () => {
  if (browser) await browser.close();
  if (server) server.close();
});

test("r12 × offline basemap: street label on local glyphs, Kazakh name in ҚАЗ, flat layers under akim-3d", { skip: SKIP }, async () => {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const warns = [], external = [];
  page.on("console", (m) => { if (m.type() === "warning" || m.type() === "error") warns.push(m.text()); });
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => { external.push(r.request().url()); return r.abort(); });
  // Переключатель языка как у R11 (BirgeI18n.getLang + событие birge:lang); словарь не нужен.
  await page.addInitScript(() => { let lang = "ru"; window.BirgeI18n = { getLang: () => lang, has: () => false, t: (k) => k,
    setLang: (l) => { lang = l; document.dispatchEvent(new CustomEvent("birge:lang", { detail: { lang } })); } }; });
  const qs = new URLSearchParams({ today: "2026-10-10", basemap: "offline", fit: "0", persist: "0", objects: "/data/civic/astana/demo_synthetic.json",
    streets: STREETS, snapped: "/web/civic/map/demo_snapped.json" });
  await page.goto(base + "/tests/civic/R12/map/stand/?" + qs);
  await page.waitForFunction(() => window.__stand && window.__stand.instance && window.__stand.instance.getState().list === "ready", null, { timeout: 30000 });
  // Как офлайн-стиль: глифы из web/civic/offline/fonts, подпись подложки со шрифтом «Noto Sans Regular»,
  // 3D-здания — слой «akim-3d» (fill-extrusion), который web/map.js добавляет после модуля.
  await page.evaluate(async () => {
    const m = window.__stand.map;
    m.setGlyphs(location.origin + "/web/civic/offline/fonts/{fontstack}/{range}.pbf");
    m.addLayer({ id: "offline-label-road", type: "symbol", source: "stand-streets", layout: { visibility: "none", "text-field": "", "text-font": ["Noto Sans Regular"] } });
    window.__stand.destroy(); window.__stand.mount();   // модуль берёт шрифт подложки при добавлении слоёв
    await new Promise((r) => setTimeout(r, 300));
    m.addSource("offline-buildings", { type: "geojson", data: { type: "Feature", properties: { height: 24 }, geometry: { type: "Polygon",
      coordinates: [[[71.4270, 51.1720], [71.4282, 51.1720], [71.4282, 51.1728], [71.4270, 51.1728], [71.4270, 51.1720]]] } } });
    m.addLayer({ id: "akim-3d", type: "fill-extrusion", source: "offline-buildings", paint: { "fill-extrusion-height": ["get", "height"], "fill-extrusion-color": "#c9d3c2" } });
    m.jumpTo({ center: [71.4289, 51.1716], zoom: 16.4, pitch: 45, bearing: -15 });
  });
  await page.waitForFunction(() => window.__stand.instance.getState().list === "ready");
  const label = (lang) => page.evaluate(async (l) => {
    window.BirgeI18n.setLang(l);
    const m = window.__stand.map;
    await new Promise((r) => { const done = () => (m.loaded() && !m.isMoving() ? r() : setTimeout(done, 100)); setTimeout(done, 400); });
    await new Promise((r) => setTimeout(r, 600));
    return { layer: !!m.getLayer("civic-r03-street-label"), font: m.getLayoutProperty("civic-r03-street-label", "text-font"),
      texts: [...new Set(m.queryRenderedFeatures({ layers: ["civic-r03-street-label"] }).map((f) => f.properties.street))] };
  }, lang);
  const ru = await label("ru");
  assert.equal(ru.layer, true, "слой подписи улицы R12 есть (у стиля есть glyphs)");
  assert.deepEqual(ru.font, ["Noto Sans Regular"]);
  assert.deepEqual(ru.texts, ["улица Сакена Сейфуллина"], JSON.stringify(ru));
  const kk = await label("kk");
  assert.deepEqual(kk.texts, ["Сәкен Сейфуллин көшесі"], JSON.stringify(kk));
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "offline-glyphs-street-label-kk-1366.png") });
  const order = await page.evaluate(() => { const ids = window.__stand.map.getStyle().layers.map((l) => l.id);
    return { ext: ids.indexOf("akim-3d"), line: ids.indexOf("civic-r03-line"), approx: ids.indexOf("civic-r03-approx-fill"),
      point: ids.indexOf("civic-r03-point"), label: ids.indexOf("civic-r03-street-label") }; });
  assert.ok(order.line < order.ext && order.approx < order.ext, "линии и области — под зданиями: " + JSON.stringify(order));
  assert.ok(order.point > order.ext && order.label > order.ext, "значки и подписи — над зданиями: " + JSON.stringify(order));
  assert.deepEqual(warns.filter((t) => /glyph|font|pbf|could not be loaded/i.test(t)), [], warns.join("\n"));
  assert.deepEqual(external, [], "ни одного запроса в интернет");
  await ctx.close();
});
