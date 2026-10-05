// K02 r6: минимальное воспроизведение T7 на web/facts.js сборки 064ed25.
// node repro_t7_city_substitution.cjs <app-root>
const fs = require("fs"), path = require("path"), vm = require("vm");
const root = process.argv[2], c = {}; vm.createContext(c); c.window = c;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(root, "web", f), "utf8"), c);
const F = require(path.resolve(root, "web/facts.js"));
const ev = JSON.parse(JSON.stringify(c.CITY_OBS));
ev.cities.shymkent.observations = ev.cities.astana.observations;          // наблюдения kz.astana под ключом shymkent
const b = F.buildCatalog(c.CITY_EVIDENCE, ev, "shymkent", new Set(F.GROUP_ORDER));
const f = b.catalog.get(`${b.city}/${b.scenario}/segments.foot_unknown`);
console.log(JSON.stringify({ accepted: true, fact_id: f.id, value: f.value, source_obs: f.source,
  source_city: ev.cities.shymkent.observations.find((o) => o.obs_id === f.source).city_id }));
