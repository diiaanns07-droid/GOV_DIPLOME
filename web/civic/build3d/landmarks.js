/*
 * Birge · ориентиры города (R05, раунд 15, поправка П1 «Настоящий город»): поиск по названию и перелёт камеры
 * к НАСТОЯЩЕМУ зданию подложки. Моделей нет: здания рисует подложка R01 (web/civic/shell/basemap-style.js — 3D-здания
 * по высоте из OSM, слой akim-3d-landmark и подписи birge-landmark-label); здесь — только данные и камера.
 *
 * Данные: /civic/build3d/data/landmarks.json — один источник центров и названий ru/kk (data/civic/astana/landmarks/,
 * центры выведены из колец дорожек снимка OSM, пометка LOCAL-13 «сверить с контурами»).
 *
 *   const lm = await BirgeLandmarks.load();                 // один раз; повтор — тот же Promise
 *   lm.query("бай", { lang: "ru", limit: 3 })
 *     → [{ kind: "landmark", id: "baiterek", label: "Байтерек", other: "Бәйтерек", type: "монумент",
 *          point: [lon, lat], district: "esil" }]
 *   lm.get("baiterek")                                       // запись landmarks.json
 *   BirgeLandmarks.flyTo(map, "baiterek", { padding })        // → Promise: камера у здания (наклон 52°)
 *
 * Поиск — с начала любого слова названия на обоих языках и других написаний («бай», «бәй», «baiterek», «пирамида»),
 * без учёта регистра, «ё/е» и казахских букв — та же свёртка, что у индекса R12 (BirgeSearchIndex.norm).
 * padding перелёта — свободная часть карты хозяина {top, right, bottom, left}: здание встаёт в её центр (offset,
 * а не padding MapLibre — тот остался бы на карте после перелёта). «Уменьшить движение» — сразу, без полёта.
 * Без DOM и без three.js; в Node — require(...) для тестов (tests/civic/R05/round15/).
 */
(function (root, factory) {
  "use strict";
  var api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BirgeLandmarks = api;
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var URL_DEFAULT = "/civic/build3d/data/landmarks.json";
  var FOLD = { ё: "е", ә: "а", і: "и", ң: "н", ғ: "г", ү: "у", ұ: "у", қ: "к", ө: "о", һ: "х" };
  function norm(s) {
    var R12 = root && root.BirgeSearchIndex;
    if (R12 && typeof R12.norm === "function") return R12.norm(s);
    return String(s || "")
      .toLowerCase()
      .replace(/[ёәіңғүұқөһ]/g, function (c) {
        return FOLD[c];
      })
      .replace(/[«»"'().,;:!?\-–—/]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  // Сколько совпало: 0 — с начала названия, 1 — с начала слова (каждое слово запроса — начало какого-то слова), -1 — нет.
  function score(name, q, qWords) {
    var n = norm(name);
    if (!n) return -1;
    if (n.indexOf(q) === 0) return 0;
    var words = n.split(" ");
    var ok = qWords.every(function (qw) {
      return words.some(function (w) {
        return w.indexOf(qw) === 0;
      });
    });
    return ok ? 1 : -1;
  }

  function makeIndex(data) {
    var list = (data && Array.isArray(data.landmarks) ? data.landmarks : []).filter(function (l) {
      return l && typeof l.id === "string" && l.name && isFinite(l.lat) && isFinite(l.lon);
    });
    var byId = {};
    list.forEach(function (l) {
      byId[l.id] = l;
    });
    return {
      size: list.length,
      get: function (id) {
        return byId[id] || null;
      },
      all: function () {
        return list.slice();
      },
      query: function (text, opts) {
        var o = opts || {};
        var lang = o.lang === "kk" ? "kk" : "ru",
          other = lang === "kk" ? "ru" : "kk";
        var q = norm(text);
        if (!q) return [];
        var qWords = q.split(" ");
        var found = [];
        list.forEach(function (l) {
          // Своё название на языке интерфейса — первым; другое и другие написания — на шаг ниже.
          var best = score(l.name[lang], q, qWords);
          [l.name[other]].concat(l.aliases || []).forEach(function (alt) {
            var s = score(alt, q, qWords);
            if (s >= 0 && (best < 0 || s + 0.5 < best)) best = s + 0.5;
          });
          if (best >= 0) found.push([best, String(l.name[lang] || "").length, l]);
        });
        found.sort(function (a, b) {
          return a[0] - b[0] || a[1] - b[1];
        });
        return found.slice(0, o.limit || 3).map(function (f) {
          var l = f[2];
          return {
            kind: "landmark",
            id: l.id,
            label: l.name[lang] || l.name.ru,
            other: l.name[other] && l.name[other] !== l.name[lang] ? l.name[other] : "",
            type: (l.kind && (l.kind[lang] || l.kind.ru)) || "",
            point: [l.lon, l.lat],
            district: l.district || null,
          };
        });
      },
    };
  }

  var cache = null;
  function load(url, fetchFn) {
    var u = url || URL_DEFAULT;
    var f = fetchFn || (typeof fetch === "function" ? fetch : null);
    if (!f) return Promise.reject(new Error("fetch недоступен"));
    if (cache && cache.url === u) return cache.promise;
    var promise = f(u, { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("landmarks HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data || !/^birge-landmarks-v/.test(data.schema || "")) throw new Error("landmarks: неизвестный формат");
        return makeIndex(data);
      });
    cache = { url: u, promise: promise };
    promise.catch(function () {
      if (cache && cache.promise === promise) cache = null; // ошибка — следующая попытка заново
    });
    return promise;
  }

  function reducedMotion() {
    try {
      return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (e) {
      return false;
    }
  }

  // Перелёт к ориентиру: камера из landmarks.json (масштаб по размеру здания, наклон 52° — как кнопка «3D» оболочки,
  // чтобы автонаклон R01 не доворачивал камеру второй раз; поворот — вдоль оси бульвара или по двору).
  // item — id, запись landmarks.json или строка поиска (query). Возврат — Promise(true), когда камера встала.
  function flyTo(map, item, opts) {
    var o = opts || {};
    if (!map || typeof map.flyTo !== "function") return Promise.resolve(false);
    var go = function (l) {
      if (!l) return false;
      var cam = l.camera || {};
      var p = o.padding;
      // Центр здания — в центр свободной части карты: сдвиг от середины холста (не padding MapLibre: тот остаётся).
      var offset = p ? [Math.round(((p.left || 0) - (p.right || 0)) / 2), Math.round(((p.top || 0) - (p.bottom || 0)) / 2)] : [0, 0];
      var target = {
        center: [l.lon, l.lat],
        zoom: o.zoom || cam.zoom || 16.2,
        pitch: cam.pitch != null ? cam.pitch : 52,
        bearing: cam.bearing != null ? cam.bearing : -16,
        offset: offset,
      };
      return new Promise(function (resolve) {
        var done = false;
        var finish = function () {
          if (done) return;
          done = true;
          resolve(true);
        };
        map.once("moveend", finish);
        setTimeout(finish, (o.maxDuration || 3200) + 800); // полёт прервали (человек тронул карту) — не висим
        if (reducedMotion() || o.duration === 0) map.jumpTo(target);
        else map.flyTo(Object.assign({ speed: 1.1, curve: 1.42, maxDuration: o.maxDuration || 3200, essential: false }, target));
      });
    };
    if (item && typeof item === "object" && isFinite(item.lat)) return Promise.resolve(go(item));
    var id = item && typeof item === "object" ? item.id : item;
    return load(o.url).then(function (ix) {
      return go(ix.get(id));
    });
  }

  return { load: load, makeIndex: makeIndex, flyTo: flyTo, norm: norm, version: "r15-landmarks-1" };
});
