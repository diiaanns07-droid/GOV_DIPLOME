/* R04 editor core: contract-level checks of web/civic/editor/editor-core.js (civic-v1).
 * Run: node --test tests/civic/R04/
 * fixtures/civic_object.json is a byte copy of research/round-11/fixtures/civic_object.json at PACK_SHA 9c2f5c0d.
 */
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const C = require(path.resolve(__dirname, "../../../web/civic/editor/editor-core.js"));
const FIXTURE = require("./fixtures/civic_object.json");
const TODAY = "2026-10-06";
const clone = (x) => JSON.parse(JSON.stringify(x));
const validForm = (over) => Object.assign(C.emptyForm(), { title: "Ремонт тротуара", kind: "roadworks", evidence_type: "hypothesis" }, over || {});
const check = (form, item) => C.validateForm(form, { today: TODAY, item: item || null });
const withSource = (form, fields) => { const s = C.newSource(form.sources); Object.assign(s, { url: "https://www.gov.kz/x", fields: fields || [] }); form.sources.push(s); return s; };

test("new form: unknown stays unknown (null dates, null amount, no geometry), no server-owned fields", () => {
  const f = C.fieldsFromForm(validForm(), { internalNotes: true });
  assert.deepEqual(f.schedule, { planned_start: null, original_planned_end: null, current_planned_end: null, actual_end: null });
  assert.deepEqual(f.budget, { amount_kzt: null, basis: "unknown", source_id: null });
  assert.equal(f.geometry, null);
  assert.equal(f.geometry_precision, "unknown");
  assert.equal(f.status, "unknown");
  assert.equal(f.internal_notes, null);
  for (const k of ["id", "revision", "publication", "updated_at", "created_by", "actor", "city", "schema_version"]) assert.ok(!(k in f), k + " must be set by the server");
  assert.deepEqual(check(validForm()).errors, {});
});

test("required fields are reported next to their field and the form text is not touched", () => {
  const form = Object.assign(C.emptyForm(), { description: "Текст, который нельзя потерять" });
  const before = clone(form);
  const { errors } = check(form);
  assert.deepEqual(Object.keys(errors).sort(), ["evidence_type", "kind", "title"]);
  assert.deepEqual(form, before);
});

test("plain text only: HTML markup is rejected, not stripped", () => {
  const form = validForm({ title: "<img src=x onerror=alert(1)>Ремонт" });
  assert.match(check(form).errors.title, /HTML/);
  assert.equal(form.title, "<img src=x onerror=alert(1)>Ремонт");
  assert.equal(check(validForm({ title: "Участок 3 < 5 км" })).errors.title, undefined);
});

test("money: empty is null, never 0; an amount needs basis and a listed source", () => {
  assert.equal(C.parseAmount(""), null);
  assert.equal(C.parseAmount("1 250 000,50"), 1250000.5);
  assert.equal(C.parseAmount("1 250 000"), 1250000);
  assert.ok(Number.isNaN(C.parseAmount("-5")));
  assert.ok(Number.isNaN(C.parseAmount("12e3")));
  assert.ok(Number.isNaN(C.parseAmount("Infinity")));
  let form = validForm({ amount: "125 000 000" });
  let e = check(form).errors;
  assert.ok(e.basis && e.budget_source_id, "amount without basis/source must not pass");
  const s = withSource(form, ["budget"]);
  Object.assign(form, { basis: "contract", budget_source_id: s.id });
  assert.deepEqual(check(form).errors, {});
  assert.deepEqual(C.fieldsFromForm(form).budget, { amount_kzt: 125000000, basis: "contract", source_id: s.id });
  form = validForm({ basis: "planned" });
  assert.ok(check(form).errors.amount, "basis without amount");
  form = validForm({ amount: "0", basis: "spent" });
  const s0 = withSource(form, ["budget"]); form.budget_source_id = s0.id;
  const r = check(form);
  assert.deepEqual(r.errors, {});
  assert.match(r.warnings.amount, /0 ₸/);
  form = validForm({ amount: "сто тысяч" });
  assert.ok(check(form).errors.amount);
  assert.equal(C.fieldsFromForm(form).budget.amount_kzt, null, "invalid text never becomes a number");
  form = validForm({ amount: "10", basis: "planned", budget_source_id: "src-9" });
  assert.match(check(form).errors.budget_source_id, /не найден/);
});

test("dates: calendar validity, order, planned vs actual end", () => {
  assert.ok(check(validForm({ planned_start: "2026-02-30" })).errors.planned_start);
  assert.ok(check(validForm({ planned_start: "14.10.2026" })).errors.planned_start);
  assert.ok(check(validForm({ planned_start: "2026-10-14", current_planned_end: "2026-10-01" })).errors.current_planned_end);
  assert.ok(check(validForm({ planned_start: "2026-10-14", original_planned_end: "2026-10-01" })).errors.original_planned_end);
  assert.match(check(validForm({ status: "in_progress", actual_end: "2026-10-01" })).errors.actual_end, /Завершено/);
  assert.match(check(validForm({ status: "completed", actual_end: "2026-10-07" })).errors.actual_end, /будущем/);
  const done = check(validForm({ status: "completed" }));
  assert.deepEqual(done.errors, {});
  assert.match(done.warnings.actual_end, /неизвестна/);
  assert.deepEqual(check(validForm({ status: "completed", actual_end: TODAY })).errors, {});
});

test("original planned end is locked after first publication; the current one moves", () => {
  const item = clone(FIXTURE);
  const form = C.formFromItem(item);
  assert.equal(C.isOriginalLocked(item), true);
  assert.deepEqual(check(form, item).errors, {});
  form.current_planned_end = "2026-11-05";
  assert.deepEqual(check(form, item).errors, {});
  form.original_planned_end = "2026-11-05";
  assert.match(check(form, item).errors.original_planned_end, /зафиксирован/);
  const draft = Object.assign(clone(item), { publication: "draft" });
  assert.equal(C.isOriginalLocked(draft), false);
  assert.deepEqual(check(form, draft).errors, {});
});

test("fixture round trip: opening and saving without edits changes nothing (no silent date/revision change)", () => {
  const item = clone(FIXTURE);
  const fields = C.fieldsFromForm(C.formFromItem(item));
  assert.deepEqual(C.diffFields(item, fields), []);
  assert.deepEqual(C.buildChanges(item, fields), {});
  for (const k of Object.keys(fields)) if (k !== "internal_notes") assert.deepEqual(fields[k], item[k], k);
});

test("changes: only edited top-level fields; schedule goes whole with the unchanged original", () => {
  const item = clone(FIXTURE);
  const form = C.formFromItem(item);
  form.current_planned_end = "2026-11-05";
  const fields = C.fieldsFromForm(form);
  const d = C.diffFields(item, fields);
  assert.deepEqual(d.map((x) => x.path), ["schedule.current_planned_end"]);
  assert.equal(C.fmtValue(d[0].path, d[0].before), "22.10.2026");
  assert.equal(C.fmtValue(d[0].path, d[0].after), "05.11.2026");
  const ch = C.buildChanges(item, fields);
  assert.deepEqual(Object.keys(ch), ["schedule"]);
  assert.equal(ch.schedule.original_planned_end, "2026-10-20");
  assert.ok(!("revision" in ch) && !("publication" in ch));
  assert.deepEqual(C.scheduleShift(fields.schedule), { from: "2026-10-20", to: "2026-11-05", later: true });
});

test("place: confirm before save, Astana only, line needs two points, 'source' precision needs a geometry source", () => {
  const pt = { type: "Point", coordinates: [71.43, 51.13] };
  assert.match(check(validForm({ geometry: pt, geometry_precision: "approximate" })).errors.geometry, /Подтвердите/);
  assert.deepEqual(check(validForm({ geometry: pt, geometry_confirmed: true, geometry_precision: "approximate" })).errors, {});
  const swapped = { type: "Point", coordinates: [51.13, 71.43] };
  assert.match(check(validForm({ geometry: swapped, geometry_confirmed: true, geometry_precision: "approximate" })).errors.geometry, /Астаны/);
  const nan = { type: "Point", coordinates: [NaN, 51.1] };
  assert.ok(check(validForm({ geometry: nan, geometry_confirmed: true })).errors.geometry);
  const line1 = { type: "LineString", coordinates: [[71.43, 51.13], [71.43, 51.13]] };
  assert.match(check(validForm({ geometry: line1, geometry_confirmed: true, geometry_precision: "approximate" })).errors.geometry, /две/);
  const form = validForm({ geometry: pt, geometry_confirmed: true, geometry_precision: "source" });
  assert.ok(check(form).errors.place, "exact place needs a source marked 'Место' (shown at the place choice)");
  withSource(form, ["geometry"]);
  assert.deepEqual(check(form).errors, {});
  const none = C.fieldsFromForm(validForm({ geometry: null, geometry_precision: "source" }));
  assert.equal(none.geometry, null);
  assert.equal(none.geometry_precision, "unknown", "absent place has unknown precision");
});

test("provenance: 'observed' requires a source; source rows are validated", () => {
  const form = validForm({ evidence_type: "observed" });
  assert.ok(check(form).errors.evidence_type);
  const s = withSource(form, ["schedule"]);
  assert.deepEqual(check(form).errors, {});
  s.url = "javascript:alert(1)";
  assert.ok(check(form).errors["sources.0.url"]);
  s.url = "https://example.kz"; s.retrieved_at = "2026-12-01";
  assert.match(check(form).errors["sources.0.retrieved_at"], /будущем/);
  assert.equal(C.newSource(form.sources).id, "src-2");
});

test("reason rules: drafts edit freely; published edits, publish and archive need a reason", () => {
  const draft = { publication: "draft" }, pub = { publication: "published" };
  assert.equal(C.reasonRule(draft, "update").required, false);
  assert.equal(C.reasonRule(pub, "update").required, true);
  assert.equal(C.reasonRule(draft, "publish").required, true);
  assert.equal(C.reasonRule(pub, "archive").required, true);
  assert.ok(C.validateReason("  ок "));
  assert.ok(C.validateReason("<b>Перенос</b> срока"));
  assert.equal(C.validateReason("Перенос срока подрядчиком"), null);
});

test("state matrix: logged-out UI has no actions; browser role is not a source of rights", () => {
  const out = C.allowedActions({ publication: "draft" }, { authenticated: false, user: { role: "admin" } });
  assert.ok(Object.values(out).every((v) => v === false));
  const a = C.allowedActions({ publication: "draft" }, { authenticated: true, user: { role: "editor" } });
  const b = C.allowedActions({ publication: "draft" }, { authenticated: true, user: { role: "admin" } });
  assert.deepEqual(a, b);
  assert.equal(a.publish, true);
  const p = C.allowedActions({ publication: "published" }, { authenticated: true });
  assert.deepEqual([p.edit, p.publish, p.archive, p.editNeedsReason], [true, false, true, true]);
  const z = C.allowedActions({ publication: "archived" }, { authenticated: true });
  assert.deepEqual([z.edit, z.publish, z.archive], [false, false, false]);
  assert.equal(C.allowedActions({ publication: "weird" }, { authenticated: true }).edit, false);
});

test("pending-changes servers (R02 staff block): publish again only when edits are pending; server lock flag wins", () => {
  const sess = { authenticated: true };
  const live = { publication: "published" };
  assert.equal(C.pendingInfo(live).known, false);
  assert.equal(C.allowedActions(live, sess).publish, false, "live model: nothing to re-publish");
  const clean = { publication: "published", staff: { has_unpublished_changes: false, public_item: { title: "A" }, original_planned_end_locked: true } };
  const dirty = { publication: "published", staff: { has_unpublished_changes: true, public_item: { title: "A" }, original_planned_end_locked: true } };
  assert.equal(C.allowedActions(clean, sess).publish, false);
  assert.equal(C.allowedActions(dirty, sess).publish, true);
  assert.deepEqual(C.pendingInfo(dirty), { known: true, pending: true, publicItem: { title: "A" } });
  assert.equal(C.reasonRule(dirty, "publish").title, "Причина публикации изменений");
  assert.equal(C.isOriginalLocked({ publication: "archived", staff: { original_planned_end_locked: false } }), false, "archived draft never published");
  assert.equal(C.isOriginalLocked({ publication: "archived" }), true, "unknown history: safe side");
  assert.ok(!("staff" in C.pickPublic(dirty)), "staff block never reaches the public projection");
});

test("public preview is an allowlist: internal notes and service fields never appear", () => {
  const item = Object.assign(clone(FIXTURE), {
    internal_notes: "служебно", created_by: { name: "editor1" }, actor: "editor1", password_hash: "x", csrf_token: "t",
    schedule: Object.assign(clone(FIXTURE.schedule), { secret: 1 }),
    source_refs: [{ id: "s1", url: "https://x.kz", publisher: null, published_on: null, retrieved_at: null, access_status: "fetched", license: null, fields: [], author_phone: "+7" }],
  });
  const pub = C.pickPublic(item);
  const text = JSON.stringify(pub);
  for (const bad of ["internal_notes", "служебно", "created_by", "editor1", "password_hash", "csrf_token", "secret", "author_phone"]) assert.ok(!text.includes(bad), bad);
  assert.equal(pub.title, FIXTURE.title);
  assert.equal(pub.evidence_type, "synthetic");
  const form = C.formFromItem(item);
  form.internal_notes = "ещё служебное";
  const prev = C.previewFromForm(Object.assign(clone(item), { publication: "draft" }), form);
  assert.equal(prev.publication, "draft", "preview never pretends a draft is published");
  assert.ok(!JSON.stringify(prev).includes("служебн"));
});

test("API errors: normalized kinds and server field paths mapped to form fields", () => {
  assert.equal(C.normalizeError(new TypeError("Failed to fetch")).kind, "network");
  // R01 shell CivicApiError shapes (status 0 + code)
  for (const code of ["network", "timeout", "aborted"]) assert.equal(C.normalizeError({ name: "CivicApiError", status: 0, code }).kind, "network", code);
  assert.equal(C.normalizeError({ name: "CivicApiError", status: 422, code: "validation_failed", fields: { "schedule.current_planned_end": "x" } }).fields.current_planned_end, "x");
  assert.equal(C.normalizeError({ status: 401, code: "unauthenticated" }).kind, "auth");
  assert.equal(C.normalizeError({ status: 403, code: "csrf" }).kind, "csrf");
  assert.equal(C.normalizeError({ status: 403, code: "forbidden" }).kind, "forbidden");
  assert.equal(C.normalizeError({ status: 409, code: "stale_revision" }).kind, "conflict");
  assert.equal(C.normalizeError({ status: 409, code: "invalid_transition" }).kind, "transition");
  assert.equal(C.normalizeError({ status: 500, message: "<html><body>Traceback" }).detail, "");
  const v = C.normalizeError({ status: 422, error: { code: "validation", fields: {
    "schedule.original_planned_end": "locked", "budget.amount_kzt": "bad", "source_refs[0].url": "bad", reason: "need", "geometry.coordinates": "bad", zzz: "?" } } });
  assert.equal(v.kind, "validation");
  assert.deepEqual(Object.keys(v.fields).sort(), ["_form", "amount", "geometry", "original_planned_end", "reason", "sources.0.url"]);
  assert.deepEqual(C.normalizeError({ status: 422, fields: [{ field: "title", message: "m" }] }).fields, { title: "m" });
  assert.throws(() => C.unwrap({ ok: false, error: { code: "csrf", message: "no" }, status: 403 }), (e) => e.code === "csrf");
  assert.deepEqual(C.unwrap({ ok: true, data: { a: 1 } }), { a: 1 });
  assert.deepEqual(C.unwrap({ items: [] }), { items: [] });
});

test("uncertain create: a draft with the same title/kind made after the attempt is found, older ones are not", () => {
  const items = [
    { id: "o1", publication: "draft", title: "Ремонт", kind: "roadworks", updated_at: "2026-10-06T09:00:00Z" },
    { id: "o2", publication: "draft", title: "Ремонт", kind: "roadworks", updated_at: "2026-10-06T10:00:05Z" },
  ];
  assert.equal(C.findPossibleDuplicate(items, { title: "Ремонт ", kind: "roadworks" }, "2026-10-06T10:00:00Z").id, "o2");
  assert.equal(C.findPossibleDuplicate(items, { title: "Ремонт", kind: "event" }, "2026-10-06T10:00:00Z"), null);
});

test("409 rebase: my edits survive, server edits are taken, overlaps are reported, nothing is silently dropped", () => {
  const base = C.formFromItem(clone(FIXTURE));
  const mine = clone(base);
  mine.description = "Мой длинный текст, который нельзя потерять";
  mine.current_planned_end = "2026-11-01";
  const latestItem = clone(FIXTURE);
  latestItem.title = "Новое название от коллеги";
  latestItem.schedule.current_planned_end = "2026-10-30";
  latestItem.revision = 3;
  const r = C.rebaseForm(base, mine, C.formFromItem(latestItem));
  assert.equal(r.form.description, mine.description);
  assert.equal(r.form.title, "Новое название от коллеги");
  assert.equal(r.form.current_planned_end, "2026-11-01");
  assert.deepEqual(r.conflicts, ["current_planned_end"]);
  assert.deepEqual(r.theirs, ["title"]);
  // new geometry of mine keeps my confirmation state; theirs keeps the server's
  const mine2 = clone(base);
  mine2.geometry = { type: "Point", coordinates: [71.5, 51.1] }; mine2.geometry_confirmed = false;
  assert.equal(C.rebaseForm(base, mine2, C.formFromItem(latestItem)).form.geometry_confirmed, false);
  // restoring a new-object draft: no base, latest is the empty form
  const fresh = Object.assign(C.emptyForm(), { title: "Черновик в памяти" });
  assert.equal(C.rebaseForm(null, fresh, C.emptyForm()).form.title, "Черновик в памяти");
});

test("formatting helpers: unknown never renders as zero or today", () => {
  assert.equal(C.fmtDateTime("2026-10-06T09:05:00Z"), "06.10.2026 14:05");
  assert.equal(C.fmtDateTime(null), "время неизвестно");
  assert.equal(C.fmtValue("budget.amount_kzt", null), "неизвестно");
  assert.equal(C.fmtValue("schedule.actual_end", null), "неизвестно");
  assert.equal(C.fmtValue("geometry", null), "без места на карте");
  assert.equal(C.fmtDate("2026-10-14"), "14.10.2026");
  assert.equal(C.todayIso(new Date("2026-10-06T20:30:00Z")), "2026-10-07", "Astana calendar day (UTC+5)");
  assert.match(C.fmtMoney(1250000), /^1\s250\s000 ₸$/);
});

// ---------- round 12 ----------
const SQ = [[71.430, 51.130], [71.432, 51.130], [71.432, 51.131], [71.430, 51.131]];

test("round 12 place: unknown / approximate / exact map onto geometry + precision; unknown keeps the drawing but sends none", () => {
  const pt = { type: "Point", coordinates: [71.43, 51.13] };
  const unknown = validForm({ place: "unknown", geometry: pt, geometry_confirmed: true });
  assert.deepEqual(C.placeFields(unknown), { geometry: null, geometry_precision: "unknown" });
  assert.equal(unknown.geometry.type, "Point", "the drawing stays in the form");
  assert.match(check(unknown).warnings.place, /не будет сохранено/);
  assert.deepEqual(check(unknown).errors, {});
  const approx = validForm({ place: "approximate", geometry: pt, geometry_confirmed: true });
  assert.deepEqual(C.fieldsFromForm(approx).geometry_precision, "approximate");
  const exact = validForm({ place: "exact", geometry: pt, geometry_confirmed: true });
  assert.match(check(exact).errors.place, /источник/);
  withSource(exact, ["geometry"]);
  assert.deepEqual(check(exact).errors, {});
  assert.equal(C.fieldsFromForm(exact).geometry_precision, "source");
  const chosenButEmpty = validForm({ place: "approximate" });
  assert.match(check(chosenButEmpty).errors.geometry, /Отметьте место/);
});

test("round 12 place: a stored geometry with unknown precision opens as 'unspecified' and round-trips unchanged", () => {
  const item = Object.assign(clone(FIXTURE), { geometry_precision: "unknown" });
  const form = C.formFromItem(item);
  assert.equal(form.place, "unspecified");
  assert.match(check(form, item).warnings.place, /Точность места не указана/);
  assert.deepEqual(C.buildChanges(item, C.fieldsFromForm(form)), {}, "opening and saving does not rewrite precision");
  assert.equal(C.formFromItem(FIXTURE).place, "approximate");
  assert.equal(C.formFromItem(Object.assign(clone(FIXTURE), { geometry: null, geometry_precision: "unknown" })).place, "unknown");
});

test("round 12 geometry: polygons are closed, counter-clockwise and checked for degenerate or self-crossing outlines", () => {
  const poly = C.polygonFromVertices(SQ.slice().reverse());  // clockwise clicks
  const ring = poly.coordinates[0];
  assert.deepEqual(ring[0], ring[ring.length - 1], "ring is closed");
  assert.ok(C.ringAreaM2(ring) > 0, "exterior ring is counter-clockwise (RFC 7946)");
  assert.equal(C.geometryProblem(poly), null);
  assert.match(C.describeGeometry(poly), /площадь, вершин: 4, ≈ 1[.,]5\d га/);
  const flat = C.polygonFromVertices([[71.43, 51.13], [71.431, 51.13], [71.432, 51.13]]);
  assert.match(C.geometryProblem(flat), /почти нулевая/);
  const bow = C.polygonFromVertices([SQ[0], SQ[2], SQ[1], SQ[3]]);
  assert.match(C.geometryProblem(bow), /пересекает/);
  assert.match(C.geometryProblem(C.polygonFromVertices(SQ.slice(0, 2))), /три разные/);
  assert.match(C.geometryProblem({ type: "LineString", coordinates: [[71.43, 51.13], [71.43001, 51.13]] }), /короче 5 м/);
  assert.match(C.geometryProblem({ type: "Polygon", coordinates: [[[71.43, 51.13], [71.44, 51.13], [71.44, 51.14], [71.43, 51.13]], [[71.431, 51.131], [71.432, 51.131], [71.432, 51.132], [71.431, 51.131]]] }), /без вырезов/);
  const form = validForm({ place: "approximate", geometry: poly, geometry_confirmed: true });
  assert.deepEqual(check(form).errors, {});
  assert.deepEqual(C.fieldsFromForm(form).geometry, poly, "drawn shape is sent as drawn: no snapping to the route graph");
});
