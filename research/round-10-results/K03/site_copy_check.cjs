// K03 r10: проверка патча на КОПИИ основного сайта d2ff344 (не общий сайт и не интеграция BUILD).
//   NODE_PATH="$(npm root -g)" node site_copy_check.cjs <url_patched> <url_unpatched> <out.json>
// Открывает главную страницу копии, ждёт загрузки, проверяет window.K03_ROUTING / K03_SCHOOL_ROUTING, загружает граф с сервера копии,
// проверяет graph_sha256 функцией CITY_FACTS.sha256hex страницы, считает матрицу и сравнивает с Node. Ошибки страницы сравниваются с копией без патча.
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const R = require("./routing.js"), A = require("./school-access-routing.js");
const [urlP, urlB, outFile] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch();
  const visit = async (url, run) => {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [], external = [];
    page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)); });
    page.on("request", (r) => { if (!r.url().startsWith(url)) external.push(new URL(r.url()).host); });
    await page.goto(url, { waitUntil: "load" });
    await page.waitForTimeout(1500);
    const res = run ? await page.evaluate(run.fn, run.arg) : null;
    await page.close();
    return { errors, external_hosts: [...new Set(external)].sort(), res };
  };
  const cases = Object.fromEntries(["shymkent", "astana"].map((c) => [c, JSON.parse(fs.readFileSync(path.join(__dirname, `examples/${c}_case.json`), "utf8"))]));
  const P = await visit(urlP, { arg: cases, fn: async (cases) => {
    const out = { has_modules: !!(window.K03_ROUTING && window.K03_SCHOOL_ROUTING), plan_untouched: !!window.CITY_PLAN, cities: {} };
    for (const city of ["shymkent", "astana"]) {
      const g = await (await fetch("/govtech/k03/" + city + ".graph.json")).json();
      const G = K03_ROUTING.prepare(g, { sha256hex: CITY_FACTS.sha256hex });
      const m = K03_SCHOOL_ROUTING.distanceMatrix({ ...cases[city], parameters: { ...cases[city].parameters, distance_method: "pedestrian-v1", routing_policy_id: "pedestrian-v1-exploratory" } }, G);
      out.cities[city] = { graph_sha256: G.g.graph_sha256, rows: m.rows };
    }
    return out;
  } });
  const B = await visit(urlB, null);
  const results = [];
  const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: ok ? undefined : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? " — " + String(detail).slice(0, 300) : "")); };
  check("главная страница копии загружает window.K03_ROUTING и K03_SCHOOL_ROUTING рядом с CITY_PLAN", P.res.has_modules && P.res.plan_untouched);
  for (const city of ["shymkent", "astana"]) {
    const g = JSON.parse(fs.readFileSync(path.join(__dirname, `graph/${city}.graph.json`), "utf8"));
    const node = A.distanceMatrix({ ...cases[city], parameters: { ...cases[city].parameters, distance_method: "pedestrian-v1", routing_policy_id: "pedestrian-v1-exploratory" } }, R.prepare(g)).rows;
    check(`${city}: граф с сервера копии прошёл проверку graph_sha256 (CITY_FACTS.sha256hex)`, P.res.cities[city].graph_sha256 === g.graph_sha256);
    check(`${city}: ${node.length} строк матрицы в странице сайта = Node`, JSON.stringify(P.res.cities[city].rows) === JSON.stringify(node));
  }
  const newErr = P.errors.filter((e) => !B.errors.includes(e));
  check("патч не добавляет ошибок страницы относительно копии без патча", newErr.length === 0, newErr.join(" | "));
  const newHosts = P.external_hosts.filter((h) => !B.external_hosts.includes(h));
  check("патч не добавляет внешних запросов", newHosts.length === 0, newHosts.join(" "));
  const v = browser.version();
  await browser.close();
  fs.writeFileSync(outFile, JSON.stringify({ what: "копия основного сайта d2ff344 + patches/build_d2ff344_k03_routing_assets.patch + install_for_build.py; не общий сайт",
    browser: `Chromium ${v}`, results, patched_page: { errors: P.errors, external_hosts: P.external_hosts }, unpatched_page: { errors: B.errors, external_hosts: B.external_hosts } }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
