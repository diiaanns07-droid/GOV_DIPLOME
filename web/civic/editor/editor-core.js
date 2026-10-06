/* civic-v1 staff editor (R04, round 11): pure logic without DOM or network.
 * Form model <-> contract object, field validation, "было/станет" diff, reason rules,
 * draft/published/archived action matrix, public preview allowlist, API error normalization.
 * Browser: attaches to window.CivicEditor.core (the only global of this role is CivicEditor).
 * Node tests: require() returns the same object.
 * Client-side checks only help the editor; rights and the final validation belong to the server (R02).
 */
(function (root, factory) {
  "use strict";
  const core = factory();
  if (typeof module === "object" && module.exports) module.exports = core;
  if (root) {
    root.CivicEditor = root.CivicEditor || {};
    root.CivicEditor.core = core;
  }
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  // ---------- contract enums (CONTRACT.txt, civic-v1) ----------
  const KINDS = { construction: "Строительство", roadworks: "Дорожные работы", landscaping: "Благоустройство", event: "Событие / мероприятие" };
  const STATUSES = { planned: "Запланировано", in_progress: "Идут работы", completed: "Завершено", cancelled: "Отменено", unknown: "Статус неизвестен" };
  const PUBLICATION = { draft: "Черновик", published: "Опубликовано", archived: "В архиве" };
  const PRECISION = { approximate: "Приблизительно (указано на карте)", source: "Точно по источнику", unknown: "Точность неизвестна" };
  const BASIS = { unknown: "Неизвестно", planned: "Плановая смета", contract: "Сумма контракта", spent: "Фактически израсходовано" };
  const EVIDENCE = {
    observed: "Наблюдаемо — подтверждено источником",
    derived: "Выведено — рассчитано из источников",
    hypothesis: "Предположение — требует проверки",
    synthetic: "Синтетические — демонстрационные данные",
  };
  const ACCESS = { not_fetched: "Не открывался", fetched: "Открыт и прочитан", unavailable: "Недоступен" };
  // Top-level paths a source can support (contract: source_refs[].fields).
  const SOURCE_FIELDS = { status: "Статус", schedule: "Сроки", geometry: "Место", budget: "Стоимость", responsible: "Ответственный", description: "Описание" };
  // Generous frame around Astana (WGS84 lon/lat). Round 11 covers Astana only.
  const ASTANA_BBOX = [70.9, 50.9, 72.0, 51.4];
  const LIMITS = { title: 200, description: 5000, evidence_notes: 2000, internal_notes: 2000, organization: 200, public_contact: 200,
    reason: 500, url: 2000, publisher: 200, license: 100, maxAmount: 1e13 };
  const REASON_MIN = 5;

  // Public object fields (allowlist). Anything else (internal_notes, created_by, actor, tokens) never reaches the preview.
  const PUBLIC_SHAPE = {
    schema_version: true, id: true, city: true, kind: true, title: true, description: true, status: true, publication: true,
    geometry: "geometry", geometry_precision: true,
    schedule: ["planned_start", "original_planned_end", "current_planned_end", "actual_end"],
    budget: ["amount_kzt", "basis", "source_id"],
    responsible: ["organization", "public_contact"],
    evidence_type: true, source_refs: "sources", evidence_notes: true, updated_at: true, revision: true,
  };
  const SOURCE_KEYS = ["id", "url", "publisher", "published_on", "retrieved_at", "access_status", "license", "fields"];

  // Comparable paths for the diff, in display order, with labels.
  const PATHS = [
    ["title", "Название"], ["kind", "Тип"], ["status", "Статус работ"], ["description", "Описание"],
    ["schedule.planned_start", "Плановое начало"], ["schedule.original_planned_end", "Первоначальный плановый срок окончания"],
    ["schedule.current_planned_end", "Актуальный плановый срок окончания"], ["schedule.actual_end", "Фактически завершено"],
    ["geometry", "Место на карте"], ["geometry_precision", "Точность места"],
    ["responsible.organization", "Ответственная организация"], ["responsible.public_contact", "Публичный контакт"],
    ["budget.amount_kzt", "Стоимость"], ["budget.basis", "Основание суммы"], ["budget.source_id", "Источник суммы"],
    ["evidence_type", "Достоверность"], ["source_refs", "Источники"], ["evidence_notes", "Пояснение к достоверности"],
    ["internal_notes", "Внутренняя заметка (не публикуется)"],
  ];
  const PATH_LABEL = Object.fromEntries(PATHS);
  // Server error path -> form field key (where the error is shown).
  const PATH_TO_FIELD = {
    "schedule.planned_start": "planned_start", "schedule.original_planned_end": "original_planned_end",
    "schedule.current_planned_end": "current_planned_end", "schedule.actual_end": "actual_end",
    "budget.amount_kzt": "amount", "budget.basis": "basis", "budget.source_id": "budget_source_id", budget: "amount",
    "responsible.organization": "organization", "responsible.public_contact": "public_contact",
    schedule: "current_planned_end", responsible: "organization",
  };

  // ---------- small helpers ----------
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const clone = (x) => (x === undefined ? undefined : JSON.parse(JSON.stringify(x)));
  const str = (v) => (v === null || v === undefined ? "" : String(v));
  const blankToNull = (v) => { const s = str(v).trim(); return s === "" ? null : s; };
  const HTML_RE = /<\s*[a-zA-Z!\/?]/;
  const isPlain = (s) => !HTML_RE.test(s);
  const stable = (v) => JSON.stringify(v === undefined ? null : v);

  function isIsoDate(s) {
    if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    const [y, m, d] = s.split("-").map(Number);
    const t = new Date(Date.UTC(y, m - 1, d));
    return t.getUTCFullYear() === y && t.getUTCMonth() === m - 1 && t.getUTCDate() === d;
  }
  // Today in Astana (UTC+5 since 2024; the editor compares calendar dates only).
  function todayIso(now) {
    const t = new Date((now ? now.getTime() : Date.now()) + 5 * 3600 * 1000);
    return t.toISOString().slice(0, 10);
  }
  function fmtDate(s) {
    if (!s) return "неизвестно";
    return isIsoDate(s) ? s.slice(8, 10) + "." + s.slice(5, 7) + "." + s.slice(0, 4) : String(s);
  }
  function fmtMoney(n) {
    if (n === null || n === undefined) return "неизвестно";
    return Number(n).toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " ₸";
  }
  // "1 250 000,50" / "1250000.5" -> number; "" -> null; otherwise NaN.
  function parseAmount(text) {
    const s = str(text).replace(/[\s  ]/g, "");
    if (s === "") return null;
    if (!/^\d+([.,]\d{1,2})?$/.test(s)) return NaN;
    return Number(s.replace(",", "."));
  }
  function parseCoord(text) {
    const s = str(text).trim().replace(",", ".");
    if (s === "" || !/^-?\d+(\.\d+)?$/.test(s)) return NaN;
    return Number(s);
  }
  function inAstana(lon, lat) {
    return lon >= ASTANA_BBOX[0] && lon <= ASTANA_BBOX[2] && lat >= ASTANA_BBOX[1] && lat <= ASTANA_BBOX[3];
  }
  function positionsOf(g) {
    if (!g) return [];
    if (g.type === "Point") return [g.coordinates];
    if (g.type === "LineString") return g.coordinates || [];
    if (g.type === "Polygon") return (g.coordinates || []).flat();
    return [];
  }

  // ---------- form model ----------
  function emptyForm() {
    return {
      title: "", kind: "", status: "unknown", description: "",
      planned_start: "", original_planned_end: "", current_planned_end: "", actual_end: "",
      geometry: null, geometry_confirmed: false, geometry_precision: "unknown",
      organization: "", public_contact: "",
      amount: "", basis: "unknown", budget_source_id: "",
      evidence_type: "", evidence_notes: "", internal_notes: "",
      sources: [],
    };
  }
  function formFromItem(item) {
    const f = emptyForm();
    if (!item) return f;
    const sc = item.schedule || {}, b = item.budget || {}, r = item.responsible || {};
    Object.assign(f, {
      title: str(item.title), kind: str(item.kind), status: str(item.status) || "unknown", description: str(item.description),
      planned_start: str(sc.planned_start), original_planned_end: str(sc.original_planned_end),
      current_planned_end: str(sc.current_planned_end), actual_end: str(sc.actual_end),
      geometry: clone(item.geometry || null), geometry_confirmed: !!item.geometry, geometry_precision: str(item.geometry_precision) || "unknown",
      organization: str(r.organization), public_contact: str(r.public_contact),
      amount: b.amount_kzt === null || b.amount_kzt === undefined ? "" : String(b.amount_kzt).replace(".", ","),
      basis: str(b.basis) || "unknown", budget_source_id: str(b.source_id),
      evidence_type: str(item.evidence_type), evidence_notes: str(item.evidence_notes), internal_notes: str(item.internal_notes),
      sources: (item.source_refs || []).map((s) => ({
        id: str(s.id), url: str(s.url), publisher: str(s.publisher), published_on: str(s.published_on),
        retrieved_at: str(s.retrieved_at).slice(0, 10), access_status: str(s.access_status) || "not_fetched",
        license: str(s.license), fields: Array.isArray(s.fields) ? s.fields.slice() : [],
      })),
    });
    return f;
  }
  function nextSourceId(sources) {
    let n = 1;
    const ids = new Set(sources.map((s) => s.id));
    while (ids.has("src-" + n)) n++;
    return "src-" + n;
  }
  function newSource(sources) {
    return { id: nextSourceId(sources || []), url: "", publisher: "", published_on: "", retrieved_at: "", access_status: "not_fetched", license: "", fields: [] };
  }

  // Contract fields from the form. Unknown stays null: no 0 amount, no "today" dates, no invented precision.
  function fieldsFromForm(form, opts) {
    const o = opts || {};
    const amount = parseAmount(form.amount);
    const geometry = form.geometry ? clone(form.geometry) : null;
    const out = {
      title: str(form.title).trim(),
      description: str(form.description).trim(),
      kind: form.kind || null,
      status: form.status || "unknown",
      geometry,
      geometry_precision: geometry ? form.geometry_precision || "unknown" : "unknown",
      schedule: {
        planned_start: blankToNull(form.planned_start), original_planned_end: blankToNull(form.original_planned_end),
        current_planned_end: blankToNull(form.current_planned_end), actual_end: blankToNull(form.actual_end),
      },
      budget: {
        amount_kzt: amount === null || Number.isNaN(amount) ? null : amount,
        basis: form.basis || "unknown",
        source_id: blankToNull(form.budget_source_id),
      },
      responsible: { organization: blankToNull(form.organization), public_contact: blankToNull(form.public_contact) },
      evidence_type: form.evidence_type || null,
      source_refs: (form.sources || []).map((s) => ({
        id: s.id, url: str(s.url).trim(), publisher: blankToNull(s.publisher), published_on: blankToNull(s.published_on),
        retrieved_at: blankToNull(s.retrieved_at), access_status: s.access_status || "not_fetched",
        license: blankToNull(s.license), fields: (s.fields || []).slice(),
      })),
      evidence_notes: str(form.evidence_notes).trim(),
    };
    if (o.internalNotes) out.internal_notes = blankToNull(form.internal_notes);
    return out;
  }

  // ---------- validation ----------
  // ctx: {today:"YYYY-MM-DD", item: server item|null}
  // Returns {errors:{fieldKey:msg}, warnings:{fieldKey:msg}}; keys match form inputs so the message sits next to its field.
  function validateForm(form, ctx) {
    const c = ctx || {};
    const today = c.today || todayIso();
    const item = c.item || null;
    const locked = isOriginalLocked(item);
    const errors = {}, warnings = {};
    const err = (k, m) => { if (!errors[k]) errors[k] = m; };
    const text = (k, max, required) => {
      const v = str(form[k]).trim();
      if (required && !v) return err(k, "Обязательное поле.");
      if (v.length > max) return err(k, "Слишком длинно: " + v.length + " из " + max + " символов.");
      if (v && !isPlain(v)) err(k, "Только обычный текст, без HTML-разметки.");
    };
    text("title", LIMITS.title, true);
    text("description", LIMITS.description, false);
    text("organization", LIMITS.organization, false);
    text("public_contact", LIMITS.public_contact, false);
    text("evidence_notes", LIMITS.evidence_notes, false);
    text("internal_notes", LIMITS.internal_notes, false);
    if (!has(KINDS, form.kind)) err("kind", "Выберите тип объекта.");
    if (!has(STATUSES, form.status)) err("status", "Выберите статус работ (или «Статус неизвестен»).");

    // dates: empty = unknown; never replaced by today
    const D = ["planned_start", "original_planned_end", "current_planned_end", "actual_end"];
    for (const k of D) {
      const v = str(form[k]).trim();
      if (!v) continue;
      if (!isIsoDate(v)) err(k, "Дата в формате ГГГГ-ММ-ДД, например 2026-10-14.");
      else if (v < "1990-01-01" || v > "2100-12-31") err(k, "Проверьте год.");
    }
    const ds = (k) => (errors[k] ? "" : str(form[k]).trim());
    const ps = ds("planned_start"), oe = ds("original_planned_end"), ce = ds("current_planned_end"), ae = ds("actual_end");
    if (ps && oe && oe < ps) err("original_planned_end", "Окончание раньше планового начала (" + fmtDate(ps) + ").");
    if (ps && ce && ce < ps) err("current_planned_end", "Окончание раньше планового начала (" + fmtDate(ps) + ").");
    if (ae) {
      if (form.status !== "completed") err("actual_end", "Дата фактического завершения указывается только при статусе «Завершено». Иначе оставьте пустым.");
      else if (ae > today) err("actual_end", "Фактическое завершение не может быть в будущем.");
      else if (ps && ae < ps) warnings.actual_end = "Завершено раньше планового начала — проверьте даты.";
    } else if (form.status === "completed") {
      warnings.actual_end = "Дата фактического завершения неизвестна — жители увидят «неизвестно».";
    }
    if (locked) {
      const was = str(item && item.schedule && item.schedule.original_planned_end);
      if (str(form.original_planned_end).trim() !== was) err("original_planned_end", "Первоначальный срок зафиксирован при первой публикации и не меняется. Меняйте актуальный срок.");
    }
    if (oe && !ce && !errors.original_planned_end) warnings.current_planned_end = "Актуальный срок пуст — жители увидят «неизвестно».";

    // place
    const g = form.geometry;
    if (g) {
      const pos = positionsOf(g);
      const bad = pos.some((p) => !Array.isArray(p) || p.length < 2 || !Number.isFinite(p[0]) || !Number.isFinite(p[1]) || Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90);
      if (!pos.length || bad) err("geometry", "Координаты некорректны: долгота −180…180, широта −90…90.");
      else if (pos.some((p) => !inAstana(p[0], p[1]))) err("geometry", "Точка за пределами Астаны. Проверьте порядок: долгота ≈ 71.4, широта ≈ 51.1.");
      else if (g.type === "LineString" && (pos.length < 2 || new Set(pos.map((p) => p[0] + "," + p[1])).size < 2)) err("geometry", "Участок работ — минимум две разные точки.");
      else if (!form.geometry_confirmed) err("geometry", "Подтвердите расположение или удалите место. Без достоверного места запись можно сохранить без координат.");
      if (!has(PRECISION, form.geometry_precision)) err("geometry_precision", "Выберите точность места.");
      else if (form.geometry_precision === "source" && !(form.sources || []).some((s) => (s.fields || []).includes("geometry")))
        err("geometry_precision", "«Точно по источнику» требует источник, у которого отмечено «Место».");
    }

    // money: unknown is empty, never 0
    const amount = parseAmount(form.amount);
    const sourceIds = new Set((form.sources || []).map((s) => s.id));
    if (Number.isNaN(amount)) err("amount", "Только число в тенге, например 125 000 000 или 1 250,50.");
    else if (amount !== null) {
      if (amount > LIMITS.maxAmount) err("amount", "Проверьте сумму: слишком большое число.");
      if (form.basis === "unknown" || !has(BASIS, form.basis)) err("basis", "Укажите, что означает сумма: смета, контракт или израсходовано.");
      if (!form.budget_source_id) err("budget_source_id", "Сумма без источника не сохраняется. Добавьте источник ниже или оставьте сумму пустой — будет «неизвестно».");
      if (amount === 0 && !errors.amount) warnings.amount = "Будет показано «0 ₸», а не «неизвестно». Если сумма неизвестна — оставьте поле пустым.";
    } else if (form.basis && form.basis !== "unknown") {
      err("amount", "Основание выбрано, а сумма пуста. Введите сумму или выберите «Неизвестно».");
    }
    if (form.budget_source_id && !sourceIds.has(form.budget_source_id)) err("budget_source_id", "Источник не найден в списке источников.");

    // provenance
    if (!has(EVIDENCE, form.evidence_type)) err("evidence_type", "Выберите, насколько сведения подтверждены.");
    else if (form.evidence_type === "observed" && !(form.sources || []).length) err("evidence_type", "«Наблюдаемо» требует хотя бы один источник. Иначе выберите «Предположение».");
    (form.sources || []).forEach((s, i) => {
      const k = (f) => "sources." + i + "." + f;
      const url = str(s.url).trim();
      if (!url) err(k("url"), "Укажите адрес источника.");
      else if (url.length > LIMITS.url) err(k("url"), "Слишком длинный адрес.");
      else {
        let u = null;
        try { u = new URL(url); } catch (e) { u = null; }
        if (!u || (u.protocol !== "https:" && u.protocol !== "http:")) err(k("url"), "Адрес должен начинаться с https:// или http://.");
      }
      for (const f of ["published_on", "retrieved_at"]) {
        const v = str(s[f]).trim();
        if (v && !isIsoDate(v)) err(k(f), "Дата в формате ГГГГ-ММ-ДД.");
        else if (v && v > today) err(k(f), "Дата не может быть в будущем.");
      }
      if (!has(ACCESS, s.access_status)) err(k("access_status"), "Выберите состояние доступа.");
      if (str(s.publisher).length > LIMITS.publisher) err(k("publisher"), "Слишком длинно.");
      if (str(s.license).length > LIMITS.license) err(k("license"), "Слишком длинно.");
      if (s.publisher && !isPlain(str(s.publisher))) err(k("publisher"), "Только обычный текст.");
      if ((s.fields || []).some((f) => !has(SOURCE_FIELDS, f))) err(k("fields"), "Неизвестное поле источника.");
      if (s.access_status === "unavailable" && (s.fields || []).length) warnings[k("fields")] = "Недоступный источник не подтверждает отмеченные поля — жители увидят, что он недоступен.";
    });
    return { errors, warnings };
  }

  function validateReason(text) {
    const v = str(text).trim();
    if (v.length < REASON_MIN) return "Опишите причину изменения (минимум " + REASON_MIN + " символов). Её увидят в истории.";
    if (v.length > LIMITS.reason) return "Слишком длинно: " + v.length + " из " + LIMITS.reason + " символов.";
    if (!isPlain(v)) return "Только обычный текст, без HTML-разметки.";
    return null;
  }

  // ---------- state matrix ----------
  // UI affordances only: the server decides. Session role is displayed, never used as a source of rights.
  const MATRIX = {
    draft: { edit: true, publish: true, archive: true, editNeedsReason: false },
    published: { edit: true, publish: false, archive: true, editNeedsReason: true },
    archived: { edit: false, publish: false, archive: false, editNeedsReason: true },
  };
  // Two server models fit civic-v1: edits of a published record are public at once ("live"), or they stay
  // pending until published again ("pending", R02: item.staff.has_unpublished_changes / public_item).
  function pendingInfo(item) {
    const st = item && item.staff && typeof item.staff === "object" ? item.staff : null;
    if (!st || typeof st.has_unpublished_changes !== "boolean") return { known: false, pending: false, publicItem: null };
    return { known: true, pending: item.publication === "published" && st.has_unpublished_changes,
      publicItem: st.public_item && typeof st.public_item === "object" ? st.public_item : null };
  }
  function allowedActions(item, session) {
    const none = { create: false, edit: false, publish: false, archive: false, preview: false, editNeedsReason: false };
    if (!session || !session.authenticated) return none;
    if (!item) return { create: true, edit: true, publish: false, archive: false, preview: true, editNeedsReason: false };
    const m = MATRIX[item.publication];
    if (!m) return Object.assign({}, none, { preview: true });
    const out = Object.assign({ create: true, preview: true }, m);
    if (item.publication === "published" && pendingInfo(item).pending) out.publish = true;  // publish the pending edits
    return out;
  }
  // The server flag wins when present (an archived record that was never published is not locked);
  // otherwise any non-draft is treated as published once, which is the safe side.
  function isOriginalLocked(item) {
    if (!item) return false;
    if (item.staff && typeof item.staff.original_planned_end_locked === "boolean") return item.staff.original_planned_end_locked;
    return item.publication !== "draft";
  }
  function reasonRule(item, action) {
    if (action === "publish" && item && item.publication === "published")
      return { required: true, title: "Причина публикации изменений", suggestions: ["Перенос срока", "Уточнение по источнику", "Исправление ошибки ввода"] };
    if (action === "publish") return { required: true, title: "Причина публикации", suggestions: ["Первая публикация", "Сведения проверены по источнику"] };
    if (action === "archive") return { required: true, title: "Причина переноса в архив", suggestions: ["Работы завершены, запись больше не актуальна", "Запись создана по ошибке", "Дубликат другой записи"] };
    if (action === "update" && item && item.publication !== "draft")
      return { required: true, title: "Причина изменения опубликованной записи", suggestions: ["Перенос срока", "Уточнение по источнику", "Исправление ошибки ввода", "Работы завершены"] };
    return { required: false, title: "", suggestions: [] };
  }

  // ---------- diff ----------
  function getPath(obj, path) {
    return path.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), obj);
  }
  function diffFields(before, after) {
    const out = [];
    for (const [path] of PATHS) {
      const a = getPath(after, path);
      if (a === undefined) continue;  // field not edited by this form (e.g. internal_notes unsupported)
      const b = getPath(before || {}, path);
      const norm = (v) => (v === undefined ? null : v);
      if (stable(norm(b)) !== stable(norm(a))) out.push({ path, label: PATH_LABEL[path], before: norm(b), after: norm(a) });
    }
    return out;
  }
  // Update body: top-level changed keys only, nested objects sent whole (unchanged original_planned_end included as is).
  function buildChanges(item, fields) {
    const changes = {};
    for (const d of diffFields(item, fields)) {
      const top = d.path.split(".")[0];
      changes[top] = clone(fields[top]);
    }
    return changes;
  }
  function fmtValue(path, v) {
    if (v === null || v === undefined || v === "") {
      if (path === "geometry") return "без места на карте";
      if (path === "source_refs") return "нет";
      if (path === "description" || path === "evidence_notes" || path === "internal_notes") return "пусто";
      return "неизвестно";
    }
    if (path.startsWith("schedule.")) return fmtDate(v);
    if (path === "budget.amount_kzt") return fmtMoney(v);
    if (path === "kind") return KINDS[v] || v;
    if (path === "status") return STATUSES[v] || v;
    if (path === "geometry_precision") return PRECISION[v] || v;
    if (path === "budget.basis") return BASIS[v] || v;
    if (path === "evidence_type") return EVIDENCE[v] || v;
    if (path === "geometry") {
      const p = positionsOf(v);
      if (v.type === "Point") return "точка " + p[0][1].toFixed(5) + ", " + p[0][0].toFixed(5);
      return (v.type === "LineString" ? "участок, точек: " : "контур, точек: ") + p.length;
    }
    if (path === "source_refs") return v.length + " " + (v.length === 1 ? "источник" : v.length >= 2 && v.length <= 4 ? "источника" : "источников");
    return String(v);
  }

  // ---------- public projection ----------
  function pickPublic(item) {
    const out = {};
    if (!item || typeof item !== "object") return out;
    for (const [k, shape] of Object.entries(PUBLIC_SHAPE)) {
      if (!has(item, k)) continue;
      const v = item[k];
      if (shape === true) out[k] = clone(v);
      else if (shape === "geometry") out[k] = v ? { type: v.type, coordinates: clone(v.coordinates) } : null;
      else if (shape === "sources") out[k] = Array.isArray(v) ? v.map((s) => Object.fromEntries(SOURCE_KEYS.filter((x) => s && has(s, x)).map((x) => [x, clone(s[x])]))) : [];
      else if (Array.isArray(shape)) out[k] = v && typeof v === "object" ? Object.fromEntries(shape.filter((x) => has(v, x)).map((x) => [x, clone(v[x])])) : v === null ? null : undefined;
    }
    return out;
  }
  // "Станет": the server item with the form's contract fields applied. Server keeps id/revision/updated_at/publication.
  function previewFromForm(item, form, opts) {
    const fields = fieldsFromForm(form, { internalNotes: false });
    const base = item ? clone(item) : { schema_version: "civic-v1", id: null, city: "astana", publication: "draft", revision: null, updated_at: null };
    return pickPublic(Object.assign(base, fields, opts && opts.publication ? { publication: opts.publication } : {}));
  }
  function scheduleShift(schedule) {
    const s = schedule || {};
    if (s.original_planned_end && s.current_planned_end && s.original_planned_end !== s.current_planned_end)
      return { from: s.original_planned_end, to: s.current_planned_end, later: s.current_planned_end > s.original_planned_end };
    return null;
  }

  // ---------- API results and errors ----------
  // api.request resolves with data (R01). Tolerate a raw envelope too, and turn {ok:false} into a thrown error.
  function unwrap(result) {
    if (result && typeof result === "object" && result.ok === false && result.error) {
      const e = new Error(result.error.message || "Ошибка сервера");
      Object.assign(e, { code: result.error.code, fields: result.error.fields, status: result.status || result.error.status });
      throw e;
    }
    if (result && typeof result === "object" && result.ok === true && has(result, "data")) return result.data;
    return result;
  }
  function fieldKeyFromPath(path) {
    const p = String(path).replace(/\[(\d+)\]/g, ".$1");
    if (has(PATH_TO_FIELD, p)) return PATH_TO_FIELD[p];
    const m = /^source_refs\.(\d+)\.(\w+)/.exec(p);
    if (m) return "sources." + m[1] + "." + m[2];
    if (p.startsWith("geometry")) return p === "geometry_precision" ? "geometry_precision" : "geometry";
    if (p.startsWith("source_refs")) return "sources";
    const top = p.split(".")[0];
    return ["title", "kind", "status", "description", "evidence_type", "evidence_notes", "internal_notes", "reason", "expected_revision"].includes(top) ? top : "_form";
  }
  const KIND_TEXT = {
    network: "Нет связи с сервером. Введённый текст сохранён в форме — повторите, когда связь восстановится.",
    auth: "Сессия истекла или вы вышли. Войдите снова — введённый текст сохранён в форме.",
    csrf: "Сервер отклонил запрос как небезопасный (проверка CSRF/Origin). Обновите сессию входом и повторите.",
    forbidden: "Недостаточно прав на это действие. Решение принимает сервер.",
    not_found: "Запись не найдена или недоступна.",
    conflict: "Запись уже изменил кто-то другой. Ваши правки не потеряны — сравните версии ниже.",
    transition: "Это действие недоступно для текущего состояния записи.",
    validation: "Сервер нашёл ошибки в полях — они отмечены рядом с полями.",
    too_large: "Слишком большой объём данных для одного сохранения.",
    rate: "Слишком много попыток. Подождите немного и повторите.",
    server: "Ошибка сервера. Текст сохранён в форме — повторите позже.",
    unknown: "Не удалось выполнить действие.",
  };
  function normalizeError(e) {
    const x = e || {};
    const inner = x.error && typeof x.error === "object" ? x.error : {};
    const status = Number(x.status || x.httpStatus || x.statusCode || (x.response && x.response.status) || inner.status || 0) || null;
    const code = x.code || inner.code || null;
    const raw = x.fields || inner.fields || (x.data && x.data.error && x.data.error.fields) || null;
    let kind;
    // status 0/absent: transport failure (R01 CivicApiError codes network/timeout/aborted, raw fetch TypeError).
    if (!status && (["network", "timeout", "aborted"].includes(code) || x.name === "TypeError" || x.name === "AbortError" || /network|failed to fetch|load failed/i.test(String(x.message || "")))) kind = "network";
    else if (status === 401 || code === "unauthenticated") kind = "auth";
    else if (status === 403) kind = code === "csrf" || code === "origin" ? "csrf" : "forbidden";
    else if (status === 404) kind = "not_found";
    else if (status === 409) kind = code === "invalid_transition" ? "transition" : "conflict";
    else if (status === 400 || status === 422) kind = "validation";
    else if (status === 413) kind = "too_large";
    else if (status === 429) kind = "rate";
    else if (status && status >= 500) kind = "server";
    else kind = code === "stale_revision" ? "conflict" : "unknown";
    const fields = {};
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      for (const [p, m] of Object.entries(raw)) { const k = fieldKeyFromPath(p); if (!fields[k]) fields[k] = typeof m === "string" ? m : "Проверьте поле."; }
    } else if (Array.isArray(raw)) {
      for (const it of raw) {
        if (typeof it === "string") { const k = fieldKeyFromPath(it); if (!fields[k]) fields[k] = "Проверьте поле."; }
        else if (it && typeof it === "object") { const k = fieldKeyFromPath(it.field || it.path || "_form"); if (!fields[k]) fields[k] = String(it.message || "Проверьте поле."); }
      }
    }
    const detail = typeof x.message === "string" && x.message && !/^<|<html/i.test(x.message) ? x.message.slice(0, 300) : "";
    return { kind, status, code, fields, text: KIND_TEXT[kind], detail };
  }

  // Three-way merge at form-field level (409 conflict, restoring an in-memory draft over a newer revision).
  // Field edited only by me -> mine; only by the server -> theirs; by both differently -> mine, reported as a conflict.
  function rebaseForm(baseForm, mineForm, latestForm) {
    const base = baseForm || emptyForm(), mine = mineForm, latest = latestForm;
    const out = clone(latest), conflicts = [], theirs = [], kept = [];
    for (const k of Object.keys(mine)) {
      if (k === "geometry_confirmed") continue;
      const b = stable(base[k]), m = stable(mine[k]), l = stable(latest[k]);
      if (m !== b) {
        out[k] = clone(mine[k]);
        kept.push(k);
        if (l !== b && l !== m) conflicts.push(k);
        if (k === "geometry") out.geometry_confirmed = !!mine.geometry_confirmed;
      } else if (l !== b) theirs.push(k);
    }
    return { form: out, conflicts, theirs, kept };
  }
  // Server timestamps shown in Astana time (UTC+5), independent of the browser time zone.
  function fmtDateTime(iso) {
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return iso ? String(iso) : "время неизвестно";
    const d = new Date(t + 5 * 3600 * 1000).toISOString();
    return d.slice(8, 10) + "." + d.slice(5, 7) + "." + d.slice(0, 4) + " " + d.slice(11, 16);
  }

  // After an uncertain create (connection lost), look for the draft the server may already have made.
  function findPossibleDuplicate(items, fields, sinceIso) {
    const since = sinceIso ? Date.parse(sinceIso) : 0;
    return (items || []).find((it) => it && it.publication === "draft" && str(it.title).trim() === str(fields.title).trim() && it.kind === fields.kind
      && (!since || !it.updated_at || Date.parse(it.updated_at) >= since)) || null;
  }

  return {
    KINDS, STATUSES, PUBLICATION, PRECISION, BASIS, EVIDENCE, ACCESS, SOURCE_FIELDS, ASTANA_BBOX, LIMITS, REASON_MIN, PATHS, PATH_LABEL,
    isIsoDate, todayIso, fmtDate, fmtMoney, parseAmount, parseCoord, inAstana, positionsOf,
    emptyForm, formFromItem, newSource, fieldsFromForm, validateForm, validateReason,
    allowedActions, isOriginalLocked, pendingInfo, reasonRule, diffFields, buildChanges, fmtValue,
    pickPublic, previewFromForm, scheduleShift, unwrap, normalizeError, fieldKeyFromPath, findPossibleDuplicate,
    rebaseForm, fmtDateTime,
  };
});
