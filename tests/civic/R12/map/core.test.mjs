// R03 core logic tests: node --test tests/civic/R12/map/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const C = require(path.join(here, "../../../../web/civic/map/civic-map-core.js"));
const fixtures = JSON.parse(readFileSync(path.join(here, "fixtures/objects.json"), "utf8")).items;
const hostile = JSON.parse(readFileSync(path.join(here, "fixtures/hostile.json"), "utf8")).items;
const pack = JSON.parse(readFileSync(path.join(here, "fixtures/pack_civic_object.json"), "utf8"));
const byId = (id) => fixtures.find((x) => x.id === id);

test("pack fixture normalises without inventing values", () => {
  const { item } = C.normalizeObject(pack);
  assert.equal(item.id, "demo-astana-work-01");
  assert.equal(item.evidence, "synthetic");
  assert.equal(item.budget.state, "missing");
  assert.equal(item.budget.amount, null);
  assert.equal(item.budget.text, "нет данных");
  assert.equal(item.responsible.organization, null);
  assert.equal(item.precision, "approximate");
  assert.deepEqual(C.scheduleShift(item), { days: 2, from: "2026-10-20", to: "2026-10-22" });
});

test("unknown budget is never 0 and negative/NaN is flagged, not shown as money", () => {
  assert.equal(C.budgetInfo({ amount_kzt: null, basis: "unknown" }).text, "нет данных");
  assert.equal(C.budgetInfo(undefined).state, "missing");
  assert.equal(C.budgetInfo({ amount_kzt: 0, basis: "spent" }).text, "0 ₸");
  assert.equal(C.budgetInfo({ amount_kzt: -5 }).state, "invalid");
  assert.equal(C.budgetInfo({ amount_kzt: Number.NaN }).state, "invalid");
  assert.equal(C.budgetInfo({ amount_kzt: "100" }).state, "invalid");
  const b = C.budgetInfo({ amount_kzt: 2350000000, basis: "planned" });
  assert.equal(b.text, "2 350 000 000 ₸");
  assert.equal(b.approx, "≈ 2,4 млрд ₸");
  assert.equal(b.basisLabel, "плановая стоимость");
  assert.equal(C.budgetInfo({ amount_kzt: 1, basis: "bogus" }).basis, "unknown");
});

test("dates: strict YYYY-MM-DD, no timezone drift, Russian long form", () => {
  assert.equal(C.parseDay("2026-02-30"), null);
  assert.equal(C.parseDay("06.10.2026"), null);
  assert.equal(C.formatDay("2026-10-06"), "06.10.2026");
  assert.equal(C.formatDay("2026-10-06", "long"), "6 октября 2026");
  assert.equal(C.formatDay(null), "нет данных");
  assert.equal(C.dayDiff("2026-10-20", "2026-11-05"), 16);
  assert.equal(C.addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(C.formatTimestamp("yesterday"), "нет данных");
});

test("timestamps are shown in Astana time from the instant (UTC+5 since 2024-03-01, UTC+6 before)", () => {
  // R02 stores UTC: 21:30Z on 6 Oct is 02:30 on 7 Oct in Astana.
  assert.equal(C.formatTimestamp("2026-10-06T21:30:00+00:00"), "7 октября 2026, 02:30 (время Астаны)");
  assert.equal(C.formatTimestamp("2026-10-06T07:05:00Z"), "6 октября 2026, 12:05 (время Астаны)");
  assert.equal(C.formatTimestamp("2026-10-06T12:00:00+06:00"), "6 октября 2026, 11:00 (время Астаны)");
  assert.equal(C.formatTimestamp("2026-10-06T16:40:00+05:00"), "6 октября 2026, 16:40 (время Астаны)");
  assert.equal(C.formatTimestamp("2023-05-01T10:00:00Z"), "1 мая 2023, 16:00 (время Астаны)");
  assert.equal(C.formatTimestamp("2024-02-29T17:59:00Z"), "29 февраля 2024, 23:59 (время Астаны)");
  assert.equal(C.formatTimestamp("2024-02-29T18:00:00Z"), "29 февраля 2024, 23:00 (время Астаны)");
  assert.equal(C.formatTimestamp("2026-10-06T12:00"), "6 октября 2026, 12:00", "no offset: written wall time, no zone claim");
  assert.equal(C.timestampDay("2026-10-06T21:30:00+00:00"), "2026-10-07");
});

test("safeUrl allows only http(s) without credentials", () => {
  assert.equal(C.safeUrl("https://www.gov.kz/x?a=1"), "https://www.gov.kz/x?a=1");
  for (const bad of ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<b>", "vbscript:x", "//evil.example", "https://u:p@example.org/", "https://exa mple.org", "https://example.org/\u0000", "", null, 42]) {
    assert.equal(C.safeUrl(bad), null, String(bad));
  }
});

test("geometry: valid shapes kept; invalid, out-of-contract or swapped coords become list-only with a reason", () => {
  assert.equal(C.normalizeGeometry(null).geometry, null);
  assert.equal(C.normalizeGeometry(null).issue, null);
  assert.ok(C.normalizeGeometry({ type: "Point", coordinates: [71.43, 51.13] }, C.ASTANA_BBOX).geometry);
  const swapped = C.normalizeGeometry({ type: "Point", coordinates: [51.13, 71.43] }, C.ASTANA_BBOX);
  assert.equal(swapped.geometry, null);
  assert.equal(swapped.kind, "out_of_region");
  assert.match(swapped.issue, /вне области карты Астаны — похоже, перепутаны долгота и широта/);
  // the same envelope as R02 validate.py: approach roads accepted by the server stay on the map
  assert.ok(C.normalizeGeometry({ type: "Point", coordinates: [71.45, 51.5] }, C.ASTANA_BBOX).geometry);
  assert.ok(C.normalizeGeometry({ type: "LineString", coordinates: [[71.43, 51.1], [71.55, 50.8]] }, C.ASTANA_BBOX).geometry);
  const far = C.normalizeGeometry({ type: "Point", coordinates: [76.9, 43.2] }, C.ASTANA_BBOX);
  assert.equal(far.issue, "координаты вне области карты Астаны", "no swap hint when swapping does not help");
  assert.match(C.normalizeGeometry({ type: "MultiPoint", coordinates: [[71.4, 51.1]] }).issue, /не входит в civic-v1/);
  assert.match(C.normalizeGeometry({ type: "LineString", coordinates: [[71.4, 51.1]] }).issue, /некорректны/);
  const open = { type: "Polygon", coordinates: [[[71.4, 51.1], [71.41, 51.1], [71.41, 51.11], [71.4, 51.11]]] };
  assert.equal(C.normalizeGeometry(open).geometry, null, "unclosed ring is not silently repaired");
  assert.equal(C.normalizeGeometry({ type: "Point", coordinates: [181, 51] }).geometry, null);
});

test("normalizeList drops drafts, other cities and duplicates; keeps null-geometry items", () => {
  const { items, excluded } = C.normalizeList([...fixtures, ...hostile, fixtures[0]]);
  const ids = items.map((x) => x.id);
  assert.ok(!ids.includes("r03-hostile-draft"));
  assert.ok(!ids.includes("r03-hostile-othercity"));
  assert.ok(ids.includes("r03-demo-nogeo"));
  assert.equal(items.find((x) => x.id === "r03-demo-nogeo").geometry, null);
  assert.ok(excluded.includes("не опубликовано"));
  assert.ok(excluded.includes("другой город"));
  assert.ok(excluded.includes("повтор id"));
  const bad = items.find((x) => x.id === "r03-hostile-baddate");
  assert.equal(bad.schedule.planned_start, null);
  assert.equal(bad.schedule.original_planned_end, null);
  assert.equal(bad.issues.length, 2);
});

test("hostile source URLs are dropped and flagged", () => {
  const { item } = C.normalizeObject(hostile[0]);
  assert.equal(item.sourceRefs[0].url, null);
  assert.equal(item.sourceRefs[0].rawUrlRejected, true);
  assert.equal(item.sourceRefs[1].url, null);
  // the text stays text; rendering is responsible for textContent
  assert.match(item.title, /<img/);
});

test("period filter uses known planned intervals only; undated and partial are reported", () => {
  const { items } = C.normalizeList(fixtures);
  const today = "2026-10-06";
  const r = C.applyFilters(items, { period: "custom", from: "2026-10-01", to: "2026-10-31" }, { today });
  const ids = r.shown.map((x) => x.item.id);
  assert.ok(ids.includes("r03-demo-shifted"));
  assert.ok(ids.includes("r03-demo-closure"));
  assert.ok(ids.includes("r03-demo-area"), "long-running interval overlaps the month");
  assert.ok(!ids.includes("r03-demo-historical"), "2024 plan is not shown as current");
  assert.ok(!ids.includes("r03-demo-nodata"));
  assert.equal(r.counts.undated, 2);
  assert.equal(r.counts.total, items.length);
});

test("period rule matches contract §2 / R02: unknown bound is open and flagged, original end is history only", () => {
  // only the start is known: open end, shown with a flag (R02 returns it as incomplete too)
  const a = C.matchPeriod({ schedule: { planned_start: "2026-03-01" } }, "2026-10-01", "2026-10-31");
  assert.deepEqual([a.match, a.partial, a.missing], [true, true, "end"]);
  const later = C.matchPeriod({ schedule: { planned_start: "2026-11-15" } }, "2026-10-01", "2026-10-31");
  assert.equal(later.match, false);
  const endOnly = C.matchPeriod({ schedule: { current_planned_end: "2026-09-01" } }, "2026-10-01", "2026-10-31");
  assert.equal(endOnly.match, false);
  // current end cleared after publication: the old original end is not used as the active end
  const cleared = { schedule: { planned_start: "2024-03-01", original_planned_end: "2024-11-30", current_planned_end: null, actual_end: null }, status: "in_progress" };
  assert.deepEqual(C.plannedInterval(cleared), { start: "2024-03-01", end: null, complete: false });
  // ...but the historical mark still sees the passed first promise
  const mark = C.staleness(cleared, "2026-10-06");
  assert.deepEqual([mark.kind, mark.end, mark.original], ["plan_end_passed", "2024-11-30", true]);
  const old = C.staleness({ schedule: { planned_start: "2019-05-01" }, status: "planned" }, "2026-10-06");
  assert.equal(old.kind, "old_start_no_end");
  assert.equal(C.staleness({ schedule: { planned_start: "2026-03-01" }, status: "planned" }, "2026-10-06"), null);
  assert.equal(C.matchPeriod(cleared, "2026-01-01", "2026-12-31").match, true);
  // one-sided custom period must not throw (regression: lo "0000-01-01" made parseDay null)
  assert.equal(C.matchPeriod({ schedule: { planned_start: "2026-03-01", current_planned_end: "2026-04-01" } }, null, "2026-10-31").match, true);
  assert.equal(C.matchPeriod({ schedule: { planned_start: "2026-03-01", current_planned_end: "2026-04-01" } }, "2026-05-01", null).match, false);
  const range = C.periodRange("custom", "2026-10-06", { to: "2026-10-31" });
  assert.deepEqual(range, { from: null, to: "2026-10-31" });
});

test("kind/status filters and facet counts", () => {
  const { items } = C.normalizeList(fixtures);
  const r = C.applyFilters(items, { kinds: ["roadworks"], statuses: ["planned"] }, { today: "2026-10-06" });
  assert.ok(r.shown.every((x) => x.item.kind === "roadworks" && x.item.status === "planned"));
  assert.ok(r.counts.byKind.landscaping >= 1, "facet counts ignore the kind filter");
  const none = C.applyFilters(items, { kinds: ["event"], statuses: ["completed"] }, { today: "2026-10-06" });
  assert.equal(none.shown.length, 0);
});

test("area filter: null geometry is counted, not placed", () => {
  const { items } = C.normalizeList(fixtures);
  const view = [71.42, 51.12, 71.44, 51.14];
  const r = C.applyFilters(items, { area: true }, { today: "2026-10-06", viewBox: view });
  assert.ok(r.shown.every((x) => x.item.bbox));
  assert.equal(r.counts.noGeometry, 1);
  assert.ok(r.counts.outsideArea > 0);
});

test("periodRange presets come from the injected day, not from the clock", () => {
  assert.deepEqual(C.periodRange("month", "2026-02-10"), { from: "2026-02-01", to: "2026-02-28" });
  assert.deepEqual(C.periodRange("nextMonth", "2026-12-31"), { from: "2027-01-01", to: "2027-01-31" });
  assert.deepEqual(C.periodRange("next30", "2026-10-06"), { from: "2026-10-06", to: "2026-11-05" });
  assert.deepEqual(C.periodRange("custom", "2026-10-06", { from: "2026-12-01", to: "2026-11-01" }), { from: "2026-11-01", to: "2026-12-01" });
  assert.deepEqual(C.periodRange("all", "2026-10-06"), { from: null, to: null });
});

test("staleness marks a passed plan without claiming completion", () => {
  const { item } = C.normalizeObject(byId("r03-demo-historical"));
  const s = C.staleness(item, "2026-10-06");
  assert.equal(s.kind, "plan_end_passed");
  assert.equal(s.end, "2024-09-30");
  const done = C.normalizeObject(byId("r03-demo-completed")).item;
  assert.equal(C.staleness(done, "2026-10-06"), null);
});

test("history: shift reason comes from the latest published end-date change; compare two revisions", () => {
  const H = JSON.parse(readFileSync(path.join(here, "fixtures/history.json"), "utf8")).history;
  const rows = C.normalizeHistory(H["r03-demo-area"]);
  assert.equal(rows[0].revision, 4);
  assert.equal(C.shiftReason(rows).reason, "Демо: второй перенос");
  const cmp = C.compareRevisions(rows, 2, 4);
  assert.equal(cmp.fields.length, 1);
  assert.equal(cmp.fields[0].before, "2026-08-31");
  assert.equal(cmp.fields[0].after, "2026-12-25");
  assert.equal(cmp.reasons.length, 2);
  const plain = C.normalizeHistory(H["r03-demo-shifted"]);
  assert.equal(C.shiftReason(plain).revision, 3);
  assert.equal(C.compareRevisions(plain, 1, 3).fields.every((f) => !f.hasValues), true);
});

test("sequence guard: only the newest ticket is current", () => {
  const s = C.createSequence();
  const a = s.next(), b = s.next();
  assert.equal(s.isCurrent(a), false);
  assert.equal(s.isCurrent(b), true);
  s.cancel();
  assert.equal(s.isCurrent(b), false);
});

test("unwrap/errorInfo handle raw envelopes and HTTP errors", () => {
  assert.deepEqual(C.unwrap({ ok: true, data: { items: [] } }), { items: [] });
  assert.throws(() => C.unwrap({ ok: false, error: { code: "not_found", message: "x" } }), /x/);
  assert.equal(C.errorInfo({ status: 500 }).text.includes("500"), true);
  assert.equal(C.errorInfo({ status: 404 }).notFound, true);
  assert.equal(C.errorInfo({ code: "not_found" }).notFound, true);
});

test("featureCollection skips null geometry and marks approximate/synthetic", () => {
  const { items } = C.normalizeList(fixtures);
  const fc = C.featureCollection(items);
  // R12: у записи без точного места есть мягкая область approx_area; каждая запись с геометрией есть на карте.
  assert.equal(new Set(fc.features.map((f) => f.properties.cid)).size, items.filter((x) => x.geometry).length);
  assert.ok(!fc.features.some((f) => f.properties.cid === "r03-demo-nogeo"));
  const approx = fc.features.find((f) => f.properties.cid === "r03-demo-nodata");
  assert.equal(approx.properties.exact, false);
  assert.equal(approx.properties.synthetic, true);
  assert.equal(approx.properties.approx_area, true);
  assert.equal(approx.geometry.type, "Polygon");
});

test("kind colours meet 4.5:1 on white (they double as legend text colours)", () => {
  for (const k of Object.values(C.KINDS).concat(C.OTHER_KIND)) {
    assert.ok(C.contrast(k.color, "#ffffff") >= 4.5, k.label + " " + C.contrast(k.color, "#ffffff"));
  }
});

test("counters only count what the other filters let through (search, kind, area)", () => {
  const mk = (id, kind, dates, title) => ({ id, kind, status: "planned", title, publication: "published", geometry: null, schedule: dates });
  const { items } = C.normalizeList([
    mk("r1", "roadworks", { planned_start: "2026-10-01", current_planned_end: "2026-10-20" }, "мост"),
    mk("e1", "event", {}, "событие"), mk("e2", "event", {}, "событие"), mk("c1", "construction", {}, "школа"),
  ]);
  const r = C.applyFilters(items, { kinds: ["roadworks"], period: "month" }, { today: "2026-10-06" });
  assert.equal(r.shown.length, 1);
  assert.equal(r.counts.undated, 0, "undated records of other kinds are not promised");
  const q = C.applyFilters(items, {}, { today: "2026-10-06", match: (it) => it.title.includes("мост") });
  assert.deepEqual(q.counts.byKind, { roadworks: 1 }, "chip counts follow the search");
});

test("malformed records are dropped one by one, never the whole list", () => {
  const raw = JSON.parse('[{"id":"a","title":"ok"},{"id":"b","status":{"toString":1}},{"id":"c","schema_version":{"toString":1}},{"id":"d","kind":{"valueOf":1},"evidence_type":{"toString":1},"budget":{"basis":{"toString":1}},"source_refs":[{"access_status":{"toString":1}}]}]');
  const { items, excluded } = C.normalizeList(raw);
  assert.equal(items.length, 4);
  assert.deepEqual(excluded, []);
  assert.equal(items[1].status, "unknown");
  const rings = Array.from({ length: 130000 }, () => [[71.4, 51.1], [71.41, 51.1], [71.41, 51.11], [71.4, 51.1]]);
  assert.doesNotThrow(() => C.normalizeList([{ id: "big", title: "x", geometry: { type: "Polygon", coordinates: rings } }]));
  assert.notEqual(C.errorInfo(new TypeError("Cannot convert object to primitive value")).text, "Нет связи с сервером. Проверьте подключение и повторите.");
  assert.equal(C.errorInfo({ status: 0, code: "network" }).text, "Нет связи с сервером. Проверьте подключение и повторите.");
  assert.match(C.errorInfo({ status: 404, code: "not_found" }, "list").text, /адрес списка/);
});

test("synthetic records never show an amount in tenge (same rule as R02 validation)", () => {
  const b = C.budgetInfo({ amount_kzt: 48500000, basis: "contract", source_id: "s" }, "synthetic");
  assert.equal(b.state, "suppressed");
  assert.doesNotMatch(b.text, /₸/);
  assert.equal(C.budgetInfo({ amount_kzt: 48500000, basis: "contract", source_id: "s" }, "derived").text, "48\u202f500\u202f000 ₸");
});

test("feature collection draws small polygons above large ones", () => {
  const poly = (id, w, s, e, n) => ({ id, title: id, publication: "published", geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } });
  const { items } = C.normalizeList([poly("small", 71.44, 51.14, 71.444, 51.142), poly("big", 71.43, 51.13, 71.46, 51.15)]);
  assert.deepEqual(C.featureCollection(items).features.map((f) => f.properties.cid), ["big", "small"]);
});

test("draw order: polygons largest first even with points in between; area counters respect the period", () => {
  const poly = (id, w, s, e, n, end) => ({ id, title: id, publication: "published", schedule: { planned_start: "2026-01-01", current_planned_end: end }, geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } });
  const pt = { id: "p1", title: "p1", publication: "published", schedule: { planned_start: "2026-01-01", current_planned_end: "2026-10-20" }, geometry: { type: "Point", coordinates: [71.45, 51.14] } };
  const { items } = C.normalizeList([poly("small", 71.44, 51.14, 71.444, 51.142, "2026-10-10"), pt, poly("big", 71.43, 51.13, 71.46, 51.15, "2026-11-30")]);
  const cids = C.featureCollection(C.sortItems(items)).features.map((f) => f.properties.cid);
  assert.deepEqual([...new Set(cids)], ["big", "small", "p1"]);
  const mk = (id, geo, dates) => ({ id, title: id, publication: "published", geometry: geo, schedule: dates });
  const P = (x, y) => ({ type: "Point", coordinates: [x, y] });
  const list = C.normalizeList([
    mk("in-oct", P(71.43, 51.13), { planned_start: "2026-10-01", current_planned_end: "2026-10-20" }),
    mk("out-2025", P(71.6, 51.3), { planned_start: "2025-01-01", current_planned_end: "2025-02-01" }),
    mk("nogeo-2025", null, { planned_start: "2025-01-01", current_planned_end: "2025-02-01" }),
    mk("nogeo-undated", null, {}),
  ]).items;
  const r = C.applyFilters(list, { period: "month", area: true }, { today: "2026-10-06", viewBox: [71.4, 51.1, 71.5, 51.2] });
  assert.deepEqual([r.shown.length, r.counts.outsideArea, r.counts.noGeometry, r.counts.undated], [1, 0, 0, 0]);
});

test("r12: cost and responsible are shown only when a source covers them; provenance in plain words", () => {
  const base = { id: "x", title: "x", publication: "published", evidence_type: "derived",
    budget: { amount_kzt: 1000000, basis: "contract", source_id: null }, responsible: { organization: "ТОО Пример", public_contact: "+7 700" } };
  const none = C.normalizeObject({ ...base, source_refs: [] }).item;
  assert.deepEqual([C.costView(none).show, C.costView(none).state], [false, "unsourced"]);
  assert.deepEqual([C.responsibleView(none).show, C.responsibleView(none).state], [false, "unsourced"]);
  assert.equal(C.provenanceLine(none).text, "Источник не указан — сведения нельзя проверить по документу.");
  const ref = { id: "s1", url: "https://example.org/a", publisher: "Акимат (тест)", published_on: "2026-09-01", fields: ["responsible.organization"] };
  const org = C.normalizeObject({ ...base, source_refs: [ref] }).item;
  const rv = C.responsibleView(org);
  assert.deepEqual([rv.show, rv.organization, rv.contact], [true, "ТОО Пример", null], "contact is not covered by the source");
  assert.equal(C.costView(org).show, false, "a source for the organisation does not vouch for the money");
  const money = C.normalizeObject({ ...base, budget: { amount_kzt: 1000000, basis: "contract", source_id: "s1" }, source_refs: [ref] }).item;
  assert.equal(C.costView(money).show, true);
  const parent = C.normalizeObject({ ...base, source_refs: [{ ...ref, fields: ["responsible"] }] }).item;
  assert.equal(C.responsibleView(parent).contact, "+7 700", "a parent field covers its children");
  assert.equal(C.provenanceLine(org).text, "Акимат (тест), 01.09.2026");
  const demo = C.normalizeObject({ id: "d", title: "d", evidence_type: "synthetic", budget: { amount_kzt: 5, basis: "planned", source_id: null } }).item;
  assert.equal(C.costView(demo).state, "suppressed");
  assert.equal(C.provenanceLine(demo).state, "demo");
});

test("r12 review: 'hide past plans' keeps overdue works in progress; every counter honours it; groups follow the card's sources", () => {
  const P = (x, y) => ({ type: "Point", coordinates: [x, y] });
  const mk = (id, status, geo, dates, extra) => ({ id, title: id, publication: "published", status, geometry: geo, schedule: dates, ...extra });
  const list = C.normalizeList([
    mk("overdue-in-progress", "in_progress", P(71.43, 51.13), { planned_start: "2026-08-01", current_planned_end: "2026-09-30" }),
    mk("past-plan", "planned", P(71.43, 51.13), { planned_start: "2026-01-01", current_planned_end: "2026-03-01" }),
    mk("past-unknown", "unknown", P(71.43, 51.13), { original_planned_end: "2026-02-01" }),
    mk("done-2024", "completed", P(71.43, 51.13), { planned_start: "2024-01-01", current_planned_end: "2024-05-01" }),
    mk("far-past-plan", "planned", P(71.6, 51.3), { planned_start: "2026-01-01", current_planned_end: "2026-03-01" }),
    mk("undated-past", "planned", P(71.43, 51.13), { original_planned_end: "2026-01-15" }),
    mk("old-start-no-end", "planned", P(71.43, 51.13), { planned_start: "2025-03-01" }),
  ]).items;
  const today = "2026-10-07";
  assert.deepEqual(list.filter((it) => C.pastPlan(it, today)).map((it) => it.id).sort(), ["far-past-plan", "past-plan", "past-unknown", "undated-past"]);
  const r = C.applyFilters(list, { hidePast: true }, { today });
  assert.deepEqual(r.shown.map((x) => x.item.id).sort(), ["done-2024", "old-start-no-end", "overdue-in-progress"], "an overdue work in progress stays visible; no end = no passed deadline");
  assert.equal(r.counts.past, 4);
  // area + hidePast: a far-away past plan is not promised by «Вне видимой части»
  const a = C.applyFilters(list, { hidePast: true, area: true }, { today, viewBox: [71.4, 51.1, 71.5, 51.2] });
  assert.deepEqual([a.counts.outsideArea, a.counts.past], [0, 3]);
  // period + hidePast: a record with only a past original end is not promised by «Без плановых дат … Показать все сроки»
  const y = C.applyFilters(list, { hidePast: true, period: "month" }, { today });
  assert.equal(y.counts.undated, 0);
  // «Сведения»: grouped by the sources the card lists
  const hyp = C.normalizeObject({ id: "h", title: "h", evidence_type: "hypothesis", source_refs: [{ id: "s1", publisher: "Акимат s1", published_on: "2026-09-01", fields: ["status"] }] }).item;
  const obsNoRef = C.normalizeObject({ id: "o", title: "o", evidence_type: "observed", source_refs: [] }).item;
  const demo = C.normalizeObject({ id: "d", title: "d", evidence_type: "synthetic", source_refs: [{ id: "s", publisher: "x", fields: [] }] }).item;
  assert.deepEqual([C.evidenceGroup(hyp), C.evidenceGroup(obsNoRef), C.evidenceGroup(demo)], ["sourced", "unsourced", "demo"]);
  assert.equal(C.provenanceLine(hyp).text, "Акимат s1, 01.09.2026", "the card and the filter agree");
});


// ---------- R12 round 14: линии по улицам OSM и «примерное место» областью ----------
test("r12: demo_snapped replaces a free-hand line only when the stored geometry is unchanged", () => {
  const hand = [[71.4251, 51.1712], [71.4289, 51.1716], [71.4326, 51.1719]];
  const street = [[71.4251, 51.17129], [71.4270, 51.17140], [71.4300, 51.17165], [71.4326, 51.17188]];
  const raw = { id: "d1", title: "Демо", publication: "published", evidence_type: "synthetic", geometry_precision: "approximate",
    geometry: { type: "LineString", coordinates: hand } };
  const { items } = C.normalizeList([raw, Object.assign({}, raw, { id: "d2" })]);
  const snapped = { items: {
    d1: { status: "snapped", original_coordinates: hand, geometry: { type: "LineString", coordinates: street },
      geometry_source: "osm-graph", street_ru: "улица Сакена Сейфуллина", display: "street_line", length_m: 528.2 },
    d2: { status: "snapped", original_coordinates: [[71.0, 51.0], [71.1, 51.1]], geometry: { type: "LineString", coordinates: street } },
  } };
  const out = C.applySnapped(items, snapped);
  assert.deepEqual(out[0].geometry.coordinates, street);
  assert.equal(C.displayMode(out[0]), "exact", "линия по оси улицы рисуется сплошной");
  assert.match(C.placeText(out[0]), /Участок улицы по карте OSM: улица Сакена Сейфуллина/);
  assert.deepEqual(out[1].geometry.coordinates, hand, "геометрию в хранилище изменили — замена не применяется");
  assert.equal(items[0].geometry.coordinates, hand, "исходная запись не мутируется");
  const fc = C.featureCollection(out);
  const d1 = fc.features.filter((f) => f.properties.cid === "d1");
  assert.equal(d1.length, 1);
  assert.equal(d1[0].geometry.type, "LineString");
  assert.equal(d1[0].properties.snapped, true);
  const d2 = fc.features.filter((f) => f.properties.cid === "d2");
  assert.deepEqual(d2.map((f) => f.geometry.type), ["LineString"], "примерная линия из хранилища — пунктиром по своей форме, не кругом");
  assert.equal(d2[0].properties.exact, false);
  assert.match(C.placeText(out[1]), /границы примерные/);
  // демо-линия, которую snap_demo не смог честно положить на одну улицу, — только область «примерное место»
  const forced = C.applySnapped(items, { items: { d1: { status: "not_snapped", display: "approximate_area", original_coordinates: hand } } });
  const f1 = C.featureCollection(forced).features.filter((f) => f.properties.cid === "d1");
  assert.deepEqual(f1.map((f) => f.geometry.type), ["Polygon"]);
  assert.equal(f1[0].properties.approx_area, true);
  assert.deepEqual(C.applySnapped(items, null), items);
  assert.deepEqual(C.applySnapped(items, { items: { d1: { status: "snapped", original_coordinates: hand, geometry: { type: "LineString", coordinates: [[1, 2], [3, 4]] } } } })[0].geometry.coordinates, hand,
    "привязка вне Астаны отбрасывается");
});

test("r12: approximate point -> 120 m area plus its marker; exact point -> marker only", () => {
  const { items } = C.normalizeList([
    { id: "a", title: "a", publication: "published", geometry_precision: "approximate", geometry: { type: "Point", coordinates: [71.43, 51.16] } },
    { id: "e", title: "e", publication: "published", geometry_precision: "source", geometry: { type: "Point", coordinates: [71.44, 51.16] } },
  ]);
  const fc = C.featureCollection(items);
  const a = fc.features.filter((f) => f.properties.cid === "a");
  assert.deepEqual(a.map((f) => f.geometry.type), ["Polygon", "Point"]);
  const ring = a[0].geometry.coordinates[0];
  for (const p of ring) assert.ok(Math.abs(C.haversineM([71.43, 51.16], p) - C.APPROX_RADIUS_M) < 1);
  assert.deepEqual(ring[0], ring[ring.length - 1]);
  assert.deepEqual(fc.features.filter((f) => f.properties.cid === "e").map((f) => f.geometry.type), ["Point"]);
  assert.equal(C.placeText(items[0]), "Примерное место — показано областью");
  assert.equal(C.placeText(items[1]), null);
});

test("r12: new strings go through BirgeI18n keys when the dictionary has them, Russian text otherwise", () => {
  const it = { snap: { display: "street_line", street: "улица Сакена Сейфуллина" }, precision: "approximate", geometry: { type: "LineString", coordinates: [[71.4, 51.1], [71.41, 51.1]] } };
  assert.equal(C.placeText(it), "Участок улицы по карте OSM: улица Сакена Сейфуллина");
  const prev = globalThis.self;
  globalThis.self = { BirgeI18n: { has: (k) => k === "geo.place.street_line", t: (k, p) => "OSM картасы бойынша көше бөлігі: " + p.street } };
  try {
    assert.equal(C.placeText(it), "OSM картасы бойынша көше бөлігі: улица Сакена Сейфуллина");
    assert.equal(C.tr("geo.badge.street", "По улице"), "По улице", "нет ключа — русский текст, не сам ключ");
  } finally { if (prev === undefined) delete globalThis.self; else globalThis.self = prev; }
});

test("r12: in ҚАЗ the street name on the map and in the card is the Kazakh one from OSM (street_kk), else Russian", () => {
  const it = { id: "s", kind: "roadworks", status: "planned", title: "Перекрытие", evidence: "synthetic", precision: "approximate",
    snap: { display: "street_line", street: "улица Сакена Сейфуллина", streetKk: "Сәкен Сейфуллин көшесі" },
    geometry: { type: "LineString", coordinates: [[71.4, 51.1], [71.41, 51.1]] }, bbox: [71.4, 51.1, 71.41, 51.1] };
  const prev = globalThis.self;
  try {
    globalThis.self = { BirgeI18n: { getLang: () => "kk", has: () => false, t: () => "" } };
    assert.equal(C.snapStreet(it), "Сәкен Сейфуллин көшесі");
    assert.equal(C.placeText(it), "Участок улицы по карте OSM: Сәкен Сейфуллин көшесі");
    const f = C.featureCollection([it]).features.find((x) => x.geometry.type === "LineString");
    assert.equal(f.properties.street, "Сәкен Сейфуллин көшесі");
    globalThis.self = { BirgeI18n: { getLang: () => "ru", has: () => false, t: () => "" } };
    assert.equal(C.snapStreet(it), "улица Сакена Сейфуллина");
    globalThis.self = { BirgeI18n: { getLang: () => "kk", has: () => false, t: () => "" } };
    assert.equal(C.snapStreet({ snap: { street: "улица Без Казахского" } }), "улица Без Казахского", "нет street_kk — русское имя, не пусто");
  } finally { if (prev === undefined) delete globalThis.self; else globalThis.self = prev; }
});
