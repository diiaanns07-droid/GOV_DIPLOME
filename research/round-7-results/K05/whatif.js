/* «Если добавить объект» — чистый модуль расчёта before/after (FEATURE_SPEC round 7, контракт city-whatif-v1).
 * K05 round 7. Без DOM, сети и API-ключей. Работает в браузере (window.CITY_WHATIF) и в Node (module.exports).
 *
 * Входы: срез города из data.js (window.CITY_EVIDENCE.cities[city]) и QA из evidence.js (window.CITY_OBS.cities[city].qa).
 * Расстояние — ПО ПРЯМОЙ (гаверсинус, R = 6371008.8 м). Не время пешком, не изохроны, не обеспеченность.
 *
 * API:
 *   makeContext(cityKey, cityData, evidenceCity)  -> ctx (записи среза, bbox, QA, отпечаток по категориям)
 *   sourceSnapshot(ctx, category)                 -> "wif1-sha256:<hex>" из актуальных записей + параметров
 *   validateScenario(scn, ctx)                    -> {ok, errors[]}
 *   compute(ctx, scn)                             -> result (city-whatif-result-v1)
 *   parseImport(text, ctx)                        -> {ok, errors[], scenario|null}  (строгий JSON ≤ 256 KiB)
 *   exportScenario(scn, result)                   -> объект для JSON-экспорта (без путей/токенов)
 *   explain(result, lang)                         -> {text, digest}  шаблон, не LLM
 *   resetOnChange(prev, next)                     -> {reset, reason} при смене города/категории
 *   haversineM(lon1, lat1, lon2, lat2)
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-whatif-v1";
  const RESULT_SCHEMA = "city-whatif-result-v1";
  const CITIES = ["shymkent", "astana"];
  const CATEGORIES = ["school", "outpatient_clinic"];
  const R_EARTH_M = 6371008.8;
  const MAX_POINTS = 10;
  const MAX_IMPORT_BYTES = 256 * 1024;
  const ID_RE = /^[A-Za-z0-9_.-]{1,64}$/;
  const TOP_KEYS = new Set(["schema_version", "city_id", "source_snapshot", "category", "control_points", "proposed_object", "result"]);
  const PARAMS = { formula: "haversine", radius_m: R_EARTH_M, coord_order: "lon,lat", clamp: "[0,1]", version: 1 };
  const NO_BASE = "В срезе нет исходных записей; улучшение не вычисляется";

  // ---------------- геометрия ----------------
  function haversineM(lon1, lat1, lon2, lat2) {
    const rad = Math.PI / 180;
    const dp = (lat2 - lat1) * rad, dl = (lon2 - lon1) * rad;
    let a = Math.sin(dp / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dl / 2) ** 2;
    a = Math.min(1, Math.max(0, a));
    return 2 * R_EARTH_M * Math.asin(Math.sqrt(a));
  }

  function inBbox(lon, lat, bb) {
    return bb[0] <= lon && lon <= bb[2] && bb[1] <= lat && lat <= bb[3];
  }

  // ---------------- SHA-256 (синхронный, для отпечатка и digest) ----------------
  const K = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb,
    0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f,
    0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);

  function utf8(str) {
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(str);
    return Uint8Array.from(Buffer.from(str, "utf8"));
  }

  function sha256Hex(str) {
    const msg = utf8(str);
    const l = msg.length, nBlocks = ((l + 9 + 63) >> 6);
    const buf = new Uint8Array(nBlocks * 64);
    buf.set(msg); buf[l] = 0x80;
    const bits = l * 8, dv = new DataView(buf.buffer);
    dv.setUint32(buf.length - 4, bits >>> 0); dv.setUint32(buf.length - 8, Math.floor(bits / 2 ** 32));
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const W = new Uint32Array(64);
    const rotr = (x, n) => (x >>> n) | (x << (32 - n));
    for (let b = 0; b < nBlocks; b++) {
      for (let i = 0; i < 16; i++) W[i] = dv.getUint32(b * 64 + i * 4);
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(W[i - 15], 7) ^ rotr(W[i - 15], 18) ^ (W[i - 15] >>> 3);
        const s1 = rotr(W[i - 2], 17) ^ rotr(W[i - 2], 19) ^ (W[i - 2] >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
      }
      let [a, b2, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + W[i]) >>> 0;
        const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b2) ^ (a & c) ^ (b2 & c))) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b2; b2 = a; a = (t1 + t2) >>> 0;
      }
      H[0] += a; H[1] += b2; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    return Array.from(H, (x) => x.toString(16).padStart(8, "0")).join("");
  }

  // Каноническая сериализация: ключи по алфавиту, числа как в JSON.stringify (Python-эталон даёт то же для наших входов).
  function canon(v) {
    if (v === null || typeof v !== "object") return JSON.stringify(v);
    if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
    return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}";
  }

  // ---------------- контекст и отпечаток ----------------
  function qaIndex(qa) {
    const idx = {};
    const add = (id, flag) => { (idx[id] = idx[id] || []).push(flag); };
    for (const [id, v] of Object.entries((qa && qa.category_doubt) || {})) add(id, "category_doubt:" + v.rule);
    for (const g of (qa && qa.colocated) || []) for (const id of g.ids || []) add(id, "colocated:" + (g.ids || []).length);
    for (const p of (qa && qa.possible_duplicates) || []) { add(p.a, "possible_duplicate:" + p.rule); add(p.b, "possible_duplicate:" + p.rule); }
    for (const k of Object.keys(idx)) idx[k] = Array.from(new Set(idx[k])).sort();
    return idx;
  }

  function makeContext(cityKey, cityData, evidenceCity) {
    if (!CITIES.includes(cityKey)) throw new Error("неизвестный город: " + cityKey);
    const bbox = cityData.bbox.slice();
    const records = cityData.places.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat, group: p.group, name: p.name }));
    const ctx = { city_id: cityKey, bbox, release: cityData.release,
      places_sha256: cityData.files && cityData.files.places_social && cityData.files.places_social.sha256,
      records, qa: qaIndex(evidenceCity && evidenceCity.qa), snapshots: {} };
    for (const c of CATEGORIES) ctx.snapshots[c] = sourceSnapshot(ctx, c);
    return ctx;
  }

  // Отпечаток из фактических записей категории (id, координаты), bbox, выпуска, sha256 исходного файла и параметров расчёта.
  function sourceSnapshot(ctx, category) {
    const recs = ctx.records.filter((r) => r.group === category).map((r) => [r.id, r.lon, r.lat]).sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    const body = { schema: SCHEMA, city_id: ctx.city_id, category, release: ctx.release, places_sha256: ctx.places_sha256 || null,
      bbox: ctx.bbox, records: recs, params: PARAMS };
    return "wif1-sha256:" + sha256Hex(canon(body));
  }

  // ---------------- валидация сценария ----------------
  function finiteNum(x) { return typeof x === "number" && Number.isFinite(x); }

  function hasUrlOrCode(v) {
    if (typeof v === "string") return /:\/\/|^\s*(javascript|data):|<\s*script/i.test(v);
    if (v && typeof v === "object") return Object.values(v).some(hasUrlOrCode);
    return false;
  }

  function validateScenario(s, ctx) {
    const E = [];
    if (!s || typeof s !== "object" || Array.isArray(s)) return { ok: false, errors: ["SCENARIO: ожидается объект"] };
    for (const k of Object.keys(s)) if (!TOP_KEYS.has(k)) E.push(`UNKNOWN_FIELD: ${k}`);
    if (s.schema_version !== SCHEMA) E.push(`SCHEMA_VERSION: ожидается ${SCHEMA}`);
    if (!CITIES.includes(s.city_id)) E.push("CITY: неизвестный город");
    else if (ctx && s.city_id !== ctx.city_id) E.push(`CITY_MISMATCH: сценарий для ${s.city_id}, открыт ${ctx.city_id}`);
    if (!CATEGORIES.includes(s.category)) E.push("CATEGORY: только school или outpatient_clinic");
    if (ctx && CATEGORIES.includes(s.category) && s.source_snapshot !== ctx.snapshots[s.category])
      E.push("SNAPSHOT_MISMATCH: сценарий построен на другом срезе или другой версии расчёта");
    if (hasUrlOrCode(s)) E.push("FORBIDDEN_CONTENT: адреса URL или код в сценарии не принимаются");
    const ids = new Set();
    const pt = (p, label) => {
      if (!p || typeof p !== "object" || Array.isArray(p)) { E.push(`${label}: ожидается объект`); return; }
      if (typeof p.id !== "string" || !ID_RE.test(p.id)) E.push(`${label}: id 1–64 символа [A-Za-z0-9_.-]`);
      else if (ids.has(p.id)) E.push(`DUPLICATE_ID: ${p.id}`);
      else ids.add(p.id);
      if (!finiteNum(p.lon) || !finiteNum(p.lat) || p.lon < -180 || p.lon > 180 || p.lat < -90 || p.lat > 90)
        E.push(`${label}: координаты должны быть конечными числами в диапазоне`);
      else if (ctx && !inBbox(p.lon, p.lat, ctx.bbox)) E.push(`OUTSIDE_BBOX: ${label} ${p.id} вне сохранённого квадрата среза`);
    };
    if (!Array.isArray(s.control_points)) E.push("CONTROL_POINTS: ожидается список");
    else {
      if (s.control_points.length < 1 || s.control_points.length > MAX_POINTS) E.push(`CONTROL_POINTS: от 1 до ${MAX_POINTS}`);
      s.control_points.forEach((p, i) => {
        pt(p, `control_points[${i}]`);
        if (p && typeof p === "object") for (const k of Object.keys(p)) if (!["id", "lon", "lat"].includes(k)) E.push(`UNKNOWN_FIELD: control_points[${i}].${k}`);
      });
    }
    if (Array.isArray(s.proposed_object)) E.push("PROPOSED: не более одного проектного объекта");
    else if (s.proposed_object !== null && s.proposed_object !== undefined) {
      const p = s.proposed_object;
      pt(p, "proposed_object");
      if (p && typeof p === "object") {
        if (p.kind !== "hypothetical") E.push("PROPOSED: kind должен быть hypothetical");
        if (p.category !== s.category) E.push("PROPOSED: категория проекта не совпадает с category");
        for (const k of Object.keys(p)) if (!["id", "lon", "lat", "category", "kind"].includes(k)) E.push(`UNKNOWN_FIELD: proposed_object.${k}`);
      }
    } else if (!("proposed_object" in s)) E.push("PROPOSED: поле proposed_object обязательно (null или объект)");
    return { ok: E.length === 0, errors: E };
  }

  // ---------------- расчёт ----------------
  function nearest(lon, lat, recs) {
    let best = null;
    for (const r of recs) {
      const d = haversineM(lon, lat, r.lon, r.lat);
      if (best === null || d < best.d || (d === best.d && r.id < best.r.id)) best = { d, r };
    }
    return best;
  }

  function compute(ctx, s) {
    const v = validateScenario(s, ctx);
    if (!v.ok) throw new Error("сценарий не прошёл проверку: " + v.errors.join("; "));
    const recs = ctx.records.filter((r) => r.group === s.category);
    const prop = s.proposed_object || null;
    const rows = s.control_points.map((p) => {
      const nb = nearest(p.lon, p.lat, recs);
      const before = nb ? nb.d : null;
      const dProp = prop ? haversineM(p.lon, p.lat, prop.lon, prop.lat) : null;
      let after, src;
      if (before === null) { after = dProp; src = prop ? "proposed" : null; }
      else if (prop && dProp < before) { after = dProp; src = "proposed"; }
      else { after = before; src = "existing"; }
      const delta = before !== null && after !== null ? before - after : null;
      return {
        point_id: p.id, lon: p.lon, lat: p.lat,
        before_m: before,
        before_record: nb ? { id: nb.r.id, name: nb.r.name, lon: nb.r.lon, lat: nb.r.lat, kind: "observed_secondary",
          qa_flags: ctx.qa[nb.r.id] || [] } : null,
        distance_to_proposed_m: dProp,
        after_m: after, after_source: src, delta_m: delta,
        note: before === null ? NO_BASE : null,
      };
    });
    return {
      schema_version: RESULT_SCHEMA, scenario_schema: SCHEMA, city_id: s.city_id, category: s.category,
      source_snapshot: ctx.snapshots[s.category], release: ctx.release, bbox: ctx.bbox.slice(),
      n_source_records: recs.length,
      formula: { name: "haversine", radius_m: R_EARTH_M, straight_line: true, units: "m", rounding: "только при выводе" },
      proposed_object: prop ? { id: prop.id, lon: prop.lon, lat: prop.lat, category: prop.category, kind: "hypothetical" } : null,
      rows,
      limitations: [
        "Расстояние по прямой, не по улицам; не время пути и не обеспеченность местами.",
        "База — записи Overture внутри квадрата среза; ближайшая запись в срезе не обязательно ближайшее учреждение города.",
        "Контрольная точка — выбранное место, не дом с известным населением.",
        "Положительная разница — только уменьшение геометрического расстояния, не улучшение здоровья, образования или качества жизни.",
        "Записи с QA-флагами (совпадающие координаты, возможные дубли, сомнение в категории) не удалены и могут менять результат.",
      ],
    };
  }

  // ---------------- строгий импорт ----------------
  // Проверка повторяющихся ключей: JSON.parse молча берёт последний.
  function duplicateKey(text) {
    const stack = [];
    let i = 0, expectKey = false;
    while (i < text.length) {
      const ch = text[i];
      if (ch === '"') {
        let j = i + 1, s = "";
        while (j < text.length && text[j] !== '"') { if (text[j] === "\\") { s += text[j] + text[j + 1]; j += 2; } else { s += text[j]; j++; } }
        const top = stack[stack.length - 1];
        let k = j + 1;
        while (k < text.length && /\s/.test(text[k])) k++;
        if (top && top.obj && text[k] === ":") {
          if (top.keys.has(s)) return s;
          top.keys.add(s);
        }
        i = j + 1; continue;
      }
      if (ch === "{") stack.push({ obj: true, keys: new Set() });
      else if (ch === "[") stack.push({ obj: false });
      else if (ch === "}" || ch === "]") stack.pop();
      i++;
    }
    void expectKey;
    return null;
  }

  function deepFinite(v) {
    if (typeof v === "number") return Number.isFinite(v);
    if (v && typeof v === "object") return Object.values(v).every(deepFinite);
    return true;
  }

  function parseImport(text, ctx) {
    if (typeof text !== "string") return { ok: false, errors: ["IMPORT: ожидается текст"], scenario: null };
    if (utf8(text).length > MAX_IMPORT_BYTES) return { ok: false, errors: ["IMPORT_TOO_LARGE: больше 256 KiB"], scenario: null };
    let obj;
    try { obj = JSON.parse(text); } catch (e) { return { ok: false, errors: ["JSON: " + e.message], scenario: null }; }
    const dup = duplicateKey(text);
    if (dup !== null) return { ok: false, errors: [`JSON_DUPLICATE_KEY: ${dup}`], scenario: null };
    if (!deepFinite(obj)) return { ok: false, errors: ["JSON_NONFINITE: число переполняется (например, 1e999)"], scenario: null };
    const v = validateScenario(obj, ctx);
    if (!v.ok) return { ok: false, errors: v.errors, scenario: null };
    // Импортированный result не доверенный: отбрасывается, значения пересчитываются compute().
    const scn = { schema_version: obj.schema_version, city_id: obj.city_id, source_snapshot: obj.source_snapshot, category: obj.category,
      control_points: obj.control_points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat })),
      proposed_object: obj.proposed_object ? { id: obj.proposed_object.id, lon: obj.proposed_object.lon, lat: obj.proposed_object.lat,
        category: obj.proposed_object.category, kind: "hypothetical" } : null };
    return { ok: true, errors: [], scenario: scn, ignored_result: "result" in obj };
  }

  function exportScenario(s, result) {
    const out = { schema_version: SCHEMA, city_id: s.city_id, source_snapshot: s.source_snapshot, category: s.category,
      control_points: s.control_points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat })),
      proposed_object: s.proposed_object ? { id: s.proposed_object.id, lon: s.proposed_object.lon, lat: s.proposed_object.lat,
        category: s.proposed_object.category, kind: "hypothetical" } : null };
    if (result) out.result = { note: "вычисленные значения; при импорте не доверяются и пересчитываются",
      rows: result.rows.map((r) => ({ point_id: r.point_id, before_m: r.before_m, after_m: r.after_m, delta_m: r.delta_m })) };
    return out;
  }

  // ---------------- шаблонное объяснение ----------------
  function fmt(m) { return m === null ? "—" : `${Math.round(m)} м`; }

  function explain(result, lang) {
    void lang; // ru-шаблон; kk — после проверки носителем
    const digestBody = { source_snapshot: result.source_snapshot, category: result.category,
      control_points: result.rows.map((r) => [r.point_id, r.lon, r.lat]), proposed_object: result.proposed_object,
      values: result.rows.map((r) => [r.point_id, r.before_m, r.after_m, r.delta_m, r.before_record ? r.before_record.id : null]) };
    const digest = "wifx1-sha256:" + sha256Hex(canon(digestBody));
    const cat = result.category === "school" ? "школы" : "поликлиники";
    const lines = [`Шаблонное объяснение (не LLM). Категория: ${cat}; записей в срезе: ${result.n_source_records}.`];
    lines.push(result.proposed_object ? "Проектный объект — условный, не существующее учреждение." : "Проектный объект не задан: «после» совпадает с «до».");
    for (const r of result.rows) {
      if (r.before_m === null) lines.push(`Точка ${r.point_id}: ${NO_BASE}.`);
      else lines.push(`Точка ${r.point_id}: до ${fmt(r.before_m)} (запись ${r.before_record.id}${r.before_record.qa_flags.length ? ", есть QA-флаги" : ""}), после ${fmt(r.after_m)}, разница ${fmt(r.delta_m)} по прямой.`);
    }
    lines.push("Разница — только расстояние по прямой; не время пути, не население и не обеспеченность.");
    return { text: lines.join("\n"), digest };
  }

  function resetOnChange(prev, next) {
    if (!prev) return { reset: false, reason: null };
    if (prev.city_id !== next.city_id) return { reset: true, reason: "Город изменён: точки и проект сброшены (не переносятся между городами)." };
    if (prev.category !== next.category) return { reset: true, reason: "Категория изменена: проект и объяснение сброшены." };
    return { reset: false, reason: null };
  }

  const API = { SCHEMA, RESULT_SCHEMA, CATEGORIES, MAX_POINTS, MAX_IMPORT_BYTES, R_EARTH_M, NO_BASE,
    haversineM, sha256Hex, canon, makeContext, sourceSnapshot, validateScenario, compute, parseImport, exportScenario, explain,
    resetOnChange };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.CITY_WHATIF = API;
})(typeof window !== "undefined" ? window : this);
