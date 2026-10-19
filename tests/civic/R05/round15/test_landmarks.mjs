// R05 · раунд 15 · ориентиры: landmarks.json — один источник центров и названий ru/kk для подписей, поиска и условных
// 3D-моделей пяти ориентиров на карте (build3d-landmarks.js; поправка П1 их убирала, владелец 19 окт вернул на карту).
// Модели — на настоящем three.js 0.169 из web/vendor.
// Запуск из корня репозитория:  node --test tests/civic/R05/round15/test_landmarks.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath, pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const THREE = await import(pathToFileURL(path.join(ROOT, "web/vendor/three/three.module.min.js")).href);
const C = require(path.join(ROOT, "web/civic/build3d/build3d-core.js"));
const M = require(path.join(ROOT, "web/civic/build3d/build3d-models.js")).create(THREE);
const L = require(path.join(ROOT, "web/civic/build3d/build3d-landmarks.js")).create(THREE, M);
const DATA = path.join(ROOT, "data/civic/astana/landmarks/landmarks.json");
const WEB = path.join(ROOT, "web/civic/build3d/data/landmarks.json");
const data = JSON.parse(readFileSync(DATA, "utf8"));
// Те же id, что у ориентиров R01 в web/civic/shell/basemap-style.js — один источник без перевода id.
const IDS = ["khan-shatyr", "baiterek", "akorda", "hazrat-sultan", "palace-peace", "nur-alem"];
// У этих пяти есть 3D-модель; мечеть Хазрет Султан показывает подложка.
const MODELED = ["baiterek", "khan-shatyr", "nur-alem", "akorda", "palace-peace"];

test("landmarks.json v2: шесть ориентиров R01, ru/kk, вид здания, координаты в Астане, LOCAL-13", () => {
  assert.equal(data.schema, "birge-landmarks-v2");
  assert.deepEqual(data.landmarks.map((l) => l.id).sort(), IDS.slice().sort());
  for (const l of data.landmarks) {
    assert.ok(l.name.ru && l.name.kk && l.kind.ru && l.kind.kk, l.id + ": название и вид ru/kk");
    assert.ok(l.label && l.label.ru && l.label.kk, l.id + ": подпись на карте ru/kk (R01 basemap-style.js)");
    assert.ok(l.lat > 51.05 && l.lat < 51.2 && l.lon > 71.35 && l.lon < 71.5, l.id + ": координаты вне центра Астаны");
    assert.ok(typeof l.district === "string" && l.district.length > 2, l.id + ": район по контурам OSM");
    assert.ok(l.radius_m >= 20 && l.radius_m <= 80, l.id + ": радиус «здание подложки — ориентир»");
    assert.equal(l.camera.pitch, 52, l.id + ": наклон как у кнопки «3D» оболочки (без второго доворота)");
    assert.ok(l.camera.zoom >= 15 && l.camera.zoom <= 17, l.id + ": масштаб ≥ 15 (уровень «рядом» автонаклона R01)");
    assert.equal(l.coords.check, "LOCAL-13", l.id + ": «координаты проверить» до сверки с контурами Overpass");
    assert.ok(Array.isArray(l.coords.osm) && l.coords.osm.length, l.id + ": откуда координаты (id OSM)");
    if (MODELED.includes(l.id)) {
      assert.ok(L.MODELS.includes(l.model), l.id + ": модель " + l.model);
      assert.equal(l.conditional, true, l.id + ": модель условная");
      assert.ok(Number.isFinite(l.rotation_deg) && l.height_m > 0 && l.size_m && l.mask_m, l.id + ": поворот, высота, размеры, маска");
    } else {
      for (const f of ["model", "height_m", "mask_m", "conditional"]) assert.ok(!(f in l), l.id + ": без модели, а поле " + f);
    }
  }
  assert.ok(/не точные копии/.test(data.note.ru) && data.note.kk.length > 20, "подпись «условные модели» ru/kk");
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
for (const spec of data.landmarks.filter((l) => l.model)) {
  test(`${spec.id}: модель стоит на земле, высота ≈ ${spec.height_m} м, тело в границах маски, рост по частям`, () => {
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

test("модуль 3D показывает ориентиры на самой карте: с 12-го масштаба, без наклона и без слоёв; файл моделей отдаёт сервер", () => {
  const src = readFileSync(path.join(ROOT, "web/civic/build3d/build3d.js"), "utf8");
  assert.match(src, /var LM_MIN_ZOOM = 12;/);
  assert.match(src, /function lmWanted\(\) \{\s*return LM\.on && !S\.destroyed && S\.three !== "unsupported" && map\.getZoom\(\) >= LM_MIN_ZOOM - 0\.15;/);
  assert.match(src, /landmarks: opts\.landmarks !== false/, "ориентиры включены по умолчанию");
  assert.match(src, /modelsOnMap: opts\.modelsOnMap !== false/, "макеты проектов на карте по умолчанию");
  assert.match(readFileSync(path.join(ROOT, "ui/web_server.py"), "utf8"), /"build3d\/build3d-landmarks\.js"/);
});

// ───────────── Поиск и перелёт (web/civic/build3d/landmarks.js) ─────────────
const LM = require(path.join(ROOT, "web/civic/build3d/landmarks.js"));
const ix = LM.makeIndex(data);

test("поиск: с первой буквы, оба языка и другие написания, казахские буквы без разницы", () => {
  const top = (q, lang) => (ix.query(q, { lang })[0] || {}).id;
  assert.equal(top("бай", "ru"), "baiterek");
  assert.equal(top("бәй", "kk"), "baiterek");
  assert.equal(top("Baiterek", "ru"), "baiterek");
  assert.equal(top("хан ш", "ru"), "khan-shatyr");
  assert.equal(top("ақ", "kk"), "akorda");
  assert.equal(top("ак орда", "ru"), "akorda");
  assert.equal(top("пирамида", "ru"), "palace-peace");
  assert.equal(top("экспо", "kk"), "nur-alem");
  assert.equal(top("мечеть", "ru"), "hazrat-sultan");
  assert.equal(ix.query("zzz", { lang: "ru" }).length, 0);
  const r = ix.query("бай", { lang: "kk" })[0];
  assert.equal(r.label, "Бәйтерек");
  assert.deepEqual({ ...r.names }, { ru: "Байтерек", kk: "Бәйтерек" }, "оба названия — подпись вида при смене языка");
  assert.equal(r.type, "монумент");
  assert.deepEqual(r.point, [ix.get("baiterek").lon, ix.get("baiterek").lat]);
});

test("перелёт: камера из landmarks.json, наклон 52°, центр — в свободной части карты (offset, не padding)", async () => {
  const calls = [];
  const map = {
    flyTo: (o) => { calls.push(["flyTo", o]); setTimeout(() => map._end && map._end(), 5); },
    jumpTo: (o) => { calls.push(["jumpTo", o]); setTimeout(() => map._end && map._end(), 5); },
    once: (ev, fn) => { if (ev === "moveend") map._end = fn; },
  };
  const ok = await LM.flyTo(map, ix.get("khan-shatyr"), { padding: { top: 64, right: 80, bottom: 0, left: 420 } });
  assert.equal(ok, true);
  const [kind, o] = calls[0];
  assert.equal(kind, "flyTo");
  assert.equal(o.pitch, 52);
  assert.equal(o.zoom, ix.get("khan-shatyr").camera.zoom);
  assert.deepEqual(o.center, [ix.get("khan-shatyr").lon, ix.get("khan-shatyr").lat]);
  assert.deepEqual(o.offset, [170, 32]);
  assert.equal("padding" in o, false, "padding MapLibre остался бы на карте после перелёта");
});
