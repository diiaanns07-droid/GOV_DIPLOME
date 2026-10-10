// R01 round 12: the resident path "open the city -> find a place -> understand what happens there -> act"
// at 360x800, 768x1024 and 1440x900 (layout overlaps, map notice, search, district, camera/3D state).
// Usage: node tests/civic/R01/browser/r12_city.cjs <out_dir> [--empty]
// Starts `python3 -B app.py` on a free port with a temporary SQLite file: R02 init + R05's synthetic
// slice (or nothing with --empty). No editor account is needed: a resident session has no login.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r12-out");
const EMPTY = process.argv.includes("--empty");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff/i;
const VIEWPORTS = [[360, 800], [768, 1024], [1440, 900]];
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined && detail !== null ? " — " + JSON.stringify(detail).slice(0, 400) : "")); };
const notRun = (name, reason) => { checks.push({ name, status: "NOT_RUN", detail: reason }); console.log("NOT_RUN " + name + " — " + reason); };
// R03's intermittent "Image civic-r03-demo-ring could not be loaded" (race after the offline style
// swap; R03-owned, fix proposed in research/round-13-results/R01/proposed/r03_r01_proposal.patch) is
// reported as its own FAIL so it neither hides other page errors nor masquerades as an R01 error.
const R03_RING = /Image "civic-r03-demo-ring" could not be loaded/;
// Лента работ раунда 13 («К объектам», список) в Birge скрыта; этот тест проверяет именно её — открываем с ?tools=all.
const TOOLS = "?tools=all";
function checkPageErrors(name, errs) {
  const ring = errs.filter((e) => R03_RING.test(e)), other = errs.filter((e) => !R03_RING.test(e));
  check(name, other.length === 0, other);
  if (ring.length) check(name + " — R03 demo-ring image race (R03-owned)", false, ring.length + " warning(s)");
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  if (!EMPTY) run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

// Телефон: раскрыть свёрнутую панель «Территория» (после выбора улицы она сворачивается сама — карта свободна).
async function openExplore(page) {
  await page.evaluate(() => { const b = document.querySelector(".civic-explore-toggle"), box = document.querySelector(".civic-explore");
    if (b && box && box.dataset.open !== "true" && getComputedStyle(b).display !== "none") b.click(); });
  await page.waitForTimeout(300);
}

async function openPage(browser, base, w, h, hash = "") {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) page.errs.push(m.type() + ": " + m.text()); });
  await page.goto(base + TOOLS + hash);
  await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady, null, { timeout: 40000 });
  await page.waitForSelector(".civic-explore", { timeout: 15000 });
  await page.waitForTimeout(1200);
  // B3: на телефоне панель «Территория» свёрнута в кнопку 48 px — этот тест проверяет саму панель, раскрываем её.
  if (mobile) await openExplore(page);
  return { ctx, page };
}

// Visible rectangles of the floating controls; overlapping pairs are reported.
const layout = (page) => page.evaluate(() => {
  const rect = (sel) => { const e = document.querySelector(sel); if (!e || !e.getClientRects().length || getComputedStyle(e).visibility === "hidden") return null;
    const b = e.getBoundingClientRect(); return b.width && b.height ? { l: b.left, t: b.top, r: b.right, b: b.bottom } : null; };
  const boxes = { topbar: rect(".topbar"), explore: rect(".civic-explore"), tools: rect(".map-tools"), panel: rect("#civic-panel") };
  const status = document.getElementById("map-status");
  let statusInfo = null;
  if (status && !status.classList.contains("hidden") && status.getClientRects().length) {
    const b = status.getBoundingClientRect();
    const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
    statusInfo = { text: status.textContent.trim().slice(0, 80), readable: !!hit && (hit === status || status.contains(hit)), insideExplore: !!status.closest(".civic-explore") };
  }
  const over = [];
  const names = Object.keys(boxes).filter((k) => boxes[k]);
  for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) {
    const a = boxes[names[i]], c = boxes[names[j]];
    const ix = Math.min(a.r, c.r) - Math.max(a.l, c.l), iy = Math.min(a.b, c.b) - Math.max(a.t, c.t);
    if (ix > 1 && iy > 1) over.push(names[i] + "×" + names[j]);
  }
  return { scrollW: document.documentElement.scrollWidth, innerW: innerWidth, over, status: statusInfo,
    explore: boxes.explore && Math.round(boxes.explore.r - boxes.explore.l) };
});


// A resident opens a shared link to a record, then reloads: no account, no staff calls, card and view
// line agree, the record is in the free map area.
async function directLinkAndReload(browser, base, w, h, item) {
  const tag = `${w}x${h}`;
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile });
  const page = await ctx.newPage();
  const staffCalls = [], errs = [];
  page.on("request", (r) => { if (/\/api\/civic\/v1\/staff/.test(r.url())) staffCalls.push(r.url()); });
  page.on("pageerror", (e) => errs.push(e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) errs.push(m.text()); });
  const state = async () => page.evaluate((id) => {
    const card = document.querySelector("#civic-map-root .civic-r03-card");
    const feats = map.querySourceFeatures("civic-r03-objects", { filter: ["==", ["get", "cid"], id] });
    const pts = []; const walk = (c) => { if (typeof c[0] === "number") pts.push(c); else c.forEach(walk); };
    feats.forEach((f) => walk(f.geometry.coordinates));
    let covered = null;
    if (pts.length) {
      const p = map.project([pts.reduce((a, q) => a + q[0], 0) / pts.length, pts.reduce((a, q) => a + q[1], 0) / pts.length]);
      covered = ["#civic-panel", ".civic-explore", ".map-tools", ".topbar"].filter((sel) => {
        const e = document.querySelector(sel); if (!e || !e.getClientRects().length || getComputedStyle(e).visibility === "hidden") return false;
        const b = e.getBoundingClientRect(); return p.x >= b.left && p.x <= b.right && p.y >= b.top && p.y <= b.bottom; });
      if (p.x < 0 || p.y < 0 || p.x > innerWidth || p.y > innerHeight) covered.push("off-screen");
    }
    return { selected: window.CivicShell.selected, hash: location.hash, cardTitle: card && !card.hidden ? (card.querySelector("h2, h3")?.textContent || "").trim() : null,
      view: document.querySelector(".civic-explore-view")?.textContent || "", covered,
      session: window.CivicShell.api.session.authenticated };
  }, item.id);
  await page.goto(base + TOOLS + "#object=" + encodeURIComponent(item.id));
  await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady, null, { timeout: 40000 });
  await page.waitForFunction((id) => window.CivicShell.selected === id && document.querySelector("#civic-map-root .civic-r03-card"), item.id, { timeout: 15000 }).catch(() => null);
  await page.waitForTimeout(2600);
  const first = await state();
  check(`${tag}: direct link opens the record card for a resident without an account`, first.selected === item.id && !!first.cardTitle && first.session === false, first);
  check(`${tag}: direct link: record in the free map area, view line names it`, Array.isArray(first.covered) && first.covered.length === 0 && /Открыта запись/.test(first.view), first);
  await page.screenshot({ path: path.join(OUT, `06_direct_link_${tag}.png`) });
  await page.reload();
  await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady, null, { timeout: 40000 });
  await page.waitForFunction((id) => window.CivicShell.selected === id && document.querySelector("#civic-map-root .civic-r03-card"), item.id, { timeout: 15000 }).catch(() => null);
  await page.waitForTimeout(2600);
  const again = await state();
  check(`${tag}: F5 keeps the city mode, the record and its place`, again.selected === item.id && !!again.cardTitle && Array.isArray(again.covered) && again.covered.length === 0, again);
  check(`${tag}: resident session makes no staff API calls`, staffCalls.length === 0, staffCalls.slice(0, 3));
  checkPageErrors(`${tag}: no page errors on direct link / reload`, errs);
  await ctx.close();
}

// City -> training -> civic and city -> school -> civic: the navigation box goes away and comes back,
// the map notice is readable in every mode, training districts are hidden again in the city mode.
async function modeRoundTrip(browser, base, w, h) {
  const tag = `${w}x${h}`;
  const { ctx, page } = await openPage(browser, base, w, h);
  const probe = () => page.evaluate(() => {
    const st = document.getElementById("map-status");
    let readable = null;
    if (st && !st.classList.contains("hidden") && st.getClientRects().length) {
      const b = st.getBoundingClientRect(); const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      readable = !!hit && (hit === st || st.contains(hit));
    }
    return { mode: window.CivicShell.mode, explore: !!document.querySelector(".civic-explore"), statusInExplore: !!st?.closest(".civic-explore"), readable,
      districts: map.getLayer("district-fill") ? map.getLayoutProperty("district-fill", "visibility") : "absent",
      view: document.querySelector(".civic-explore-view")?.textContent || null, scrollW: document.documentElement.scrollWidth };
  });
  for (const other of ["training", "school"]) {
    // Round 14: old modes are reachable only by link (#training / #school); «Город» returns to the map.
    await page.evaluate((m) => { location.hash = "#" + m; }, other);
    await page.waitForTimeout(1500);
    if (other === "training") {
      // The training district view keeps its soft 22° tilt without switching the 3D button on.
      await page.evaluate(() => selectDistrict("esil"));
      await page.waitForTimeout(2200);
      const t = await page.evaluate(() => ({ pitch: Math.round(map.getPitch()), pressed: document.getElementById("toggle-3d").getAttribute("aria-pressed") }));
      check(`${tag}: training district view: soft tilt, 3D button stays off`, t.pressed === "false" && t.pitch < 30, t);
    }
    const away = await probe();
    check(`${tag}: ${other} mode: no navigation box, map notice back in place and readable`, away.mode === other && !away.explore && !away.statusInExplore && away.readable !== false && away.scrollW <= w, away);
    await page.click("#civic-modes [data-mode=civic]");
    await page.waitForTimeout(1800);
    const back = await probe();
    check(`${tag}: back from ${other}: navigation box, notice inside it, city overview, training districts hidden`,
      back.mode === "civic" && back.explore && (back.readable === null || (back.statusInExplore && back.readable)) && /Обзор: вся Астана/.test(back.view || "") && back.districts !== "visible", back);
  }
  checkPageErrors(`${tag}: no page errors across mode switches`, page.errs);
  await ctx.close();
}

// Empty registry (no published records): stated at city level, distinct from "nothing in frame".
async function emptyRegistry(browser, base) {
  for (const [w, h] of VIEWPORTS) {
    const tag = `${w}x${h}`;
    const { ctx, page } = await openPage(browser, base, w, h);
    await page.waitForSelector(".civic-explore-registry:not([hidden])", { timeout: 15000 }).catch(() => null);
    const st = await page.evaluate(() => ({ registry: document.querySelector(".civic-explore-registry")?.hidden ? null : document.querySelector(".civic-explore-registry")?.textContent,
      list: (document.getElementById("civic-map-root").textContent.replace(/\s+/g, " ").match(/Опубликованных объектов пока нет[^.]*\./) || [""])[0],
      scrollW: document.documentElement.scrollWidth }));
    check(`${tag}: empty registry is stated (not "no works"), list agrees`, /Реестр пуст/.test(st.registry || "") && /не значит/.test(st.registry || "") && /пока нет/.test(st.list) && st.scrollW <= w, st);
    const lay = await layout(page);
    check(`${tag}: empty registry: no overlaps`, lay.over.length === 0, lay.over);
    await page.screenshot({ path: path.join(OUT, `07_empty_registry_${tag}.png`) });
    await page.click(".civic-explore-objects");
    await page.waitForTimeout(600);
    const toastText = await page.evaluate(() => document.querySelector(".toast")?.textContent || "");
    check(`${tag}: "К объектам" on an empty registry says the registry is empty`, /реестре пока нет/.test(toastText), toastText);
    await page.selectOption(".civic-explore select", { index: 1 });
    await page.waitForTimeout(2600);
    const view = await page.textContent(".civic-explore-view");
    check(`${tag}: district view on an empty registry says "реестр пуст"`, /реестр пуст/.test(view || ""), view);
    checkPageErrors(`${tag}: no page errors (empty registry)`, page.errs);
    await ctx.close();
  }
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "civic-r12-"));
  const port = await freePort(), base = `http://127.0.0.1:${port}/`;
  const srv = await startServer(port, path.join(dbDir, "civic.sqlite3"));
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const result = { base, empty: EMPTY, started_at: new Date().toISOString(), checks };
  try {
    if (EMPTY) await emptyRegistry(browser, base);
    else for (const [w, h] of VIEWPORTS) {
      const tag = `${w}x${h}`;
      const { ctx, page } = await openPage(browser, base, w, h);
      const lay = await layout(page);
      check(`${tag}: no horizontal scroll`, lay.scrollW <= lay.innerW, lay);
      check(`${tag}: navigation box, map tools, top bar and panel do not overlap`, lay.over.length === 0, lay.over);
      if (lay.status) check(`${tag}: map notice readable (not under the navigation box)`, lay.status.readable, lay.status);
      else notRun(`${tag}: map notice readable`, "no map notice shown (basemap loaded)");
      check(`${tag}: navigation box wide enough for the district name and search (≥ 280px)`, (lay.explore || 0) >= 280, lay.explore);
      await page.screenshot({ path: path.join(OUT, `01_start_${tag}.png`) });
      const startView = await page.textContent(".civic-explore-view");
      check(`${tag}: city overview is named as such`, /Обзор: вся Астана/.test(startView || ""), startView);

      // ---- street search: same-name streets are labelled by district; keyboard and touch both work
      const input = page.locator(".civic-explore-field input");
      await input.click();
      await input.fill("Кабанбай");
      await page.waitForSelector("#civic-explore-listbox:not([hidden]) [role=option]", { timeout: 8000 });
      const opts = await page.$$eval("#civic-explore-listbox [role=option]", (els) => els.map((e) => ({
        name: e.querySelector(".civic-explore-opt-name").textContent, place: e.querySelector(".civic-explore-opt-place").textContent })));
      check(`${tag}: ambiguous search lists variants with a readable place, no raw coordinates`,
        opts.length >= 2 && opts.every((o) => /район|окрестности/.test(o.place) && !/\d+\.\d{3}/.test(o.place + o.name)), opts.slice(0, 4));
      await page.screenshot({ path: path.join(OUT, `02_search_${tag}.png`) });
      const zoomBefore = await page.evaluate(() => map.getZoom());
      if (w < 761) await page.locator("#civic-explore-listbox [role=option]").nth(1).tap();
      else { await input.press("ArrowDown"); await input.press("ArrowDown"); await input.press("Enter"); }
      await page.waitForTimeout(1300);
      const chosen = await page.evaluate(() => ({ value: document.querySelector(".civic-explore-field input").value,
        listHidden: document.getElementById("civic-explore-listbox").hidden, status: document.querySelector(".civic-explore-status").textContent,
        zoom: map.getZoom() }));
      check(`${tag}: choosing a variant (${w < 761 ? "tap" : "arrows + Enter"}) frames the street and says where`,
        chosen.listHidden && /Кабанбай/.test(chosen.value) && /Показана улица/.test(chosen.status) && chosen.zoom > zoomBefore + 1, chosen);
      const pinFree = await page.evaluate(() => {
        const pin = document.querySelector(".civic-explore-pin");
        if (!pin) return { pin: false };
        const p = pin.getBoundingClientRect();
        const hits = ["#civic-panel", ".civic-explore", ".map-tools", ".topbar"].filter((sel) => {
          const e = document.querySelector(sel); if (!e || !e.getClientRects().length) return false;
          const b = e.getBoundingClientRect();
          return Math.min(p.right, b.right) - Math.max(p.left, b.left) > 1 && Math.min(p.bottom, b.bottom) - Math.max(p.top, b.top) > 1;
        });
        return { pin: true, rect: [p.left, p.top, p.right, p.bottom].map(Math.round), covered: hits, inView: p.left >= 0 && p.right <= innerWidth && p.top >= 0 && p.bottom <= innerHeight };
      });
      check(`${tag}: chosen street is marked in the free map area (not under panel/navigation/tools)`, pinFree.pin && pinFree.inView && pinFree.covered.length === 0, pinFree);
      const streetView = await page.textContent(".civic-explore-view");
      // Текст — из словаря R11 (с a62a67c: «на видимой части карты»), запасной shell-text.js — «в кадре».
      check(`${tag}: street view line says how many published records are in frame (zero is not "no works")`,
        /Улица: .*(записей (в кадре|на видимой части карты): \d+|(в кадре|на этой части карты) опубликованных записей нет \(это не значит, что работ нет\))/.test(streetView || ""), streetView);
      await page.screenshot({ path: path.join(OUT, `03_street_${tag}.png`) });
      await openExplore(page);
      await input.fill("Егемен Қазақстан");
      await page.waitForSelector("#civic-explore-listbox:not([hidden]) [role=option]", { timeout: 8000 });
      const longName = await page.evaluate(() => { const l = document.getElementById("civic-explore-listbox"), b = l.getBoundingClientRect();
        return { overflowX: l.scrollWidth - l.clientWidth, inside: b.left >= 0 && b.right <= innerWidth, first: l.querySelector(".civic-explore-opt-name")?.textContent,
          pageScrollW: document.documentElement.scrollWidth }; });
      check(`${tag}: long Kazakh street name wraps inside the list (no sideways scroll)`, longName.overflowX <= 1 && longName.inside && longName.pageScrollW <= w && /Егемен/.test(longName.first || ""), longName);
      await input.press("Escape");
      const afterEsc1 = await page.evaluate(() => ({ listHidden: document.getElementById("civic-explore-listbox").hidden, value: document.querySelector(".civic-explore-field input").value }));
      await input.press("Escape");
      const afterEsc2 = await page.evaluate(() => document.querySelector(".civic-explore-field input").value);
      check(`${tag}: Escape closes the list, second Escape clears the field`, afterEsc1.listHidden && afterEsc1.value !== "" && afterEsc2 === "", { afterEsc1, afterEsc2 });
      await input.fill("Сарыарка");
      await page.click(".civic-explore-clear");
      const cleared = await page.evaluate(() => ({ value: document.querySelector(".civic-explore-field input").value, focused: document.activeElement === document.querySelector(".civic-explore-field input"),
        clearHidden: document.querySelector(".civic-explore-clear").hidden }));
      check(`${tag}: clear button empties the field and keeps focus`, cleared.value === "" && cleared.focused && cleared.clearHidden, cleared);

      // ---- camera: a fast 3D -> zoom -> "К объектам" sequence ends in a consistent 3D state
      await page.click("#toggle-3d"); await page.waitForTimeout(120);
      await page.click("#zoom-in"); await page.waitForTimeout(80);
      await page.click(".civic-explore-objects"); await page.waitForTimeout(2600);
      const cam = await page.evaluate(() => ({ pitch: Math.round(map.getPitch()), pressed: document.getElementById("toggle-3d").getAttribute("aria-pressed") === "true",
        moving: map.isMoving() }));
      const viewLine = await page.textContent(".civic-explore-view");
      check(`${tag}: the view line says what is shown (all records)`, /Все опубликованные записи/.test(viewLine || ""), viewLine);
      check(`${tag}: 3D button matches the real tilt after an interrupted 3D -> zoom -> objects sequence`,
        !cam.moving && (cam.pressed ? cam.pitch >= 35 : cam.pitch <= 5), cam);
      // ---- the selected object is framed in the free map area, not under the navigation box/panel/tools
      const item = page.locator("#civic-map-root .civic-r03-item").first();
      await item.scrollIntoViewIfNeeded();
      await item.click();
      await page.waitForTimeout(2800);
      const sel = await page.evaluate(() => {
        const id = window.CivicShell.selected;
        const feats = id ? map.querySourceFeatures("civic-r03-objects", { filter: ["==", ["get", "cid"], id] }) : [];
        const pts = [];
        const walk = (c) => { if (typeof c[0] === "number") pts.push(c); else c.forEach(walk); };
        feats.forEach((f) => walk(f.geometry.coordinates));
        if (!pts.length) return { id, found: false };
        const lon = pts.reduce((a, p) => a + p[0], 0) / pts.length, lat = pts.reduce((a, p) => a + p[1], 0) / pts.length;
        const p = map.project([lon, lat]);
        const c = map.getContainer().getBoundingClientRect();
        const x = c.left + p.x, y = c.top + p.y;
        const covered = ["#civic-panel", ".civic-explore", ".map-tools", ".topbar"].filter((sel) => {
          const e = document.querySelector(sel); if (!e || !e.getClientRects().length || getComputedStyle(e).visibility === "hidden") return false;
          const b = e.getBoundingClientRect(); return x >= b.left && x <= b.right && y >= b.top && y <= b.bottom; });
        return { id, found: true, xy: [Math.round(x), Math.round(y)], covered, inView: x >= 0 && x <= innerWidth && y >= 0 && y <= innerHeight };
      });
      check(`${tag}: selected object is shown in the free map area (not under navigation/panel/tools)`, sel.found && sel.inView && sel.covered.length === 0, sel);
      const selView = await page.textContent(".civic-explore-view");
      check(`${tag}: the view line names the open record`, /Открыта запись/.test(selView || ""), selView);
      await page.screenshot({ path: path.join(OUT, `05_selected_${tag}.png`) });
      checkPageErrors(`${tag}: no page errors`, page.errs);
      await ctx.close();
    }

    if (!EMPTY) {
      const items = (await (await fetch(base + "api/civic/v1/objects")).json()).data.items;
      for (const [w, h] of VIEWPORTS) await directLinkAndReload(browser, base, w, h, items[0]);
      for (const [w, h] of [[1440, 900], [360, 800]]) await modeRoundTrip(browser, base, w, h);
    }

    // ---- street index loading and failure (phone): honest states, retry, district navigation still works
    if (!EMPTY) {
      const mobile = { width: 360, height: 800 };
      const ctx = await browser.newContext({ viewport: mobile, isMobile: true, hasTouch: true });
      const page = await ctx.newPage();
      let release, failNext = true;
      const gate = new Promise((r) => (release = r));
      await page.route("**/civic/map/streets.json", async (route) => {
        if (failNext) { failNext = false; await gate; return route.fulfill({ status: 503, body: "unavailable" }); }
        return route.continue();
      });
      await page.goto(base + TOOLS);
      await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady, null, { timeout: 40000 });
      await page.waitForSelector(".civic-explore", { timeout: 15000 });
      await openExplore(page);
      const input = page.locator(".civic-explore-field input");
      await input.fill("Кабанбай");
      const loading = await page.textContent(".civic-explore-status");
      release();
      await page.waitForSelector(".civic-explore-retry", { timeout: 8000 });
      const failed = await page.textContent(".civic-explore-status");
      check("360x800: index loading and failure are stated, not a silent empty list", /Загружаем список улиц/.test(loading) && /недоступен/.test(failed), { loading, failed });
      const cityZoom = await page.evaluate(() => map.getZoom());
      await page.selectOption(".civic-explore select", { index: 1 });
      await page.waitForTimeout(2000);
      const district = await page.evaluate(() => ({ zoom: map.getZoom(), value: document.querySelector(".civic-explore select").value,
        retryKept: !!document.querySelector(".civic-explore-retry") }));
      check("360x800: district navigation works while street search is down (retry stays offered)",
        !!district.value && district.zoom > cityZoom + 0.3 && district.retryKept, { cityZoom, ...district });
      await openExplore(page);
      await page.click(".civic-explore-retry");
      await input.fill("Кабанбай");
      const recovered = await page.waitForSelector("#civic-explore-listbox:not([hidden]) [role=option]", { timeout: 8000 }).then(() => true).catch(() => false);
      check("360x800: retry loads the street index", recovered);
      await page.screenshot({ path: path.join(OUT, "04_search_recovered_360x800.png") });
      await ctx.close();
    }
  } catch (error) {
    check("flow completed without exception", false, String(error && error.stack || error).slice(0, 1500));
  } finally {
    await browser.close();
    srv.kill("SIGTERM");
    fs.rmSync(dbDir, { recursive: true, force: true });
    result.finished_at = new Date().toISOString();
    result.summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length,
      not_run: checks.filter((c) => c.status === "NOT_RUN").length };
    fs.writeFileSync(path.join(OUT, "r12_city.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result.summary));
    process.exit(result.summary.fail ? 1 : 0);
  }
})();
