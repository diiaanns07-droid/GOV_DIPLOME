// R05 · 3D-превью · процедурные модели (build3d-models.js) на настоящем three.js 0.169 из web/vendor/three.
// Запуск из корня репозитория:  node --test tests/civic/R05/build3d/
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const THREE = await import(pathToFileURL(path.join(ROOT, "web/vendor/three/three.module.min.js")).href);
const C = require(path.join(ROOT, "web/civic/build3d/build3d-core.js"));
const M = require(path.join(ROOT, "web/civic/build3d/build3d-models.js")).create(THREE);

const BOXES = ["square", "playground", "sports", "stop"];
const verts = (g) => (g ? g.attributes.position.count : 0);

test("three.js из vendor — версия 169", () => {
  assert.equal(THREE.REVISION, "169");
});

for (const kind of BOXES) {
  test(`${kind}: габарит в метрах по каталогу, стоит на земле, разумное число вершин`, () => {
    const k = C.KINDS[kind];
    const g = M.build(kind, { seed: "t", w: k.w, d: k.d });
    const b = g.bounds;
    assert.ok(b.max.x - b.min.x <= k.w + 0.1 && b.max.x - b.min.x >= k.w - 0.5, `ширина ${b.min.x}..${b.max.x}`);
    assert.ok(b.max.y - b.min.y <= k.d + 0.15 && b.max.y - b.min.y >= k.d - 0.5, `глубина ${b.min.y}..${b.max.y}`);
    assert.ok(Math.abs(b.min.x + b.max.x) < 0.2 && Math.abs(b.min.y + b.max.y) < 0.2, "центр пятна в (0,0)");
    assert.ok(b.min.z > -0.1, "ничего не уходит под землю: " + b.min.z);
    assert.ok(g.height > 1 && g.height <= k.h, `высота ${g.height} ≤ ${k.h}`);
    // Пунктир границы «проект» — всегда есть и лежит у земли, чуть шире пятна.
    assert.ok(g.outline, "пунктир границы проекта");
    g.outline.computeBoundingBox();
    assert.ok(g.outline.boundingBox.max.z < 0.1);
    assert.ok(g.outline.boundingBox.max.x > k.w / 2);
    // Бюджет: 20 объектов на ноутбуке — до ~12 тыс. вершин в теле каждого.
    const total = ["solid", "glass", "glow", "decal", "outline"].reduce((s, n) => s + verts(g[n]), 0);
    assert.ok(verts(g.solid) < 12000, `${kind}: ${verts(g.solid)} вершин`);
    assert.ok(total < 16000, `${kind}: всего ${total}`);
    // Цвета в вершинах, нормали посчитаны (плоские грани).
    assert.equal(g.solid.attributes.color.itemSize, 3);
    assert.ok(g.solid.attributes.normal.array.some((v) => v !== 0));
    if (g.decal) assert.equal(g.decal.attributes.color.itemSize, 4, "мягкие пятна — с прозрачностью в вершинах");
  });
}

test("одинаковый id → одинаковый вид после перезагрузки; другой id → другие деревья", () => {
  const a = M.build("square", { seed: "p-1", w: 40, d: 30 }).solid.attributes.position.array;
  const b = M.build("square", { seed: "p-1", w: 40, d: 30 }).solid.attributes.position.array;
  const c = M.build("square", { seed: "p-2", w: 40, d: 30 }).solid.attributes.position.array;
  assert.deepEqual(Array.from(a.slice(0, 3000)), Array.from(b.slice(0, 3000)));
  assert.equal(a.length === c.length && a.every((v, i) => v === c[i]), false);
});

test("освещение: столб на каждую точку через ~30 м, в 5 м от оси улицы, высота ~8 м", () => {
  const line = [[0, 0], [120, 0], [120, 90]];
  const poles = C.sampleAlong(line, 30);
  const g = M.build("lighting", { poles, line, offset: 5 });
  assert.equal(poles.length, 8); // 210 м → 7 промежутков по 30 м
  assert.ok(g.height > 8 && g.height < 9.5, "высота " + g.height);
  // Светящиеся плафоны: по одному на столб.
  const glowBoxVerts = 36; // BoxGeometry без индексов
  assert.equal(verts(g.glow) / glowBoxVerts, poles.length);
  // Основания столбов (плинтус 0.45 м) — в 5 м справа от направления участка.
  const pos = g.solid.attributes.position;
  const first = poles[0];
  const expected = [first.p[0] + first.dir[1] * 5, first.p[1] - first.dir[0] * 5];
  let found = false;
  for (let i = 0; i < pos.count; i++) {
    if (pos.getZ(i) < 0.01 && Math.hypot(pos.getX(i) - expected[0], pos.getY(i) - expected[1]) < 0.4) found = true;
  }
  assert.ok(found, "основание первого столба на месте");
  assert.ok(g.outline, "пунктир вдоль участка");
});

test("неизвестный вид — понятная ошибка", () => {
  assert.throws(() => M.build("tower", {}), /неизвестный вид/);
});

test("геометрии освобождаются: dispose() у каждой части", () => {
  const g = M.build("stop", { seed: "x", w: 12, d: 4.5 });
  let disposed = 0;
  for (const n of ["solid", "glass", "glow", "decal", "outline"]) {
    if (!g[n]) continue;
    g[n].addEventListener("dispose", () => disposed++);
    g[n].dispose();
  }
  assert.ok(disposed >= 4);
});

test("тень (дизайн-марафон): плиты тени не дают, высокие части сдвинуты от солнца, треугольники против часовой", () => {
  const k = C.KINDS.square;
  const g = M.build("square", { seed: "shadow", w: k.w, d: k.d });
  const sh = M.shadowShape(g.solid, 0.3, 0.5, 0.3);
  assert.ok(sh && sh.cast.length > 0 && sh.foot.length > 0); // стенки сверху — нулевой площади, в «след» не идут
  for (let i = 0; i < sh.cast.length; i += 6) {
    const a = sh.cast;
    const area = (a[i + 2] - a[i]) * (a[i + 5] - a[i + 1]) - (a[i + 4] - a[i]) * (a[i + 3] - a[i + 1]);
    assert.ok(area > 0, "треугольник тени по часовой: " + i);
  }
  // Тень уходит на северо-восток (от солнца с юго-запада): её край дальше «следа».
  const maxOf = (arr, off) => Math.max(...Array.from(arr).filter((_, i) => i % 2 === off));
  assert.ok(maxOf(sh.cast, 0) > maxOf(sh.foot, 0) && maxOf(sh.cast, 1) > maxOf(sh.foot, 1));
  // Мощение 40×30 (высота 0.1) — не тень: «след» без плит уже всего объекта.
  assert.ok(sh.bounds[2] - sh.bounds[0] < 40 + 8);
  // Плоская плита без высоких частей — тени нет.
  const flat = new THREE.BoxGeometry(10, 10, 0.1).toNonIndexed();
  assert.equal(M.shadowShape(flat, 0.3, 0.5, 0.3), null);
  assert.ok(Array.isArray(M.SUN) && M.SUN[2] > 0 && M.lights().length === 3);
});

test("постройка: у тел aGrow (0 — плиты, до 0.5 — края) и aPivot; части одной группы растут из одного центра", () => {
  const k = C.KINDS.stop;
  const g = M.build("stop", { seed: "grow", w: k.w, d: k.d });
  const grow = g.solid.attributes.aGrow, pivot = g.solid.attributes.aPivot;
  assert.ok(grow && pivot && grow.count === g.solid.attributes.position.count);
  const vals = new Set(Array.from(grow.array).map((v) => v.toFixed(3)));
  assert.ok(vals.has("0.000"), "плиты сразу");
  assert.ok(Math.max(...grow.array) <= 0.5 + 1e-6 && Math.max(...grow.array) > 0.08);
  // Павильон — одна группа: все вершины выше 2.5 м (крыша) — с одним центром.
  const pos = g.solid.attributes.position;
  const roofPivots = new Set();
  for (let i = 0; i < pos.count; i++) if (pos.getZ(i) > 2.5 && Math.abs(pos.getX(i)) < 4) roofPivots.add(pivot.getX(i).toFixed(2) + "," + pivot.getY(i).toFixed(2));
  assert.equal(roofPivots.size, 1, [...roofPivots].join(" "));
});
