// R05 · раунд 15 · патч R05 для подложки R01 (web/civic/shell/basemap-style.js) без браузера и без подложки.
// В облаке нет 3D-зданий (OpenFreeMap недоступен), поэтому вид проверяет LOCAL-12, а здесь — логика патча:
// центры, радиусы и подписи ориентиров берутся из landmarks.json; ориентир — «белый макет» (светлее соседей, без
// отдельной краски); без файла — запасные центры R01 и никаких ошибок.
// Файл R01 берётся из рабочей копии: если патч уже применён (сборка R01) — как есть, иначе недостающее (весь патч или
// дельта D1.2) накладывается на копию.
// Запуск: node --test tests/civic/R05/round15/test_basemap_patch.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, mkdirSync, copyFileSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const FILE = "web/civic/shell/basemap-style.js";
// Полный патч (D1/D1.1; в сборке R01 с B0.2) и дельта к сборке R01 B0.3 adb5fba9 (подпись из label, names, avoid).
const PATCH_FULL = path.join(ROOT, "research/round-15-results/R05/patches/R01_landmarks_search_basemap.patch");
const PATCH_D12 = path.join(ROOT, "research/round-15-results/R05/patches/R01_delta_b03.patch");
const DATA = JSON.parse(readFileSync(path.join(ROOT, "web/civic/build3d/data/landmarks.json"), "utf8"));
const byId = Object.fromEntries(DATA.landmarks.map((l) => [l.id, l]));

// Файл R01 из рабочей копии + то, чего в нём ещё нет: весь патч (FINAL-4) или только дельта D1.2 (сборки R01 B0.2–B0.3).
function patchedSource() {
  const src = readFileSync(path.join(ROOT, FILE), "utf8");
  if (src.includes("f.label || f.name")) return { src, how: "патч R05 уже в файле" };
  const patch = src.includes("applyLandmarksFile") ? PATCH_D12 : PATCH_FULL;
  const dir = mkdtempSync(path.join(os.tmpdir(), "r05-basemap-"));
  try {
    mkdirSync(path.join(dir, path.dirname(FILE)), { recursive: true });
    copyFileSync(path.join(ROOT, FILE), path.join(dir, FILE));
    execFileSync("git", ["apply", "--include=" + FILE, patch], { cwd: dir, stdio: "pipe" });
    return { src: readFileSync(path.join(dir, FILE), "utf8"), how: patch === PATCH_D12 ? "дельта D1.2 наложена на копию" : "весь патч наложен на копию" };
  } finally { rmSync(dir, { recursive: true, force: true }); }
}
const PATCHED = patchedSource();

// Карта-заглушка: стиль с 3D-зданиями akim-3d (как web/map.js онлайн), запись вызовов.
function fakeMap() {
  const calls = { filter: {}, paint: {}, added: [], data: [], layout: [] };
  const layers = [
    { id: "background", type: "background" },
    { id: "akim-3d", type: "fill-extrusion", source: "openmaptiles", "source-layer": "building", minzoom: 14,
      filter: ["!=", ["get", "hide_3d"], true],
      paint: { "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 14, 0, 15, ["get", "render_height"]] } },
    { id: "poi", type: "symbol", source: "openmaptiles", "source-layer": "poi", layout: { "text-font": ["Noto Sans Regular"] } },
  ];
  const sources = {};
  const map = {
    calls,
    getStyle: () => ({ glyphs: "https://example/{fontstack}/{range}.pbf", layers }),
    getLayer: (id) => layers.find((l) => l.id === id),
    setLight() {},
    setPaintProperty: (id, k, v) => { (calls.paint[id] ||= {})[k] = v; },
    setFilter: (id, f) => { calls.filter[id] = f; },
    setLayoutProperty: (id, k, v) => calls.layout.push([id, k, v]),
    addLayer: (spec, before) => { calls.added.push(spec); layers.splice(before ? layers.findIndex((l) => l.id === before) : layers.length, 0, spec); },
    addSource: (id, spec) => { sources[id] = { spec, setData: (d) => calls.data.push(d) }; },
    getSource: (id) => sources[id],
    on() {}, off() {}, getZoom: () => 15, querySourceFeatures: () => [],
  };
  return map;
}

function load({ lang = "ru", file = DATA } = {}) {
  const listeners = {};
  const ctx = {
    console,
    document: { documentElement: { lang } },
    window: { addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); } },
    fetch: async (url) => {
      assert.equal(url, "/civic/build3d/data/landmarks.json");
      return file ? { ok: true, json: async () => JSON.parse(JSON.stringify(file)) } : { ok: false, json: async () => null };
    },
  };
  vm.createContext(ctx);
  vm.runInContext(PATCHED.src, ctx, { filename: FILE });
  return { api: ctx.window.BirgeBasemapStyle, ctx, listeners };
}
const settle = () => new Promise((r) => setTimeout(r, 30));
// Значения из vm-контекста — другие Array/Object (другая «реальность»): для deepEqual — обычные копии.
const plain = (x) => JSON.parse(JSON.stringify(x));
// Точки выражения distance в фильтре слоя (["distance", {type:"Point", coordinates}]).
const points = (f) => JSON.stringify(f).match(/"coordinates":\[[^\]]+\]/g).map((s) => JSON.parse(s.slice(14)));
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const lum = (hex) => rgb(hex).map((c) => c / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  .reduce((s, c, i) => s + c * [0.2126, 0.7152, 0.0722][i], 0);
const chroma = (hex) => Math.max(...rgb(hex)) - Math.min(...rgb(hex));

test(`патч ложится на ${FILE} R01 (${PATCHED.how}) и ничего не ломает в API подложки`, () => {
  const { api } = load();
  for (const k of ["palette", "light", "buildingColor", "landmarks", "landmarkNear", "install", "recolorBasemap", "filterPois", "POI_KEEP"])
    assert.ok(k in api, "BirgeBasemapStyle." + k);
  assert.deepEqual(plain(api.landmarks.map((l) => l.id).sort()), Object.keys(byId).sort(), "id ориентиров R01 = id landmarks.json");
});

test("центры, радиусы и подписи ru/kk ориентиров — из landmarks.json (один источник с поиском)", async () => {
  const { api } = load();
  const map = fakeMap();
  assert.equal(api.install(map), true);
  await settle();
  for (const l of api.landmarks) {
    const f = byId[l.id];
    assert.deepEqual(plain(l.center), [f.lon, f.lat], l.id + ": центр");
    assert.equal(l.radius, f.radius_m, l.id + ": радиус");
    assert.equal(l.ru, f.label.ru, l.id + ": подпись ru");
    assert.equal(l.kk, f.label.kk, l.id + ": подпись kk");
  }
  assert.equal(byId["nur-alem"].label.ru, "Нур Алем · ЭКСПО", "подпись ЭКСПО как была у R01");
  // Фильтры обоих слоёв зданий пересчитаны по новым центрам, подписи — по новым точкам.
  const order = plain(api.landmarks.map((l) => l.id)).map((id) => byId[id]);  // порядок списка R01
  const want = order.map((l) => [l.lon, l.lat]);
  assert.deepEqual(points(map.calls.filter["akim-3d-landmark"]), want, "слой ориентиров: центры из файла");
  assert.deepEqual(points(map.calls.filter["akim-3d"]), want, "основной слой исключает те же здания");
  assert.equal(JSON.stringify(map.calls.filter["akim-3d"]).includes('["!",'), true);
  const last = map.calls.data.at(-1);
  assert.ok(last, "подписи обновлены (setData)");
  assert.deepEqual(plain(last.features.map((x) => [x.properties.id, x.properties.name_ru, x.properties.name_kk, x.geometry.coordinates])),
    order.map((l) => [l.id, l.label.ru, l.label.kk, [l.lon, l.lat]]));
});

test("«белый макет» (П1): ориентир чуть светлее соседних зданий, без отдельной краски; подпись спокойная", () => {
  const { api } = load();
  const p = api.palette;
  assert.equal(p.landmark.toUpperCase(), "#F6F4EF");
  for (const k of ["building0", "building60", "building150"])
    assert.ok(lum(p.landmark) > lum(p[k]), `ориентир светлее ${k} ${p[k]}`);
  assert.ok(chroma(p.landmark) <= chroma(p.building0), `без отдельной краски: насыщенность ${chroma(p.landmark)} ≤ ${chroma(p.building0)}`);
  assert.ok(chroma(p.landmarkText) <= 16, "подпись — серо-зелёная, не цветная: " + p.landmarkText);
  const map = fakeMap();
  api.install(map);
  const layer = map.calls.added.find((l) => l.id === "akim-3d-landmark");
  assert.equal(layer.paint["fill-extrusion-color"], p.landmark);
  const label = map.calls.added.find((l) => l.id === "birge-landmark-label");
  assert.equal(label.paint["text-color"], p.landmarkText);
});

test("нет landmarks.json — запасные центры R01, без ошибок; язык подписи переключается", async () => {
  const { api, ctx, listeners } = load({ file: null });
  const before = plain(api.landmarks.map((l) => [l.id, l.center, l.radius]));
  const map = fakeMap();
  assert.equal(api.install(map), true);
  await settle();
  assert.deepEqual(plain(api.landmarks.map((l) => [l.id, l.center, l.radius])), before, "центры не тронуты");
  ctx.document.documentElement.lang = "kk";
  for (const fn of listeners["birge:lang"] || []) fn();
  assert.deepEqual(plain(map.calls.layout.at(-1)), ["birge-landmark-label", "text-field", ["get", "name_kk"]]);
});
