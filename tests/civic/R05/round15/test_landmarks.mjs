// R05 · раунд 15 · 3D-Астана: данные ориентиров и условные модели (Node, настоящий three.js 0.169 из web/vendor).
// Запуск из корня репозитория:  node --test tests/civic/R05/round15/test_landmarks.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const THREE = await import(pathToFileURL(path.join(ROOT, "web/vendor/three/three.module.min.js")).href);
const C = require(path.join(ROOT, "web/civic/build3d/build3d-core.js"));
const M = require(path.join(ROOT, "web/civic/build3d/build3d-models.js")).create(THREE);
const L = require(path.join(ROOT, "web/civic/build3d/build3d-landmarks.js")).create(THREE, M);
const DATA = path.join(ROOT, "data/civic/astana/landmarks/landmarks.json");
const WEB = path.join(ROOT, "web/civic/build3d/data/landmarks.json");
const data = JSON.parse(readFileSync(DATA, "utf8"));
const IDS = ["baiterek", "khan-shatyr", "nur-alem", "akorda", "palace-peace"];

test("landmarks.json: пять ориентиров, ru/kk, координаты в Астане, пометка LOCAL-13, копия для браузера та же", () => {
  assert.equal(data.schema, "birge-landmarks-v1");
  assert.deepEqual(data.landmarks.map((l) => l.id).sort(), IDS.slice().sort());
  for (const l of data.landmarks) {
    assert.ok(l.name.ru && l.name.kk, l.id + ": название ru/kk");
    assert.ok(l.lat > 51.05 && l.lat < 51.2 && l.lon > 71.35 && l.lon < 71.5, l.id + ": координаты вне центра Астаны");
    assert.equal(l.coords.check, "LOCAL-13", l.id + ": «координаты проверить» до сверки с контурами Overpass");
    assert.ok(Array.isArray(l.coords.osm) && l.coords.osm.length, l.id + ": откуда координаты (id OSM)");
    assert.equal(l.conditional, true, l.id + ": модель условная");
    assert.ok(L.MODELS.includes(l.model), l.id + ": модель " + l.model);
  }
  assert.ok(/не точные копии/.test(data.note.ru) && data.note.kk.length > 20, "подпись «условная модель» ru/kk");
  assert.equal(readFileSync(WEB, "utf8"), readFileSync(DATA, "utf8"), "web/civic/build3d/data/landmarks.json = data/civic/astana/landmarks/landmarks.json");
});

test("координаты пересобираются из снимка OSM тем же инструментом (derive_landmarks.py --check)", () => {
  execFileSync("python3", [path.join(ROOT, "data/civic/astana/landmarks/tools/derive_landmarks.py"), "--check"], { cwd: ROOT, stdio: "pipe" });
});

test("ось бульвара: Хан Шатыр — Байтерек — Ақорда — пирамида почти на одной прямой, повороты ≈ оси", () => {
  const by = Object.fromEntries(data.landmarks.map((l) => [l.id, l]));
  const o = [by["baiterek"].lon, by["baiterek"].lat];
  const pt = (id) => C.toLocal(o, [by[id].lon, by[id].lat]);
  const [ax, ay] = pt("akorda");
  const axis = Math.atan2(ay, ax); // от Байтерека к Ақорде
  for (const id of ["khan-shatyr", "palace-peace"]) {
    const [x, y] = pt(id);
    const off = Math.abs(-x * Math.sin(axis) + y * Math.cos(axis));
    assert.ok(off < 60, `${id}: ${off.toFixed(0)} м от оси бульвара`);
  }
  for (const id of ["akorda", "palace-peace", "khan-shatyr"]) {
    const d = Math.abs(((by[id].rotation_deg + (axis * 180) / Math.PI + 90) % 180) - 90);
    assert.ok(d < 3, `${id}: поворот ${by[id].rotation_deg}° не по оси (${((-axis * 180) / Math.PI).toFixed(1)}°)`);
  }
});

let total = 0;
for (const spec of data.landmarks) {
  test(`${spec.id}: модель стоит на земле, высота ≈ ${spec.height_m} м, пятно в границах маски, рост по частям`, () => {
    const g = L.build(spec);
    const b = g.bounds;
    assert.ok(b.min.z > -0.05, "ничего не уходит под землю: " + b.min.z);
    assert.ok(Math.abs(g.height - spec.height_m) <= spec.height_m * 0.08, `высота ${g.height.toFixed(1)} при ${spec.height_m}`);
    const m = spec.mask_m;
    const half = m.shape === "circle" ? [m.r, m.r] : m.shape === "ellipse" ? [m.a, m.b] : [m.w / 2, m.d / 2];
    // Тела (без мягкого пятна на земле) — внутри маски, где прячутся здания подложки: модель не «протыкает» соседей.
    g.solid.computeBoundingBox();
    const sb = g.solid.boundingBox;
    assert.ok(Math.max(-sb.min.x, sb.max.x) <= half[0] + 1 && Math.max(-sb.min.y, sb.max.y) <= half[1] + 1, `тело ${JSON.stringify([sb.min.x, sb.max.x, sb.min.y, sb.max.y].map((v) => +v.toFixed(1)))} шире маски ${half}`);
    // Шейдер постройки (build3d.js revealHook) берёт aGrow и aPivot — без них модель не вырастет.
    assert.ok(g.solid.attributes.aGrow && g.solid.attributes.aPivot, "атрибуты роста");
    assert.equal(g.solid.attributes.color.itemSize, 3);
    const tri = L.triangles(g);
    total += tri;
    assert.ok(tri < 15000, `${tri} треугольников`);
  });
}

test("бюджет: все ориентиры вместе ≤ 50 000 треугольников", () => {
  assert.ok(total > 3000 && total <= 50000, "всего " + total);
});

test("одинаковая запись → одинаковая модель (детерминированно, без Math.random)", () => {
  const s = data.landmarks.find((l) => l.id === "nur-alem");
  const a = L.build(s).solid.attributes.color.array, b = L.build(s).solid.attributes.color.array;
  assert.deepEqual(Array.from(a.slice(0, 600)), Array.from(b.slice(0, 600)));
});

test("неизвестная модель — понятная ошибка, а не пустая сцена", () => {
  assert.throws(() => L.build({ id: "x", model: "eiffel" }), /неизвестная модель ориентира/);
});
