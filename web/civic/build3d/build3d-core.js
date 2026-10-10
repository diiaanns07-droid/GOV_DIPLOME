/*
 * Birge · 3D-превью предложений (R05, раунд 14) — ядро без DOM и без three.js.
 *
 * Здесь только «чистая» логика, которую можно проверить в Node (tests/civic/R05/build3d/):
 *  - каталог из 5 видов объектов и их размеры в метрах;
 *  - перевод lon/lat ↔ меркатор MapLibre ↔ локальные метры (восток, север);
 *  - линии: длина, точки через ~30 м, проекция точки на линию;
 *  - индекс улиц (настоящая форма OSM): ближайшая улица, участок между двумя точками;
 *  - районы Астаны: «внутри города?», какой район;
 *  - проверка места (за городом, наложение, лимит 20);
 *  - хранилища предложений: API R06 (/api/civic/v2/proposals) и локальная заглушка по CONTRACT §7.
 *
 * Подключение в браузере: <script src="/civic/build3d/build3d-core.js"></script> → window.CivicBuild3DCore.
 * В Node: require("…/build3d-core.js").
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CivicBuild3DCore = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ───────────── Каталог ─────────────
  // w — ширина (по оси «восток» при повороте 0°), d — глубина (по оси «север»), метры.
  // Размеры — типичные для дворовых объектов Астаны; модели строятся ровно в этих габаритах.
  var KINDS = {
    square: { id: "square", icon: "trees", key: "proposal.kind.square", w: 40, d: 30, h: 7 },
    playground: { id: "playground", icon: "playground", key: "proposal.kind.playground", w: 24, d: 18, h: 4.2 },
    sports: { id: "sports", icon: "ball", key: "proposal.kind.sports", w: 32, d: 20, h: 3.2 },
    stop: { id: "stop", icon: "bus", key: "proposal.kind.stop", w: 12, d: 4.5, h: 3.2 },
    // Освещение — не прямоугольник, а линия вдоль участка улицы: столбы примерно через 30 м.
    lighting: { id: "lighting", icon: "bulb", key: "proposal.kind.lighting", line: true, step: 30, h: 9 },
  };
  var KIND_ORDER = ["square", "playground", "sports", "stop", "lighting"];
  var MAX_OBJECTS = 20;
  var LIGHT_STEP_M = 30;
  var LIGHT_OFFSET_M = 5; // столбы ставим сбоку от оси улицы, а не посреди проезжей части
  var LIGHT_MAX_M = 900; // длиннее — уже не «участок», а вся улица (≈ 30 столбов)
  var LIGHT_MIN_M = 20;
  var SNAP_STREET_M = 45; // насколько далеко от оси улицы можно нажать при выборе участка
  var STOP_ALIGN_M = 35; // остановка сама разворачивается вдоль улицы, если улица ближе этого

  // ───────────── Меркатор как в MapLibre ─────────────
  // MapLibre считает метры через радиус 6371008.8 (MercatorCoordinate.meterInMercatorCoordinateUnits).
  var EARTH_R = 6371008.8;
  var EARTH_C = 2 * Math.PI * EARTH_R;
  var DEG = Math.PI / 180;

  function mercX(lon) {
    return (180 + lon) / 360;
  }
  function mercY(lat) {
    return (180 - (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))) / 360;
  }
  function lonFromMercX(x) {
    return x * 360 - 180;
  }
  function latFromMercY(y) {
    var y2 = 180 - y * 360;
    return (360 / Math.PI) * Math.atan(Math.exp((y2 * Math.PI) / 180)) - 90;
  }
  // Сколько единиц меркатора в одном метре на широте lat.
  function meterInMerc(lat) {
    return 1 / EARTH_C / Math.cos(lat * DEG);
  }

  // Локальная система «ENU»: x — метры на восток, y — метры на север от точки origin [lon, lat].
  // Считается через меркатор того же масштаба, что и у сцены, поэтому объект встаёт ровно в точку
  // щелчка (расхождение масштаба на 1 км — около 0.04 %, то есть 1 см на 30-метровом объекте).
  function toLocal(origin, lngLat) {
    var s = meterInMerc(origin[1]);
    return [(mercX(lngLat[0]) - mercX(origin[0])) / s, -(mercY(lngLat[1]) - mercY(origin[1])) / s];
  }
  function fromLocal(origin, xy) {
    var s = meterInMerc(origin[1]);
    return [lonFromMercX(mercX(origin[0]) + xy[0] * s), latFromMercY(mercY(origin[1]) - xy[1] * s)];
  }
  // Настоящее расстояние по поверхности Земли (для тестов и проверки допусков).
  function haversineM(a, b) {
    var p1 = a[1] * DEG,
      p2 = b[1] * DEG;
    var dp = p2 - p1,
      dl = (b[0] - a[0]) * DEG;
    var h = Math.sin(dp / 2) * Math.sin(dp / 2) + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) * Math.sin(dl / 2);
    return 2 * EARTH_R * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  // ───────────── Линии (в локальных метрах) ─────────────

  function polylineLength(pts) {
    var L = 0;
    for (var i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    return L;
  }

  // Точки через равные промежутки около step метров, включая оба конца:
  // n = round(L / step) промежутков → шаг L / n (на 100 м при step 30 — 3 промежутка по 33 м, 4 столба).
  // У каждой точки — направление линии (единичный вектор) для разворота столба.
  function sampleAlong(pts, step) {
    var L = polylineLength(pts);
    if (!(L > 0)) return [];
    var n = Math.max(1, Math.round(L / step));
    var spacing = L / n;
    var out = [];
    var seg = 0,
      segStart = 0;
    for (var k = 0; k <= n; k++) {
      var target = Math.min(L, k * spacing);
      while (seg < pts.length - 2) {
        var segLen = Math.hypot(pts[seg + 1][0] - pts[seg][0], pts[seg + 1][1] - pts[seg][1]);
        if (segStart + segLen >= target - 1e-9) break;
        segStart += segLen;
        seg++;
      }
      var a = pts[seg],
        b = pts[seg + 1];
      var len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
      var t = Math.max(0, Math.min(1, (target - segStart) / len));
      out.push({
        p: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t],
        dir: [(b[0] - a[0]) / len, (b[1] - a[1]) / len],
        along: target,
      });
    }
    return out;
  }

  // Проекция точки на ломаную: ближайшая точка, расстояние, номер отрезка и путь от начала.
  function projectOnPolyline(p, pts) {
    var best = null,
      along = 0;
    for (var i = 0; i < pts.length - 1; i++) {
      var a = pts[i],
        b = pts[i + 1];
      var dx = b[0] - a[0],
        dy = b[1] - a[1];
      var L2 = dx * dx + dy * dy;
      var t = L2 > 0 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2)) : 0;
      var q = [a[0] + dx * t, a[1] + dy * t];
      var d = Math.hypot(p[0] - q[0], p[1] - q[1]);
      var segLen = Math.sqrt(L2);
      if (!best || d < best.dist) best = { dist: d, seg: i, t: t, point: q, along: along + segLen * t };
      along += segLen;
    }
    return best;
  }

  // Часть ломаной между двумя расстояниями от начала (from ≤ to), с точками излома внутри.
  function sliceAlong(pts, from, to) {
    var out = [];
    var acc = 0;
    for (var i = 0; i < pts.length - 1; i++) {
      var a = pts[i],
        b = pts[i + 1];
      var len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      var s0 = acc,
        s1 = acc + len;
      if (s1 >= from && s0 <= to && len > 0) {
        var t0 = Math.max(0, (from - s0) / len),
          t1 = Math.min(1, (to - s0) / len);
        var p0 = [a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0];
        var p1 = [a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1];
        if (!out.length) out.push(p0);
        else {
          var last = out[out.length - 1];
          if (Math.hypot(last[0] - p0[0], last[1] - p0[1]) > 1e-6) out.push(p0);
        }
        out.push(p1);
      }
      acc = s1;
    }
    return out;
  }

  // Направление (азимут) в градусах: 0 — север, 90 — восток.
  function bearingDeg(dx, dy) {
    var a = (Math.atan2(dx, dy) * 180) / Math.PI;
    return (a + 360) % 360;
  }
  function normDeg(a) {
    a = a % 360;
    return a < 0 ? a + 360 : a;
  }

  // ───────────── Индекс улиц ─────────────
  // data — web/civic/build3d/data/nura-streets.json (рёбра пешеходного графа с id как у R12).
  function StreetIndex(data) {
    if (!data || !Array.isArray(data.edges)) throw new Error("street data: нет edges");
    var bbox = data.bbox || [71.4, 51.12, 71.4, 51.12];
    this.bbox = bbox;
    this.origin = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
    this.names = data.names || [];
    var origin = this.origin;
    this.edges = data.edges.map(function (row, i) {
      var geom = row[5];
      var local = geom.map(function (c) {
        return toLocal(origin, c);
      });
      var xs = local.map(function (p) {
        return p[0];
      });
      var ys = local.map(function (p) {
        return p[1];
      });
      return {
        i: i,
        id: row[0],
        name: data.names[row[1]] || "",
        from: row[2],
        to: row[3],
        geom: geom,
        local: local,
        length: polylineLength(local),
        box: [Math.min.apply(null, xs), Math.min.apply(null, ys), Math.max.apply(null, xs), Math.max.apply(null, ys)],
      };
    });
  }

  // Ближайшее ребро (по желанию — только с заданным именем) не дальше maxDist метров.
  StreetIndex.prototype.nearest = function (lngLat, maxDist, onlyName) {
    var p = toLocal(this.origin, lngLat);
    var best = null;
    for (var k = 0; k < this.edges.length; k++) {
      var e = this.edges[k];
      if (onlyName && e.name !== onlyName) continue;
      if (p[0] < e.box[0] - maxDist || p[0] > e.box[2] + maxDist || p[1] < e.box[1] - maxDist || p[1] > e.box[3] + maxDist)
        continue;
      var pr = projectOnPolyline(p, e.local);
      if (pr && pr.dist <= maxDist && (!best || pr.dist < best.dist)) {
        best = { edge: e, dist: pr.dist, along: pr.along, seg: pr.seg, point: pr.point };
      }
    }
    if (!best) return null;
    var a = best.edge.local[best.seg],
      b = best.edge.local[best.seg + 1];
    best.bearing = bearingDeg(b[0] - a[0], b[1] - a[1]);
    best.lngLat = fromLocal(this.origin, best.point);
    return best;
  };

  // Участок улицы между двумя точками: по рёбрам ОДНОЙ улицы (одно имя), кратчайший путь (Дейкстра).
  // Возврат: {ok:true, name, coords:[[lon,lat]…], length_m, edge_ids:[…]} или {ok:false, reason}.
  // reason: "far_from_street" | "other_street" | "no_path" | "too_short" | "too_long".
  StreetIndex.prototype.section = function (aLngLat, bLngLat, opts) {
    opts = opts || {};
    var maxDist = opts.maxDist || SNAP_STREET_M;
    var A = this.nearest(aLngLat, maxDist);
    if (!A) return { ok: false, reason: "far_from_street", end: "a" };
    var B = this.nearest(bLngLat, maxDist, A.edge.name);
    if (!B) {
      var anyB = this.nearest(bLngLat, maxDist);
      return { ok: false, reason: anyB ? "other_street" : "far_from_street", end: "b", name: A.edge.name };
    }
    var path;
    if (A.edge === B.edge) {
      var lo = Math.min(A.along, B.along),
        hi = Math.max(A.along, B.along);
      var part = sliceAlong(A.edge.local, lo, hi);
      if (A.along > B.along) part.reverse();
      path = { local: part, ids: [A.edge.id] };
    } else {
      path = this._pathBetween(A, B);
      if (!path) return { ok: false, reason: "no_path", name: A.edge.name };
    }
    var length = polylineLength(path.local);
    if (length < (opts.minLength || LIGHT_MIN_M)) return { ok: false, reason: "too_short", name: A.edge.name };
    if (length > (opts.maxLength || LIGHT_MAX_M)) return { ok: false, reason: "too_long", name: A.edge.name };
    var origin = this.origin;
    return {
      ok: true,
      name: A.edge.name,
      coords: path.local.map(function (p) {
        return fromLocal(origin, p);
      }),
      length_m: length,
      edge_ids: path.ids,
    };
  };

  // Дейкстра по рёбрам одного имени. Старт — оба конца ребра A (с частичной длиной),
  // финиш — оба конца ребра B. Возвращает ломаную от точки A до точки B.
  StreetIndex.prototype._pathBetween = function (A, B) {
    var name = A.edge.name;
    var adj = {};
    this.edges.forEach(function (e) {
      if (e.name !== name || e === A.edge || e === B.edge) return;
      (adj[e.from] = adj[e.from] || []).push({ e: e, to: e.to, fwd: true });
      (adj[e.to] = adj[e.to] || []).push({ e: e, to: e.from, fwd: false });
    });
    var dist = {},
      prev = {},
      done = {};
    var queue = [];
    function push(node, d, via) {
      if (dist[node] === undefined || d < dist[node]) {
        dist[node] = d;
        prev[node] = via;
        queue.push([d, node]);
      }
    }
    // Из точки A к началу ребра (назад) и к концу (вперёд).
    push(A.edge.from, A.along, { start: "back" });
    push(A.edge.to, A.edge.length - A.along, { start: "fwd" });
    while (queue.length) {
      queue.sort(function (x, y) {
        return x[0] - y[0];
      });
      var cur = queue.shift();
      var node = cur[1];
      if (done[node]) continue;
      done[node] = true;
      (adj[node] || []).forEach(function (step) {
        push(step.to, dist[node] + step.e.length, { edge: step.e, fwd: step.fwd, from: node });
      });
    }
    // Финиш: через начало ребра B (идём по нему вперёд до точки) или через конец (назад).
    var viaFrom = dist[B.edge.from] !== undefined ? dist[B.edge.from] + B.along : Infinity;
    var viaTo = dist[B.edge.to] !== undefined ? dist[B.edge.to] + (B.edge.length - B.along) : Infinity;
    if (!isFinite(viaFrom) && !isFinite(viaTo)) return null;
    var endNode = viaFrom <= viaTo ? B.edge.from : B.edge.to;
    // Восстанавливаем цепочку рёбер от endNode к старту.
    var chain = [];
    var n = endNode,
      startMode = null,
      guard = 0;
    while (guard++ < 100000) {
      var v = prev[n];
      if (!v) return null;
      if (v.start) {
        startMode = v.start;
        break;
      }
      chain.unshift(v);
      n = v.from;
    }
    var pts = [];
    var ids = [A.edge.id];
    // Кусок ребра A от точки до выхода.
    var aPart =
      startMode === "fwd"
        ? sliceAlong(A.edge.local, A.along, A.edge.length)
        : sliceAlong(A.edge.local, 0, A.along).reverse();
    appendPts(pts, aPart);
    chain.forEach(function (v) {
      var g = v.fwd ? v.edge.local.slice() : v.edge.local.slice().reverse();
      appendPts(pts, g);
      ids.push(v.edge.id);
    });
    var bPart =
      endNode === B.edge.from ? sliceAlong(B.edge.local, 0, B.along) : sliceAlong(B.edge.local, B.along, B.edge.length).reverse();
    appendPts(pts, bPart);
    ids.push(B.edge.id);
    return { local: pts, ids: ids };
  };

  function appendPts(out, pts) {
    pts.forEach(function (p) {
      var last = out[out.length - 1];
      if (!last || Math.hypot(last[0] - p[0], last[1] - p[1]) > 0.01) out.push(p);
    });
  }

  // ───────────── Районы ─────────────

  function pointInRing(x, y, ring) {
    var c = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      var xi = ring[i][0],
        yi = ring[i][1],
        xj = ring[j][0],
        yj = ring[j][1];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
    }
    return c;
  }
  // data — web/civic/build3d/data/astana-districts.json. Возвращает id района или null (за городом).
  function districtAt(data, lngLat) {
    if (!data || !Array.isArray(data.districts)) return null;
    for (var i = 0; i < data.districts.length; i++) {
      var d = data.districts[i];
      for (var k = 0; k < d.rings.length; k++) {
        if (pointInRing(lngLat[0], lngLat[1], d.rings[k])) return d.id;
      }
    }
    return null;
  }

  // ───────────── Пятно объекта и проверка места ─────────────

  // Углы прямоугольника объекта в локальных метрах (x — восток, y — север), поворот по часовой.
  function footprintCorners(kind, center, rotationDeg) {
    var k = KINDS[kind];
    var hw = k.w / 2,
      hd = k.d / 2;
    var r = -rotationDeg * DEG; // поворот по часовой стрелке, как азимут
    var c = Math.cos(r),
      s = Math.sin(r);
    return [
      [-hw, -hd],
      [hw, -hd],
      [hw, hd],
      [-hw, hd],
    ].map(function (p) {
      return [center[0] + p[0] * c - p[1] * s, center[1] + p[0] * s + p[1] * c];
    });
  }

  // Пересечение двух выпуклых многоугольников (теорема о разделяющей оси).
  function polygonsOverlap(a, b) {
    var polys = [a, b];
    for (var pi = 0; pi < 2; pi++) {
      var poly = polys[pi];
      for (var i = 0; i < poly.length; i++) {
        var p1 = poly[i],
          p2 = poly[(i + 1) % poly.length];
        var nx = p2[1] - p1[1],
          ny = p1[0] - p2[0];
        var minA = Infinity,
          maxA = -Infinity,
          minB = Infinity,
          maxB = -Infinity;
        a.forEach(function (p) {
          var v = p[0] * nx + p[1] * ny;
          minA = Math.min(minA, v);
          maxA = Math.max(maxA, v);
        });
        b.forEach(function (p) {
          var v = p[0] * nx + p[1] * ny;
          minB = Math.min(minB, v);
          maxB = Math.max(maxB, v);
        });
        // Небольшой зазор (касание краями — допустимо).
        if (maxA <= minB + 1e-6 || maxB <= minA + 1e-6) return false;
      }
    }
    return true;
  }

  // Пятно предложения в локальных метрах вокруг origin: прямоугольник или «коридор» линии.
  function proposalShape(p, origin) {
    if (p.kind === "lighting") {
      var line = p.geometry.coordinates.map(function (c) {
        return toLocal(origin, c);
      });
      return { line: line };
    }
    var center = toLocal(origin, p.geometry.coordinates);
    return { poly: footprintCorners(p.kind, center, p.rotation_deg || 0) };
  }

  // Можно ли поставить объект: {ok, reason}. reason: "limit" | "outside_city" | "overlap" | "invalid".
  // candidate — черновик предложения (как в хранилище), existing — уже стоящие предложения.
  function checkPlacement(candidate, existing, districtsData) {
    existing = existing || [];
    if (existing.length >= MAX_OBJECTS) return { ok: false, reason: "limit" };
    if (!candidate || !KINDS[candidate.kind] || !candidate.geometry) return { ok: false, reason: "invalid" };
    var pts =
      candidate.geometry.type === "Point" ? [candidate.geometry.coordinates] : candidate.geometry.coordinates || [];
    if (!pts.length) return { ok: false, reason: "invalid" };
    if (districtsData) {
      for (var i = 0; i < pts.length; i++) {
        if (!districtAt(districtsData, pts[i])) return { ok: false, reason: "outside_city" };
      }
    }
    if (candidate.kind === "lighting") return { ok: true };
    var origin = candidate.geometry.coordinates;
    var mine = proposalShape(candidate, origin).poly;
    for (var k = 0; k < existing.length; k++) {
      var other = existing[k];
      if (other.kind === "lighting" || other.id === candidate.id) continue;
      var shape = proposalShape(other, origin);
      if (shape.poly && polygonsOverlap(mine, shape.poly)) return { ok: false, reason: "overlap", with: other.id };
    }
    return { ok: true };
  }

  // ───────────── Запись предложения (CONTRACT §7 + поля 3D) ─────────────
  // {id, kind, geometry, status:"proposal", votes_up, votes_down} — обязательные поля контракта.
  // Дополнительно (передано R06 в INTEGRATION.txt): rotation_deg, year, district, near_street,
  // target (для освещения — участок улицы), created_at, demo.

  function newId() {
    var rnd = Math.floor(Math.random() * 0xffffff)
      .toString(36)
      .padStart(5, "0");
    return "p-" + Date.now().toString(36) + "-" + rnd;
  }

  function isLngLat(c) {
    return (
      Array.isArray(c) &&
      c.length >= 2 &&
      isFinite(c[0]) &&
      isFinite(c[1]) &&
      Math.abs(c[0]) <= 180 &&
      Math.abs(c[1]) <= 85 &&
      c[0] !== null &&
      c[1] !== null
    );
  }

  // Приводит запись из API/хранилища к ожидаемому виду; неверная запись → null (её не рисуем).
  function normalizeProposal(raw) {
    if (!raw || typeof raw !== "object") return null;
    var kind = raw.kind;
    if (!KINDS[kind]) return null;
    var g = raw.geometry;
    if (!g || typeof g !== "object") return null;
    if (kind === "lighting") {
      if (g.type !== "LineString" || !Array.isArray(g.coordinates) || g.coordinates.length < 2) return null;
      if (!g.coordinates.every(isLngLat)) return null;
    } else if (g.type !== "Point" || !isLngLat(g.coordinates)) return null;
    var num = function (v, d) {
      v = Number(v);
      return isFinite(v) ? v : d;
    };
    return {
      id: String(raw.id || newId()),
      kind: kind,
      geometry:
        kind === "lighting"
          ? {
              type: "LineString",
              coordinates: g.coordinates.map(function (c) {
                return [Number(c[0]), Number(c[1])];
              }),
            }
          : { type: "Point", coordinates: [Number(g.coordinates[0]), Number(g.coordinates[1])] },
      rotation_deg: normDeg(num(raw.rotation_deg, 0)),
      status: typeof raw.status === "string" ? raw.status : "proposal",
      votes_up: Math.max(0, Math.round(num(raw.votes_up, 0))),
      votes_down: Math.max(0, Math.round(num(raw.votes_down, 0))),
      my_vote: raw.my_vote === 1 || raw.my_vote === -1 ? raw.my_vote : 0,
      year: Math.round(num(raw.year, 2027)),
      district: typeof raw.district === "string" ? raw.district : null,
      near_street: typeof raw.near_street === "string" ? raw.near_street : null,
      target: raw.target && typeof raw.target === "object" ? raw.target : null,
      created_at: typeof raw.created_at === "string" ? raw.created_at : null,
      demo: raw.demo === true,
    };
  }

  // ───────────── Хранилища ─────────────
  // Общий интерфейс (всё — Promise):
  //   list() → [proposal]; create(draft) → proposal; remove(id) → true; restore(proposal) → proposal;
  //   vote(id, value, deviceId) → proposal.   Поле mode: "api" | "local".

  var LOCAL_KEY = "birge.build3d.proposals.v1";
  var DEVICE_KEY = "birge.device_id";

  function safeStorage(storage) {
    // localStorage может отсутствовать (Node, приватный режим) — тогда память процесса.
    var mem = {};
    var s = storage;
    return {
      get: function (k) {
        try {
          return s ? s.getItem(k) : mem[k] || null;
        } catch (e) {
          return mem[k] || null;
        }
      },
      set: function (k, v) {
        try {
          if (s) s.setItem(k, v);
          else mem[k] = v;
        } catch (e) {
          mem[k] = v;
        }
      },
    };
  }

  function getDeviceId(storage) {
    var st = safeStorage(storage);
    var id = st.get(DEVICE_KEY);
    if (!id) {
      id = "dev-" + Date.now().toString(36) + "-" + Math.floor(Math.random() * 1e9).toString(36);
      st.set(DEVICE_KEY, id);
    }
    return id;
  }

  function clone(o) {
    return JSON.parse(JSON.stringify(o));
  }

  // Заглушка R06 на этом устройстве: localStorage + стартовые примеры из фикстуры (demo:true).
  // Голос: один с устройства; повторное нажатие той же кнопки ничего не меняет, другой — переносит голос.
  function createLocalStore(opts) {
    opts = opts || {};
    var st = safeStorage(opts.storage);
    var key = opts.key || LOCAL_KEY;
    var seed = (opts.fixture && opts.fixture.proposals) || [];
    function read() {
      var raw = st.get(key);
      var data = null;
      try {
        data = raw ? JSON.parse(raw) : null;
      } catch (e) {
        data = null;
      }
      if (!data || !Array.isArray(data.items)) {
        data = { items: seed.map(normalizeProposal).filter(Boolean), votes: {} };
        write(data);
      }
      data.votes = data.votes || {};
      return data;
    }
    function write(data) {
      st.set(key, JSON.stringify(data));
    }
    function withVote(p, data) {
      var out = clone(p);
      out.my_vote = data.votes[p.id] || 0;
      return out;
    }
    return {
      mode: "local",
      list: function () {
        var data = read();
        return Promise.resolve(
          data.items.map(function (p) {
            return withVote(p, data);
          })
        );
      },
      create: function (draft) {
        var data = read();
        if (data.items.length >= MAX_OBJECTS) return Promise.reject(storeError("limit"));
        var p = normalizeProposal(Object.assign({}, draft, { id: draft.id || newId(), votes_up: 0, votes_down: 0 }));
        if (!p) return Promise.reject(storeError("invalid"));
        p.created_at = p.created_at || new Date().toISOString();
        data.items.push(p);
        write(data);
        return Promise.resolve(withVote(p, data));
      },
      restore: function (p) {
        var data = read();
        var n = normalizeProposal(p);
        if (!n) return Promise.reject(storeError("invalid"));
        data.items = data.items.filter(function (x) {
          return x.id !== n.id;
        });
        data.items.push(n);
        if (p.my_vote) data.votes[n.id] = p.my_vote;
        write(data);
        return Promise.resolve(withVote(n, data));
      },
      remove: function (id) {
        var data = read();
        data.items = data.items.filter(function (x) {
          return x.id !== id;
        });
        delete data.votes[id];
        write(data);
        return Promise.resolve(true);
      },
      vote: function (id, value) {
        var data = read();
        var p = data.items.find(function (x) {
          return x.id === id;
        });
        if (!p) return Promise.reject(storeError("not_found"));
        if (value !== 1 && value !== -1) return Promise.reject(storeError("invalid"));
        var prevVote = data.votes[id] || 0;
        if (prevVote !== value) {
          if (prevVote === 1) p.votes_up = Math.max(0, p.votes_up - 1);
          if (prevVote === -1) p.votes_down = Math.max(0, p.votes_down - 1);
          if (value === 1) p.votes_up += 1;
          else p.votes_down += 1;
          data.votes[id] = value;
          write(data);
        }
        return Promise.resolve(withVote(p, data));
      },
    };
  }

  function storeError(code, status) {
    var e = new Error(code);
    e.code = code;
    if (status) e.status = status;
    return e;
  }

  // Клиент API R06 (CONTRACT §7). DELETE /proposals/{id} — запрошен у R06 в INTEGRATION.txt.
  function createApiStore(opts) {
    opts = opts || {};
    var prefix = (opts.prefix || "/api/civic/v2").replace(/\/$/, "");
    var fetchFn = opts.fetch || (typeof fetch === "function" ? fetch.bind(null) : null);
    var timeoutMs = opts.timeoutMs || 8000;
    function call(method, path, body) {
      if (!fetchFn) return Promise.reject(storeError("network"));
      var ctrl = typeof AbortController === "function" ? new AbortController() : null;
      var timer = ctrl
        ? setTimeout(function () {
            ctrl.abort();
          }, timeoutMs)
        : null;
      var init = { method: method, headers: { Accept: "application/json" }, signal: ctrl ? ctrl.signal : undefined };
      if (body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(body);
      }
      return fetchFn(prefix + path, init).then(
        function (res) {
          if (timer) clearTimeout(timer);
          return res.text().then(function (text) {
            var data = null;
            try {
              data = text ? JSON.parse(text) : null;
            } catch (e) {
              data = null;
            }
            if (!res.ok) {
              var code = (data && data.error && data.error.code) || (data && data.code) || "http_" + res.status;
              throw storeError(code, res.status);
            }
            if (text && data === null) throw storeError("bad_json", res.status);
            return data;
          });
        },
        function (err) {
          if (timer) clearTimeout(timer);
          throw storeError(err && err.name === "AbortError" ? "timeout" : "network");
        }
      );
    }
    function one(data) {
      var p = normalizeProposal(data && data.proposal ? data.proposal : data);
      if (!p) throw storeError("bad_response");
      return p;
    }
    return {
      mode: "api",
      list: function (bbox) {
        var q = bbox ? "?bbox=" + bbox.map(function (v) {
          return Number(v).toFixed(6);
        }).join(",") : "";
        return call("GET", "/proposals" + q).then(function (data) {
          var items = Array.isArray(data) ? data : data && (data.items || data.proposals);
          if (!Array.isArray(items)) throw storeError("bad_response");
          return items.map(normalizeProposal).filter(Boolean);
        });
      },
      create: function (draft) {
        return call("POST", "/proposals", draft).then(one);
      },
      restore: function (p) {
        // Возврат удалённого: создаём заново с теми же полями (id может смениться — его выдаёт сервер).
        var copy = clone(p);
        delete copy.my_vote;
        return call("POST", "/proposals", copy).then(one);
      },
      remove: function (id) {
        return call("DELETE", "/proposals/" + encodeURIComponent(id)).then(function () {
          return true;
        });
      },
      vote: function (id, value, deviceId) {
        return call("POST", "/proposals/" + encodeURIComponent(id) + "/vote", { value: value, device_id: deviceId }).then(
          function (data) {
            var p = one(data);
            if (!p.my_vote) p.my_vote = value;
            return p;
          }
        );
      },
    };
  }

  // «Авто»: если у сервера есть /proposals — работаем с ним; если адреса нет (404/405/501)
  // или модуль R06 не подключён (503 module_unavailable), либо сервера нет вовсе (страница
  // открыта статикой) — честно переходим на заглушку этого устройства (mode = "local").
  function isMissingApi(err) {
    if (!err) return false;
    if (err.code === "network" || err.code === "bad_json") return true;
    return err.status === 404 || err.status === 405 || err.status === 501 || err.status === 503;
  }

  function createAutoStore(opts) {
    var api = createApiStore(opts);
    var local = createLocalStore(opts);
    var active = null;
    var store = {
      mode: "pending",
      list: function (bbox) {
        if (active) return active.list(bbox);
        return api.list(bbox).then(
          function (items) {
            active = api;
            store.mode = "api";
            return items;
          },
          function (err) {
            if (!isMissingApi(err)) throw err;
            active = local;
            store.mode = "local";
            return local.list();
          }
        );
      },
    };
    ["create", "restore", "remove", "vote"].forEach(function (m) {
      store[m] = function () {
        var args = arguments;
        var go = function () {
          return active[m].apply(active, args);
        };
        return active ? go() : store.list().then(go);
      };
    });
    return store;
  }

  return {
    KINDS: KINDS,
    KIND_ORDER: KIND_ORDER,
    MAX_OBJECTS: MAX_OBJECTS,
    LIGHT_STEP_M: LIGHT_STEP_M,
    LIGHT_OFFSET_M: LIGHT_OFFSET_M,
    LIGHT_MAX_M: LIGHT_MAX_M,
    LIGHT_MIN_M: LIGHT_MIN_M,
    SNAP_STREET_M: SNAP_STREET_M,
    STOP_ALIGN_M: STOP_ALIGN_M,
    EARTH_R: EARTH_R,
    mercX: mercX,
    mercY: mercY,
    lonFromMercX: lonFromMercX,
    latFromMercY: latFromMercY,
    meterInMerc: meterInMerc,
    toLocal: toLocal,
    fromLocal: fromLocal,
    haversineM: haversineM,
    polylineLength: polylineLength,
    sampleAlong: sampleAlong,
    projectOnPolyline: projectOnPolyline,
    sliceAlong: sliceAlong,
    bearingDeg: bearingDeg,
    normDeg: normDeg,
    StreetIndex: StreetIndex,
    pointInRing: pointInRing,
    districtAt: districtAt,
    footprintCorners: footprintCorners,
    polygonsOverlap: polygonsOverlap,
    proposalShape: proposalShape,
    checkPlacement: checkPlacement,
    newId: newId,
    normalizeProposal: normalizeProposal,
    getDeviceId: getDeviceId,
    createLocalStore: createLocalStore,
    createApiStore: createApiStore,
    createAutoStore: createAutoStore,
    isMissingApi: isMissingApi,
    LOCAL_KEY: LOCAL_KEY,
  };
});
