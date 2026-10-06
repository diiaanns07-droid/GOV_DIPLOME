"use strict";
// Contract mock of the civic-v1 HTTP API (round-11 CONTRACT.txt, sections 1-2).
// Test infrastructure for R04 browser tests only. The real backend is owned by R02.
// Zero dependencies; all state is in memory; credentials come from the caller.

const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const API = "/api/civic/v1";
const COOKIE = "civic_session";
const PUBLIC_ACTOR_LABEL = "Редактор";
const MAX_LOGIN_FAILURES = 5;
const LOCKOUT_MS = 15 * 60 * 1000;

const ENUMS = {
  kind: ["construction", "roadworks", "landscaping", "event"],
  status: ["planned", "in_progress", "completed", "cancelled", "unknown"],
  publication: ["draft", "published", "archived"],
  geometry_precision: ["source", "approximate", "unknown"],
  basis: ["planned", "contract", "spent", "unknown"],
  evidence_type: ["observed", "derived", "hypothesis", "synthetic"],
  access_status: ["fetched", "not_fetched", "unavailable"],
};

// Public DTO allowlist, in contract order.
const PUBLIC_FIELDS = [
  "schema_version", "id", "city", "kind", "title", "description", "status", "publication",
  "geometry", "geometry_precision", "schedule", "budget", "responsible", "evidence_type",
  "source_refs", "evidence_notes", "updated_at", "revision",
];
const STAFF_EXTRA = ["internal_notes", "created_by"];
const EDITABLE = [
  "kind", "title", "description", "status", "geometry", "geometry_precision", "schedule",
  "budget", "responsible", "evidence_type", "source_refs", "evidence_notes", "internal_notes",
];
// Ignored on create, rejected (422) inside update.changes.
const SERVER_FIELDS = [
  "id", "revision", "publication", "updated_at", "schema_version", "city", "created_by",
  "actor", "first_published_at",
];
const NESTED = {
  schedule: ["planned_start", "original_planned_end", "current_planned_end", "actual_end"],
  budget: ["amount_kzt", "basis", "source_id"],
  responsible: ["organization", "public_contact"],
};
const SOURCE_REF_KEYS = [
  "id", "url", "publisher", "published_on", "retrieved_at", "access_status", "license", "fields",
];
const isPublicPath = (p) => p !== "internal_notes";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".cjs": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

class ApiError extends Error {
  constructor(status, code, message, extra) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra || {};
  }
}
const validationError = (fields) =>
  new ApiError(422, "validation", "Проверьте выделенные поля", { fields });

// ---------- validation helpers ----------

const isPlainObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function isDate(v) {
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const [y, m, d] = v.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === m - 1 && t.getUTCDate() === d;
}

function isHttpUrl(v) {
  if (typeof v !== "string") return false;
  try {
    const u = new URL(v);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

const isPosition = (p) =>
  Array.isArray(p) && (p.length === 2 || p.length === 3) &&
  p.every((n) => typeof n === "number" && Number.isFinite(n)) &&
  p[0] >= -180 && p[0] <= 180 && p[1] >= -90 && p[1] <= 90;
const isRing = (r) =>
  Array.isArray(r) && r.length >= 4 && r.every(isPosition) &&
  r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1];

function geometryError(g) {
  if (g === null) return null;
  if (!isPlainObject(g)) return "Ожидается GeoJSON-геометрия или пусто";
  const c = g.coordinates;
  switch (g.type) {
    case "Point":
      return isPosition(c) ? null : "Точка: [долгота, широта] в WGS84";
    case "LineString":
      return Array.isArray(c) && c.length >= 2 && c.every(isPosition)
        ? null : "Линия: не менее двух точек [долгота, широта]";
    case "Polygon":
      return Array.isArray(c) && c.length >= 1 && c.every(isRing)
        ? null : "Полигон: замкнутые кольца не менее чем из 4 точек";
    default:
      return "Допустимы только Point, LineString или Polygon";
  }
}

function checkEnum(fields, key, value, allowed) {
  if (value === null || value === undefined) fields[key] = "Обязательное поле";
  else if (!allowed.includes(value)) fields[key] = "Недопустимое значение";
}

function checkText(fields, key, value, max, nullable) {
  if (nullable && value === null) return;
  if (typeof value !== "string") fields[key] = "Ожидается строка";
  else if (value.length > max) fields[key] = `Не более ${max} символов`;
}

function validateObject(o) {
  const f = {};
  if (typeof o.title !== "string" || !o.title.trim()) f.title = "Укажите название";
  else if (o.title.length > 200) f.title = "Не более 200 символов";
  else if (/<[a-zA-Z!/]/.test(o.title)) f.title = "Только простой текст, без HTML";
  checkText(f, "description", o.description, 5000, false);
  checkEnum(f, "kind", o.kind, ENUMS.kind);
  checkEnum(f, "status", o.status, ENUMS.status);
  checkEnum(f, "geometry_precision", o.geometry_precision, ENUMS.geometry_precision);
  checkEnum(f, "evidence_type", o.evidence_type, ENUMS.evidence_type);
  const g = geometryError(o.geometry);
  if (g) f.geometry = g;

  for (const k of NESTED.schedule) {
    const v = o.schedule[k];
    if (v !== null && !isDate(v)) f[`schedule.${k}`] = "Дата в формате ГГГГ-ММ-ДД или пусто";
  }

  const refIds = new Set();
  if (!Array.isArray(o.source_refs)) f.source_refs = "Ожидается список источников";
  else {
    o.source_refs.forEach((r, i) => {
      const p = `source_refs[${i}]`;
      if (!isPlainObject(r)) { f[p] = "Ожидается объект источника"; return; }
      for (const k of Object.keys(r)) if (!SOURCE_REF_KEYS.includes(k)) f[`${p}.${k}`] = "Неизвестное поле";
      if (typeof r.id !== "string" || !r.id.trim()) f[`${p}.id`] = "Укажите идентификатор источника";
      else if (refIds.has(r.id)) f[`${p}.id`] = "Идентификатор источника повторяется";
      else refIds.add(r.id);
      if (!isHttpUrl(r.url)) f[`${p}.url`] = "Нужна ссылка http(s)";
      checkEnum(f, `${p}.access_status`, r.access_status, ENUMS.access_status);
      for (const k of ["published_on", "retrieved_at"]) {
        if (r[k] !== null && !isDate(r[k])) f[`${p}.${k}`] = "Дата в формате ГГГГ-ММ-ДД или пусто";
      }
      for (const k of ["publisher", "license"]) checkText(f, `${p}.${k}`, r[k], 500, true);
      if (!Array.isArray(r.fields) || r.fields.some((x) => typeof x !== "string")) {
        f[`${p}.fields`] = "Ожидается список путей полей";
      }
    });
  }

  const b = o.budget;
  if (b.amount_kzt !== null &&
      !(typeof b.amount_kzt === "number" && Number.isFinite(b.amount_kzt) && b.amount_kzt >= 0)) {
    f["budget.amount_kzt"] = "Сумма — неотрицательное число или пусто (неизвестно)";
  }
  checkEnum(f, "budget.basis", b.basis, ENUMS.basis);
  if (b.source_id !== null) {
    if (typeof b.source_id !== "string") f["budget.source_id"] = "Ожидается строка или пусто";
    else if (!refIds.has(b.source_id)) f["budget.source_id"] = "Источник не найден в source_refs";
  }

  checkText(f, "responsible.organization", o.responsible.organization, 500, true);
  checkText(f, "responsible.public_contact", o.responsible.public_contact, 500, true);
  checkText(f, "evidence_notes", o.evidence_notes, 5000, false);
  checkText(f, "internal_notes", o.internal_notes, 5000, true);
  return f;
}

// ---------- object helpers ----------

function blankObject() {
  return {
    schema_version: "civic-v1", id: null, city: "astana", kind: null, title: "", description: "",
    status: "unknown", publication: "draft", geometry: null, geometry_precision: "unknown",
    schedule: { planned_start: null, original_planned_end: null, current_planned_end: null, actual_end: null },
    budget: { amount_kzt: null, basis: "unknown", source_id: null },
    responsible: { organization: null, public_contact: null },
    evidence_type: null, source_refs: [], evidence_notes: "", updated_at: null, revision: 0,
    internal_notes: null, created_by: null, first_published_at: null,
  };
}

// Canonical key order; missing optional keys get explicit null/[]; unknown keys kept for validation.
function normalizeRef(r) {
  if (!isPlainObject(r)) return r;
  const out = {};
  for (const k of SOURCE_REF_KEYS) out[k] = k in r ? structuredClone(r[k]) : k === "fields" ? [] : null;
  for (const k of Object.keys(r)) if (!SOURCE_REF_KEYS.includes(k)) out[k] = r[k];
  return out;
}

// mode "create": server fields ignored; mode "update": server fields rejected.
function applyChanges(base, changes, mode) {
  const next = structuredClone(base);
  const fields = {};
  for (const [key, value] of Object.entries(changes)) {
    if (SERVER_FIELDS.includes(key)) {
      if (mode === "update") fields[key] = "Поле назначает сервер, его нельзя изменить";
      continue;
    }
    if (!EDITABLE.includes(key)) { fields[key] = "Неизвестное поле"; continue; }
    if (NESTED[key]) {
      if (!isPlainObject(value)) { fields[key] = "Ожидается объект"; continue; }
      for (const [k, v] of Object.entries(value)) {
        if (NESTED[key].includes(k)) next[key][k] = structuredClone(v);
        else fields[`${key}.${k}`] = "Неизвестное поле";
      }
    } else if (key === "source_refs") {
      next.source_refs = Array.isArray(value) ? value.map(normalizeRef) : value;
    } else if (key === "geometry" && isPlainObject(value)) {
      next.geometry = { type: value.type, coordinates: structuredClone(value.coordinates) };
    } else {
      next[key] = structuredClone(value);
    }
  }
  return { next, fields };
}

function diffPaths(a, b) {
  const out = [];
  for (const key of EDITABLE) {
    if (NESTED[key]) {
      for (const k of NESTED[key]) if (!same(a[key][k], b[key][k])) out.push(`${key}.${k}`);
    } else if (!same(a[key], b[key])) out.push(key);
  }
  return out;
}

function publicDTO(rec) {
  const out = {};
  for (const k of PUBLIC_FIELDS) out[k] = structuredClone(rec[k]);
  out.source_refs = rec.source_refs.map((r) => {
    const ref = {};
    for (const k of SOURCE_REF_KEYS) ref[k] = structuredClone(r[k]);
    return ref;
  });
  return out;
}

function staffDTO(rec) {
  const out = publicDTO(rec);
  for (const k of STAFF_EXTRA) out[k] = structuredClone(rec[k]);
  return out;
}

const publicHistoryEntry = (h) => ({
  id: h.id, object_id: h.object_id, revision: h.revision, at: h.at,
  changed_fields: h.changed_fields.filter(isPublicPath), reason: h.reason,
  public_actor_label: h.public_actor_label, action: h.action,
});
const staffHistoryEntry = (h) => ({ ...publicHistoryEntry(h), changed_fields: [...h.changed_fields], actor: h.actor, public: h.public });

function readReason(v) {
  if (v === undefined || v === null) return { value: "" };
  if (typeof v !== "string") return { error: "Ожидается строка" };
  if (v.length > 1000) return { error: "Не более 1000 символов" };
  return { value: v.trim() };
}

function safeEqual(a, b) {
  const ha = crypto.createHash("sha256").update(String(a)).digest();
  const hb = crypto.createHash("sha256").update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}

function parseCookies(header) {
  const out = {};
  for (const part of String(header || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  return out;
}

// ---------- server ----------

function createMockServer(opts = {}) {
  const users = (opts.users || []).map((u) => ({ ...u }));
  const clock = opts.clock || (() => new Date());
  const pageSize = opts.pageSize || 50;
  const maxBody = opts.maxBody || 64 * 1024;
  const staticMap = opts.static || {};
  const staticDirs = (opts.staticDirs || []).map((d) => ({ prefix: d.prefix, dir: path.resolve(d.dir) }));

  const state = { objects: new Map(), history: [], sessions: new Map() };
  const requests = [];
  const errors = [];
  const loginFailures = new Map(); // username -> {count, last}
  const faults = [];
  const writeSeq = new Map(); // id -> monotonic write order (sort tie-break)
  const timers = new Set();
  let counters = { obj: 0, hist: 0, write: 0 };
  let port = null;

  const nowIso = () => clock().toISOString();

  function nextObjectId() {
    let id;
    do id = `obj-${++counters.obj}`; while (state.objects.has(id));
    return id;
  }

  function store(rec) {
    state.objects.set(rec.id, rec);
    writeSeq.set(rec.id, ++counters.write);
  }

  function addHistory(rec, action, changed, reason, actor, isPublic) {
    state.history.push({
      id: `h-${++counters.hist}`, object_id: rec.id, revision: rec.revision, at: rec.updated_at,
      changed_fields: changed, reason: reason || null, public_actor_label: PUBLIC_ACTOR_LABEL,
      action, actor, public: isPublic,
    });
  }

  function getRec(id) {
    const rec = state.objects.get(id);
    if (!rec) throw new ApiError(404, "not_found", "Объект не найден");
    return rec;
  }

  function checkRevision(rec, expected, fields) {
    if (!Number.isInteger(expected) || expected < 1) {
      fields.expected_revision = "Укажите текущую ревизию (целое число)";
    }
    if (Object.keys(fields).length) throw validationError(fields);
    if (expected !== rec.revision) {
      throw new ApiError(409, "stale_revision", "Объект изменён другим редактором; обновите карточку",
        { current_revision: rec.revision });
    }
  }

  // ----- operations -----

  function createObject(body, actor) {
    const { next, fields } = applyChanges(blankObject(), body, "create");
    const all = { ...validateObject(next), ...fields };
    if (Object.keys(all).length) throw validationError(all);
    Object.assign(next, {
      id: nextObjectId(), revision: 1, publication: "draft", updated_at: nowIso(),
      created_by: { name: actor.name },
    });
    store(next);
    addHistory(next, "create", diffPaths(blankObject(), next), null, actor.username, false);
    return next;
  }

  function updateObject(id, body, actor) {
    const rec = getRec(id);
    const reason = readReason(body.reason);
    checkRevision(rec, body.expected_revision, {});
    if (!isPlainObject(body.changes)) throw validationError({ changes: "Ожидается объект изменений" });
    if (!Object.keys(body.changes).length) throw new ApiError(422, "no_changes", "Нет изменений для сохранения");
    const { next, fields } = applyChanges(rec, body.changes, "update");
    const all = { ...validateObject(next), ...fields };
    if (reason.error) all.reason = reason.error;
    const changed = diffPaths(rec, next);
    if (!Object.keys(all).length && !changed.length) {
      throw new ApiError(422, "no_changes", "Нет изменений для сохранения");
    }
    if (rec.first_published_at) {
      if (!reason.error && !reason.value) all.reason = "Для опубликованного объекта укажите причину изменения";
      if (changed.includes("schedule.original_planned_end")) {
        all["schedule.original_planned_end"] =
          "Первоначальный срок после публикации не меняется; измените текущий плановый срок";
      }
    }
    if (Object.keys(all).length) throw validationError(all);
    next.revision = rec.revision + 1;
    next.updated_at = nowIso();
    store(next);
    addHistory(next, "update", changed, reason.value, actor.username, next.publication === "published");
    return next;
  }

  function transition(id, body, actor, action) {
    const rec = getRec(id);
    const reason = readReason(body.reason);
    const fields = {};
    if (reason.error || !reason.value) fields.reason = reason.error || "Укажите причину";
    checkRevision(rec, body.expected_revision, fields);
    const from = action === "publish" ? ["draft"] : ["draft", "published"];
    if (!from.includes(rec.publication)) {
      throw new ApiError(409, "invalid_transition", "Переход недоступен из текущего состояния публикации");
    }
    const next = structuredClone(rec);
    next.publication = action === "publish" ? "published" : "archived";
    next.revision = rec.revision + 1;
    next.updated_at = nowIso();
    if (action === "publish" && !next.first_published_at) next.first_published_at = next.updated_at;
    store(next);
    const isPublic = action === "publish" || rec.publication === "published";
    addHistory(next, action, ["publication"], reason.value, actor.username, isPublic);
    return next;
  }

  function listPage(records, cursor) {
    const rows = records
      .map((r) => ({ r, k: [Date.parse(r.updated_at), writeSeq.get(r.id)] }))
      .sort((a, b) => b.k[0] - a.k[0] || b.k[1] - a.k[1]);
    let start = 0;
    if (cursor) {
      const m = /^(\d+)\.(\d+)$/.exec(Buffer.from(cursor, "base64url").toString());
      if (!m) throw new ApiError(400, "bad_request", "Некорректный cursor");
      const c = [Number(m[1]), Number(m[2])];
      start = rows.findIndex((x) => x.k[0] < c[0] || (x.k[0] === c[0] && x.k[1] < c[1]));
      if (start < 0) start = rows.length;
    }
    const page = rows.slice(start, start + pageSize);
    const more = start + pageSize < rows.length;
    const last = page[page.length - 1];
    return {
      records: page.map((x) => x.r),
      next_cursor: more ? Buffer.from(`${last.k[0]}.${last.k[1]}`).toString("base64url") : null,
    };
  }

  function enumParam(query, name, allowed) {
    const v = query.get(name);
    if (!v) return null;
    if (!allowed.includes(v)) throw new ApiError(400, "bad_request", `Недопустимое значение параметра ${name}`);
    return v;
  }

  function publicList(query) {
    const kind = enumParam(query, "kind", ENUMS.kind);
    const status = enumParam(query, "status", ENUMS.status);
    const [from, to] = ["from", "to"].map((n) => {
      const v = query.get(n);
      if (v && !isDate(v)) throw new ApiError(400, "bad_request", `Параметр ${n}: дата ГГГГ-ММ-ДД`);
      return v || null;
    });
    if (from && to && from > to) throw new ApiError(400, "bad_request", "Параметр from позже to");
    const matchDates = (r) => {
      if (!from && !to) return true;
      const s = r.schedule.planned_start;
      const e = r.schedule.current_planned_end;
      if (!s && !e) return false; // unknown interval never matches a date filter
      return (!from || !e || e >= from) && (!to || !s || s <= to);
    };
    const recs = [...state.objects.values()].filter((r) =>
      r.publication === "published" && (!kind || r.kind === kind) &&
      (!status || r.status === status) && matchDates(r));
    const page = listPage(recs, query.get("cursor"));
    return { items: page.records.map(publicDTO), next_cursor: page.next_cursor };
  }

  function publicGet(id) {
    const rec = state.objects.get(id);
    // Same response for unknown, draft and archived.
    if (!rec || rec.publication !== "published") throw new ApiError(404, "not_found", "Объект не найден");
    const history = state.history
      .filter((h) => h.object_id === id && h.public)
      .map(publicHistoryEntry)
      .filter((h) => h.changed_fields.length)
      .reverse();
    return { item: publicDTO(rec), history };
  }

  function staffList(query) {
    const publication = enumParam(query, "publication", ENUMS.publication);
    const recs = [...state.objects.values()].filter((r) => !publication || r.publication === publication);
    const page = listPage(recs, query.get("cursor"));
    return { items: page.records.map(staffDTO), next_cursor: page.next_cursor };
  }

  function staffGet(id) {
    const rec = getRec(id);
    const history = state.history.filter((h) => h.object_id === id).map(staffHistoryEntry).reverse();
    return { item: staffDTO(rec), history };
  }

  // ----- session / auth -----

  const sessionView = (s) => s
    ? { authenticated: true, user: { name: s.user.name, role: s.user.role }, csrf_token: s.csrf }
    : { authenticated: false, user: null, csrf_token: null };
  const sessionCookie = (sid) => `${COOKIE}=${sid}; HttpOnly; SameSite=Strict; Path=/`;
  const clearCookie = () => `${COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0`;

  function originOk(req) {
    const o = req.headers.origin;
    if (o === undefined) return true;
    return o === `http://127.0.0.1:${port}` || o === `http://localhost:${port}`;
  }

  function requireSession(req, session, { mutation, role }) {
    if (!session) throw new ApiError(401, "unauthenticated", "Требуется вход");
    if (mutation) {
      const token = req.headers["x-csrf-token"];
      if (typeof token !== "string" || !safeEqual(token, session.csrf)) {
        throw new ApiError(403, "csrf", "Недействительный CSRF-токен");
      }
      if (!originOk(req)) throw new ApiError(403, "origin", "Запрос с другого источника отклонён");
    }
    if (role && session.user.role !== role) throw new ApiError(403, "forbidden", "Недостаточно прав");
  }

  function login(req, body, oldSid) {
    if (!originOk(req)) throw new ApiError(403, "origin", "Запрос с другого источника отклонён");
    const { username, password } = body;
    const fields = {};
    if (typeof username !== "string" || !username) fields.username = "Укажите имя пользователя";
    if (typeof password !== "string" || !password) fields.password = "Укажите пароль";
    if (Object.keys(fields).length) throw validationError(fields);
    const nowMs = clock().getTime();
    let f = loginFailures.get(username);
    if (f && nowMs - f.last >= LOCKOUT_MS) { loginFailures.delete(username); f = undefined; }
    if (f && f.count >= MAX_LOGIN_FAILURES) {
      throw new ApiError(429, "rate_limited", "Слишком много попыток входа; повторите позже");
    }
    const user = users.find((u) => u.username === username);
    const ok = safeEqual(password, user ? user.password : crypto.randomUUID()) && !!user;
    if (!ok) {
      loginFailures.set(username, { count: (f ? f.count : 0) + 1, last: nowMs });
      throw new ApiError(401, "invalid_credentials", "Неверное имя пользователя или пароль");
    }
    loginFailures.delete(username);
    if (oldSid) state.sessions.delete(oldSid);
    const sid = crypto.randomBytes(32).toString("base64url");
    const session = {
      csrf: crypto.randomBytes(32).toString("base64url"),
      user: { username: user.username, name: user.name, role: user.role },
      created_at: nowIso(),
    };
    state.sessions.set(sid, session);
    return { data: sessionView(session), headers: { "Set-Cookie": sessionCookie(sid) } };
  }

  // ----- HTTP plumbing -----

  function route(sub) {
    let m;
    if (sub === "/session") return { GET: "session" };
    if (sub === "/session/login") return { POST: "login" };
    if (sub === "/session/logout") return { POST: "logout" };
    if (sub === "/objects") return { GET: "publicList" };
    if ((m = /^\/objects\/([^/]+)$/.exec(sub))) return { GET: "publicGet", id: m[1] };
    if (sub === "/staff/objects") return { GET: "staffList", POST: "create" };
    if ((m = /^\/staff\/objects\/([^/]+)$/.exec(sub))) return { GET: "staffGet", id: m[1] };
    if ((m = /^\/staff\/objects\/([^/]+)\/(update|publish|archive)$/.exec(sub))) return { POST: m[2], id: m[1] };
    return null;
  }

  function parseJson(raw) {
    if (!raw.length) return {};
    let v;
    try { v = JSON.parse(raw.toString("utf8")); } catch {
      throw new ApiError(400, "bad_json", "Тело запроса не является корректным JSON");
    }
    if (!isPlainObject(v)) throw new ApiError(400, "bad_request", "Ожидается JSON-объект");
    return v;
  }

  function jsonResponse(status, payload, headers) {
    return {
      status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        ...headers,
      },
      body: JSON.stringify(payload),
    };
  }

  function handleApi(req, rawPath, query, raw) {
    try {
      if (raw === null) throw new ApiError(413, "too_large", "Тело запроса слишком большое");
      const r = rawPath.startsWith(API + "/") ? route(rawPath.slice(API.length)) : null;
      if (!r) throw new ApiError(404, "not_found", "Неизвестный путь API");
      const action = r[req.method];
      if (!action) {
        const allow = ["GET", "POST"].filter((m) => r[m]).join(", ");
        throw new ApiError(405, "method_not_allowed", "Метод не поддерживается", { allow });
      }
      let id = null;
      if (r.id !== undefined) {
        try { id = decodeURIComponent(r.id); } catch { throw new ApiError(404, "not_found", "Объект не найден"); }
      }
      const sid = parseCookies(req.headers.cookie)[COOKIE];
      const session = sid ? state.sessions.get(sid) : undefined;
      const editorRead = { mutation: false, role: "editor" };
      const editorWrite = { mutation: true, role: "editor" };
      let data;
      let headers;
      switch (action) {
        case "session": data = sessionView(session); break;
        case "login": ({ data, headers } = login(req, parseJson(raw), sid)); break;
        case "logout":
          if (session) {
            requireSession(req, session, { mutation: true });
            state.sessions.delete(sid);
          }
          data = sessionView(null);
          headers = { "Set-Cookie": clearCookie() };
          break;
        case "publicList": data = publicList(query); break;
        case "publicGet": data = publicGet(id); break;
        case "staffList": requireSession(req, session, editorRead); data = staffList(query); break;
        case "staffGet": requireSession(req, session, editorRead); data = staffGet(id); break;
        case "create":
          requireSession(req, session, editorWrite);
          data = { item: staffDTO(createObject(parseJson(raw), session.user)) };
          break;
        case "update":
          requireSession(req, session, editorWrite);
          data = { item: staffDTO(updateObject(id, parseJson(raw), session.user)) };
          break;
        case "publish":
        case "archive":
          requireSession(req, session, editorWrite);
          data = { item: staffDTO(transition(id, parseJson(raw), session.user, action)) };
          break;
      }
      return jsonResponse(200, { ok: true, data }, headers);
    } catch (e) {
      if (e instanceof ApiError) {
        const { allow, ...extra } = e.extra;
        const error = { code: e.code, message: e.message, ...extra };
        return jsonResponse(e.status, { ok: false, error }, allow ? { Allow: allow } : undefined);
      }
      errors.push(e);
      return jsonResponse(500, { ok: false, error: { code: "internal", message: "Внутренняя ошибка mock-сервера" } });
    }
  }

  const plain = (status, text) => ({
    status, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" }, body: text,
  });

  function resolveInDirs(rawPath) {
    for (const { prefix, dir } of staticDirs) {
      if (!rawPath.startsWith(prefix)) continue;
      let rel;
      try { rel = decodeURIComponent(rawPath.slice(prefix.length)); } catch { return null; }
      if (rel === "" || rel.endsWith("/")) rel += "index.html";
      if (rel.includes("\0") || rel.includes("\\") || rel.split("/").includes("..")) return null;
      const full = path.resolve(dir, rel);
      if (!full.startsWith(dir + path.sep)) return null;
      try {
        const real = fs.realpathSync(full);
        if (!real.startsWith(fs.realpathSync(dir) + path.sep) || !fs.statSync(real).isFile()) return null;
        return real;
      } catch {
        return null;
      }
    }
    return null;
  }

  async function serveStatic(req, rawPath) {
    if (req.method !== "GET" && req.method !== "HEAD") return plain(405, "Method Not Allowed");
    const file = Object.prototype.hasOwnProperty.call(staticMap, rawPath)
      ? staticMap[rawPath] : resolveInDirs(rawPath);
    if (!file) return plain(404, "Not Found");
    try {
      const body = await fs.promises.readFile(file);
      const type = MIME[path.extname(file).toLowerCase()] || "application/octet-stream";
      return { status: 200, headers: { "Content-Type": type, "Cache-Control": "no-store" }, body };
    } catch {
      return plain(404, "Not Found");
    }
  }

  function readBody(req) {
    return new Promise((resolve, reject) => {
      const chunks = [];
      let size = 0;
      let tooBig = Number(req.headers["content-length"]) > maxBody;
      // Drain everything so the client always receives the 413 instead of a reset.
      req.on("data", (c) => {
        size += c.length;
        if (size > maxBody) { tooBig = true; chunks.length = 0; } else if (!tooBig) chunks.push(c);
      });
      req.on("end", () => resolve(tooBig ? null : Buffer.concat(chunks)));
      req.on("error", reject);
    });
  }

  function sleep(ms) {
    return new Promise((resolve) => {
      const t = setTimeout(() => { timers.delete(t); resolve(); }, ms);
      timers.add(t);
    });
  }

  function takeFault(method, rawPath) {
    const i = faults.findIndex((f) =>
      (!f.method || f.method === method) &&
      (rawPath.startsWith(f.pathPrefix) ||
        (rawPath.startsWith(API + "/") && rawPath.slice(API.length).startsWith(f.pathPrefix))));
    return i < 0 ? null : faults.splice(i, 1)[0];
  }

  // Returns true when the fault replaced the normal response.
  function breakResponse(fault, req, res, log) {
    if (log) { log.fault = fault.mode; }
    if (fault.mode === "drop") {
      if (log) log.status = 0;
      req.socket.destroy();
      return;
    }
    if (log) log.status = 500;
    res.writeHead(500, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" });
    res.end("<!doctype html><html><head><title>500 Internal Server Error</title></head>" +
      "<body><h1>Internal Server Error</h1><pre>Traceback (most recent call last): injected by mock</pre></body></html>");
  }

  async function onRequest(req, res) {
    const rawUrl = req.url || "/";
    const qi = rawUrl.indexOf("?");
    const rawPath = qi < 0 ? rawUrl : rawUrl.slice(0, qi);
    const query = new URLSearchParams(qi < 0 ? "" : rawUrl.slice(qi + 1));
    const isApi = rawPath === "/api" || rawPath.startsWith("/api/");
    const fault = takeFault(req.method, rawPath);
    const log = isApi ? {
      method: req.method, path: rawPath,
      apiPath: rawPath.startsWith(API) ? rawPath.slice(API.length) : null,
      search: qi < 0 ? "" : rawUrl.slice(qi), status: null, at: nowIso(),
    } : null;
    if (log) requests.push(log);
    try {
      const raw = await readBody(req);
      if (fault && !fault.afterCommit) {
        if (fault.delay === undefined) return breakResponse(fault, req, res, log);
        await sleep(fault.delay);
      }
      const out = isApi ? handleApi(req, rawPath, query, raw) : await serveStatic(req, rawPath);
      if (fault && fault.afterCommit) {
        if (fault.delay === undefined) return breakResponse(fault, req, res, log);
        await sleep(fault.delay);
      }
      if (log) log.status = out.status;
      if (res.destroyed) return;
      res.writeHead(out.status, out.headers);
      res.end(req.method === "HEAD" ? undefined : out.body);
    } catch (e) {
      errors.push(e);
      if (log) log.status = 500;
      if (!res.headersSent && !res.destroyed) {
        const out = jsonResponse(500, { ok: false, error: { code: "internal", message: "Внутренняя ошибка mock-сервера" } });
        res.writeHead(out.status, out.headers);
        res.end(out.body);
      }
    }
  }

  function loadSeed() {
    for (const s of opts.seed || []) {
      const { next, fields } = applyChanges(blankObject(), s, "create");
      const all = { ...validateObject(next), ...fields };
      if (s.publication !== undefined && !ENUMS.publication.includes(s.publication)) all.publication = "Недопустимое значение";
      if (s.updated_at !== undefined && Number.isNaN(Date.parse(s.updated_at))) all.updated_at = "Недопустимая дата";
      if (s.id !== undefined && (typeof s.id !== "string" || !s.id || state.objects.has(s.id))) all.id = "Пустой или повторяющийся id";
      if (Object.keys(all).length) throw new Error(`Invalid seed object ${s.id}: ${JSON.stringify(all)}`);
      next.id = s.id || nextObjectId();
      next.revision = Number.isInteger(s.revision) && s.revision >= 1 ? s.revision : 1;
      next.publication = s.publication || "draft";
      next.updated_at = s.updated_at || nowIso();
      next.created_by = s.created_by && typeof s.created_by.name === "string" ? { name: s.created_by.name } : { name: "seed" };
      next.first_published_at = s.first_published_at || (next.publication === "published" ? next.updated_at : null);
      store(next);
      addHistory(next, "create", diffPaths(blankObject(), next), null, "seed", next.publication === "published");
    }
  }

  const hooks = {
    requests,
    errors,
    expireSessions() { state.sessions.clear(); },
    // Concurrent edit by another editor; throws ApiError on validation failure.
    mutate(id, changes, reason = "Другой редактор") {
      const rec = getRec(id);
      const actor = { username: "other-editor", name: "Другой редактор", role: "editor" };
      return staffDTO(updateObject(id, { expected_revision: rec.revision, changes, reason }, actor));
    },
    failNext({ method, pathPrefix = "", mode, afterCommit = false } = {}) {
      const m = /^(drop|html500|delay:(\d+))$/.exec(String(mode));
      if (!m) throw new Error(`failNext: unknown mode ${mode}`);
      faults.push({
        method: method ? String(method).toUpperCase() : null, pathPrefix, mode: m[2] ? "delay" : m[1],
        delay: m[2] ? Number(m[2]) : undefined, afterCommit: !!afterCommit,
      });
    },
    reset() {
      state.objects.clear();
      state.history.length = 0;
      state.sessions.clear();
      requests.length = 0;
      errors.length = 0;
      loginFailures.clear();
      faults.length = 0;
      writeSeq.clear();
      counters = { obj: 0, hist: 0, write: 0 };
      loadSeed();
    },
  };

  loadSeed();
  const server = http.createServer((req, res) => { onRequest(req, res); });

  return {
    hooks,
    state,
    listen(p = 0) {
      return new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(p, "127.0.0.1", () => {
          server.off("error", reject);
          port = server.address().port;
          resolve(`http://127.0.0.1:${port}`);
        });
      });
    },
    close() {
      for (const t of timers) clearTimeout(t);
      timers.clear();
      return new Promise((resolve) => {
        if (!server.listening) return resolve();
        server.close(() => resolve());
        server.closeAllConnections();
      });
    },
  };
}

module.exports = { createMockServer };
