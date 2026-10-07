/* R04 test stand: contract mock API + harness page + editor files.
 * Used by e2e.test.cjs; also runnable by hand: node tests/civic/R04/stand.cjs [port]
 * Credentials are generated per run and live only in memory/stdout; nothing is written to the repo.
 * MapLibre is not vendored on this branch: it is read from the pinned app snapshot via `git show` into a temp dir.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const os = require("os");
const crypto = require("crypto");
const { execFileSync } = require("child_process");
const { createMockServer } = require("./contract_mock.cjs");

const REPO = path.resolve(__dirname, "../../..");
const APP_SNAPSHOT = "6de3f253d8ec0743450259f9f13722c16cd36099";  // CODE_SHA of the round-10 build (MapLibre 5.6.2)

function vendorDir() {
  const local = path.join(REPO, "web/vendor/maplibre-gl.js");
  if (fs.existsSync(local)) return path.join(REPO, "web/vendor");
  const dir = path.join(os.tmpdir(), "civic-r04-vendor-" + APP_SNAPSHOT.slice(0, 12));
  fs.mkdirSync(dir, { recursive: true });
  for (const f of ["maplibre-gl.js", "maplibre-gl.css"]) {
    const out = path.join(dir, f);
    if (!fs.existsSync(out)) fs.writeFileSync(out, execFileSync("git", ["-C", REPO, "show", APP_SNAPSHOT + ":web/vendor/" + f], { maxBuffer: 64 * 1024 * 1024 }));
  }
  return dir;
}

async function startStand(opts) {
  const o = opts || {};
  const creds = { username: "editor-test", password: crypto.randomBytes(12).toString("base64url") };
  const v = vendorDir();
  const mock = createMockServer({
    users: [{ username: creds.username, password: creds.password, name: "Тестовый редактор", role: "editor" }],
    pageSize: o.pageSize || 50,
    seed: o.seed || [],
    clock: o.clock,
    static: {
      "/": path.join(__dirname, "harness/index.html"),
      "/vendor/maplibre-gl.js": path.join(v, "maplibre-gl.js"),
      "/vendor/maplibre-gl.css": path.join(v, "maplibre-gl.css"),
    },
    staticDirs: [
      { prefix: "/harness/", dir: path.join(__dirname, "harness") },
      { prefix: "/web/civic/editor/", dir: path.join(REPO, "web/civic/editor") },
    ],
  });
  const url = await mock.listen(o.port || 0);
  return { url, mock, creds, close: () => mock.close() };
}

module.exports = { startStand, APP_SNAPSHOT };

if (require.main === module) {
  startStand({ port: Number(process.argv[2]) || 0 }).then((s) => {
    console.log("R04 stand (contract mock, NOT R02): " + s.url + "/");
    console.log("in-memory test login: " + s.creds.username + " / " + s.creds.password);
  });
}
