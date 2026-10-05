/* K11 round 8 — Unicode-safe export/import of city-plan-v2 scenario files (browser + Node, no DOM needed).
 * Export: UTF-8 text without BOM, LF only, Cyrillic/Kazakh kept as letters, non-finite numbers and lone surrogates
 * rejected BEFORE stringify (JSON.stringify would silently turn NaN into null and a lone surrogate into "\udXXX"),
 * optional derived_results clearly labelled.
 * Import: from bytes (preferred: invalid UTF-8 such as a Windows-1251 "ANSI" save is an error, not mojibake) or from
 * text; UTF-8 BOM (Windows Notepad) skipped, UTF-16 with BOM decoded; <= 256 KiB of UTF-8; strict JSON (duplicate
 * keys, NaN/Infinity, 1e999, trailing data rejected); then validatePlanScenario of the engine; derived_results are
 * never trusted.
 * Browser: window.CITY_PLAN_EXPORT ; Node: require().
 */
(function (root) {
  "use strict";
  const MAX_BYTES = 256 * 1024;
  const ORDER = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
    "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"];
  const LONE_SURROGATE = /\p{Cs}/u;  // in u-mode a valid pair is one code point, so only lone halves match
  const LONE_SURROGATE_G = /\p{Cs}/gu;
  class ExportError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }

  function utf8Length(s) { let n = 0; for (const ch of s) { const c = ch.codePointAt(0); n += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4; } return n; }
  function assertExportable(v, where) {
    if (typeof v === "number" && !Number.isFinite(v)) throw new ExportError("non_finite_number", where);
    if (typeof v === "string" && LONE_SURROGATE.test(v)) throw new ExportError("lone_surrogate", where);
    if (Array.isArray(v)) v.forEach((x, i) => assertExportable(x, where + "[" + i + "]"));
    else if (v && typeof v === "object") for (const [k, x] of Object.entries(v)) { assertExportable(k, where + " key"); assertExportable(x, where + "." + k); }
  }

  /* scenario: validated city-plan-v2 object; env: runner envelope or null (only an optimal result is attached). */
  function exportPlanFile(scenario, env, label) {
    const out = {};
    for (const k of ORDER) out[k] = scenario[k];
    if (env && env.status === "optimal" && env.result && env.result.objectives) {
      const r = env.result;
      out.derived_results = { note: "derived; recomputed on import, never trusted", problem_digest: env.problem_digest,
        metric_version: r.metric_version, engine: r.engine, status: r.status,
        objectives: Object.fromEntries(Object.entries(r.objectives).map(([k, v]) => [k, { selected_ids: v.selected_ids, metrics: v.metrics }])),
        pareto: r.pareto };
    }
    assertExportable(out, "$");
    const text = JSON.stringify(out, null, 1) + "\n";  // JSON.stringify keeps non-ASCII letters as they are, LF only
    if (utf8Length(text) > MAX_BYTES) throw new ExportError("too_large", utf8Length(text) + " bytes");
    return { filename: suggestFilename(scenario, label), text, mime: "application/json;charset=utf-8" };
  }

  // Windows-safe, NFC, readable file name: forbidden <>:"/\|?* and control characters -> "_", no trailing dot/space,
  // reserved device names (also with an extension, also COM¹..LPT³) prefixed, at most 120 UTF-16 units before ".json".
  const RESERVED = /^(con|prn|aux|nul|conin\$|conout\$|com[0-9¹²³]|lpt[0-9¹²³])(\..*)?$/i;
  const MAX_NAME_UNITS = 120;
  function suggestFilename(scenario, label) {
    const cat = { school: "школы", outpatient_clinic: "поликлиники" }[scenario.category] || "объекты";
    const city = { shymkent: "Шымкент", astana: "Астана" }[scenario.city_id] || String(scenario.city_id);
    return safeFilename(`план_${city}_${cat}${label ? "_" + label : ""}`);
  }
  function safeFilename(name) {
    const tidy = (x) => x.replace(/^\s+/u, "").replace(/[.\s]+$/u, "");
    let s = tidy(String(name).normalize("NFC").replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g, "_").replace(LONE_SURROGATE_G, "_"));
    if (!s) s = "plan";
    if (RESERVED.test(s)) s = "_" + s;
    if (s.length > MAX_NAME_UNITS) {  // cut on a code point boundary, never inside a surrogate pair
      let t = "";
      for (const ch of s) { if (t.length + ch.length > MAX_NAME_UNITS) break; t += ch; }
      s = tidy(t) || "plan";
    }
    return s + ".json";
  }

  // ---------- strict JSON parser (duplicate keys, NaN/Infinity tokens, overflow, lone surrogates, trailing data) ----------
  const RE_STR = /"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"/y;
  const RE_NUM = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
  function parseStrict(text) {
    let i = 0, depth = 0;
    const err = (m) => { throw new ExportError("bad_json", m + " at " + i); };
    const ws = () => { while (i < text.length && (text[i] === " " || text[i] === "\t" || text[i] === "\r" || text[i] === "\n")) i++; };
    function value() {
      ws();
      const c = text[i];
      if (c === "{" || c === "[") {
        if (++depth > 64) err("nesting deeper than 64");
        const v = c === "{" ? obj() : arr();
        depth--; return v;
      }
      if (c === '"') return str();
      if (c === "t" && text.startsWith("true", i)) { i += 4; return true; }
      if (c === "f" && text.startsWith("false", i)) { i += 5; return false; }
      if (c === "n" && text.startsWith("null", i)) { i += 4; return null; }
      return num();
    }
    function obj() {
      i++; const o = {}; const seen = new Set(); ws();
      if (text[i] === "}") { i++; return o; }
      for (;;) {
        ws(); if (text[i] !== '"') err("key expected");
        const k = str();
        if (seen.has(k)) throw new ExportError("duplicate_key", k);
        seen.add(k); ws(); if (text[i] !== ":") err("':' expected"); i++;
        Object.defineProperty(o, k, { value: value(), enumerable: true, writable: true, configurable: true });  // "__proto__" stays data
        ws(); if (text[i] === ",") { i++; continue; } if (text[i] === "}") { i++; return o; } err("',' or '}' expected");
      }
    }
    function arr() {
      i++; const a = []; ws();
      if (text[i] === "]") { i++; return a; }
      for (;;) { a.push(value()); ws(); if (text[i] === ",") { i++; continue; } if (text[i] === "]") { i++; return a; } err("',' or ']' expected"); }
    }
    function str() {
      RE_STR.lastIndex = i;
      const m = RE_STR.exec(text);
      if (!m) err("bad string");
      i += m[0].length;
      const s = JSON.parse(m[0]);
      if (LONE_SURROGATE.test(s)) throw new ExportError("lone_surrogate", "string ending at " + i);
      return s;
    }
    function num() {
      RE_NUM.lastIndex = i;
      const m = RE_NUM.exec(text);
      if (!m) err("unexpected token");
      i += m[0].length;
      const v = Number(m[0]);
      if (!Number.isFinite(v)) throw new ExportError("non_finite_number", m[0]);
      return v;
    }
    const v = value(); ws();
    if (i !== text.length) err("trailing data");
    return v;
  }

  /* Decode file bytes: UTF-8 (optional BOM) strictly; UTF-16 LE/BE only with a BOM. Returns {text, encoding, bom}. */
  function decodePlanBytes(bytes) {
    const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    if (b.length > 2 * MAX_BYTES + 4) throw new ExportError("too_large", b.length + " bytes");
    let enc = "utf-8", skip = 0;
    if (b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf) skip = 3;
    else if (b[0] === 0xff && b[1] === 0xfe) { enc = "utf-16le"; skip = 2; }
    else if (b[0] === 0xfe && b[1] === 0xff) { enc = "utf-16be"; skip = 2; }
    let text;
    try { text = new TextDecoder(enc, { fatal: true, ignoreBOM: true }).decode(b.subarray(skip)); }
    catch (e) { throw new ExportError(enc === "utf-8" ? "not_utf8" : "bad_utf16", "save the file as UTF-8 (Windows-1251/ANSI is not accepted)"); }
    return { text, encoding: enc, bom: skip > 0 };
  }

  /* engine: CITY_PLAN_CORE-compatible (validatePlanScenario). Returns {scenario, derived_ignored, bom}. */
  function importPlanText(text, context, engine) {
    if (typeof text !== "string") throw new ExportError("bad_input", "text expected");
    const bom = text.charCodeAt(0) === 0xfeff;
    if (bom) text = text.slice(1);
    if (utf8Length(text) > MAX_BYTES) throw new ExportError("too_large", "> " + MAX_BYTES + " bytes");
    if (text.includes("\ufffd")) throw new ExportError("replacement_char", "U+FFFD found: the file was probably decoded from a non-UTF-8 encoding");
    const parsed = parseStrict(text);
    const scenario = engine.validatePlanScenario(parsed, context);  // drops derived_results; typed PlanError otherwise
    return { scenario, derived_ignored: !!(parsed && typeof parsed === "object" && "derived_results" in parsed), bom };
  }
  function importPlanBytes(bytes, context, engine) {
    const d = decodePlanBytes(bytes);
    const r = importPlanText(d.text, context, engine);
    return Object.assign(r, { encoding: d.encoding, bom: d.bom });
  }

  /* Browser only: read a File from <input type=file> as bytes (never as lossy text). */
  async function readPlanFile(file, context, engine) {
    return importPlanBytes(new Uint8Array(await file.arrayBuffer()), context, engine);
  }
  /* Browser only: offer the text as a file download (Blob + <a download>). */
  function downloadPlanFile(file, doc) {
    const d = doc || document;
    const url = URL.createObjectURL(new Blob([file.text], { type: file.mime }));
    const a = d.createElement("a");
    a.href = url; a.download = file.filename; d.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const api = { MAX_BYTES, ExportError, exportPlanFile, importPlanText, importPlanBytes, decodePlanBytes, readPlanFile,
    parseStrict, suggestFilename, safeFilename, downloadPlanFile, utf8Length };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CITY_PLAN_EXPORT = api;
})(typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : globalThis);
