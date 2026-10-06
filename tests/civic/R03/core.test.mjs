// R03 core logic tests: node --test tests/civic/R03/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const C = require(path.join(here, "../../../web/civic/map/civic-map-core.js"));
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
  assert.equal(C.formatTimestamp("2026-10-06T12:00:00+06:00"), "6 октября 2026, 12:00 (UTC+6)");
  assert.equal(C.formatTimestamp("2026-10-06T07:05:00Z"), "6 октября 2026, 07:05 (UTC)");
  assert.equal(C.formatTimestamp("yesterday"), "нет данных");
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
  assert.match(swapped.issue, /вне Астаны/);
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
  // partial interval: only the start is known
  const partial = C.matchPeriod({ schedule: { planned_start: "2019-01-01" } }, "2026-10-01", "2026-10-31");
  assert.equal(partial.match, false, "an old start with unknown end is not 'active now'");
  const partialIn = C.matchPeriod({ schedule: { planned_start: "2026-10-03" } }, "2026-10-01", "2026-10-31");
  assert.deepEqual([partialIn.match, partialIn.partial], [true, true]);
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
  assert.equal(fc.features.length, items.filter((x) => x.geometry).length);
  assert.ok(!fc.features.some((f) => f.properties.cid === "r03-demo-nogeo"));
  const approx = fc.features.find((f) => f.properties.cid === "r03-demo-nodata");
  assert.equal(approx.properties.exact, false);
  assert.equal(approx.properties.synthetic, true);
});

test("kind colours meet 4.5:1 on white (they double as legend text colours)", () => {
  for (const k of Object.values(C.KINDS).concat(C.OTHER_KIND)) {
    assert.ok(C.contrast(k.color, "#ffffff") >= 4.5, k.label + " " + C.contrast(k.color, "#ffffff"));
  }
});
