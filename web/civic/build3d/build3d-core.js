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

  // ───────────── Настоящие объекты OSM (рядом уже есть …, двор) ─────────────
  // data — web/civic/build3d/data/astana-existing.json (из data/civic/astana/osm-objects, LOCAL-1).
  // Это СУЩЕСТВУЮЩИЕ объекты: модуль их не рисует, а только подсказывает акимату «рядом уже есть остановка»
  // и привязывает предложение к двору (yard-<id>, CONTRACT §4), чтобы оно связалось с жалобами на этот двор.
  var EXISTING_KIND = { stop: "stop", playground: "playground", sports: "sports", square: "square", lighting: "lamp" };
  var NEAR_M = { stop: 80, playground: 60, sports: 60, square: 60 };
  var LAMP_NEAR_M = 15;

  function ExistingIndex(data) {
    this.points = (data && data.points) || {};
    this.yards = ((data && data.yards) || []).map(function (row) {
      var ring = row[4] || [];
      var xs = ring.map(function (p) {
        return p[0];
      });
      var ys = ring.map(function (p) {
        return p[1];
      });
      return { id: row[0], name_ru: row[2] || null, name_kk: row[3] || null, ring: ring, box: [Math.min.apply(null, xs), Math.min.apply(null, ys), Math.max.apply(null, xs), Math.max.apply(null, ys)] };
    });
  }

  // Ближайший настоящий объект того же вида, что и проект: {id, name_ru, name_kk, dist_m} или null.
  // Расстояние — от края пятна (у парков и площадок есть радиус), не меньше 0.
  ExistingIndex.prototype.nearestSame = function (kind, lngLat, maxM) {
    var list = this.points[EXISTING_KIND[kind]] || [];
    maxM = maxM || NEAR_M[kind] || 60;
    var best = null;
    var kx = 111320 * Math.cos(lngLat[1] * DEG),
      ky = 110540;
    for (var i = 0; i < list.length; i++) {
      var row = list[i];
      var dx = (row[0] - lngLat[0]) * kx,
        dy = (row[1] - lngLat[1]) * ky;
      if (Math.abs(dx) > maxM + 600 || Math.abs(dy) > maxM + 600) continue;
      var d = Math.max(0, Math.hypot(dx, dy) - (row[5] || 0));
      if (d <= maxM && (!best || d < best.dist_m)) best = { id: row[2], name_ru: row[3] || null, name_kk: row[4] || null, dist_m: d };
    }
    return best;
  };

  // Сколько настоящих фонарей OSM стоит вдоль участка (не дальше 15 м от оси). Ноль ничего не доказывает:
  // в OSM отмечена малая часть фонарей, поэтому интерфейс говорит только о найденных.
  ExistingIndex.prototype.lampsAlong = function (coords, maxM) {
    var list = this.points.lamp || [];
    maxM = maxM || LAMP_NEAR_M;
    if (!coords || coords.length < 2) return 0;
    var origin = coords[0];
    var line = coords.map(function (c) {
      return toLocal(origin, c);
    });
    var n = 0;
    for (var i = 0; i < list.length; i++) {
      if (haversineM(origin, list[i]) > 2000) continue;
      var pr = projectOnPolyline(toLocal(origin, list[i]), line);
      if (pr && pr.dist <= maxM) n++;
    }
    return n;
  };

  // Двор (жилой квартал OSM), в котором стоит точка: {id: "yard-<id>", name_ru, name_kk} или null.
  ExistingIndex.prototype.yardAt = function (lngLat) {
    for (var i = 0; i < this.yards.length; i++) {
      var y = this.yards[i];
      if (lngLat[0] < y.box[0] || lngLat[0] > y.box[2] || lngLat[1] < y.box[1] || lngLat[1] > y.box[3]) continue;
      if (pointInRing(lngLat[0], lngLat[1], y.ring)) return { id: y.id, name_ru: y.name_ru, name_kk: y.name_kk };
    }
    return null;
  };

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
      // Год на табличке: у R06 поле planned_year (может быть пустым — тогда просто «Проект»).
      year: (function () {
        var y = raw.year != null ? raw.year : raw.planned_year !== undefined ? raw.planned_year : 2027;
        return y === null || !isFinite(Number(y)) ? null : Math.round(Number(y));
      })(),
      voting_open: typeof raw.voting_open === "boolean" ? raw.voting_open : (typeof raw.status === "string" ? raw.status : "proposal") === "proposal",
      title_ru: typeof raw.title_ru === "string" ? raw.title_ru : null,
      title_kk: typeof raw.title_kk === "string" ? raw.title_kk : null,
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

  // Случайный id устройства для «один голос с устройства». Тот же ключ и формат, что у карточки R06
  // (birge.device_id, "dev-" + 32 hex): «мой голос» совпадает в обеих карточках. Старый короткий id заменяется.
  function getDeviceId(storage) {
    var st = safeStorage(storage);
    var id = st.get(DEVICE_KEY);
    if (!id || !/^[A-Za-z0-9_-]{16,128}$/.test(id)) {
      var bytes = new Array(16);
      var g = typeof self !== "undefined" ? self : null;
      var cr = g && g.crypto && g.crypto.getRandomValues ? g.crypto : null;
      if (cr) bytes = Array.prototype.slice.call(cr.getRandomValues(new Uint8Array(16)));
      else
        for (var i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
      id =
        "dev-" +
        bytes
          .map(function (b) {
            return ("0" + b.toString(16)).slice(-2);
          })
          .join("");
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

  // Клиент API R06 — по НАСТОЯЩЕМУ контракту поставки R06 (claude/round-14-r06 @ 3d10f7d, ui/civic_store/v2.py,
  // proposals.py) и шлюза R01 (claude/sharp-dijkstra-0t87gl, ui/web_server.py V2_ROUTES):
  //   GET  /proposals?bbox&device_id            → {items:[…]}           (сервис R06 напрямую: {ok:true, data:{items}})
  //   POST /proposals  [сотрудник, X-CSRF-Token] тело ТОЛЬКО {kind, geometry, rotation_deg, planned_year, demo}
  //        (лишние поля R06 отклоняет: 422 «Неизвестное поле») → 201 {item}
  //   POST /proposals/{id}/vote {value, device_id}                    → {item, changed, previous}
  //   POST /proposals/{id}/withdraw {} [сотрудник] — «Удалить» (строка остаётся в базе, в списках не видна);
  //        если маршрута нет (404/405) — запасной DELETE /proposals/{id}.
  // Ошибки: шлюз R01 {error:"код", message, field}; сервис R06 {ok:false, error:{code, message, fields}}.
  // Контекст 3D (улица рядом, двор, участок) R06 не хранит — модуль вычисляет его по геометрии при показе.
  // opts.v2 — клиент оболочки R01 (BirgeShell.api.v2(method, path, body)): сам ставит CSRF и куки.
  var DEVICE_RE = /^[A-Za-z0-9_-]{16,128}$/;

  function errorCode(data, status) {
    var e = data && data.error;
    if (typeof e === "string") return e;
    if (e && typeof e === "object" && e.code) return e.code;
    if (data && typeof data.code === "string") return data.code;
    return "http_" + status;
  }
  function unwrap(data) {
    return data && data.ok === true && Object.prototype.hasOwnProperty.call(data, "data") ? data.data : data;
  }
  // Тело POST /proposals: только поля, которые принимает R06.
  function toServerProposal(p) {
    var body = { kind: p.kind, geometry: p.geometry, rotation_deg: Math.round(p.rotation_deg || 0), demo: p.demo === true };
    var year = p.year != null ? p.year : p.planned_year;
    if (year != null && isFinite(year)) body.planned_year = Math.round(year);
    if (typeof p.title_ru === "string" && p.title_ru) body.title_ru = p.title_ru;
    if (typeof p.title_kk === "string" && p.title_kk) body.title_kk = p.title_kk;
    return body;
  }

  function createApiStore(opts) {
    opts = opts || {};
    var prefix = (opts.prefix || "/api/civic/v2").replace(/\/$/, "");
    var fetchFn = opts.fetch || (typeof fetch === "function" ? fetch.bind(null) : null);
    var timeoutMs = opts.timeoutMs || 8000;
    var shellV2 = typeof opts.v2 === "function" ? opts.v2 : null;
    var csrfCache = null;

    // CSRF сотрудника: из оболочки R01 (CivicShell.csrfToken), иначе из GET /api/civic/v1/session (как карточка R06).
    function csrf() {
      var g = typeof self !== "undefined" ? self : null;
      try {
        var fromShell = g && g.CivicShell && typeof g.CivicShell.csrfToken === "function" ? g.CivicShell.csrfToken() : null;
        if (fromShell) return Promise.resolve(fromShell);
      } catch (e) {
        /* оболочки нет */
      }
      if (csrfCache) return Promise.resolve(csrfCache);
      if (!fetchFn) return Promise.resolve(null);
      var sessionUrl = opts.sessionUrl || "/api/civic/v1/session";
      // Никогда не падает: нет сессии или ответа — просто без токена (сервер ответит 401, модуль скажет «Войдите»).
      return Promise.resolve()
        .then(function () {
          return fetchFn(sessionUrl, { method: "GET", credentials: "same-origin", headers: { Accept: "application/json" } });
        })
        .then(function (res) {
          return res.text();
        })
        .then(function (text) {
          var data = unwrap(text ? JSON.parse(text) : null) || {};
          csrfCache = data.authenticated && typeof data.csrf_token === "string" ? data.csrf_token : null;
          return csrfCache;
        })
        .catch(function () {
          return null;
        });
    }

    function call(method, path, body, staff) {
      if (shellV2) {
        // Клиент оболочки: ошибки — объект с полями status, error (код), message.
        return Promise.resolve()
          .then(function () {
            return shellV2(method, path, body);
          })
          .then(unwrap, function (err) {
            var e = storeError((err && (typeof err.error === "string" ? err.error : err.code)) || "network", err && err.status);
            if (err && err.status === 0) e.code = "network";
            throw e;
          });
      }
      if (!fetchFn) return Promise.reject(storeError("network"));
      return (staff ? csrf() : Promise.resolve(null)).then(function (token) {
        var ctrl = typeof AbortController === "function" ? new AbortController() : null;
        var timer = ctrl
          ? setTimeout(function () {
              ctrl.abort();
            }, timeoutMs)
          : null;
        var init = {
          method: method,
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          signal: ctrl ? ctrl.signal : undefined,
        };
        if (body !== undefined) {
          init.headers["Content-Type"] = "application/json";
          init.body = JSON.stringify(body);
        }
        if (token) init.headers["X-CSRF-Token"] = token;
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
                if (res.status === 401 || res.status === 403) csrfCache = null; // сессия могла кончиться
                throw storeError(errorCode(data, res.status), res.status);
              }
              if (text && data === null) throw storeError("bad_json", res.status);
              return unwrap(data);
            });
          },
          function (err) {
            if (timer) clearTimeout(timer);
            throw storeError(err && err.name === "AbortError" ? "timeout" : "network");
          }
        );
      });
    }
    function one(data) {
      var raw = data && (data.item || data.proposal) ? data.item || data.proposal : data;
      var p = normalizeProposal(raw);
      if (!p) throw storeError("bad_response");
      return p;
    }
    var deviceId = opts.deviceId || null;
    return {
      mode: "api",
      list: function (bbox) {
        var q = [];
        if (bbox)
          q.push(
            "bbox=" +
              bbox
                .map(function (v) {
                  return Number(v).toFixed(6);
                })
                .join(",")
          );
        if (deviceId && DEVICE_RE.test(deviceId)) q.push("device_id=" + encodeURIComponent(deviceId)); // «мой голос»
        return call("GET", "/proposals" + (q.length ? "?" + q.join("&") : "")).then(function (data) {
          var items = Array.isArray(data) ? data : data && (data.items || data.proposals);
          if (!Array.isArray(items)) throw storeError("bad_response");
          return items.map(normalizeProposal).filter(Boolean);
        });
      },
      create: function (draft) {
        return call("POST", "/proposals", toServerProposal(draft), true).then(one);
      },
      restore: function (p) {
        // Возврат удалённого: создаём заново (id выдаёт сервер; голоса R06 к новому id не переносятся).
        return call("POST", "/proposals", toServerProposal(p), true).then(one);
      },
      remove: function (id) {
        var path = "/proposals/" + encodeURIComponent(id);
        return call("POST", path + "/withdraw", {}, true).then(
          function () {
            return true;
          },
          function (err) {
            if (err.status !== 404 && err.status !== 405) throw err;
            return call("DELETE", path, undefined, true).then(function () {
              return true;
            });
          }
        );
      },
      vote: function (id, value, devId) {
        return call("POST", "/proposals/" + encodeURIComponent(id) + "/vote", { value: value, device_id: devId || deviceId }).then(
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
    ExistingIndex: ExistingIndex,
    NEAR_M: NEAR_M,
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
    toServerProposal: toServerProposal,
    isMissingApi: isMissingApi,
    LOCAL_KEY: LOCAL_KEY,
  };
});
