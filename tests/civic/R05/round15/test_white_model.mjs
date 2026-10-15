// R05 · раунд 15 · «белый макет» (поправка П1, правило 3): палитра 3D проектов без насыщенных цветов (цвет — только у
// акцента нового проекта), без бликов, картинки «было / станет» и «день / ночь» одного размера и одной рамки.
// Запуск из корня репозитория:  node --test tests/civic/R05/round15/test_white_model.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const THREE = await import(pathToFileURL(path.join(ROOT, "web/vendor/three/three.module.min.js")).href);
const M = require(path.join(ROOT, "web/civic/build3d/build3d-models.js")).create(THREE);
const PREV = path.join(ROOT, "web/civic/build3d/data/previews");

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const chroma = (hex) => { const c = rgb(hex); return Math.max(...c) - Math.min(...c); };
// Акцент нового проекта (лайм эталона A) и пунктир границы (цвет метки «Проект · 2027») — единственные «цветные».
const ACCENT = new Set(["accentEdge", "brand"]);

test("палитра: белые и светло-серые объёмы, бледная зелень; насыщенный только акцент проекта", () => {
  for (const [name, v] of Object.entries(M.palette)) {
    const list = Array.isArray(v) ? v : [v];
    for (const hex of list) {
      if (ACCENT.has(name)) continue;
      assert.ok(chroma(hex) <= 40, `${name} ${hex}: насыщенность ${chroma(hex)} > 40 (игрушечный цвет)`);
    }
  }
  assert.ok(chroma(M.palette.accentEdge) > 60, "акцент проекта должен читаться");
  // Тень — нейтральная (без зелёного оттенка бренда).
  assert.ok(chroma(M.palette.shadow) <= 8, "тень с оттенком: " + M.palette.shadow);
});

test("без бликов: стекло матовое (Lambert), Phong с specular в модуле и генераторах не используется", () => {
  for (const f of ["web/civic/build3d/build3d.js", "tests/civic/R05/build3d/make_previews.mjs", "tests/civic/R05/round15/make_before_after.mjs"]) {
    const src = readFileSync(path.join(ROOT, f), "utf8");
    assert.equal(/MeshPhongMaterial|specular/.test(src.replace(/\/\/.*$/gm, "")), false, f + ": блик стекла");
  }
});

test("у каждого вида — плита/цоколь акцента; днём у освещения нет пятен «свечения»", () => {
  const K = require(path.join(ROOT, "web/civic/build3d/build3d-core.js")).KINDS;
  const accent = new THREE.Color(M.palette.accentEdge);
  for (const kind of ["square", "playground", "sports", "stop", "lighting"]) {
    const g = kind === "lighting" ? M.build("lighting", { poles: [{ p: [0, 0], dir: [1, 0] }, { p: [30, 0], dir: [1, 0] }], offset: 5 }) : M.build(kind, { seed: "t", w: K[kind].w, d: K[kind].d });
    const col = g.solid.attributes.color.array;
    let hits = 0;
    for (let i = 0; i < col.length; i += 3) if (Math.abs(col[i] - accent.r) < 0.05 && Math.abs(col[i + 1] - accent.g) < 0.05 && Math.abs(col[i + 2] - accent.b) < 0.07) hits++;
    assert.ok(hits > 0, kind + ": нет акцента нового проекта");
    if (kind === "lighting") assert.equal(g.decal ? g.decal.attributes.position.count > 200 : false, false, "дневные пятна света у освещения");
  }
});

// PNG: ширина и высота — байты 16..23 заголовка IHDR.
const pngSize = (f) => { const b = readFileSync(path.join(PREV, f)); return [b.readUInt32BE(16), b.readUInt32BE(20)]; };
test("картинки карточки: «было», «станет», день и ночь освещения — 480 × 320, как превью", () => {
  for (const f of ["square@2x.png", "square-before@2x.png", "playground-before@2x.png", "sports-before@2x.png", "stop-before@2x.png",
    "lighting-before@2x.png", "lighting-after@2x.png", "lighting-night-before@2x.png", "lighting-night-after@2x.png"]) {
    assert.deepEqual(pngSize(f), [480, 320], f);
  }
});

test("фон превью — один спокойный для всех видов (цвет только у проекта)", () => {
  const src = readFileSync(path.join(ROOT, "web/civic/build3d/build3d.js"), "utf8");
  const m = /PREVIEW_TINT = (\{[^}]+\})/.exec(src);
  const tints = Object.values(JSON.parse(m[1].replace(/(\w+):/g, '"$1":')));
  assert.equal(new Set(tints).size, 1, "разные фоны по видам: " + tints);
});
