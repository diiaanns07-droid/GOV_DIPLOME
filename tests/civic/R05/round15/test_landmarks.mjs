// R05 · раунд 15 · ориентиры (поправка П1): landmarks.json — один источник центров и названий ru/kk для подписей
// и поиска. Моделей зданий нет — ориентиры показывает подложка (R01 basemap-style.js).
// Запуск из корня репозитория:  node --test tests/civic/R05/round15/test_landmarks.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
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
    assert.ok(l.label && l.label.ru && l.label.kk, l.id + ": подпись на карте ru/kk (R01 basemap-style.js)");
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

test("П1: нарисованных моделей ориентиров в модуле нет (проверка приёмки R01)", () => {
  assert.equal(existsSync(path.join(ROOT, "web/civic/build3d/build3d-landmarks.js")), false);
  const src = readFileSync(path.join(ROOT, "web/civic/build3d/build3d.js"), "utf8");
  assert.equal(/baiterek|khan_shatyr|условн(ая|ые) модел/i.test(src), false, "в build3d.js остались модели ориентиров");
  // R01 принимает сборку командой git grep -i "baiterek\|khan.shatyr\|nur.alem\|akorda" web/civic/build3d (STATUS R01, П1).
  // Совпадения допустимы только в данных web/civic/build3d/data/landmarks.json (id и латинские написания для поиска).
  const hits = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const p = path.join(dir, name);
      if (statSync(p).isDirectory()) { walk(p); continue; }
      if (!/\.(js|mjs|css|html|json)$/.test(name)) continue;
      const rel = path.relative(ROOT, p).split(path.sep).join("/");
      if (rel === "web/civic/build3d/data/landmarks.json") continue;
      readFileSync(p, "utf8").split("\n").forEach((line, i) => { if (/baiterek|khan.shatyr|nur.alem|akorda/i.test(line)) hits.push(rel + ":" + (i + 1)); });
    }
  };
  walk(path.join(ROOT, "web/civic/build3d"));
  assert.deepEqual(hits, [], "grep приёмки R01 находит не только данные landmarks.json");
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
