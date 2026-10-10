// R05 · 3D-превью · ядро (build3d-core.js) — без браузера.
// Запуск из корня репозитория:  node --test tests/civic/R05/build3d/
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const C = require(path.join(ROOT, "web/civic/build3d/build3d-core.js"));
const STREETS = JSON.parse(readFileSync(path.join(ROOT, "web/civic/build3d/data/nura-streets.json"), "utf8"));
const DISTRICTS = JSON.parse(readFileSync(path.join(ROOT, "web/civic/build3d/data/astana-districts.json"), "utf8"));
const FIXTURE = JSON.parse(readFileSync(path.join(ROOT, "web/civic/build3d/data/proposals.fixture.json"), "utf8"));
const EXISTING = JSON.parse(readFileSync(path.join(ROOT, "web/civic/build3d/data/astana-existing.json"), "utf8"));
const NURA = [71.3995, 51.1268];

// Расстояние (м) от точки до ломаной в lon/lat — через локальные метры вокруг точки.
function distToLine(pt, coords) {
  const local = coords.map((c) => C.toLocal(pt, c));
  return C.projectOnPolyline([0, 0], local).dist;
}

test("меркатор: туда-обратно без потерь, метры совпадают с расстоянием по Земле", () => {
  for (const d of [[10, 0], [0, 10], [350, -420], [-1200, 800]]) {
    const ll = C.fromLocal(NURA, d);
    const back = C.toLocal(NURA, ll);
    assert.ok(Math.hypot(back[0] - d[0], back[1] - d[1]) < 1e-6, "round trip " + d);
    const h = C.haversineM(NURA, ll);
    const e = Math.hypot(d[0], d[1]);
    assert.ok(Math.abs(h - e) / e < 0.002, `масштаб: ${h} vs ${e}`);
  }
  // Коэффициент как у MapLibre: 1 / (2π·6371008.8·cos φ)
  assert.equal(C.meterInMerc(0), 1 / (2 * Math.PI * 6371008.8));
});

test("точки через ~30 м: оба конца, равный шаг, единичное направление", () => {
  const pts = C.sampleAlong([[0, 0], [100, 0]], 30);
  assert.equal(pts.length, 4); // 100 / 30 ≈ 3 промежутка по 33.3 м
  assert.deepEqual(pts[0].p, [0, 0]);
  assert.ok(Math.abs(pts[3].p[0] - 100) < 1e-9);
  assert.ok(Math.abs(pts[1].p[0] - 100 / 3) < 1e-9);
  const bent = C.sampleAlong([[0, 0], [60, 0], [60, 60]], 30);
  assert.equal(bent.length, 5);
  for (const s of bent) assert.ok(Math.abs(Math.hypot(...s.dir) - 1) < 1e-9);
  assert.deepEqual(bent[3].p, [60, 30]);
  assert.deepEqual(C.sampleAlong([[5, 5], [5, 5]], 30), []);
  assert.equal(C.sampleAlong([[0, 0], [10, 0]], 30).length, 2); // короче шага — два столба по концам
});

test("проекция на ломаную и вырезка участка", () => {
  const line = [[0, 0], [10, 0], [10, 10]];
  const pr = C.projectOnPolyline([12, 4], line);
  assert.equal(pr.seg, 1);
  assert.ok(Math.abs(pr.dist - 2) < 1e-9);
  assert.ok(Math.abs(pr.along - 14) < 1e-9);
  const part = C.sliceAlong(line, 5, 15);
  assert.deepEqual(part, [[5, 0], [10, 0], [10, 5]]);
});

test("участок улицы: по настоящим рёбрам OSM, отклонение от формы ребра ≤ 5 м (CONTRACT §8)", () => {
  const idx = new C.StreetIndex(STREETS);
  const byId = Object.fromEntries(idx.edges.map((e) => [e.id, e]));
  // Две точки на ул. Сыганак (рёбра osm-w1328815797-6 и -8), чуть в стороне от оси.
  const a = byId["osm-w1328815797-6"].geom[0];
  const b = byId["osm-w1328815797-8"].geom[1];
  const sec = idx.section([a[0] + 0.00003, a[1] + 0.00002], b);
  assert.equal(sec.ok, true, JSON.stringify(sec));
  assert.equal(sec.name, "улица Сыганак");
  assert.ok(sec.length_m > 150 && sec.length_m < 260, "длина " + sec.length_m);
  assert.ok(sec.edge_ids.every((id) => /^osm-w\d+-\d+$/.test(id)));
  // Каждая вершина и точки через 5 м — не дальше 0.5 м от рёбер графа (допуск контракта — 5 м).
  const edgesGeom = sec.edge_ids.map((id) => byId[id].geom);
  const near = (p) => Math.min(...edgesGeom.map((g) => distToLine(p, g)));
  for (const p of sec.coords) assert.ok(near(p) < 0.5, "вершина " + near(p));
  const local = sec.coords.map((c) => C.toLocal(sec.coords[0], c));
  for (const s of C.sampleAlong(local, 5)) {
    const ll = C.fromLocal(sec.coords[0], s.p);
    assert.ok(near(ll) < 0.5, "точка " + near(ll));
  }
  // В обратную сторону — та же длина.
  const back = idx.section(b, [a[0] + 0.00003, a[1] + 0.00002]);
  assert.equal(back.ok, true);
  assert.ok(Math.abs(back.length_m - sec.length_m) < 1);
});

test("участок улицы: понятные отказы", () => {
  const idx = new C.StreetIndex(STREETS);
  const e = idx.edges.find((x) => x.id === "osm-w1189551423-0");
  assert.equal(idx.section(e.geom[0], C.fromLocal(e.geom[0], [3, 0])).reason, "too_short");
  assert.equal(idx.section([71.2, 51.0], e.geom[1]).reason, "far_from_street");
  const far = idx.section(e.geom[0], [71.3, 51.0]);
  assert.deepEqual([far.ok, far.reason, far.end], [false, "far_from_street", "b"]);
  // Конец на другой улице.
  const other = idx.edges.find((x) => x.name && x.name !== e.name && C.haversineM(x.geom[0], e.geom[0]) < 600);
  const r = idx.section(e.geom[0], other.geom[0]);
  if (!r.ok) assert.ok(["other_street", "no_path", "too_long"].includes(r.reason), r.reason);
  // Слишком длинный участок (> 900 м) по одной улице.
  const same = idx.edges.filter((x) => x.name === "проспект Туран");
  let A = same[0].geom[0], B = null;
  for (const x of same) for (const c of x.geom) if (C.haversineM(A, c) > 1300) B = c;
  if (B) {
    const long = idx.section(A, B);
    assert.equal(long.ok, false);
    assert.ok(["too_long", "no_path"].includes(long.reason), long.reason);
  }
});

test("ближайшая улица и направление для остановки", () => {
  const idx = new C.StreetIndex(STREETS);
  const stop = FIXTURE.proposals.find((p) => p.kind === "stop");
  const n = idx.nearest(stop.geometry.coordinates, 60);
  assert.ok(n, "улица рядом с остановкой");
  assert.ok(n.dist <= 60, "остановка не дальше 60 м от улицы (CONTRACT §8): " + n.dist);
  assert.ok(n.bearing >= 0 && n.bearing < 360);
});

test("настоящие объекты OSM: «рядом уже есть», двор, фонари вдоль участка", () => {
  const E = new C.ExistingIndex(EXISTING);
  // Пример-остановка из фикстуры стоит рядом с настоящей остановкой «БЦ Саад» (OSM node 5744091177).
  const stop = FIXTURE.proposals.find((p) => p.kind === "stop");
  const near = E.nearestSame("stop", stop.geometry.coordinates);
  assert.equal(near.id, "osm-node-5744091177");
  assert.ok(near.dist_m > 20 && near.dist_m < 45, String(near.dist_m));
  assert.equal(E.nearestSame("stop", [71.0, 51.0]), null);
  // Центр двора «Evolution» (OSM way 1148721825) — внутри его кольца.
  const yard = EXISTING.yards.find((y) => y[0] === "yard-1148721825");
  const ring = yard[4];
  const c = [(Math.min(...ring.map((p) => p[0])) + Math.max(...ring.map((p) => p[0]))) / 2, (Math.min(...ring.map((p) => p[1])) + Math.max(...ring.map((p) => p[1]))) / 2];
  if (C.pointInRing(c[0], c[1], ring)) assert.equal(E.yardAt(c).id, "yard-1148721825");
  assert.equal(E.yardAt([71.0, 51.0]), null);
  // Фонари: линия через настоящий фонарь OSM находит его; далеко — ноль.
  const lamp = EXISTING.points.lamp[0];
  const line = [C.fromLocal(lamp, [-40, 3]), C.fromLocal(lamp, [40, 3])];
  assert.ok(E.lampsAlong(line) >= 1);
  assert.equal(E.lampsAlong([[71.0, 51.0], [71.001, 51.0]]), 0);
  // Сквер внутри парка — расстояние 0 (от края пятна).
  const park = EXISTING.points.square.find((r) => r[5] > 50);
  assert.equal(E.nearestSame("square", [park[0], park[1]]).dist_m, 0);
});

test("районы: точка в Нуре, за городом — null", () => {
  assert.equal(C.districtAt(DISTRICTS, NURA), "nura");
  assert.equal(C.districtAt(DISTRICTS, [71.0, 51.1]), null);
  assert.equal(C.districtAt(DISTRICTS, [51.1268, 71.3995]), null); // перепутаны lon/lat
});

test("проверка места: наложение с учётом поворота, за городом, лимит 20", () => {
  const sq = (id, c, r = 0) => ({ id, kind: "square", geometry: { type: "Point", coordinates: c }, rotation_deg: r });
  const a = sq("a", NURA);
  assert.equal(C.checkPlacement(sq("b", C.fromLocal(NURA, [30, 0])), [a], DISTRICTS).reason, "overlap");
  assert.equal(C.checkPlacement(sq("b", C.fromLocal(NURA, [41, 0])), [a], DISTRICTS).ok, true);
  // Повернутый на 90° сквер 40×30 занимает 30 по x: в 36 м уже не задевает.
  assert.equal(C.checkPlacement(sq("b", C.fromLocal(NURA, [36, 0]), 90), [sq("a", NURA, 90)], DISTRICTS).ok, true);
  assert.equal(C.checkPlacement(sq("b", C.fromLocal(NURA, [36, 0]), 0), [sq("a", NURA, 0)], DISTRICTS).reason, "overlap");
  assert.equal(C.checkPlacement(sq("b", [71.0, 51.1]), [], DISTRICTS).reason, "outside_city");
  const many = Array.from({ length: 20 }, (_, i) => sq("x" + i, C.fromLocal(NURA, [i * 100, 500])));
  assert.equal(C.checkPlacement(sq("b", NURA), many, DISTRICTS).reason, "limit");
  // Освещение не мешает объектам (оно вдоль улицы), но тоже считается в лимит.
  const light = { id: "l", kind: "lighting", geometry: { type: "LineString", coordinates: [NURA, C.fromLocal(NURA, [100, 0])] } };
  assert.equal(C.checkPlacement(sq("b", NURA), [light], DISTRICTS).ok, true);
});

test("запись предложения: неверные данные не рисуются", () => {
  assert.equal(C.normalizeProposal({ kind: "tower", geometry: { type: "Point", coordinates: NURA } }), null);
  assert.equal(C.normalizeProposal({ kind: "square", geometry: { type: "Point", coordinates: [NaN, 51] } }), null);
  assert.equal(C.normalizeProposal({ kind: "square", geometry: { type: "Point", coordinates: [71, 95] } }), null);
  assert.equal(C.normalizeProposal({ kind: "lighting", geometry: { type: "Point", coordinates: NURA } }), null);
  assert.equal(C.normalizeProposal({ kind: "lighting", geometry: { type: "LineString", coordinates: [NURA] } }), null);
  assert.equal(C.normalizeProposal(null), null);
  const p = C.normalizeProposal({ id: 5, kind: "stop", geometry: { type: "Point", coordinates: ["71.4", "51.12"] }, rotation_deg: -30, votes_up: "3" });
  assert.equal(p.id, "5");
  assert.equal(p.rotation_deg, 330);
  assert.equal(p.votes_up, 3);
  assert.equal(p.status, "proposal");
  assert.equal(p.year, 2027);
  assert.deepEqual(p.geometry.coordinates, [71.4, 51.12]);
});

test("фикстура предложений по CONTRACT §7: обязательные поля, примеры помечены demo", () => {
  assert.ok(FIXTURE.proposals.length >= 1);
  for (const raw of FIXTURE.proposals) {
    for (const k of ["id", "kind", "geometry", "status", "votes_up", "votes_down"]) assert.ok(k in raw, k);
    assert.equal(raw.status, "proposal");
    assert.equal(raw.demo, true);
    assert.ok(C.normalizeProposal(raw), raw.id);
    const pts = raw.geometry.type === "Point" ? [raw.geometry.coordinates] : raw.geometry.coordinates;
    for (const c of pts) assert.ok(C.districtAt(DISTRICTS, c), "внутри Астаны " + c);
  }
});

function memStorage() {
  const m = {};
  return { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => (m[k] = String(v)), _m: m };
}

test("локальная заглушка: примеры, создание, удаление, возврат, голос с устройства", async () => {
  const storage = memStorage();
  const s = C.createLocalStore({ storage, fixture: FIXTURE });
  assert.equal(s.mode, "local");
  const first = await s.list();
  assert.equal(first.length, FIXTURE.proposals.length);
  const created = await s.create({ kind: "square", geometry: { type: "Point", coordinates: NURA }, rotation_deg: 15, votes_up: 99 });
  assert.equal(created.votes_up, 0, "новое предложение начинает с нуля голосов");
  assert.ok(created.created_at);
  // Вторая «вкладка» читает то же хранилище — после перезагрузки объект на месте.
  const s2 = C.createLocalStore({ storage, fixture: FIXTURE });
  assert.equal((await s2.list()).length, FIXTURE.proposals.length + 1);
  let v = await s.vote(created.id, 1, "dev-1");
  assert.deepEqual([v.votes_up, v.votes_down, v.my_vote], [1, 0, 1]);
  v = await s.vote(created.id, 1, "dev-1");
  assert.deepEqual([v.votes_up, v.votes_down], [1, 0], "повторный голос «за» не добавляет");
  v = await s.vote(created.id, -1, "dev-1");
  assert.deepEqual([v.votes_up, v.votes_down, v.my_vote], [0, 1, -1], "голос переносится");
  await assert.rejects(s.vote(created.id, 2), /invalid/);
  await s.remove(created.id);
  assert.equal((await s.list()).length, FIXTURE.proposals.length);
  const back = await s.restore(v);
  assert.equal(back.id, created.id);
  assert.equal(back.my_vote, -1);
  // Испорченные данные в хранилище → снова примеры, без падения.
  storage.setItem(C.LOCAL_KEY, "{oops");
  assert.equal((await C.createLocalStore({ storage, fixture: FIXTURE }).list()).length, FIXTURE.proposals.length);
});

test("локальная заглушка: не больше 20 объектов", async () => {
  const s = C.createLocalStore({ storage: memStorage(), fixture: { proposals: [] } });
  for (let i = 0; i < 20; i++) await s.create({ kind: "stop", geometry: { type: "Point", coordinates: C.fromLocal(NURA, [i * 20, 0]) } });
  await assert.rejects(s.create({ kind: "stop", geometry: { type: "Point", coordinates: NURA } }), /limit/);
});

function fakeFetch(routes, log) {
  return async (url, init) => {
    log.push([init.method, url, init.body ? JSON.parse(init.body) : null]);
    const key = init.method + " " + url.replace(/\?.*$/, "");
    const r = routes[key] || routes["*"];
    if (r === "network") throw new TypeError("Failed to fetch");
    const [status, body] = typeof r === "function" ? r(init) : r;
    return { ok: status >= 200 && status < 300, status, text: async () => (body == null ? "" : typeof body === "string" ? body : JSON.stringify(body)) };
  };
}

test("API R06 поставки 1 (3d10f7d/7031afa): контекст 3D отклонён → базовые поля, planned_year, {item}, withdraw", async () => {
  const log = [];
  const item = { id: "p-1", kind: "square", geometry: { type: "Point", coordinates: NURA }, status: "proposal", planned_year: 2027,
    votes_up: 2, votes_down: 0, my_vote: null, voting_open: true, demo: false, title_ru: "Сквер", title_kk: "Гүлзар" };
  const ALLOWED = ["demo", "geometry", "kind", "planned_year", "rotation_deg", "title_kk", "title_ru"];
  const api = C.createApiStore({
    deviceId: "dev-0123456789abcdef0123456789abcdef",
    fetch: fakeFetch(
      {
        "GET /api/civic/v2/proposals": [200, { items: [item, { kind: "bad" }] }],
        "POST /api/civic/v2/proposals": (init) => {
          const body = JSON.parse(init.body);
          const extra = Object.keys(body).filter((k) => !ALLOWED.includes(k));
          if (extra.length) return [422, { ok: false, error: { code: "invalid_payload", fields: { [extra[0]]: "Неизвестное поле." } } }];
          return [201, { item: Object.assign({ id: "p-2", status: "proposal", votes_up: 0, votes_down: 0, my_vote: null, voting_open: true }, body) }];
        },
        "POST /api/civic/v2/proposals/p-1/vote": [200, { item: Object.assign({}, item, { votes_up: 3, my_vote: 1 }), changed: true, previous: null }],
        "POST /api/civic/v2/proposals/p-1/withdraw": [200, { item: Object.assign({}, item, { status: "withdrawn" }) }],
        "POST /api/civic/v2/proposals/zz/withdraw": [404, { error: "not_found", message: "Проект не найден" }],
        "DELETE /api/civic/v2/proposals/zz": [404, { error: "not_found" }],
      },
      log
    ),
  });
  const list = await api.list([71.3, 51.1, 71.5, 51.2]);
  assert.equal(list.length, 1, "неверная запись отброшена");
  assert.match(log[0][1], /bbox=71\.300000,51\.100000,71\.500000,51\.200000/);
  assert.match(log[0][1], /device_id=dev-0123456789abcdef/, "device_id в запросе списка — «мой голос»");
  assert.equal(list[0].year, 2027, "planned_year → год на табличке");
  assert.equal(list[0].my_vote, 0);
  // Черновик модуля несёт улицу и двор: R06 поставки 1 отвечает 422 «Неизвестное поле» — клиент один раз
  // повторяет базовым телом и дальше шлёт только его. status/district не уходят никогда.
  const draft = { kind: "stop", geometry: { type: "Point", coordinates: NURA }, rotation_deg: 30.4, year: 2027,
    status: "proposal", district: "nura", near_street: "улица Сыганак", target: { kind: "area", id: "yard-1" }, demo: false };
  const created = await api.create(draft);
  assert.equal(created.id, "p-2");
  const byPath = (m, path) => log.filter((r) => r[0] === m && r[1].replace(/\?.*$/, "") === path);
  assert.ok(log.some((r) => r[1] === "/api/civic/v1/session"), "CSRF сотрудника берётся из сессии, как в карточке R06");
  const posts = byPath("POST", "/api/civic/v2/proposals");
  assert.equal(posts.length, 2, "первый POST с контекстом 3D, повтор — базовым телом");
  assert.deepEqual(Object.keys(posts[0][2]).sort(), ["demo", "geometry", "kind", "near_street", "planned_year", "rotation_deg", "target"]);
  const sent = posts[1][2];
  assert.deepEqual(Object.keys(sent).sort(), ["demo", "geometry", "kind", "planned_year", "rotation_deg"]);
  assert.equal(sent.rotation_deg, 30);
  assert.equal(sent.planned_year, 2027);
  await api.create(draft);
  assert.equal(byPath("POST", "/api/civic/v2/proposals").length, 3, "после первого 422 — сразу базовое тело");
  assert.deepEqual(Object.keys(byPath("POST", "/api/civic/v2/proposals")[2][2]).sort(), Object.keys(sent).sort());
  const voted = await api.vote("p-1", 1);
  assert.equal(voted.votes_up, 3);
  assert.equal(voted.my_vote, 1);
  assert.deepEqual(byPath("POST", "/api/civic/v2/proposals/p-1/vote")[0][2], { value: 1, device_id: "dev-0123456789abcdef0123456789abcdef" });
  assert.equal(await api.remove("p-1"), true);
  assert.equal(byPath("POST", "/api/civic/v2/proposals/p-1/withdraw").length, 1, "«Удалить» = withdraw R06");
  await assert.rejects(api.remove("zz"), (e) => e.code === "not_found" && e.status === 404);
  assert.equal(byPath("DELETE", "/api/civic/v2/proposals/zz").length, 1, "запасной DELETE, если withdraw не найден");
});

test("API R06 поставки 2 (b42e790): near_street и target сохраняются, «Отменить» возвращает то же предложение с голосами", async () => {
  const log = [];
  const rows = {};
  const ALLOWED = ["demo", "geometry", "kind", "planned_year", "year", "rotation_deg", "title_kk", "title_ru", "status", "near_street", "target"];
  const SERVER = ["id", "votes_up", "votes_down", "my_vote", "voting_open", "created_at", "updated_at", "decided_at", "district", "proposal", "item"];
  const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;
  const api = C.createApiStore({
    fetch: fakeFetch(
      {
        "POST /api/civic/v2/proposals": (init) => {
          const body = JSON.parse(init.body);
          const extra = Object.keys(body).filter((k) => !ALLOWED.includes(k) && !SERVER.includes(k));
          if (extra.length) return [422, { ok: false, error: { code: "invalid_payload", fields: { [extra[0]]: "Неизвестное поле." } } }];
          const t = body.target;
          if (t && (!["object", "segment", "area"].includes(t.kind) || !ID_RE.test(t.id) || (t.ids || []).some((i) => !ID_RE.test(i))))
            return [422, { ok: false, error: { code: "invalid_payload", fields: { target: "Цель" } } }];
          if (body.id && rows[body.id] && rows[body.id].status === "withdrawn") {
            rows[body.id].status = "proposal";
            return [201, { item: rows[body.id], proposal: rows[body.id], restored: true, ignored_fields: ["id"] }];
          }
          const id = "p-" + (Object.keys(rows).length + 1);
          rows[id] = { id, kind: body.kind, geometry: body.geometry, rotation_deg: body.rotation_deg, planned_year: body.planned_year,
            year: body.planned_year, near_street: body.near_street || null, target: body.target || null, status: "proposal",
            votes_up: 4, votes_down: 1, my_vote: null, voting_open: true, demo: false };
          return [201, { item: rows[id], proposal: rows[id], restored: false, ignored_fields: [] }];
        },
        "POST /api/civic/v2/proposals/p-1/withdraw": () => {
          rows["p-1"].status = "withdrawn";
          return [200, { item: rows["p-1"] }];
        },
        "GET /api/civic/v1/session": [200, { authenticated: true, csrf_token: "tok" }],
      },
      log
    ),
  });
  const lightingDraft = { kind: "lighting", geometry: { type: "LineString", coordinates: [NURA, [NURA[0] + 0.002, NURA[1]]] }, year: 2027,
    near_street: "  улица Сыганак  ", demo: false,
    target: { kind: "segment", id: "osm-w623788311-1", ids: ["osm-w623788311-1", "bad id с пробелом", "osm-w425997757-0"], label_ru: "улица Сыганак", label_kk: null } };
  const saved = await api.create(lightingDraft);
  const posts = () => log.filter((r) => r[0] === "POST" && r[1] === "/api/civic/v2/proposals");
  assert.equal(posts().length, 1, "R06 поставки 2 принимает контекст с первого раза");
  assert.deepEqual(posts()[0][2].target, { kind: "segment", id: "osm-w623788311-1", ids: ["osm-w623788311-1", "osm-w425997757-0"], label_ru: "улица Сыганак" },
    "неверный id ребра и пустая подпись не уходят (иначе R06 отклонил бы всю цель)");
  assert.equal(posts()[0][2].near_street, "улица Сыганак");
  assert.equal(saved.near_street, "улица Сыганак");
  assert.equal(saved.target.kind, "segment");
  assert.equal(saved.year, 2027);
  await api.remove(saved.id);
  const back = await api.restore(Object.assign({}, saved));
  assert.equal(posts()[1][2].id, "p-1", "restore шлёт id снятого предложения");
  assert.equal(back.id, "p-1", "то же предложение, а не новое");
  assert.equal(back.votes_up, 4, "голоса сохранены");
  // Неверная цель (чужой формат id) не уходит вовсе — предложение всё равно создаётся.
  assert.equal(C.toServerTarget({ kind: "area", id: "двор 5" }), null);
  assert.equal(C.toServerTarget({ kind: "house", id: "yard-1" }), null);
  assert.deepEqual(C.toServerTarget({ kind: "area", id: "yard-1148721825", label_ru: "Evolution", label_kk: "Evolution" }),
    { kind: "area", id: "yard-1148721825", label_ru: "Evolution", label_kk: "Evolution" });
});

test("API: конверт сервиса R06 {ok, data}, ошибка без сессии сотрудника, клиент оболочки R01 api.v2", async () => {
  const env = C.createApiStore({ fetch: fakeFetch({ "GET /api/civic/v2/proposals": [200, { ok: true, data: { items: [{ id: "p-9", kind: "stop", geometry: { type: "Point", coordinates: NURA }, planned_year: null }] } }],
    "POST /api/civic/v2/proposals": [401, { ok: false, error: { code: "unauthenticated", message: "Войдите" } }], "GET /api/civic/v1/session": [200, { authenticated: false }] }, []) });
  const items = await env.list();
  assert.equal(items[0].id, "p-9");
  assert.equal(items[0].year, null, "нет года — табличка просто «Проект»");
  await assert.rejects(env.create({ kind: "stop", geometry: { type: "Point", coordinates: NURA } }), (e) => e.status === 401 && e.code === "unauthenticated");
  // Клиент оболочки: ошибки — объект со status и error-кодом (BirgeApiError R01).
  const calls = [];
  const viaShell = C.createApiStore({
    v2: async (method, path, body) => {
      calls.push([method, path, body]);
      if (method === "POST" && path === "/proposals") {
        const err = new Error("csrf");
        err.status = 403;
        err.error = "csrf_failed";
        throw err;
      }
      return { items: [] };
    },
  });
  assert.deepEqual(await viaShell.list(), []);
  await assert.rejects(viaShell.create({ kind: "stop", geometry: { type: "Point", coordinates: NURA } }), (e) => e.status === 403 && e.code === "csrf_failed");
  assert.deepEqual(calls[0], ["GET", "/proposals", undefined]);
});

test("id устройства — формат R06 (16–128 [A-Za-z0-9_-]), старый короткий заменяется", () => {
  const st = memStorage();
  st.setItem("birge.device_id", "dev-1");
  const id = C.getDeviceId(st);
  assert.match(id, /^dev-[0-9a-f]{32}$/);
  assert.equal(C.getDeviceId(st), id);
});

test("авто: нет адреса /proposals (404/503) или сервера — честно переходим на заглушку; 500 — ошибка", async () => {
  for (const r of [[404, "not found"], [503, { error: { code: "module_unavailable" } }], "network", [200, "<html>"]]) {
    const s = C.createAutoStore({ fetch: fakeFetch({ "*": r }, []), storage: memStorage(), fixture: FIXTURE });
    const items = await s.list();
    assert.equal(s.mode, "local", JSON.stringify(r));
    assert.equal(items.length, FIXTURE.proposals.length);
    const c = await s.create({ kind: "square", geometry: { type: "Point", coordinates: NURA } });
    assert.ok(c.id);
  }
  const bad = C.createAutoStore({ fetch: fakeFetch({ "*": [500, { error: { code: "internal" } }] }, []), storage: memStorage(), fixture: FIXTURE });
  await assert.rejects(bad.list(), (e) => e.status === 500);
  const ok = C.createAutoStore({ fetch: fakeFetch({ "*": [200, { items: [] }] }, []), storage: memStorage(), fixture: FIXTURE });
  assert.deepEqual(await ok.list(), []);
  assert.equal(ok.mode, "api");
});

test("устройство: один id на браузер", () => {
  const st = memStorage();
  const a = C.getDeviceId(st);
  assert.match(a, /^[A-Za-z0-9_-]{16,128}$/);
  assert.equal(C.getDeviceId(st), a);
});

test("ключи для R11 (UX_REVIEW день 3 #26): файл i18n_build3d.json совпадает со строками модуля, ru и kk есть у всех", async () => {
  const vm = await import("node:vm");
  const code = readFileSync(path.join(ROOT, "web/civic/build3d/build3d.js"), "utf8");
  const ctx = { self: { document: null, CivicBuild3DCore: {}, CivicBuild3DModels: {} } };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  const S = ctx.self.CivicBuild3D.STRINGS;
  const file = JSON.parse(readFileSync(path.join(ROOT, "research/round-14-results/R05/i18n_build3d.json"), "utf8"));
  assert.deepEqual(Object.keys(file).sort(), Object.keys(S.ru).sort());
  for (const [key, spec] of Object.entries(file)) {
    assert.match(key, /^[a-z0-9_]+(\.[a-z0-9_]+)+$/, key);
    // JSON: объекты из vm-контекста имеют другой прототип, сравниваем значения.
    assert.equal(JSON.stringify(spec.ru), JSON.stringify(S.ru[key]), key);
    assert.equal(JSON.stringify(spec.kk), JSON.stringify(S.kk[key]), key);
    assert.ok(spec.kk && spec.where, key);
    const params = (v) => JSON.stringify(v).match(/\{\w+\}/g)?.sort() || [];
    assert.deepEqual(params(spec.kk), params(typeof spec.ru === "object" ? spec.ru.many : spec.ru), "параметры ru/kk совпадают: " + key);
  }
  // Ни одного технического слова в текстах (UX_BRIEF, правило 4).
  const texts = JSON.stringify(Object.values(file).map((v) => [v.ru, v.kk])).toLowerCase(); // только тексты экрана, не «where»
  for (const word of ["ребро", "граф", "геометрия", "payload", "demo", "null", "undefined", "webgl"]) assert.ok(!texts.includes(word), word);
});
