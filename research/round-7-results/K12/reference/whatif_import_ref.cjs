// K12 round 7: REFERENCE importer for scenario contract city-whatif-v1 (FEATURE_SPEC.txt, 7927fa8).
// Oracle for the stress test module and a logic-only proposal for BUILD. No UI, no DOM, no network.
// Works in Node and in a browser (no require at call time; sha256hex is injected, e.g. facts.js F.sha256hex).
//
//   const { makeImporter } = require("./whatif_import_ref.cjs");
//   const imp = makeImporter({ D: window.CITY_EVIDENCE, sha256hex });
//   imp.snapshot("shymkent", "school");                 // fingerprint of the slice + calculation parameters
//   const r = imp.importScenario(text, state);          // {ok, code, message, state}; never mutates `state`
//   imp.compute(r.state);                               // rows recomputed from the slice (imported results ignored)
"use strict";

const SCHEMA = "city-whatif-v1";
const MAX_BYTES = 256 * 1024;
const CITIES = ["shymkent", "astana"];
const CATEGORIES = ["school", "outpatient_clinic"];
const MAX_POINTS = 10;
const ID_RE = /^[A-Za-z0-9_.-]{1,64}$/;
const R_EARTH_M = 6371008.8;
const ROOT_KEYS = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "proposed_object", "results"];
const REQUIRED = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "proposed_object"];
const POINT_KEYS = ["id", "lon", "lat"];
const PROJECT_KEYS = ["id", "lon", "lat", "category", "kind"];

class ImportError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
const fail = (code, message) => { throw new ImportError(code, message); };
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

// ---- strict JSON: no NaN/Infinity tokens, no overflow to Infinity, no duplicate keys, no BOM ----
function parseStrict(text, maxDepth = 32) {
  let i = 0;
  const err = (code, what) => fail(code, `${what} at ${i}`);
  const ws = () => { while (i < text.length && " \t\n\r".includes(text[i])) i++; };
  const value = (depth) => {
    if (depth > maxDepth) err("invalid_json", "nesting too deep");
    ws();
    const c = text[i];
    if (c === "{") return object(depth);
    if (c === "[") return array(depth);
    if (c === '"') return string();
    if (c === "t" && text.startsWith("true", i)) { i += 4; return true; }
    if (c === "f" && text.startsWith("false", i)) { i += 5; return false; }
    if (c === "n" && text.startsWith("null", i)) { i += 4; return null; }
    if (c === "-" || (c >= "0" && c <= "9")) return number();
    return err("invalid_json", `unexpected ${JSON.stringify(c === undefined ? "end" : c)}`);
  };
  const object = (depth) => {
    i++;
    const o = {};
    const seen = new Set();
    ws();
    if (text[i] === "}") { i++; return o; }
    for (;;) {
      ws();
      if (text[i] !== '"') err("invalid_json", "expected key");
      const k = string();
      if (seen.has(k)) err("duplicate_key", `duplicate key ${JSON.stringify(k)}`);
      seen.add(k);
      ws();
      if (text[i] !== ":") err("invalid_json", "expected ':'");
      i++;
      // defineProperty: a "__proto__" key stays an ordinary own property (no prototype change)
      Object.defineProperty(o, k, { value: value(depth + 1), enumerable: true, writable: true, configurable: true });
      ws();
      if (text[i] === ",") { i++; continue; }
      if (text[i] === "}") { i++; return o; }
      err("invalid_json", "expected ',' or '}'");
    }
  };
  const array = (depth) => {
    i++;
    const a = [];
    ws();
    if (text[i] === "]") { i++; return a; }
    for (;;) {
      a.push(value(depth + 1));
      ws();
      if (text[i] === ",") { i++; continue; }
      if (text[i] === "]") { i++; return a; }
      err("invalid_json", "expected ',' or ']'");
    }
  };
  const string = () => {
    const m = /^"(?:[^"\\\u0000-\u001f]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"/.exec(text.slice(i, i + MAX_BYTES + 2));
    if (!m) err("invalid_json", "bad string");
    i += m[0].length;
    return JSON.parse(m[0]);
  };
  const number = () => {
    const m = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(text.slice(i, i + 400));
    if (!m) err("invalid_json", "bad number");
    i += m[0].length;
    const v = Number(m[0]);
    if (!Number.isFinite(v)) err("nonfinite_number", `number ${m[0].slice(0, 20)} is not finite`);
    return v;
  };
  const v = value(0);
  ws();
  if (i !== text.length) err("invalid_json", "trailing data");
  return v;
}

function haversineM(lon1, lat1, lon2, lat2) {
  const rad = Math.PI / 180;
  const p1 = lat1 * rad, p2 = lat2 * rad, dp = (lat2 - lat1) * rad, dl = (lon2 - lon1) * rad;
  let a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  a = Math.min(1, Math.max(0, a));
  return 2 * R_EARTH_M * Math.asin(Math.sqrt(a));
}

function canonical(x) {
  if (Array.isArray(x)) return "[" + x.map(canonical).join(",") + "]";
  if (x && typeof x === "object") return "{" + Object.keys(x).sort().map((k) => JSON.stringify(k) + ":" + canonical(x[k])).join(",") + "}";
  return JSON.stringify(x);
}

function makeImporter({ D, sha256hex }) {
  if (!D || !D.cities) throw new Error("makeImporter: CITY_EVIDENCE data required");
  if (typeof sha256hex !== "function") throw new Error("makeImporter: sha256hex(text) required");
  const utf8Length = (s) => (typeof TextEncoder !== "undefined" ? new TextEncoder().encode(s).length : Buffer.byteLength(s, "utf8"));

  function snapshot(city, category) {
    const c = D.cities[city];
    if (!c || !CATEGORIES.includes(category)) throw new ImportError("unknown_city", "no such city/category");
    const fp = { v: 1, city, category, release: c.release, bbox: c.bbox,
                 places_sha256: c.files && c.files.places_social && c.files.places_social.sha256,
                 formula: "haversine", radius_m: R_EARTH_M };
    return "city-whatif-snap-v1:" + sha256hex(canonical(fp));
  }

  function initialState(city, category) {
    return { city, category, snapshot: snapshot(city, category), control_points: [], proposed_object: null };
  }

  function point(p, bbox, keys, what) {
    if (!p || typeof p !== "object" || Array.isArray(p)) fail(what === "project" ? "bad_project" : "bad_points", `${what} must be an object`);
    for (const k of Object.keys(p)) if (!keys.includes(k)) fail("unknown_field", `${what}: unknown field ${JSON.stringify(k).slice(0, 40)}`);
    for (const k of keys) if (!own(p, k)) fail("missing_field", `${what}: missing ${k}`);
    if (typeof p.id !== "string" || !ID_RE.test(p.id)) fail("bad_id", `${what}: id must match ${ID_RE}`);
    for (const k of ["lon", "lat"]) if (typeof p[k] !== "number" || !Number.isFinite(p[k])) fail("bad_coordinate", `${what} ${p.id}: ${k} must be a finite number`);
    if (p.lon < -180 || p.lon > 180 || p.lat < -90 || p.lat > 90) fail("bad_coordinate", `${what} ${p.id}: coordinate out of range`);
    if (p.lon < bbox[0] || p.lon > bbox[2] || p.lat < bbox[1] || p.lat > bbox[3]) fail("outside_bbox", `${what} ${p.id}: outside the slice bbox`);
    const out = {};
    for (const k of keys) out[k] = p[k];
    return out;
  }

  function validate(text) {
    if (typeof text !== "string") fail("invalid_json", "import must be text");
    if (utf8Length(text) > MAX_BYTES) fail("too_large", `import > ${MAX_BYTES} bytes`);
    const s = parseStrict(text);
    if (!s || typeof s !== "object" || Array.isArray(s)) fail("bad_root", "scenario must be a JSON object");
    for (const k of Object.keys(s)) if (!ROOT_KEYS.includes(k)) fail(k === "proposed_objects" ? "multiple_projects" : "unknown_field", `unknown field ${JSON.stringify(k).slice(0, 40)}`);
    for (const k of REQUIRED) if (!own(s, k)) fail(k === "schema_version" ? "unknown_version" : "missing_field", `missing ${k}`);
    if (s.schema_version !== SCHEMA) fail("unknown_version", "unknown schema_version");
    if (!CITIES.includes(s.city_id)) fail("unknown_city", "unknown city_id");
    if (!CATEGORIES.includes(s.category)) fail("bad_category", "category must be school or outpatient_clinic");
    if (typeof s.source_snapshot !== "string" || s.source_snapshot !== snapshot(s.city_id, s.category)) fail("foreign_snapshot", "source_snapshot does not match the current slice");
    if (!Array.isArray(s.control_points)) fail("bad_points", "control_points must be an array");
    if (s.control_points.length === 0) fail("no_points", "1..10 control points required");
    if (s.control_points.length > MAX_POINTS) fail("too_many_points", "at most 10 control points");
    const bbox = D.cities[s.city_id].bbox;
    const pts = s.control_points.map((p) => point(p, bbox, POINT_KEYS, "point"));
    let proj = null;
    if (Array.isArray(s.proposed_object)) fail("multiple_projects", "only one proposed object");
    if (s.proposed_object !== null) {
      proj = point(s.proposed_object, bbox, PROJECT_KEYS, "project");
      if (proj.kind !== "hypothetical") fail("bad_project", "proposed_object.kind must be hypothetical");
      if (proj.category !== s.category) fail("category_mismatch", "proposed_object.category must equal category");
    }
    const ids = pts.map((p) => p.id).concat(proj ? [proj.id] : []);
    if (new Set(ids).size !== ids.length) fail("duplicate_id", "IDs must be unique");
    // s.results (derived values) is ignored on purpose: everything is recomputed
    return { city: s.city_id, category: s.category, snapshot: s.source_snapshot, control_points: pts, proposed_object: proj };
  }

  function importScenario(text, state) {
    try {
      return { ok: true, code: null, message: "", state: validate(text) };
    } catch (e) {
      if (!(e instanceof ImportError)) return { ok: false, code: "internal_error", message: String(e && e.message), state };
      return { ok: false, code: e.code, message: e.message, state };
    }
  }

  function compute(state) {
    const recs = D.cities[state.city].places.filter((p) => p.group === state.category);
    const proj = state.proposed_object;
    return state.control_points.map((cp) => {
      let best = null;
      for (const r of recs) {
        const d = haversineM(cp.lon, cp.lat, r.lon, r.lat);
        if (best === null || d < best.d || (d === best.d && r.id < best.id)) best = { d, id: r.id };
      }
      const dp = proj ? haversineM(cp.lon, cp.lat, proj.lon, proj.lat) : null;
      const before = best ? best.d : null;
      let after = before, delta = before === null ? null : 0;
      if (proj) {
        after = before === null ? dp : Math.min(before, dp);
        delta = before === null ? null : before - after;
      }
      return { id: cp.id, before_m: before, after_m: after, delta_m: delta, nearest_before_id: best ? best.id : null,
               nearest_after: proj && (before === null || dp < before) ? proj.id : (best ? best.id : null),
               note: before === null ? "В срезе нет исходных записей; улучшение не вычисляется" : null };
    });
  }

  // Export: the source copy (inputs) and derived values are kept apart; derived values are recomputed on import.
  function exportScenario(state) {
    const doc = { schema_version: SCHEMA, city_id: state.city, source_snapshot: state.snapshot, category: state.category,
                  control_points: state.control_points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat })),
                  proposed_object: state.proposed_object ? { ...state.proposed_object } : null,
                  results: { derived: true, recomputed_on_import: true, rows: compute(state) } };
    return JSON.stringify(doc, null, 1);
  }

  return { snapshot, initialState, importScenario, compute, exportScenario, parseStrict, haversineM };
}

module.exports = { makeImporter, parseStrict, haversineM, ImportError, MAX_BYTES, SCHEMA };
