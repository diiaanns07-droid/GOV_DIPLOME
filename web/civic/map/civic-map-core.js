/* R03 · civic-v1 public map — pure logic (no DOM, no MapLibre).
 * Loaded in the browser as window.CivicMapCore and in Node tests via require().
 * Rule of this file: never invent values. Unknown stays unknown, null stays
 * "нет данных", a date is never derived from "today", money is never 0 by default.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module && module.exports) module.exports = api;
  else root.CivicMapCore = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SCHEMA = "civic-v1";
  const NO_DATA = "нет данных";

  // Colour = kind, fill style = status, dash/halo = approximate place. Colours keep
  // >= 4.5:1 against white so the same token is usable for text in the legend.
  const KINDS = {
    construction: { label: "Строительство", color: "#1f5fa8" },
    roadworks: { label: "Дорожные работы", color: "#b4470f" },
    landscaping: { label: "Благоустройство", color: "#22703f" },
    event: { label: "Событие, перекрытие", color: "#6b3fb8" },
  };
  const OTHER_KIND = { label: "Другое", color: "#4f5965" };
  const KIND_ORDER = ["construction", "roadworks", "landscaping", "event"];

  const STATUSES = {
    planned: "Запланировано",
    in_progress: "Идут работы",
    completed: "Завершено",
    cancelled: "Отменено",
    unknown: "Статус неизвестен",
  };
  const STATUS_ORDER = ["planned", "in_progress", "completed", "cancelled", "unknown"];

  const EVIDENCE = {
    observed: { short: "По источнику", label: "Сведения из опубликованного источника" },
    derived: { short: "Вывод", label: "Выведено из источников, не прямая цитата" },
    hypothesis: { short: "Гипотеза", label: "Гипотеза — не подтверждено источником" },
    synthetic: { short: "Демо", label: "Синтетическая демо-запись — не сведения о реальных работах" },
  };
  const EVIDENCE_UNKNOWN = { short: "Происхождение?", label: "Происхождение сведений не указано" };

  const PRECISION = {
    source: "Место указано по источнику",
    approximate: "Место примерное",
    unknown: "Точность места неизвестна",
  };

  const BASIS = {
    planned: "плановая стоимость",
    contract: "сумма договора",
    spent: "фактически освоено",
    unknown: "основание суммы не указано",
  };

  const ACCESS = {
    fetched: "источник открывался",
    not_fetched: "источник не открывался",
    unavailable: "источник был недоступен",
  };

  const FIELD_LABELS = {
    title: "название",
    description: "описание",
    kind: "вид работ",
    status: "статус",
    publication: "публикация",
    geometry: "место на карте",
    geometry_precision: "точность места",
    schedule: "сроки",
    "schedule.planned_start": "начало",
    "schedule.original_planned_end": "первоначальный срок",
    "schedule.current_planned_end": "текущий срок",
    "schedule.actual_end": "фактическое окончание",
    budget: "стоимость",
    "budget.amount_kzt": "стоимость",
    "budget.basis": "основание стоимости",
    "budget.source_id": "источник стоимости",
    responsible: "ответственный",
    "responsible.organization": "организация",
    "responsible.public_contact": "публичный контакт",
    evidence_type: "тип сведений",
    source_refs: "источники",
    evidence_notes: "примечание",
  };

  const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
    "августа", "сентября", "октября", "ноября", "декабря"];

  // Same envelope as R02 validate.py ASTANA_BBOX. Coordinates outside are kept off the
  // map (list only): a swapped [lat, lon] pair would otherwise land hundreds of km away.
  const ASTANA_BBOX = [70.8, 50.75, 72.1, 51.6];

  const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const str = (v) => (typeof v === "string" && v.trim() !== "" ? v : null);
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  // Enum lookup that never coerces untrusted values ({"toString":1} would throw in hasOwnProperty).
  const enumOf = (m, v, d) => (typeof v === "string" && own(m, v) ? v : d);

  // ---------- dates ----------
  function parseDay(value) {
    if (typeof value !== "string") return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!m) return null;
    const y = +m[1], mo = +m[2], d = +m[3];
    const t = Date.UTC(y, mo - 1, d);
    const back = new Date(t);
    if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) return null;
    return { y, m: mo, d, key: value, ord: Math.round(t / 86400000) };
  }
  function dayFromOrd(ord) {
    const dt = new Date(ord * 86400000);
    const p = (n) => String(n).padStart(2, "0");
    return dt.getUTCFullYear() + "-" + p(dt.getUTCMonth() + 1) + "-" + p(dt.getUTCDate());
  }
  function addDays(day, n) {
    const p = parseDay(day);
    return p ? dayFromOrd(p.ord + n) : null;
  }
  function dayDiff(a, b) {
    const pa = parseDay(a), pb = parseDay(b);
    return pa && pb ? pb.ord - pa.ord : null;
  }
  // Local calendar day of a Date (the viewer's day), not UTC.
  function localDay(date) {
    const p = (n) => String(n).padStart(2, "0");
    return date.getFullYear() + "-" + p(date.getMonth() + 1) + "-" + p(date.getDate());
  }
  function formatDay(value, style) {
    const p = parseDay(value);
    if (!p) return NO_DATA;
    if (style === "long") return p.d + " " + MONTHS_GEN[p.m - 1] + " " + p.y;
    return String(p.d).padStart(2, "0") + "." + String(p.m).padStart(2, "0") + "." + p.y;
  }
  // Timestamps with an offset are shown in Astana local time, computed from the
  // instant itself (no dependency on the viewer's tz database): Kazakhstan moved from
  // UTC+6 to a single UTC+5 zone at 2024-03-01 00:00 local = 2024-02-29T18:00Z.
  // R02 stores UTC (+00:00), so without this a 02:30 change in Astana read as the previous day.
  const ASTANA_UTC5_FROM = Date.UTC(2024, 1, 29, 18, 0, 0);
  function parseTimestamp(value) {
    if (typeof value !== "string") return null;
    const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/.exec(value);
    if (!m || !parseDay(m[1]) || +m[2] > 23 || +m[3] > 59 || (m[4] && +m[4] > 59)) return null;
    let ms = null;
    if (m[5]) {
      const d = parseDay(m[1]);
      let offMin = 0;
      if (m[5] !== "Z") {
        const o = /^([+-])(\d{2}):?(\d{2})$/.exec(m[5]);
        offMin = (o[1] === "-" ? -1 : 1) * (+o[2] * 60 + +o[3]);
      }
      ms = Date.UTC(d.y, d.m - 1, d.d, +m[2], +m[3], +(m[4] || 0)) - offMin * 60000;
    }
    return { day: m[1], hh: m[2], mm: m[3], offset: m[5] || null, ms };
  }
  function astanaWall(ms) {
    const off = ms >= ASTANA_UTC5_FROM ? 5 : 6;
    const t = new Date(ms + off * 3600000);
    const p = (n) => String(n).padStart(2, "0");
    return { day: t.getUTCFullYear() + "-" + p(t.getUTCMonth() + 1) + "-" + p(t.getUTCDate()), hh: p(t.getUTCHours()), mm: p(t.getUTCMinutes()), off };
  }
  // Calendar day (YYYY-MM-DD) of a timestamp in Astana, or the written day if no offset.
  function timestampDay(value) {
    const t = parseTimestamp(value);
    if (!t) return null;
    return t.ms === null ? t.day : astanaWall(t.ms).day;
  }
  function formatTimestamp(value) {
    const t = parseTimestamp(value);
    if (!t) return NO_DATA;
    if (t.ms === null) return formatDay(t.day, "long") + ", " + t.hh + ":" + t.mm;
    const w = astanaWall(t.ms);
    return formatDay(w.day, "long") + ", " + w.hh + ":" + w.mm + " (время Астаны)";
  }

  // ---------- numbers ----------
  function groupDigits(intString) {
    // U+202F narrow no-break space, as ru-RU Intl does, without depending on ICU data.
    return intString.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }
  function formatNumber(n, fractionDigits) {
    if (typeof n !== "number" || !Number.isFinite(n)) return NO_DATA;
    const digits = fractionDigits == null ? 0 : fractionDigits;
    const fixed = Math.abs(n).toFixed(digits);
    const [i, f] = fixed.split(".");
    return (n < 0 ? "−" : "") + groupDigits(i) + (f && /[1-9]/.test(f) ? "," + f.replace(/0+$/, "") : "");
  }
  function budgetInfo(budget, evidence) {
    const b = isObj(budget) ? budget : {};
    const basis = enumOf(BASIS, b.basis, "unknown");
    const raw = b.amount_kzt;
    let state = "missing", amount = null;
    if (typeof raw === "number" && Number.isFinite(raw) && raw >= 0) { state = "ok"; amount = raw; }
    else if (raw !== null && raw !== undefined) state = "invalid";
    // Same rule as R02 validation: a synthetic record never carries an amount in tenge.
    if (state === "ok" && evidence === "synthetic") {
      return { state: "suppressed", amount: null, text: NO_DATA + " (у демо-записи сумма в тенге не показывается)", approx: null, basis, basisLabel: BASIS[basis], sourceId: str(b.source_id) };
    }
    let text = NO_DATA, approx = null;
    if (state === "ok") {
      text = formatNumber(Math.round(raw)) + " ₸";
      if (raw >= 1e9) approx = "≈ " + formatNumber(raw / 1e9, raw >= 1e11 ? 0 : 1) + " млрд ₸";
      else if (raw >= 1e6) approx = "≈ " + formatNumber(raw / 1e6, raw >= 1e8 ? 0 : 1) + " млн ₸";
    } else if (state === "invalid") text = NO_DATA + " (некорректное значение в записи)";
    return { state, amount, text, approx, basis, basisLabel: BASIS[basis], sourceId: str(b.source_id) };
  }

  // ---------- urls ----------
  function safeUrl(value) {
    if (typeof value !== "string") return null;
    const s = value.trim();
    // Control characters, whitespace inside and protocol-relative tricks are refused outright.
    if (!s || /[\u0000-\u001f\u007f\s]/.test(s) || s.length > 2048) return null;
    let u;
    try { u = new URL(s); } catch (e) { return null; }
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    if (u.username || u.password) return null;
    return u.href;
  }
  function urlHost(value) {
    const s = safeUrl(value);
    if (!s) return null;
    try { return new URL(s).hostname.replace(/^www\./, ""); } catch (e) { return null; }
  }

  // ---------- geometry ----------
  function isPos(p) {
    return Array.isArray(p) && p.length >= 2 && typeof p[0] === "number" && typeof p[1] === "number" &&
      Number.isFinite(p[0]) && Number.isFinite(p[1]) && p[0] >= -180 && p[0] <= 180 && p[1] >= -90 && p[1] <= 90;
  }
  function positionsOf(g) {
    if (g.type === "Point") return [g.coordinates];
    if (g.type === "LineString") return g.coordinates;
    if (g.type === "Polygon") {
      const out = [];
      for (const ring of g.coordinates) for (const p of ring) out.push(p);
      return out;
    }
    return [];
  }
  function bboxOf(g) {
    if (!g) return null;
    const pts = positionsOf(g);
    if (!pts.length) return null;
    let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
    for (const [x, y] of pts) { if (x < w) w = x; if (x > e) e = x; if (y < s) s = y; if (y > n) n = y; }
    return [w, s, e, n];
  }
  function bboxIntersects(a, b) {
    return !!a && !!b && a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
  }
  function bboxInside(inner, outer) {
    return !!inner && !!outer && inner[0] >= outer[0] && inner[2] <= outer[2] && inner[1] >= outer[1] && inner[3] <= outer[3];
  }
  // Returns {geometry, issue, kind}. An invalid shape becomes null with a visible reason;
  // nothing is repaired or guessed. kind: null | "invalid" | "unsupported" | "out_of_region".
  function normalizeGeometry(g, region) {
    if (g === null || g === undefined) return { geometry: null, issue: null, kind: null };
    if (!isObj(g) || typeof g.type !== "string") return { geometry: null, issue: "геометрия в записи повреждена", kind: "invalid" };
    let ok = false;
    if (g.type === "Point") ok = isPos(g.coordinates);
    else if (g.type === "LineString") ok = Array.isArray(g.coordinates) && g.coordinates.length >= 2 && g.coordinates.every(isPos);
    else if (g.type === "Polygon") {
      ok = Array.isArray(g.coordinates) && g.coordinates.length >= 1 && g.coordinates.every((ring) =>
        Array.isArray(ring) && ring.length >= 4 && ring.every(isPos) &&
        ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]);
    } else return { geometry: null, issue: "тип геометрии «" + g.type.slice(0, 40) + "» не входит в civic-v1", kind: "unsupported" };
    if (!ok) return { geometry: null, issue: "координаты в записи некорректны", kind: "invalid" };
    const clean = { type: g.type, coordinates: g.coordinates };
    const box = bboxOf(clean);
    if (region && !bboxInside(box, region)) {
      // Suggest a lon/lat swap only when the swapped shape really lands in the area.
      const swapped = box && bboxInside([box[1], box[0], box[3], box[2]], region);
      return { geometry: null, kind: "out_of_region", issue: "координаты вне области карты Астаны" + (swapped ? " — похоже, перепутаны долгота и широта" : "") };
    }
    return { geometry: clean, issue: null, kind: null };
  }

  // ---------- objects ----------
  const SCHEDULE_KEYS = ["planned_start", "original_planned_end", "current_planned_end", "actual_end"];

  function normalizeObject(raw, options) {
    const opt = options || {};
    if (!isObj(raw)) return { item: null, excluded: "не объект" };
    const id = typeof raw.id === "string" && raw.id.trim() ? raw.id : (typeof raw.id === "number" && Number.isFinite(raw.id) ? String(raw.id) : null);
    if (!id) return { item: null, excluded: "нет id" };
    // Public map shows only published items even if a buggy endpoint returns more.
    if (raw.publication !== undefined && raw.publication !== "published") return { item: null, excluded: "не опубликовано" };
    if (raw.city !== undefined && raw.city !== "astana") return { item: null, excluded: "другой город" };
    const issues = [];
    if (raw.schema_version !== undefined && raw.schema_version !== SCHEMA) issues.push("версия схемы «" + (typeof raw.schema_version === "string" ? raw.schema_version : typeof raw.schema_version).slice(0, 20) + "» не civic-v1");
    const geo = normalizeGeometry(raw.geometry, opt.region === undefined ? ASTANA_BBOX : opt.region);
    if (geo.issue) issues.push(geo.issue);
    const sch = isObj(raw.schedule) ? raw.schedule : {};
    const schedule = {};
    for (const k of SCHEDULE_KEYS) {
      const v = sch[k];
      if (v === null || v === undefined) schedule[k] = null;
      else if (parseDay(v)) schedule[k] = v;
      else { schedule[k] = null; issues.push("дата «" + (FIELD_LABELS["schedule." + k] || k) + "» в неверном формате"); }
    }
    const resp = isObj(raw.responsible) ? raw.responsible : {};
    const refs = Array.isArray(raw.source_refs) ? raw.source_refs.filter(isObj).map((r, i) => ({
      id: str(r.id) || "src-" + (i + 1),
      url: safeUrl(r.url),
      rawUrlRejected: r.url != null && r.url !== "" && !safeUrl(r.url),
      host: urlHost(r.url),
      publisher: str(r.publisher),
      published_on: parseDay(r.published_on) ? r.published_on : null,
      retrieved_at: str(r.retrieved_at),
      access_status: enumOf(ACCESS, r.access_status, null),
      license: str(r.license),
      fields: Array.isArray(r.fields) ? r.fields.filter((f) => typeof f === "string").slice(0, 40) : [],
    })) : [];
    const revision = Number.isInteger(raw.revision) && raw.revision >= 1 ? raw.revision : null;
    return {
      excluded: null,
      item: {
        id,
        kind: enumOf(KINDS, raw.kind, "other"),
        rawKind: typeof raw.kind === "string" ? raw.kind : null,
        title: str(raw.title) || "Без названия",
        hasTitle: !!str(raw.title),
        description: str(raw.description),
        status: enumOf(STATUSES, raw.status, "unknown"),
        geometry: geo.geometry,
        bbox: bboxOf(geo.geometry),
        geoIssue: geo.kind,
        precision: enumOf(PRECISION, raw.geometry_precision, "unknown"),
        schedule,
        budget: budgetInfo(raw.budget, enumOf(EVIDENCE, raw.evidence_type, null)),
        responsible: { organization: str(resp.organization), public_contact: str(resp.public_contact) },
        evidence: enumOf(EVIDENCE, raw.evidence_type, null),
        sourceRefs: refs,
        evidenceNotes: str(raw.evidence_notes),
        updatedAt: str(raw.updated_at),
        revision,
        issues,
      },
    };
  }

  function normalizeList(rawItems, options) {
    const items = [], excluded = [], seen = new Set();
    for (const raw of Array.isArray(rawItems) ? rawItems : []) {
      let r;
      // One broken record must never take the whole list down.
      try { r = normalizeObject(raw, options); } catch (e) { r = { item: null, excluded: "запись повреждена" }; }
      if (!r.item) { excluded.push(r.excluded); continue; }
      if (seen.has(r.item.id)) { excluded.push("повтор id"); continue; }
      seen.add(r.item.id);
      items.push(r.item);
    }
    return { items, excluded };
  }

  // ---------- provenance ----------
  // A source supports a field when one of its `fields` paths is that field, a parent of it
  // ("responsible" covers "responsible.organization") or a child of it.
  function sourceFor(item, path) {
    const refs = (item && item.sourceRefs) || [];
    return refs.find((r) => r.fields.some((f) => f === path || path.startsWith(f + ".") || f.startsWith(path + "."))) || null;
  }
  // Money is shown only with a source: the ref named by budget.source_id or one covering the amount.
  function costView(item) {
    const b = item.budget;
    if (b.state !== "ok") return { show: false, state: b.state, text: b.text };
    const src = (b.sourceId && item.sourceRefs.find((r) => r.id === b.sourceId)) || sourceFor(item, "budget.amount_kzt");
    if (!src) return { show: false, state: "unsourced", text: "сумма в записи есть, но источник не указан — не показываем" };
    return { show: true, state: "ok", text: b.text, approx: b.approx, basisLabel: b.basisLabel, source: src };
  }
  // The responsible organisation/contact is shown only when a source covers it.
  function responsibleView(item) {
    const r = item.responsible || {};
    if (!r.organization && !r.public_contact) return { show: false, state: "missing" };
    const orgSrc = r.organization ? sourceFor(item, "responsible.organization") : null;
    const contactSrc = r.public_contact ? sourceFor(item, "responsible.public_contact") : null;
    if (!orgSrc && !contactSrc) return { show: false, state: "unsourced" };
    return { show: true, state: "ok", organization: orgSrc ? r.organization : null, contact: contactSrc ? r.public_contact : null, source: orgSrc || contactSrc };
  }
  // One plain-language line about where the record comes from.
  function provenanceLine(item) {
    const refs = item.sourceRefs || [];
    if (!refs.length) {
      if (item.evidence === "synthetic") return { state: "demo", text: "Демонстрационная запись — источника нет." };
      return { state: "none", text: "Источник не указан — сведения нельзя проверить по документу." };
    }
    // The newest dated source leads (dates are YYYY-MM-DD strings); undated ones only when nothing is dated.
    const r = refs.reduce((a, x) => (x.published_on && (!a.published_on || x.published_on > a.published_on) ? x : a), refs[0]);
    const name = r.publisher || r.host || "источник без названия";
    return { state: "ok", ref: r, text: name + (r.published_on ? ", " + formatDay(r.published_on) : "") + (refs.length > 1 ? " и ещё " + (refs.length - 1) : "") };
  }

  // ---------- schedule semantics ----------
  // Planned interval only: [planned_start, current_planned_end ?? original_planned_end].
  // Planned interval exactly as civic-v1 §2 and R02 define it: [planned_start, current_planned_end].
  // original_planned_end is history (the first promise), never the active end.
  function plannedInterval(item) {
    const s = item.schedule || {};
    const start = s.planned_start || null;
    const end = s.current_planned_end || null;
    return { start, end, complete: !!(start && end) };
  }
  // Same rule as R02 _filter_sql: an unknown bound is open, the record is flagged as an
  // incomplete interval and shown with that badge; nothing is concluded about the work
  // being active. Records with no planned dates at all do not match a period.
  function matchPeriod(item, from, to) {
    const pf = parseDay(from), pt = parseDay(to);
    if (!pf && !pt) return { match: true, partial: false, undated: false, missing: null };
    const iv = plannedInterval(item);
    if (!iv.start && !iv.end) return { match: false, partial: false, undated: true, missing: "both" };
    const lo = pf ? pf.ord : -Infinity, hi = pt ? pt.ord : Infinity;
    const s = iv.start ? parseDay(iv.start).ord : -Infinity;
    const e = iv.end ? parseDay(iv.end).ord : Infinity;
    const a = iv.complete ? Math.min(s, e) : s, b = iv.complete ? Math.max(s, e) : e;
    return { match: a <= hi && b >= lo, partial: !iv.complete, undated: false, missing: !iv.start ? "start" : !iv.end ? "end" : null };
  }

  function scheduleShift(item) {
    const s = item.schedule || {};
    if (!s.original_planned_end || !s.current_planned_end) return null;
    const days = dayDiff(s.original_planned_end, s.current_planned_end);
    if (!days) return null;
    return { days, from: s.original_planned_end, to: s.current_planned_end };
  }

  // "План прошлых лет": the plan's end date is behind the viewer's day while the
  // record does not say the work finished. We do not conclude what happened.
  // The mark uses every published promise: the current end, else the first (original) end
  // when no new end was published, else a start more than a year old with no end at all.
  function staleness(item, today) {
    if (!today || !parseDay(today)) return null;
    const sc = item.schedule || {};
    if (item.status === "completed" || item.status === "cancelled" || sc.actual_end) return null;
    const end = sc.current_planned_end || sc.original_planned_end || null;
    if (end && end < today) return { kind: "plan_end_passed", end, days: dayDiff(end, today), original: !sc.current_planned_end };
    if (!end && sc.planned_start && dayDiff(sc.planned_start, today) > 365) {
      return { kind: "old_start_no_end", start: sc.planned_start, days: dayDiff(sc.planned_start, today) };
    }
    return null;
  }

  function plural(n, one, few, many) {
    const a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return many;
    if (b > 1 && b < 5) return few;
    if (b === 1) return one;
    return many;
  }
  function daysText(n) { return formatNumber(Math.abs(n)) + " " + plural(n, "день", "дня", "дней"); }

  // ---------- history ----------
  function normalizeChanged(cf) {
    // civic-v1 says changed_fields; accept ["path"], [{field,before,after}] or {path:{before,after}}.
    const out = [];
    if (Array.isArray(cf)) {
      for (const f of cf) {
        if (typeof f === "string") out.push({ field: f });
        else if (isObj(f) && typeof (f.field || f.path) === "string") out.push({ field: f.field || f.path, before: f.before, after: f.after, hasValues: own(f, "before") || own(f, "after") });
      }
    } else if (isObj(cf)) {
      for (const [k, v] of Object.entries(cf)) out.push(isObj(v) ? { field: k, before: v.before ?? v.from, after: v.after ?? v.to, hasValues: true } : { field: k });
    }
    return out.slice(0, 60);
  }
  function fieldLabel(path) {
    if (own(FIELD_LABELS, path)) return FIELD_LABELS[path];
    const top = String(path).split(".")[0];
    return own(FIELD_LABELS, top) ? FIELD_LABELS[top] : String(path).slice(0, 60);
  }
  function normalizeHistory(history) {
    const rows = (Array.isArray(history) ? history : []).filter(isObj).map((h) => ({
      id: str(h.id) || null,
      revision: Number.isInteger(h.revision) ? h.revision : null,
      at: str(h.at),
      changed: normalizeChanged(h.changed_fields),
      reason: str(h.reason),
      actor: str(h.public_actor_label),
    }));
    rows.sort((a, b) => (b.revision ?? -1) - (a.revision ?? -1) || String(b.at || "").localeCompare(String(a.at || "")));
    return rows;
  }
  function touchesEnd(row) {
    return row.changed.some((c) => c.field === "schedule.current_planned_end" || c.field === "schedule");
  }
  // Latest published history entry that moved the current planned end.
  function shiftReason(rows) {
    const hit = rows.find(touchesEnd);
    return hit ? { reason: hit.reason, at: hit.at, revision: hit.revision, actor: hit.actor } : null;
  }
  // Stretch: what changed between two published revisions (a < b): union of fields
  // touched by revisions (a, b], with their reasons. Values only if history carries them.
  function compareRevisions(rows, a, b) {
    if (!Number.isInteger(a) || !Number.isInteger(b)) return null;
    const lo = Math.min(a, b), hi = Math.max(a, b);
    const span = rows.filter((r) => r.revision !== null && r.revision > lo && r.revision <= hi)
      .sort((x, y) => x.revision - y.revision);
    const fields = new Map();
    for (const r of span) for (const c of r.changed) {
      const prev = fields.get(c.field);
      fields.set(c.field, {
        field: c.field,
        label: fieldLabel(c.field),
        before: prev ? prev.before : c.before,
        after: c.after,
        hasValues: (prev ? prev.hasValues : true) && !!c.hasValues,
        revisions: (prev ? prev.revisions : []).concat(r.revision),
      });
    }
    return { from: lo, to: hi, steps: span.length, fields: [...fields.values()], reasons: span.filter((r) => r.reason).map((r) => ({ revision: r.revision, reason: r.reason })) };
  }

  // ---------- filters ----------
  const PERIODS = {
    all: "Все сроки",
    next30: "Ближайшие 30 дней",
    month: "Этот месяц",
    nextMonth: "Следующий месяц",
    year: "Этот год",
    custom: "Свой период",
  };
  function periodRange(period, today, custom) {
    const t = parseDay(today);
    if (period === "all" || !t) return { from: null, to: null };
    const p = (n) => String(n).padStart(2, "0");
    const lastDay = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
    if (period === "next30") return { from: today, to: addDays(today, 30) };
    if (period === "month") return { from: t.y + "-" + p(t.m) + "-01", to: t.y + "-" + p(t.m) + "-" + p(lastDay(t.y, t.m)) };
    if (period === "nextMonth") {
      const y = t.m === 12 ? t.y + 1 : t.y, m = t.m === 12 ? 1 : t.m + 1;
      return { from: y + "-" + p(m) + "-01", to: y + "-" + p(m) + "-" + p(lastDay(y, m)) };
    }
    if (period === "year") return { from: t.y + "-01-01", to: t.y + "-12-31" };
    if (period === "custom") {
      const c = custom || {};
      let from = parseDay(c.from) ? c.from : null, to = parseDay(c.to) ? c.to : null;
      if (from && to && from > to) [from, to] = [to, from];
      return { from, to };
    }
    return { from: null, to: null };
  }
  // evidence: which records by provenance — all | sourced (at least one source shown on the card) | demo
  // (synthetic) | unsourced (no source). Grouped by the sources the card lists, so the filter never
  // contradicts the card's «Откуда сведения» (R02 lets a hypothesis carry a source).
  // hidePast: hide plans that never started (planned/unknown) whose planned end passed; overdue works in
  // progress stay visible — a delay is what the resident needs to see (see pastPlan()).
  const EVIDENCE_FILTERS = { all: "Все записи", sourced: "С источником", demo: "Демонстрационные", unsourced: "Без источника" };
  function evidenceGroup(item) {
    if (item.evidence === "synthetic") return "demo";
    return Array.isArray(item.sourceRefs) && item.sourceRefs.length ? "sourced" : "unsourced";
  }
  function pastPlan(item, today) {
    if (item.status !== "planned" && item.status !== "unknown") return false;
    const st = staleness(item, today);
    return !!st && st.kind === "plan_end_passed";   // an old start with no end has no passed deadline
  }
  function defaultFilters() {
    return { kinds: [], statuses: [], period: "all", from: null, to: null, area: false, evidence: "all", hidePast: false };
  }
  function sanitizeFilters(f) {
    const d = defaultFilters();
    if (!isObj(f)) return d;
    const kinds = Array.isArray(f.kinds) ? f.kinds.filter((k) => typeof k === "string" && (own(KINDS, k) || k === "other")) : [];
    const statuses = Array.isArray(f.statuses) ? f.statuses.filter((v) => typeof v === "string" && own(STATUSES, v)) : [];
    return {
      kinds: [...new Set(kinds)].slice(0, 10),
      statuses: [...new Set(statuses)].slice(0, 10),
      period: enumOf(PERIODS, f.period, "all"),
      from: parseDay(f.from) ? f.from : null,
      to: parseDay(f.to) ? f.to : null,
      area: f.area === true,
      evidence: enumOf(EVIDENCE_FILTERS, f.evidence, "all"),
      hidePast: f.hidePast === true,
    };
  }
  function isDefaultFilters(f) {
    const s = sanitizeFilters(f);
    return !s.kinds.length && !s.statuses.length && s.period === "all" && !s.area && s.evidence === "all" && !s.hidePast;
  }
  // Returns visible items plus honest counters for what was left out and why. Every
  // counter only counts records that pass all the other active filters (ctx.match is the
  // text search), so "show them" really yields that many. Input order is preserved.
  function applyFilters(items, filters, ctx) {
    const f = sanitizeFilters(filters);
    const c = ctx || {};
    const match = typeof c.match === "function" ? c.match : null;
    const range = periodRange(f.period, c.today, { from: f.from, to: f.to });
    const shown = [];
    const counts = { total: items.length, shown: 0, undated: 0, partial: 0, outsideArea: 0, noGeometry: 0, mappedOut: 0, past: 0, byKind: {}, byStatus: {}, byEvidence: {} };
    for (const it of items) {
      if (match && !match(it)) continue;
      const eg = evidenceGroup(it);
      const kindOk = !f.kinds.length || f.kinds.includes(it.kind);
      const statusOk = !f.statuses.length || f.statuses.includes(it.status);
      const evOk = f.evidence === "all" || f.evidence === eg;
      const pastOk = !f.hidePast || !pastPlan(it, c.today);
      let areaOut = null;
      if (f.area && c.viewBox) areaOut = !it.bbox ? "noGeometry" : !bboxIntersects(it.bbox, c.viewBox) ? "outsideArea" : null;
      const pm = matchPeriod(it, range.from, range.to);
      // Facets: each counts what choosing that value would give, i.e. all other filters applied.
      const rest = pm.match && !areaOut && pastOk;
      if (rest && statusOk && evOk) counts.byKind[it.kind] = (counts.byKind[it.kind] || 0) + 1;
      if (rest && kindOk && evOk) counts.byStatus[it.status] = (counts.byStatus[it.status] || 0) + 1;
      if (rest && kindOk && statusOk) counts.byEvidence[eg] = (counts.byEvidence[eg] || 0) + 1;
      if (!kindOk || !statusOk || !evOk) continue;
      // Each counter promises what its «show» action yields, so it only counts records every other
      // filter lets through: undated (period) needs area and past, area needs past, past needs both.
      if (!pm.match) { if (pm.undated && !areaOut && pastOk) counts.undated++; continue; }
      if (areaOut) { if (pastOk) counts[areaOut]++; continue; }
      if (!pastOk) { counts.past++; continue; }
      if (pm.partial) counts.partial++;
      if (!it.bbox) counts.mappedOut++;
      shown.push({ item: it, partial: pm.partial, missing: pm.missing });
    }
    counts.shown = shown.length;
    return { shown, counts, range };
  }

  // Sort: things with a known planned end soonest first, undated last, then title.
  function sortItems(rows) {
    return rows.slice().sort((a, b) => {
      const ea = plannedInterval(a.item || a).end, eb = plannedInterval(b.item || b).end;
      if (ea && eb && ea !== eb) return ea < eb ? -1 : 1;
      if (ea && !eb) return -1;
      if (!ea && eb) return 1;
      return String((a.item || a).title).localeCompare(String((b.item || b).title), "ru");
    });
  }

  // ---------- R12: точность карты (линии по улицам OSM, «примерное место» областью) ----------
  const APPROX_RADIUS_M = 120;   // радиус области «примерное место» вокруг примерной точки
  const M_PER_DEG = Math.PI / 180 * 6371008.8;

  // Круг радиусом radiusM метров вокруг точки как полигон (n вершин) — область, а не уверенная точка.
  function circlePolygon(center, radiusM, n) {
    const k = n || 48;
    const dLat = radiusM / M_PER_DEG, dLon = dLat / Math.cos(center[1] * Math.PI / 180);
    const ring = [];
    for (let i = 0; i < k; i++) {
      const a = (2 * Math.PI * i) / k;
      ring.push([+(center[0] + dLon * Math.cos(a)).toFixed(7), +(center[1] + dLat * Math.sin(a)).toFixed(7)]);
    }
    ring.push(ring[0].slice());
    return { type: "Polygon", coordinates: [ring] };
  }
  function haversineM(a, b) {
    const r = Math.PI / 180, dLat = (b[1] - a[1]) * r, dLon = (b[0] - a[0]) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dLon / 2) ** 2;
    return 2 * 6371008.8 * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  // Область «примерное место» для записи без точного места: круг вокруг точки или вокруг всей линии/площади.
  function approxArea(g) {
    if (!g) return null;
    if (g.type === "Point") return circlePolygon(g.coordinates, APPROX_RADIUS_M);
    const b = bboxOf(g);
    const c = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
    return circlePolygon(c, Math.max(APPROX_RADIUS_M, haversineM([b[0], b[1]], [b[2], b[3]]) / 2 + 40));
  }
  const sameCoords = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  // demo_snapped.json (engine/civic_geo/snap_demo.py): замена «линий от руки» участками по рёбрам графа.
  // Замена применяется только если исходная геометрия записи не менялась с момента привязки
  // (иначе запись уже исправили в хранилище — её и показываем). Запись не мутируется.
  function applySnapped(items, snapped) {
    const map = isObj(snapped) && isObj(snapped.items) ? snapped.items : null;
    if (!map) return items;
    return items.map((it) => {
      const s = own(map, it.id) ? map[it.id] : null;
      if (!isObj(s) || !it.geometry || !sameCoords(s.original_coordinates, it.geometry.coordinates)) return it;
      if (s.status === "snapped" && isObj(s.geometry)) {
        const g = normalizeGeometry(s.geometry, ASTANA_BBOX);
        if (!g.geometry) return it;
        return Object.assign({}, it, {
          geometry: g.geometry, bbox: bboxOf(g.geometry),
          snap: { source: str(s.geometry_source) || "osm-graph", street: str(s.street_ru), streetKk: str(s.street_kk),
            lengthM: typeof s.length_m === "number" ? s.length_m : null, display: str(s.display) },
        });
      }
      if (s.display === "approximate_area") return Object.assign({}, it, { forceApprox: true });
      return it;
    });
  }
  // Как запись показывается: line/area/point — точно; approx — областью «примерное место».
  function displayMode(it) {
    if (!it.geometry) return null;
    if (it.snap) return "exact";
    if (it.forceApprox || it.precision !== "source") return "approx";
    return "exact";
  }
  function placeText(it) {
    if (it.snap && it.snap.display === "street_line") return "Участок улицы по карте OSM" + (it.snap.street ? ": " + it.snap.street : "");
    if (it.snap && it.snap.display === "yard") return "Двор по карте OSM";
    if (displayMode(it) === "approx") return "Примерное место — показано областью";
    return null;
  }

  // ---------- map data ----------
  // Polygons go largest first so a small area inside a big one is drawn (and picked) on top.
  // Записи без точного места дают ещё и мягкую область approx_area (свои слои, под точками).
  function featureCollection(items) {
    const features = [];
    const area = (it) => (it.bbox ? (it.bbox[2] - it.bbox[0]) * (it.bbox[3] - it.bbox[1]) : 0);
    const withGeo = items.filter((it) => it.geometry);
    // Partition (a mixed comparator is not a consistent order): polygons by area descending, then the rest.
    const ordered = withGeo.filter((it) => it.geometry.type === "Polygon").sort((a, b) => area(b) - area(a))
      .concat(withGeo.filter((it) => it.geometry.type !== "Polygon"));
    const props = (it, extra) => Object.assign({
      cid: it.id,
      kind: it.kind,
      status: it.status,
      exact: displayMode(it) === "exact",
      synthetic: it.evidence === "synthetic",
      snapped: !!it.snap,
      title: it.title.slice(0, 160),
    }, it.snap && it.snap.street ? { street: it.snap.street } : null, extra || {});
    const approx = ordered.filter((it) => displayMode(it) === "approx");
    // Области «примерное место» — первыми (под всеми линиями и площадями).
    for (const it of approx) {
      const g = it.geometry.type === "Polygon" ? it.geometry : approxArea(it.geometry);
      if (g) features.push({ type: "Feature", geometry: g, properties: props(it, { approx_area: true }) });
    }
    for (const it of ordered) {
      const mode = displayMode(it);
      // Примерная линия или площадь не рисуется уверенной линией: только областью (выше) — CONTRACT §8.4.
      if (mode === "approx" && it.geometry.type !== "Point") continue;
      features.push({ type: "Feature", geometry: it.geometry, properties: props(it) });
    }
    return { type: "FeatureCollection", features };
  }

  // ---------- requests ----------
  // Monotonic ticket: a response is applied only if no newer request was issued.
  function createSequence() {
    let n = 0;
    return { next: () => ++n, isCurrent: (t) => t === n, cancel: () => { n++; } };
  }
  // Accept R01's normalised data or a raw civic envelope; throw on {ok:false}.
  function unwrap(resp) {
    if (isObj(resp) && resp.ok === false) {
      const e = new Error((isObj(resp.error) && str(resp.error.message)) || "Ошибка сервера");
      e.code = isObj(resp.error) ? resp.error.code : null;
      throw e;
    }
    if (isObj(resp) && resp.ok === true && own(resp, "data")) return resp.data;
    return resp;
  }
  function errorInfo(err, context) {
    const e = err || {};
    const status = [e.status, e.httpStatus, e.statusCode, e.response && e.response.status]
      .find((v) => Number.isInteger(v)) || null;
    const code = typeof e.code === "string" ? e.code : (isObj(e.error) && typeof e.error.code === "string" ? e.error.code : null);
    // Only a failed fetch is "offline"; a TypeError from bad data is not a network problem.
    const offline = (typeof navigator !== "undefined" && navigator && navigator.onLine === false) ||
      (e.name === "TypeError" && /fetch|network|load failed/i.test(String(e.message || "")));
    let text;
    if (code === "aborted") text = "Запрос отменён.";
    else if (code === "timeout") text = "Сервер не ответил вовремя. Повторите попытку.";
    else if (code === "network") text = "Нет связи с сервером. Проверьте подключение и повторите.";
    else if ((status === 404 || code === "not_found") && context === "list") text = "Сервер не знает адрес списка объектов (404). Сообщите администратору.";
    else if (status === 404 || code === "not_found") text = "Объект не найден или снят с публикации.";
    else if (status === 429) text = "Слишком много запросов. Подождите немного и повторите.";
    else if (status === 503 || code === "module_unavailable") text = "Сервис объектов сейчас недоступен. Повторите позже.";
    else if (status && status >= 500) text = "Сервер не смог ответить (" + status + "). Данные не изменены — повторите позже.";
    else if (offline && !status) text = "Нет связи с сервером. Проверьте подключение и повторите.";
    else text = "Не удалось получить данные" + (status ? " (" + status + ")" : "") + ".";
    return { status: status || null, code, text, notFound: context !== "list" && (status === 404 || code === "not_found"), aborted: code === "aborted" };
  }

  // ---------- contrast (WCAG 2.x) ----------
  function luminance(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex);
    if (!m) return null;
    const v = parseInt(m[1], 16);
    const ch = [(v >> 16) & 255, (v >> 8) & 255, v & 255].map((c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  }
  function contrast(a, b) {
    const la = luminance(a), lb = luminance(b);
    if (la === null || lb === null) return null;
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }

  return {
    SCHEMA, NO_DATA, KINDS, OTHER_KIND, KIND_ORDER, STATUSES, STATUS_ORDER, EVIDENCE, EVIDENCE_UNKNOWN,
    PRECISION, BASIS, ACCESS, FIELD_LABELS, PERIODS, ASTANA_BBOX,
    kindInfo: (k) => KINDS[k] || OTHER_KIND,
    evidenceInfo: (e) => EVIDENCE[e] || EVIDENCE_UNKNOWN,
    parseDay, addDays, dayDiff, localDay, formatDay, parseTimestamp, formatTimestamp, timestampDay, formatNumber,
    sourceFor, costView, responsibleView, provenanceLine,
    budgetInfo, safeUrl, urlHost, normalizeGeometry, bboxOf, bboxIntersects, normalizeObject, normalizeList,
    plannedInterval, matchPeriod, scheduleShift, staleness, plural, daysText, normalizeHistory, fieldLabel,
    shiftReason, compareRevisions, periodRange, defaultFilters, sanitizeFilters, isDefaultFilters, EVIDENCE_FILTERS, evidenceGroup, pastPlan,
    applyFilters, sortItems, featureCollection, createSequence, unwrap, errorInfo, contrast,
    APPROX_RADIUS_M, circlePolygon, approxArea, applySnapped, displayMode, placeText, haversineM,
  };
});
