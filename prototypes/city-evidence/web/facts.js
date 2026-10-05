/* Facts catalog + verified template explanation (format city-evidence/2).
 * Port of K02 r4 fixed verified_explainer with the BUILD r5 adaptation (inputs/k02v4, see its MANIFEST):
 * catalog -> catalog_digest -> selector (IDs only) -> validate_plan -> render.
 * tests/conformance.cjs checks equal text and equal digest against tests/expected_explanations.json, produced by
 * tools/explain_ref.py with the Python module. The selector is a deterministic stub, not an LLM.
 * Works in the browser (window.CITY_FACTS) and in Node (module.exports).
 */
(function (root) {
  "use strict";
  const GROUP_ORDER = ["school", "preschool", "college_university", "hospital", "outpatient_clinic", "pharmacy", "government_office"];
  const ID_PATTERN = /^([a-z][a-z0-9_.]*)\/([A-Za-z0-9_.\-]+)\/([a-z][a-z0-9_.]*)$/;
  const SECTION_TYPES = ["summary", "weakest", "risks", "data_gaps"];
  const MAX_FACTS = 6, MAX_SECTIONS = 4;
  const STUB_NAME = "шаблонное объяснение (детерминированная заглушка, не LLM)";
  const KINDS = new Set(["observed", "derived", "model", "synthetic", "unknown", "hypothesis"]);
  const UNITS = { records: { ru: " записей", kk: " жазба" }, segments: { ru: " сегментов", kk: " сегмент" },
    places: { ru: " мест", kk: " орын" }, persons: { ru: " чел.", kk: " адам" } };
  const REASON = {
    source_access_denied: { ru: "источник недоступен", kk: "дереккөзге қол жетімсіз" },
    not_collected: { ru: "не собиралось", kk: "жиналмаған" },
    not_in_source: { ru: "нет в источнике", kk: "дереккөзде жоқ" },
    zero_in_partial_coverage: { ru: "ноль при неполном охвате", kk: "толық емес қамтудағы нөл" },
    suppressed_by_publisher: { ru: "скрыто публикатором", kk: "жариялаушы жасырған" },
  };
  const TEXT = {
    header: { ru: "Проверяемая часть (значения из каталога фактов среза)", kk: "Тексерілетін бөлік (мәндер кесінді деректер каталогынан)" },
    scenario: { ru: "Срез", kk: "Кесінді" },
    summary: { ru: "Итог", kk: "Қорытынды" }, weakest: { ru: "Самый слабый район", kk: "Ең әлсіз аудан" },
    risks: { ru: "Риски", kk: "Тәуекелдер" }, data_gaps: { ru: "Нет данных", kk: "Дерек жоқ" },
    unknown: { ru: "нет данных", kk: "дерек жоқ" },
    kind_model: { ru: "учебная модель", kk: "оқу моделі" }, kind_observed: { ru: "наблюдение", kk: "бақылау" },
    kind_derived: { ru: "расчёт", kk: "есептелген" }, kind_synthetic: { ru: "синтетика", kk: "синтетикалық" },
    kind_unknown: { ru: "неизвестно", kk: "белгісіз" }, kind_hypothesis: { ru: "гипотеза", kk: "болжам" },
    incomplete: { ru: "неполный охват", kk: "толық емес қамту" },
  };
  const FIXED = {
    "places.selected": ["Выбранные категории в квадрате", "Таңдалған санаттар шаршыда"],
    "district_status.matched": ["С проверенной привязкой к району", "Ауданға сенімді байланған"],
    "district_status.ambiguous": ["С неоднозначным районом", "Ауданы анық емес"],
    "district_status.unmatched": ["В городе, но вне районов", "Қала ішінде, ауданнан тыс"],
    "qa.colocated": ["С совпадающими координатами", "Координаттары бірдей"],
    "qa.category_doubt": ["С сомнением в категории", "Санаты күмәнді"],
    "segments.foot_unknown": ["Дороги без данных о проходе пешком", "Жаяу өту дерегі жоқ жолдар"],
    "city.place_records_total": ["Соцобъекты по всему городу", "Бүкіл қаладағы әлеуметтік нысандар"],
    "registry.official_schools": ["Официальный реестр школ", "Мектептердің ресми тізілімі"],
    "capacity.school_places": ["Мощность школ", "Мектептер сыйымдылығы"],
    "population.children": ["Число детей", "Балалар саны"],
  };
  const CITY_OBS = { "city.place_records_total": "overture_place_records.city_total", "registry.official_schools": "official_registry.schools",
    "capacity.school_places": "capacity.school_places", "population.children": "population.children" };

  class PlanError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }

  // ---------- SHA-256 (synchronous, UTF-8) — same digest in file:// and http, checked against Python hashlib ----------
  const K256 = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb,
    0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f,
    0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
  function sha256hex(str) {
    const bytes = new TextEncoder().encode(str), len = bytes.length, nblk = ((len + 9 + 63) >> 6);
    const buf = new Uint8Array(nblk * 64); buf.set(bytes); buf[len] = 0x80;
    const bits = len * 8, dv = new DataView(buf.buffer);
    dv.setUint32(buf.length - 4, bits >>> 0); dv.setUint32(buf.length - 8, Math.floor(bits / 0x100000000));
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const W = new Uint32Array(64), rotr = (x, n) => (x >>> n) | (x << (32 - n));
    for (let b = 0; b < nblk; b++) {
      for (let i = 0; i < 16; i++) W[i] = dv.getUint32(b * 64 + i * 4);
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(W[i - 15], 7) ^ rotr(W[i - 15], 18) ^ (W[i - 15] >>> 3), s1 = rotr(W[i - 2], 17) ^ rotr(W[i - 2], 19) ^ (W[i - 2] >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
      }
      let [a, b2, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K256[i] + W[i]) >>> 0;
        const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b2) ^ (a & c) ^ (b2 & c))) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b2; b2 = a; a = (t1 + t2) >>> 0;
      }
      H[0] += a; H[1] += b2; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    return [...H].map((x) => x.toString(16).padStart(8, "0")).join("");
  }

  // Python repr() for the value types the catalog allows (integers and None).
  function pyRepr(v) {
    if (v === null) return "None";
    if (Number.isInteger(v)) return String(v);
    throw new Error("catalog values must be integers or null");
  }
  // Python json.dumps(..., ensure_ascii=False) of a list of lists with default separators.
  function pyJson(v) {
    if (v === null) return "null";
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v === "string") return JSON.stringify(v);
    if (Array.isArray(v)) return "[" + v.map(pyJson).join(", ") + "]";
    throw new Error("pyJson: unsupported " + typeof v);
  }
  // K02 catalog_digest (+unit, missing_reason): sha256(json(sorted tuples))[:16]
  function catalogDigest(cat) {
    const rows = [...cat.values()].map((f) => [f.id, pyRepr(f.value), f.kind, f.coverage_complete, f.unit, f.missing_reason])
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    return sha256hex(pyJson(rows)).slice(0, 16);
  }

  // agent.evidence.format_value: integers as is; decimal point -> comma; strings escaped.
  function formatValue(v) {
    if (typeof v === "string") return v.replace(/([\\`*_{}\[\]()<>#!|])/g, "\\$1");
    if (typeof v !== "number" || !isFinite(v)) throw new Error("format_value: not a finite number");
    return String(v).replace(".", ",");
  }

  function scenarioId(release, groups) {
    let mask = 0;
    GROUP_ORDER.forEach((g, i) => { if (groups.has(g)) mask |= 1 << i; });
    return `k10r3-${release}-g${mask}`;
  }

  function makeFact(r) {
    const id = `${r.city}/${r.period}/${r.path}`, m = ID_PATTERN.exec(id);
    if (!m || m[1] !== r.city || m[2] !== r.period) throw new Error("bad fact id " + id);
    if (!UNITS[r.unit]) throw new Error(`unknown unit ${r.unit}`);
    if (r.value !== null && (typeof r.value !== "number" || !isFinite(r.value))) throw new Error(`${id}: неконечное значение`);
    for (const l of [r.label_ru, r.label_kk]) if (typeof l !== "string" || /\d/.test(l)) throw new Error(`${id}: подпись отсутствует или содержит цифры`);
    const kind = r.value === null ? "unknown" : r.kind;
    if (!KINDS.has(kind)) throw new Error("unknown kind " + kind);
    return { id, city: r.city, scenario: r.period, kind, value: r.value, unit: r.unit, label: { ru: r.label_ru, kk: r.label_kk },
      source: r.source, coverage_complete: r.coverage_complete ?? null, missing_reason: r.missing_reason ?? null };
  }

  // Same rows as tools/explain_ref.py catalog_rows.
  function buildCatalog(data, ev, city, groups) {
    const c = data.cities[city], e = ev && ev.cities && ev.cities[city];
    if (!c || !e) throw new PlanError("foreign_city", `нет данных для города ${city}`);
    const period = scenarioId(e.release, groups), cid = "kz." + city, obs = {};
    for (const o of e.observations) obs[o.indicator_id] = o;
    const sel = c.places.filter((p) => groups.has(p.group)), selIds = new Set(sel.map((p) => p.id));
    const cat = new Map();
    const add = (path, value, kind, unit, complete, reason, source, labels) => {
      const [ru, kk] = labels || FIXED[path];
      const f = makeFact({ city: cid, period, path, value, kind, unit, label_ru: ru, label_kk: kk, source, coverage_complete: complete, missing_reason: reason });
      if (cat.has(f.id)) throw new Error(`${f.id}: два наблюдения на один ID`);
      cat.set(f.id, f);
    };
    const fromObs = (path, o, labels) => add(path, o.value, o.kind, o.unit, o.coverage.complete, o.missing_reason ?? null, o.obs_id, labels);
    add("places.selected", sel.length, "derived", "records", true, null, "data.js: записи выбранных категорий");
    for (const g of GROUP_ORDER) if (groups.has(g))
      fromObs("places." + g, obs[`overture_place_records.${g}.conf_ge_0_0`], [data.groups[g].label + " в квадрате", ev.group_kk[g] + ", шаршыда"]);
    const st = {};
    for (const p of sel) { const s = (e.place_district[p.id] || { status: "unknown" }).status; st[s] = (st[s] || 0) + 1; }
    for (const s of ["matched", "ambiguous", "unmatched"]) add("district_status." + s, st[s] || 0, "derived", "records", true, null, "k03_assign_v2 по записям фильтра");
    const coloc = new Set(e.qa.colocated.flatMap((g) => g.ids));
    add("qa.colocated", [...selIds].filter((i) => coloc.has(i)).length, "derived", "records", true, null, "K05 check_objects COLOCATED");
    add("qa.category_doubt", [...selIds].filter((i) => i in e.qa.category_doubt).length, "derived", "records", true, null, "правило CATEGORY_DOUBT build_evidence.py");
    fromObs("segments.foot_unknown", obs["segments_foot_access.unknown"]);
    for (const [path, ind] of Object.entries(CITY_OBS)) fromObs(path, obs[ind]);
    return { catalog: cat, scenario: period, city: cid, digest: catalogDigest(cat) };
  }

  function catalogView(cat) { return [...cat.values()].map((f) => ({ id: f.id, label_ru: f.label.ru, kind: f.kind, has_value: f.value !== null })); }

  const StubSelector = {
    name: STUB_NAME,
    select(view, digest) {
      const ends = (v, ...s) => s.some((x) => v.id.endsWith("/" + x));
      const summary = view.filter((v) => v.has_value && v.id.includes("/places.")).map((v) => v.id).slice(0, MAX_FACTS);
      const risks = view.filter((v) => v.has_value && ends(v, "district_status.ambiguous", "district_status.unmatched", "qa.colocated", "qa.category_doubt", "segments.foot_unknown")).map((v) => v.id);
      const gaps = view.filter((v) => !v.has_value).map((v) => v.id).slice(0, MAX_FACTS);
      const sections = [{ type: "summary", fact_ids: summary }, { type: "risks", fact_ids: risks }, { type: "data_gaps", fact_ids: gaps }];
      return { sections: sections.filter((s) => s.fact_ids.length), comment: null, catalog_digest: digest };
    },
  };

  // validate_plan (K02 r4): shape, digest (stale_catalog), section types, ID syntax, city, scenario, membership,
  // null only in data_gaps, duplicates within and across sections.
  function validatePlan(plan, built) {
    const { catalog: cat, city, scenario, digest } = built;
    if (!plan || typeof plan !== "object" || Array.isArray(plan) || !("sections" in plan) || Object.keys(plan).some((k) => !["sections", "comment", "catalog_digest"].includes(k)))
      throw new PlanError("bad_shape", "ожидается объект {sections, catalog_digest, comment?}");
    if (plan.catalog_digest !== digest) throw new PlanError("stale_catalog", `отпечаток плана ${plan.catalog_digest} ≠ текущему каталогу ${digest}`);
    const secs = plan.sections;
    if (!Array.isArray(secs) || !secs.length || secs.length > MAX_SECTIONS) throw new PlanError("bad_shape", `нужно 1–${MAX_SECTIONS} секций`);
    const seen = new Set(), used = new Set(), out = [];
    for (const s of secs) {
      if (!s || typeof s !== "object" || Object.keys(s).sort().join() !== "fact_ids,type") throw new PlanError("bad_shape", "секция = {type, fact_ids}");
      if (!SECTION_TYPES.includes(s.type)) throw new PlanError("bad_section", `тип секции ${s.type} не разрешён`);
      if (seen.has(s.type)) throw new PlanError("bad_section", `секция ${s.type} повторяется`);
      seen.add(s.type);
      if (!Array.isArray(s.fact_ids) || !s.fact_ids.length || s.fact_ids.length > MAX_FACTS) throw new PlanError("bad_shape", `в секции 1–${MAX_FACTS} ID`);
      for (const fid of s.fact_ids) {
        if (typeof fid !== "string") throw new PlanError("not_an_id", `${fid} не строка`);
        const m = ID_PATTERN.exec(fid);
        if (!m) throw new PlanError("not_an_id", `${fid.slice(0, 60)} не является ID факта`);
        if (m[1] !== city) throw new PlanError("foreign_city", `${fid}: город ${m[1]}, запрос по ${city}`);
        if (m[2] !== scenario) throw new PlanError("stale_scenario", `${fid}: срез ${m[2]}, текущий ${scenario}`);
        if (!cat.has(fid)) throw new PlanError("unknown_id", `${fid} нет в каталоге текущего среза`);
        const f = cat.get(fid);
        if (f.value === null && s.type !== "data_gaps") throw new PlanError("null_as_fact", `${fid} не имеет значения; его место только в data_gaps`);
        if (f.value !== null && s.type === "data_gaps") throw new PlanError("value_in_gaps", `${fid} имеет значение, а секция data_gaps для неизвестных`);
        if (used.has(fid)) throw new PlanError("duplicate_id", `${fid} повторяется в плане`);
        used.add(fid);
      }
      out.push({ type: s.type, fact_ids: s.fact_ids.slice() });
    }
    if (plan.comment !== undefined && plan.comment !== null && typeof plan.comment !== "string") throw new PlanError("bad_shape", "comment — строка или null");
    return { sections: out, comment: plan.comment ?? null, catalog_digest: plan.catalog_digest };
  }

  function renderValue(f, lang) { return f.value === null ? TEXT.unknown[lang] : formatValue(f.value) + UNITS[f.unit][lang]; }
  function render(plan, built, lang) {
    if (lang !== "ru" && lang !== "kk") throw new Error("lang: ru | kk");
    const lines = [`**${TEXT.header[lang]}.** ${TEXT.scenario[lang]}: ${built.scenario}.`], used = [];
    for (const s of plan.sections) {
      lines.push(`\n**${TEXT[s.type][lang]}**`);
      for (const fid of s.fact_ids) {
        const f = built.catalog.get(fid);
        let kind = TEXT["kind_" + f.kind][lang];
        if (f.coverage_complete === false && f.value !== null) kind += ", " + TEXT.incomplete[lang];
        if (f.value === null && f.missing_reason) kind += ", " + ((REASON[f.missing_reason] || {})[lang] || f.missing_reason);
        lines.push(`- ${f.label[lang]}: ${renderValue(f, lang)} (${kind})`);
        used.push({ id: fid, value: f.value, kind: f.kind, unit: f.unit, source: f.source, coverage_complete: f.coverage_complete, missing_reason: f.missing_reason });
      }
    }
    return { text: lines.join("\n"), facts_used: used, catalog_digest: plan.catalog_digest };  // comment dropped
  }

  function explain(data, ev, city, groups, lang, selector) {
    const built = buildCatalog(data, ev, city, groups);
    const sel = selector || StubSelector;
    const accepted = validatePlan(sel.select(catalogView(built.catalog), built.digest), built);
    return { ...render(accepted, built, lang), scenario: built.scenario, selector: sel.name };
  }

  // ---------- UI glue (browser only) ----------
  const STATUS_RU = { matched: "проверенная привязка", ambiguous: "неоднозначно", unmatched: "в городе, вне районов", outside: "вне города", invalid: "ошибка координат" };
  function districtOf(city, place) {
    const ev = root.CITY_OBS, rec = ev && ev.cities && ev.cities[city] && ev.cities[city].place_district[place.id];
    if (!rec) return { text: "не определён", badge: "нет привязки" };
    const coloc = ev.cities[city].qa.colocated.some((g) => g.ids.includes(place.id));
    if (rec.status === "matched") {
      const n = ev.district_names[rec.district] || {};
      const name = n.kk && n.ru && n.kk !== n.ru ? `${n.ru} / ${n.kk}` : (n.ru || n.kk || rec.district);
      return { text: name, badge: coloc ? "по координате под вопросом (COLOCATED)" : "K03 v2 · OSM, не официально" };
    }
    return { text: `не присвоен (${STATUS_RU[rec.status] || rec.status})`, badge: rec.candidates.length ? "кандидаты: " + rec.candidates.join(", ") : "K03 v2" };
  }
  function qaOf(city, place) {
    const ev = root.CITY_OBS, e = ev && ev.cities && ev.cities[city];
    if (!e) return [];
    const out = [];
    const g = e.qa.colocated.find((x) => x.ids.includes(place.id));
    if (g) out.push({ code: "COLOCATED", text: `координата совпадает ещё с ${g.ids.length - 1} записями (${g.lon}, ${g.lat}); точное место не проверено`, ids: g.ids });
    for (const d of e.qa.possible_duplicates) if (d.a === place.id || d.b === place.id)
      out.push({ code: "POSSIBLE_DUPLICATE", text: `возможный дубликат (${d.rule}, ${d.distance_m} м)`, ids: [d.a, d.b] });
    const c = e.qa.category_doubt[place.id];
    if (c) out.push({ code: "CATEGORY_DOUBT", text: `сомнение в категории: ${c.reason} (правило ${c.rule})`, ids: [place.id] });
    return out;
  }
  function provenanceNotes(city) {
    const ev = root.CITY_OBS;
    if (!ev || !ev.cities || !ev.cities[city]) return ["Каталог фактов не загружен (evidence.js)."];
    const e = ev.cities[city];
    return [`Привязка к районам: ${ev.assign_rule} (K03 + патч r4, локальная копия), границы OSM/Overture, юридически не проверены.`,
      `Наблюдения: контракт ${ev.contract} — ${e.observations.length} записей, ошибок ${e.validation.errors}; предупреждения: ${e.validation.warnings.join(", ") || "нет"}.`,
      "Районные суммы E02/E03 прежних раундов к квадрату не применяются (K05 LEGACY_UNIT/SPATIAL_MIX; K08: двойной счёт границ)."];
  }

  function renderExplanation(body, ctx) {
    const { state, data, isCurrent, el } = ctx;
    const ev = root.CITY_OBS;
    body.replaceChildren();
    if (!ev || !ev.cities || !ev.cities[state.city] || ev.format !== "city-evidence/2") {
      body.append(el("p", { class: "err" }, "Каталог фактов недоступен: нет или устарел web/evidence.js. Соберите: tools/build_evidence.py."));
      return;
    }
    const groups = state.places ? state.groups : new Set();
    let built;
    try { built = buildCatalog(data, ev, state.city, groups); } catch (e) { body.append(el("p", { class: "err" }, "Ошибка каталога: " + e.message)); return; }
    const tbl = el("table", { class: "facts" }), tb = el("tbody");
    for (const f of built.catalog.values()) {
      const tr = el("tr");
      const why = f.value === null ? (REASON[f.missing_reason] || {}).ru || "" : f.coverage_complete === false ? "неполный охват" : "";
      tr.append(el("td", { class: "k" }, f.label.ru),
        el("td", { class: "num" + (f.value === null ? " kv-unknown" : "") }, renderValue(f, "ru").trim()),
        el("td", null, TEXT["kind_" + f.kind].ru + (why ? ", " + why : "")));
      tb.append(tr);
    }
    tbl.append(tb);
    const det = el("details"); det.append(el("summary", null, `Каталог фактов (${built.catalog.size}) · срез ${built.scenario} · отпечаток ${built.digest}`), tbl);
    body.append(det, el("p", { class: "muted" }, "«нет данных» — значение неизвестно (причина указана), а не 0. «0 записей» — ноль в полном ответе запроса по этому квадрату, а не отсутствие объектов в городе."));
    const row = el("div", { class: "ctl" });
    const btn = el("button", { class: "tool", type: "button" }, "Объяснить срез");
    const langSel = el("select", { "aria-label": "Язык объяснения" });
    for (const [v, t] of [["ru", "русский"], ["kk", "қазақша (черновик)"]]) { const o = el("option", { value: v }, t); if (v === (state.lang || "ru")) o.selected = true; langSel.append(o); }
    langSel.addEventListener("change", () => { state.lang = langSel.value; });
    row.append(btn, langSel);
    const outBox = el("div", { class: "explain", hidden: "" });
    body.append(row, outBox);
    btn.addEventListener("click", () => {
      btn.disabled = true;
      const requested = built;  // the plan is made for this catalog; a newer catalog rejects it by digest
      Promise.resolve().then(() => StubSelector.select(catalogView(requested.catalog), requested.digest)).then((plan) => {
        if (!isCurrent()) return;  // city/filter changed: drop the reply silently
        btn.disabled = false;
        outBox.hidden = false; outBox.replaceChildren();
        try {
          const cur = buildCatalog(data, root.CITY_OBS, state.city, state.places ? state.groups : new Set());
          const r = render(validatePlan(plan, cur), cur, state.lang || "ru");
          outBox.append(el("div", { class: "who" }, STUB_NAME + ". Модель не вызывалась; текст собран кодом из фактов."));
          for (const line of r.text.split("\n")) {
            if (!line.trim()) continue;
            const m = /^\*\*(.+?)\*\*(.*)$/.exec(line.trim());
            if (m) { const p = el("p"); p.append(el("strong", null, m[1]), document.createTextNode(m[2])); outBox.append(p); }
            else outBox.append(el("div", null, line.replace(/^- /, "• ")));
          }
        } catch (e) {
          outBox.append(el("p", { class: "err" }, `Ответ отклонён (${e.code || "error"}): ${e.detail || e.message}`));
        }
      });
    });
  }

  const api = { GROUP_ORDER, PlanError, sha256hex, catalogDigest, formatValue, scenarioId, buildCatalog, catalogView, StubSelector,
    validatePlan, render, explain, districtOf, qaOf, provenanceNotes, renderExplanation };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_FACTS = api;
})(typeof window !== "undefined" ? window : globalThis);
