/* R12 · подсказки поиска по индексу R12 (web/civic/map/search_index.json) — помощь R01 по правилу Linear 1 эталона A:
 * «подсказки с первой буквы — улицы, остановки, дворы, районы и горячие места». Поле, список, клавиши и горячие места —
 * у R01 (и R07); здесь — только загрузка индекса и подбор вариантов.
 *
 *   const ix = await BirgeSearchIndex.load("/civic/map/search_index.json");
 *   ix.query("тур", { lang: "ru", limit: 8, exclude: ["osm-node-4109037549"] })
 *     → [{ kind: "street"|"bus_stop"|"yard"|"park"|"pitch"|"playground", id, label, other, point:[lon,lat],
 *          bbox?, seg?, district?, also? }]
 *
 * Совпадение — с начала любого слова (с первой буквы), без учёта регистра, «ё/е» и казахских букв (ә→а, і→и, ң→н,
 * ғ→г, ү/ұ→у, қ→к, ө→о, һ→х): «қаб» найдёт «Қабанбай батыр», «каб» — тоже. Порядок: с начала названия, потом с начала
 * имени после слова-типа («проспект», «Остановка»), потом с начала слова; внутри — улицы, остановки и парки раньше дворов
 * и площадок, короче — раньше. exclude — id, уже показанные R01 (горячие места R07): строка
 * объекта с таким id или его «also» не повторяется. Без DOM — проверяется в Node (tests/civic/R12/map/search_index.test.mjs).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BirgeSearchIndex = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const FOLD = { ё: "е", ә: "а", і: "и", ң: "н", ғ: "г", ү: "у", ұ: "у", қ: "к", ө: "о", һ: "х" };
  function norm(s) {
    return String(s || "").toLowerCase().replace(/[ёәіңғүұқөһ]/g, (c) => FOLD[c]).replace(/[«»"'().,;:!?\-–—/]+/g, " ").replace(/\s+/g, " ").trim();
  }
  // Улицы и остановки — главное, что ищут; дворы, парки — следом; площадки — последними. Внутри — короче раньше.
  const KIND_RANK = { street: 0, bus_stop: 0, park: 0, yard: 1, pitch: 2, playground: 2 };
  // Слова-типы не считаются «началом названия»: «тур» → «проспект Туран» и «Остановка «Туран»» — как «с начала».
  const TYPE_WORDS = new Set(["улица", "ул", "проспект", "пр", "просп", "переулок", "пер", "шоссе", "ш", "бульвар", "бул", "площадь",
    "пл", "остановка", "двор", "сквер", "детская", "площадка", "спортплощадка", "жк", "мкр", "микрорайон",
    "кошеси", "дангылы", "аялдамасы", "аула", "гулзары", "алаңы", "аланы", "тас", "жолы", "тужык"].map(norm));

  function prepare(data) {
    const items = [];
    for (const s of (data && data.streets) || []) {
      items.push({ kind: "street", id: s.seg, ru: s.ru, kk: s.kk, point: s.c, bbox: s.b, seg: s.seg, district: s.d || null });
    }
    for (const o of (data && data.objects) || []) {
      items.push({ kind: o.k, id: o.id, ru: o.ru, kk: o.kk, point: o.c, district: o.d || null, also: o.also || [] });
    }
    for (const it of items) {
      it.n = { ru: norm(it.ru), kk: norm(it.kk) };
      it.w = { ru: it.n.ru.split(" "), kk: it.n.kk.split(" ") };
    }
    return items;
  }
  // 0 — с начала названия, 0.5 — с начала после слова-типа, 1 — с начала слова, -1 — нет
  function score(words, full, q, qWords) {
    if (full.startsWith(q)) return 0;
    const core = words.filter((w) => !TYPE_WORDS.has(w));
    if (core.length && core.join(" ").startsWith(q)) return 0.5;  // после слова-типа: чуть ниже, чем само название
    if (qWords.length === 1) return words.some((w) => w.startsWith(q)) ? 1 : -1;
    // несколько слов запроса: каждое — начало какого-то слова названия («хан шат» → «Хан Шатыр»)
    return qWords.every((qw) => words.some((w) => w.startsWith(qw))) ? 1 : -1;
  }
  function makeIndex(data) {
    const items = prepare(data);
    return {
      size: items.length,
      source: (data && data.source) || null,
      query(text, opts) {
        const o = opts || {};
        const lang = o.lang === "kk" ? "kk" : "ru", other = lang === "kk" ? "ru" : "kk";
        const q = norm(text);
        if (!q) return [];
        const qWords = q.split(" ");
        const skip = new Set(o.exclude || []);
        const found = [];
        for (const it of items) {
          if (skip.has(it.id) || (it.also && it.also.some((a) => skip.has(a)))) continue;
          // ищем в обоих языках: житель может набрать русское название, сидя в ҚАЗ
          // совпадение на другом языке — на шаг ниже («парк» в ru: сам парк раньше «Остановки «Парк…»», хотя kk-подпись
          // остановки «Парк … аялдамасы» начинается с «парк»)
          const a = score(it.w[lang], it.n[lang], q, qWords), b = score(it.w[other], it.n[other], q, qWords);
          const s = a < 0 ? (b < 0 ? -1 : b + 1) : b < 0 ? a : Math.min(a, b + 1);
          if (s >= 0) found.push([s, KIND_RANK[it.kind] ?? 4, (it[lang] || "").length, it]);
        }
        found.sort((x, y) => x[0] - y[0] || x[1] - y[1] || x[2] - y[2] || String(x[3][lang]).localeCompare(String(y[3][lang])));
        const seen = new Set(), out = [];
        for (const [, , , it] of found) {
          const key = it.kind === "street" ? "s|" + it.n.ru + "|" + (it.district || "") : it.id;
          if (seen.has(key)) continue;
          seen.add(key);
          out.push({ kind: it.kind, id: it.id, label: it[lang] || it.ru, other: it[other] || "", point: it.point, bbox: it.bbox, seg: it.seg,
            district: it.district, also: it.also && it.also.length ? it.also.slice() : undefined });
          if (out.length >= (o.limit || 8)) break;
        }
        return out;
      },
    };
  }
  let cache = null;
  function load(url, fetchFn) {
    const f = fetchFn || (typeof fetch === "function" ? fetch : null);
    if (!f) return Promise.reject(new Error("fetch недоступен"));
    if (cache && cache.url === (url || "/civic/map/search_index.json")) return cache.promise;
    const u = url || "/civic/map/search_index.json";
    const promise = f(u, { headers: { Accept: "application/json" } }).then((r) => {
      if (!r.ok) throw new Error("search index HTTP " + r.status);
      return r.json();
    }).then((data) => {
      if (!data || data.schema !== "birge.search_index.v1") throw new Error("search index format");
      return makeIndex(data);
    });
    cache = { url: u, promise };
    promise.catch(() => { if (cache && cache.promise === promise) cache = null; });  // ошибка — следующая попытка заново
    return promise;
  }
  return { load, makeIndex, norm, version: "r12-search-1" };
});
