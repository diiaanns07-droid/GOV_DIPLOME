// R05 · раунд 15 · ориентиры (поправка П1): landmarks.json — один источник центров и названий ru/kk для подписей
// и поиска. Моделей зданий нет — ориентиры показывает подложка (R01 basemap-style.js).
// Запуск из корня репозитория:  node --test tests/civic/R05/round15/test_landmarks.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { readFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const DATA = path.join(ROOT, "data/civic/astana/landmarks/landmarks.json");
const WEB = path.join(ROOT, "web/civic/build3d/data/landmarks.json");
const data = JSON.parse(readFileSync(DATA, "utf8"));
// Те же id, что у ориентиров R01 в web/civic/shell/basemap-style.js — один источник без перевода id.
const IDS = ["khan-shatyr", "baiterek", "akorda", "hazrat-sultan", "palace-peace", "nur-alem"];

test("landmarks.json v2: шесть ориентиров R01, ru/kk, вид здания, координаты в Астане, LOCAL-13", () => {
  assert.equal(data.schema, "birge-landmarks-v2");
  assert.deepEqual(data.landmarks.map((l) => l.id).sort(), IDS.slice().sort());
  for (const l of data.landmarks) {
    assert.ok(l.name.ru && l.name.kk && l.kind.ru && l.kind.kk, l.id + ": название и вид ru/kk");
    assert.ok(l.lat > 51.05 && l.lat < 51.2 && l.lon > 71.35 && l.lon < 71.5, l.id + ": координаты вне центра Астаны");
    assert.ok(typeof l.district === "string" && l.district.length > 2, l.id + ": район по контурам OSM");
    assert.ok(l.radius_m >= 20 && l.radius_m <= 80, l.id + ": радиус «здание подложки — ориентир»");
    assert.equal(l.camera.pitch, 52, l.id + ": наклон как у кнопки «3D» оболочки (без второго доворота)");
    assert.ok(l.camera.zoom >= 15 && l.camera.zoom <= 17, l.id + ": масштаб ≥ 15 (уровень «рядом» автонаклона R01)");
    assert.equal(l.coords.check, "LOCAL-13", l.id + ": «координаты проверить» до сверки с контурами Overpass");
    assert.ok(Array.isArray(l.coords.osm) && l.coords.osm.length, l.id + ": откуда координаты (id OSM)");
    for (const bad of ["model", "height_m", "mask_m", "conditional"]) assert.ok(!(bad in l), l.id + ": поле модели " + bad + " (П1: моделей нет)");
  }
  assert.equal(readFileSync(WEB, "utf8"), readFileSync(DATA, "utf8"), "web/civic/build3d/data/landmarks.json = data/civic/astana/landmarks/landmarks.json");
});

test("координаты пересобираются из снимка OSM тем же инструментом (derive_landmarks.py --check)", () => {
  execFileSync("python3", [path.join(ROOT, "data/civic/astana/landmarks/tools/derive_landmarks.py"), "--check"], { cwd: ROOT, stdio: "pipe" });
});

test("П1: нарисованных моделей ориентиров в модуле нет", () => {
  assert.equal(existsSync(path.join(ROOT, "web/civic/build3d/build3d-landmarks.js")), false);
  const src = readFileSync(path.join(ROOT, "web/civic/build3d/build3d.js"), "utf8");
  assert.equal(/baiterek|khan_shatyr|условн(ая|ые) модел/i.test(src), false, "в build3d.js остались модели ориентиров");
});
