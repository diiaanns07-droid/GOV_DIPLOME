// K07 r10: ветка «подложка загрузилась» без сети. Стиль OpenFreeMap подменяется минимальным локальным стилем
// (только фон), чтобы MapLibre выдал load и mapReady=true. Это НЕ проверка 3D-зданий (тайлов зданий нет) —
// проверяется только, что путь «Проверка школ» работает через камеру MapLibre (map.project / слои gov-*).
// Usage: node k07r10_stubmap.cjs --url http://127.0.0.1:8502/ --shots DIR --out result.json
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const URL = arg("--url", "http://127.0.0.1:8502/"), SHOTS = arg("--shots", "."), OUT = arg("--out", null);
const results = []; const check = (id, ok, info) => { results.push({ id, ok: !!ok, info }); console.log(`${ok ? "PASS" : "FAIL"} ${id} ${info ? JSON.stringify(info).slice(0, 240) : ""}`); };
const STYLE = { version: 8, name: "stub", sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef2ea" } }] };
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"] });
  const pg = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = [];
  pg.on("pageerror", (e) => errs.push(String(e)));
  await pg.route("https://tiles.openfreemap.org/styles/liberty", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(STYLE) }));
  await pg.route("https://tiles.openfreemap.org/planet", (r) => r.abort());
  await pg.goto(URL, { waitUntil: "load" });
  await pg.waitForFunction(() => typeof mapReady !== "undefined" && mapReady, null, { timeout: 20000 }).catch(() => {});
  const ready = await pg.evaluate(() => typeof mapReady !== "undefined" && mapReady);
  check("stub_mapReady", ready);
  if (!ready) { await b.close(); if (OUT) fs.writeFileSync(OUT, JSON.stringify({ url: URL, results }, null, 1)); process.exit(1); }
  await pg.click("#govtech-toggle"); await pg.waitForTimeout(1200);
  const s1 = await pg.evaluate(() => ({ page: GOVTECH.page, offline: !document.getElementById("gov-offline").hidden,
    feats: map.querySourceFeatures ? map.getSource("gov-records")._data?.features?.length ?? null : null, vis: map.getLayoutProperty("gov-sources", "visibility") }));
  check("stub_path_page_records_layer", s1.page === "path" && !s1.offline && s1.vis === "visible" && s1.feats === 15, s1);
  await pg.evaluate(() => { const P = CITY_SCHOOL_PATH, c = CITY_APP.ui.D.cities[CITY_APP.state.city].bbox; P.example();
    P.state.A = { lon: c[0] + (c[2] - c[0]) * .3, lat: c[1] + (c[3] - c[1]) * .3 }; P.state.B = { lon: c[0] + (c[2] - c[0]) * .7, lat: c[1] + (c[3] - c[1]) * .65 }; P.go(4); });
  await pg.waitForTimeout(800);
  const s2 = await pg.evaluate(() => ({ lines: document.querySelectorAll("#gov-overlay line").length, changed: document.querySelectorAll("#gov-overlay line.sp-changed").length,
    inside: [...document.querySelectorAll("#gov-overlay circle")].every((c) => +c.getAttribute("cx") > 0 && +c.getAttribute("cx") < innerWidth) }));
  check("stub_lines_projected", s2.lines === 9 && s2.changed > 0 && s2.inside, s2);
  // клик по записи школы на карте MapLibre открывает карточку источника
  const pt = await pg.evaluate(() => { const p = CITY_APP.ui.D.cities[CITY_APP.state.city].places.find((x) => x.group === "school"); const q = map.project([p.lon, p.lat]); const r = document.getElementById("map").getBoundingClientRect(); return [q.x + r.left, q.y + r.top]; });
  await pg.mouse.click(pt[0], pt[1]); await pg.waitForTimeout(300);
  check("stub_click_school_record", await pg.evaluate(() => GOVTECH.page === "data" && !!document.getElementById("gov-selection").textContent));
  await pg.click('#gov-panel [data-page="path"]');
  await pg.click("#toggle-3d"); await pg.waitForTimeout(1200);
  const pitch = await pg.evaluate(() => map.getPitch());
  check("stub_3d_toggle_tilts_camera", pitch > 30, { pitch, note: "здания не проверены: тайлов нет (NOT_RUN)" });
  await pg.screenshot({ path: path.join(SHOTS, "after_1440_stubmap_3d.png") });
  await pg.click("#govtech-toggle"); await pg.waitForTimeout(500);
  const back = await pg.evaluate(() => ({ markers: markers.filter((m) => m.el.style.display !== "none").length, overlay: getComputedStyle(document.getElementById("gov-overlay")).display, vis: map.getLayoutProperty("gov-sources", "visibility") }));
  check("stub_return_restores_simulator_layers", back.markers > 0 && back.overlay === "none" && back.vis === "none", back);
  check("stub_no_page_errors", errs.length === 0, errs.slice(0, 3));
  await b.close();
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ url: URL, results }, null, 1));
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})();
