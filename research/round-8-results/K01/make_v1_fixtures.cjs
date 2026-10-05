// Writes fixtures/v1/<city>_v1_from_build_whatif.json with the BUILD's own web/whatif.js exportScenario (provenance: build SHA).
//   node make_v1_fixtures.cjs --app-root APP && python3 make_fixtures.py --app-root APP --build-sha SHA   (refreshes MANIFEST)
const fs = require("fs"), path = require("path");
const APP = process.argv[process.argv.indexOf("--app-root") + 1];
const { loadApp } = require("./load_app.cjs");
const { data: D, F } = loadApp(APP);
const X = require(path.join(path.resolve(APP), "web", "whatif.js"));
const dir = path.join(__dirname, "fixtures", "v1"); fs.mkdirSync(dir, { recursive: true });
for (const city of ["shymkent", "astana"]) {
  const bb = D.cities[city].bbox, mid = (i) => [bb[0] + (bb[2] - bb[0]) * (0.3 + 0.2 * i), bb[1] + (bb[3] - bb[1]) * 0.5];
  const sc = { schema_version: X.SCHEMA, city_id: city, source_snapshot: X.sourceSnapshot(D, city, F), category: "school",
    control_points: [0, 1].map((i) => ({ id: `p${i}`, lon: mid(i)[0], lat: mid(i)[1] })),
    proposed_object: { id: "proj1", lon: mid(2)[0], lat: mid(2)[1], category: "school", kind: "hypothetical" } };
  fs.writeFileSync(path.join(dir, `${city}_v1_from_build_whatif.json`), X.exportScenario(sc, D, F));
}
console.log("wrote fixtures/v1 (synthetic v1 scenarios exported by BUILD whatif.js)");
