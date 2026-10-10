// R12 round 14: точность карты в браузере (стенд, настоящий MapLibre 5.6.2, Chromium).
//   node --test --test-concurrency=1 tests/civic/R12/map/r12_accuracy.test.mjs
//   R12_SHOTS=research/round-14-results/R12/screenshots node --test tests/civic/R12/map/r12_accuracy.test.mjs
// Данные: демо-срез R05 (data/civic/astana/demo_synthetic.json — СИНТЕТИКА) и demo_snapped.json R12.
// Подложка: OpenFreeMap в облаке отвечает 403, поэтому на стенде рисуются настоящие оси улиц OSM
// (рёбра графа, tests/civic/R12/map/make_streets_fixture.py) — без домов и 3D-зданий.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { mkdirSync, readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "./serve.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../../../..");
function loadPlaywright() {
  try { return createRequire(import.meta.url)("playwright"); } catch (e) { /* fall through */ }
  try { return createRequire(path.join(execSync("npm root -g", { encoding: "utf8" }).trim(), "x.js"))("playwright"); } catch (e) { return null; }
}
const pw = loadPlaywright();
const SKIP = pw ? false : "playwright is not installed (NOT_RUN)";
const SHOTS = process.env.R12_SHOTS ? path.resolve(ROOT, process.env.R12_SHOTS) : null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const STREETS = "/tests/civic/R12/map/fixtures/.generated/streets_demo_area.json";
const SNAPPED = JSON.parse(readFileSync(path.join(ROOT, "web/civic/map/demo_snapped.json"), "utf8"));
const DELAY = "demo-astana-roadworks-delay";

let server, base, browser;
before(async () => {
  if (!pw) return;
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

async function open(params, viewport) {
  const ctx = await browser.newContext({ viewport: viewport || { width: 1366, height: 768 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|ERR_FAILED/.test(m.text())) errors.push(m.text()); });
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  const qs = new URLSearchParams(Object.assign({ today: "2026-10-10", basemap: "offline", fit: "0", persist: "0",
    objects: "/data/civic/astana/demo_synthetic.json", streets: STREETS }, params));
  await page.goto(base + "/tests/civic/R12/map/stand/?" + qs);
  await page.waitForFunction(() => window.__stand && window.__stand.instance && window.__stand.instance.getState().list === "ready", null, { timeout: 30000 });
  return { ctx, page, errors };
}
const features = (page) => page.evaluate(async () => (await window.__stand.map.getSource("civic-r03-objects").getData()).features);
async function frameDelay(page) {
  await page.evaluate(() => { window.__stand.map.jumpTo({ center: [71.4289, 51.1716], zoom: 16.2, pitch: 0, bearing: 0 }); });
  await page.waitForFunction(() => window.__stand.map.loaded() && !window.__stand.map.isMoving(), null, { timeout: 10000 });
  await page.waitForTimeout(400);
}

test("r12: demo closure is drawn along the OSM street, not by hand", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ snapped: "/web/civic/map/demo_snapped.json" });
  await page.waitForFunction(async () => (await window.__stand.map.getSource("civic-r03-objects").getData()).features.some((f) => f.properties.snapped), null, { timeout: 10000 });
  const fs = await features(page);
  const line = fs.filter((f) => f.properties.cid === DELAY);
  assert.equal(line.length, 1);
  assert.equal(line[0].geometry.type, "LineString");
  assert.deepEqual(line[0].geometry.coordinates, SNAPPED.items[DELAY].geometry.coordinates);
  assert.equal(line[0].properties.exact, true);
  assert.equal(line[0].properties.street, "улица Сакена Сейфуллина");
  // Каждая линия на карте — привязанная (ни одной «от руки»).
  for (const f of fs.filter((x) => x.geometry.type === "LineString")) assert.equal(f.properties.snapped, true, f.properties.cid);
  // Демо-линия, которую нельзя честно положить на одну улицу, — областью, не крюком по соседним улицам.
  assert.deepEqual(fs.filter((f) => f.properties.cid === "demo-astana-roadworks-completed").map((f) => f.geometry.type), ["Polygon"]);
  // Примерная точка — область «примерное место» + значок.
  const approx = fs.filter((f) => f.properties.cid === "demo-astana-construction-unknown").map((f) => f.geometry.type);
  assert.deepEqual(approx, ["Polygon", "Point"]);
  // Карточка говорит, где участок, простыми словами.
  await page.evaluate((id) => window.__stand.instance.selectObject(id), DELAY);
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready", null, { timeout: 8000 });
  const card = await page.locator(".civic-r03-card").innerText();
  assert.match(card, /Участок улицы по карте OSM: улица Сакена Сейфуллина/);
  assert.doesNotMatch(card, /ребр|граф|геометри/i, "в интерфейсе нет технических слов");
  await page.evaluate(() => window.__stand.instance.selectObject(null));
  await frameDelay(page);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "after-closure-1366.png") });
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("r12: before — the same record without snapping is a free-hand line that leaves the street", { skip: SKIP }, async () => {
  // Старый модуль рисовал исходные 3 точки линией. Сейчас без demo_snapped.json примерная линия
  // показывается областью «примерное место»; для скриншота «было» рисуем исходную линию на стенде отдельно.
  const { ctx, page, errors } = await open({});
  const fs = await features(page);
  const raw = fs.filter((f) => f.properties.cid === DELAY);
  assert.deepEqual(raw.map((f) => [f.geometry.type, f.properties.exact]), [["LineString", false]],
    "без файла привязки — исходная линия только пунктиром (примерно), не сплошной");
  const hand = SNAPPED.items[DELAY].original_coordinates;
  await page.evaluate((coords) => {
    const m = window.__stand.map;
    // На снимке «было» — только старая линия и улицы (слои модуля скрыты, чтобы не мешала область).
    for (const l of m.getStyle().layers) if (l.id.startsWith("civic-r03-")) m.setLayoutProperty(l.id, "visibility", "none");
    m.addSource("before-hand", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } } });
    m.addLayer({ id: "before-hand-casing", type: "line", source: "before-hand", paint: { "line-color": "#fff", "line-width": 9 } });
    m.addLayer({ id: "before-hand", type: "line", source: "before-hand", paint: { "line-color": "#b4470f", "line-width": 5, "line-dasharray": [1.4, 1.1] } });
  }, hand);
  await frameDelay(page);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "before-closure-1366.png") });
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("r12: flat layers stay under host 3D buildings added after the module; points stay on top", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ snapped: "/web/civic/map/demo_snapped.json" });
  const order = await page.evaluate(async () => {
    const m = window.__stand.map;
    // Хост (как web/map.js «akim-3d») добавляет 3D-здания ПОСЛЕ модуля, перед своими подписями.
    m.addSource("host-buildings", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "Polygon",
      coordinates: [[[71.427, 51.172], [71.428, 51.172], [71.428, 51.1727], [71.427, 51.1727], [71.427, 51.172]]] } } });
    m.addLayer({ id: "host-3d", type: "fill-extrusion", source: "host-buildings", paint: { "fill-extrusion-height": 30, "fill-extrusion-color": "#c9d3c2" } });
    await new Promise((r) => setTimeout(r, 300));
    const ids = m.getStyle().layers.map((l) => l.id);
    return { ext: ids.indexOf("host-3d"), line: ids.indexOf("civic-r03-line"), approx: ids.indexOf("civic-r03-approx-fill"), point: ids.indexOf("civic-r03-point") };
  });
  assert.ok(order.line < order.ext && order.approx < order.ext, JSON.stringify(order));
  assert.ok(order.point > order.ext, "значки — над зданиями: " + JSON.stringify(order));
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("r12: phone 375 px — the snapped closure and the card fit without horizontal scroll", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ snapped: "/web/civic/map/demo_snapped.json" }, { width: 375, height: 740 });
  await page.waitForFunction(async () => (await window.__stand.map.getSource("civic-r03-objects").getData()).features.some((f) => f.properties.snapped), null, { timeout: 10000 });
  await frameDelay(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(overflow <= 0, "горизонтальная прокрутка " + overflow + " px");
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "after-closure-375.png") });
  assert.deepEqual(errors, []);
  await ctx.close();
});

// R01 INTEGRATION §7: при смене режима (карта → учебная модель) модуль уничтожается, пока воркер MapLibre ещё
// разбирает тайл с нашим слоем «Пример»; раньше картинка кольца снималась сразу и воркер получал
// «Image "civic-r03-demo-ring" could not be loaded». Теперь картинка снимается после idle; повторный mount до
// этого момента берёт ту же картинку.
test("r12: destroy while tiles are in flight — no missing demo-ring image; a remount before idle keeps the ring", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ snapped: "/web/civic/map/demo_snapped.json" });
  const warns = [];
  page.on("console", (m) => { if (m.type() === "warning" || m.type() === "error") warns.push(m.text()); });
  await page.evaluate(() => window.__stand.map.jumpTo({ center: [71.4289, 51.1716], zoom: 14, pitch: 0, bearing: 0 }));
  for (let i = 0; i < 6; i++) {
    // новые данные → новый разбор тайлов в воркере → сразу destroy (как переключение режима оболочкой)
    await page.evaluate((k) => {
      const s = window.__stand;
      s.map.jumpTo({ center: [71.4289 + k * 0.004, 51.1716], zoom: 14 + (k % 3) });
      s.instance.refresh();
      s.destroy();
    }, i);
    await page.waitForTimeout(i % 2 ? 30 : 400);
    // remount до idle: картинка ещё на карте или добавляется заново — слой «Пример» её находит
    await page.evaluate(() => window.__stand.mount());
    await page.waitForFunction(() => window.__stand.instance.getState().list === "ready", null, { timeout: 15000 });
  }
  await page.waitForFunction(() => window.__stand.map.loaded(), null, { timeout: 10000 });
  await page.waitForTimeout(1500);
  const live = await page.evaluate(() => ({ ring: window.__stand.map.hasImage("civic-r03-demo-ring"), layer: !!window.__stand.map.getLayer("civic-r03-point-synthetic") }));
  assert.deepEqual(live, { ring: true, layer: true }, "после последнего mount кольцо на месте (отложенное снятие его не тронуло)");
  // окончательный destroy: картинка снимается, когда карта затихла
  await page.evaluate(() => window.__stand.destroy());
  await page.waitForFunction(() => !window.__stand.map.hasImage("civic-r03-demo-ring"), null, { timeout: 8000 });
  assert.equal(warns.filter((t) => /could not be loaded|civic-r03-demo-ring/.test(t)).length, 0, warns.join("\n"));
  assert.deepEqual(errors, []);
  await ctx.close();
});
