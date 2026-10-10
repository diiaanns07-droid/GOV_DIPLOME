// Minimal read-only static server for the R03 stand and browser tests.
// Usage: node tests/civic/R12/map/serve.mjs [port]   (binds 127.0.0.1 only)
import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".txt": "text/plain; charset=utf-8" };
// Only what the stand needs; nothing else in the repository is served.
const ALLOWED = ["web/", "tests/civic/R12/map/stand/", "tests/civic/R12/map/fixtures/"];

export function createServer() {
  return http.createServer(async (req, res) => {
    try {
      if (req.method !== "GET" && req.method !== "HEAD") { res.writeHead(405).end(); return; }
      let rel = decodeURIComponent(new URL(req.url, "http://x").pathname).replace(/^\/+/, "");
      if (rel.endsWith("/") || rel === "") rel += "index.html";
      const abs = path.resolve(ROOT, rel);
      if (!abs.startsWith(ROOT + path.sep) || !ALLOWED.some((p) => rel.startsWith(p)) || rel.includes("..")) { res.writeHead(404).end(); return; }
      const s = await stat(abs).catch(() => null);
      if (!s || !s.isFile()) { res.writeHead(404).end(); return; }
      res.writeHead(200, { "content-type": TYPES[path.extname(abs)] || "application/octet-stream", "cache-control": "no-store", "x-content-type-options": "nosniff" });
      res.end(req.method === "HEAD" ? undefined : await readFile(abs));
    } catch (e) {
      res.writeHead(500).end();
    }
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.argv[2] || 8765);
  createServer().listen(port, "127.0.0.1", () => console.log("R03 stand: http://127.0.0.1:" + port + "/tests/civic/R12/map/stand/"));
}
