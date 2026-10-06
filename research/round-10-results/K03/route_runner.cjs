// K03 r10: headless-прогон routing.js (без DOM). node route_runner.cjs <request.json> [<routing.js>]
// request = {graphs: {key: {path} | {graph}}, verify_hash: bool, tamper: [key], queries: [{id, graph, origin, target, method, policy}]}
// Печатает {results: [{id, ok, result | error:{code}}], hash: {key: "ok" | code}}.
"use strict";
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const req = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const R = require(path.resolve(process.argv[3] || path.join(__dirname, "routing.js")));
const sha256hex = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
const G = {}, hash = {};
for (const [key, src] of Object.entries(req.graphs)) {
  const g = src.path ? JSON.parse(fs.readFileSync(path.resolve(__dirname, src.path), "utf8")) : src.graph;
  try { G[key] = R.prepare(g, req.verify_hash ? { sha256hex } : undefined); hash[key] = req.verify_hash ? "ok" : "not_checked"; }
  catch (e) { hash[key] = e.code || String(e); }
  if ((req.tamper || []).includes(key)) {
    const t = JSON.parse(JSON.stringify(g)); t.edges[0].len_mm += 1;
    try { R.prepare(t, { sha256hex }); hash[key + ":tampered"] = "accepted"; } catch (e) { hash[key + ":tampered"] = e.code || String(e); }
  }
}
const out = [];
for (const q of req.queries) {
  try {
    const g = G[q.graph];
    const r = q.method === "geodesic" ? R.geodesic(g, q.origin, q.target) : R.route(g, q.origin, q.target, q.policy);
    out.push({ id: q.id, ok: true, result: r });
  } catch (e) { out.push({ id: q.id, ok: false, error: { code: e.code || "crash", detail: String(e && e.stack || e).slice(0, 300) } }); }
}
process.stdout.write(JSON.stringify({ results: out, hash }));
