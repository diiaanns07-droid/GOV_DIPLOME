// R01 round 14, build B2: what B2 adds to the demo path in one app (CONTRACT §0, steps 2 and 5, «Картина дня»).
//   API:      R12 /targets and street routes, R04 /classify and /similar, R06 proposals and stages, R13 /forecast
//   resident: «Сообщить о проблеме» -> «Это здесь?» offers a real R12 place -> R04 suggests the category -> sent
//   akimat:   R05 3D catalog over the map (left of the panel) -> «Сквер» -> place on the left bank -> «Поставить»
//             -> R06 stores the proposal (R05 speaks the R06 contract itself)
//   resident: the same proposal card has «За / Против» -> vote counted by R06 (my_vote of this device)
//   akimat:   «Удалить» (R05 -> R06 POST …/withdraw); «Картина дня» hides the 3D dock
// Usage: node tests/civic/R01/browser/r14_b2.cjs <out_dir>
// Starts `python3 -B app.py` with CIVIC_DEMO=1 on a temporary SQLite file seeded with seed-demo + seed-r14-demo
// (synthetic objects, stages and proposals, all flagged demo).
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r14-b2-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|GPU stall|WebGL/i;
const R03_RING = /civic-r03-demo-ring/;  // known R12/R03 map race, reported separately (BUILD_LOG)
const USER = "operator", PASSWORD = "Tz7-qerB-91vk-Lmsd";
const PLACE = [71.4148, 51.1131];  // left bank (R06 district: esil), away from the seeded demo proposals (Zhagalau)
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined && detail !== null ? " — " + JSON.stringify(detail).slice(0, 400) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: ["pipe", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run("seed-r14-demo");
  run(`create-editor ${USER} --password-stdin`, PASSWORD + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const ready = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady
  && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 }).then(() => page.waitForTimeout(800));
const b3dReady = (page) => page.waitForFunction(() => {
  const h = window.CivicShell?.build3d; const s = h?.getState?.();
  return s && s.phase !== "loading" && s.storeMode !== "pending";
}, null, { timeout: 60000 });
const b3dState = (page) => page.evaluate(() => window.CivicShell.build3d?.getState?.() || null);
const api = (page, url, init) => page.evaluate(async ([u, i]) => {
  const r = await fetch(u, i || undefined); let body = null; try { body = await r.json(); } catch { /* пусто */ }
  return { status: r.status, body };
}, [url, init || null]);
const deviceId = (page) => page.evaluate(() => localStorage.getItem("birge.device_id"));
// R10 B-025: с начала страницы первый Tab — «Перейти к главной кнопке», Enter — фокус на главное действие вида.
async function skipToMain(page) {
  // Начало страницы: фокус на body (временный tabindex), иначе Chromium продолжит Tab от последней нажатой кнопки.
  await page.evaluate(() => { const b = document.body; b.setAttribute("tabindex", "-1"); b.focus(); b.removeAttribute("tabindex"); });
  await page.keyboard.press("Tab");
  const first = await page.evaluate(() => { const a = document.activeElement, r = a.getBoundingClientRect();
    return { skip: a.classList.contains("birge-skip"), text: a.textContent.trim(), top: Math.round(r.top) }; });
  await page.keyboard.press("Enter");
  const target = await page.evaluate(() => { const a = document.activeElement;
    return { fab: a.classList.contains("bc-fab"), heat: !!a.closest("#birge-heat-root"), text: (a.textContent || "").trim().slice(0, 40) }; });
  return { first, target };
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r01-b2-"));
  const port = await freePort();
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const errs = [];
  try {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
    page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) errs.push(m.type() + ": " + m.text()); });
    await page.addInitScript(() => { try { if (!localStorage.getItem("birge.mode")) localStorage.setItem("birge.mode", "akimat"); } catch (e) {} });
    await page.goto(base);
    await ready(page);

    const keysAkimat = await skipToMain(page);
    check("keyboard (akimat): first Tab = «Перейти к главной кнопке», Enter -> «Карта жалоб» panel",
      keysAkimat.first.skip && keysAkimat.first.top >= 0 && keysAkimat.first.text.length > 3 && keysAkimat.target.heat, keysAkimat);

    // ---- what B2 connects
    const modules = (await api(page, "/api/civic/v2/modules")).body.modules;
    const b2 = ["targets", "classify", "similar", "geo.segment", "geo.snap", "geo.objects", "geo.yard", "geo.status",
      "proposals.list", "proposals.create", "proposals.vote", "proposals.withdraw", "proposals.summary",
      "objects.list", "objects.lagging", "objects.stage", "forecast"];
    check("B2: R12, R04, R06, R13 routes are connected", b2.every((k) => modules[k]?.status === "ready"),
      Object.fromEntries(b2.map((k) => [k, modules[k]?.status])));
    const targets = await api(page, `/api/civic/v2/targets?lon=${PLACE[0]}&lat=${PLACE[1]}`);
    const cands = targets.body && (targets.body.candidates || targets.body.items);
    check("step 2 (R12): /targets offers places near a point on the left bank", targets.status === 200 && Array.isArray(cands) && cands.length > 0,
      { status: targets.status, n: cands?.length, first: cands?.[0] && { kind: cands[0].kind ?? cands[0].target?.kind, label: cands[0].label_ru ?? cands[0].target?.label_ru } });
    const cls = await api(page, "/api/civic/v2/classify", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Аялдамада жарық жоқ, вечером на остановке темно" }) });
    check("step 2 (R04): /classify suggests a category for mixed kk/ru text", cls.status === 200 && !!cls.body?.category && Array.isArray(cls.body?.top3),
      cls.body && { category: cls.body.category, suggest: cls.body.suggest, source: cls.body.source });
    const fc = await api(page, "/api/civic/v2/forecast?k=5");
    check("R13: /forecast answers and is marked synthetic (prototype)", fc.status === 200 && fc.body?.evidence_type === "synthetic"
      && fc.body?.demo === true && Array.isArray(fc.body?.items), fc.body && { month: fc.body.month, n: fc.body.items?.length, evidence: fc.body.evidence_type });
    const lagging = await api(page, "/api/civic/v2/objects/lagging");
    check("R06: lagging objects for «Картина дня» come from the store (seed-r14-demo)", lagging.status === 200
      && (lagging.body?.late?.length || 0) + (lagging.body?.stale?.length || 0) > 0, lagging.body && { late: lagging.body.late?.length, stale: lagging.body.stale?.length });

    // ---- step 1–2 with R12 and R04: the resident picks a real place and gets a category suggestion
    await page.click("#birge-header [data-mode=resident]");
    await page.waitForTimeout(300);
    const keysResident = await skipToMain(page);
    check("keyboard (resident): first Tab = «Перейти к главной кнопке», Enter -> «Сообщить о проблеме»",
      keysResident.first.skip && keysResident.target.fab, keysResident);
    await page.click(".bc-fab");
    await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 });
    const tap = await page.evaluate((p) => { const c = map.getCanvas().getBoundingClientRect(); map.jumpTo({ center: p, zoom: 16 });
      const q = map.project(p); return [c.left + q.x, c.top + q.y]; }, PLACE);
    await page.waitForTimeout(400);
    await page.mouse.click(tap[0], tap[1]);
    const firstOption = await page.waitForSelector(".bc-option--first", { timeout: 12000 }).then((n) => n.textContent()).catch(() => null);
    check("step 2 (R12 in the form): «Это здесь?» offers a real place first", !!firstOption && !/примерн/i.test(firstOption), firstOption && firstOption.trim());
    if (firstOption) await page.click(".bc-option--first");
    else if (await page.$(".bc-option")) await page.click(".bc-option");
    await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 10000 });
    await page.fill("#bc-text", "Аялдамада жарық жоқ, вечером на остановке темно");
    const suggested = await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 10000 })
      .then(() => page.evaluate(() => ({ label: document.querySelector(".bc-cat-row__label")?.textContent.trim(),
        chip: document.querySelector(".bc-cat-row .bk-chip")?.textContent.trim() }))).catch(() => null);
    check("step 2 (R04 in the form): the category is suggested by the model", !!suggested && /Освещ/i.test(suggested.chip || ""), suggested);
    if (!suggested && await page.$(".bc-change")) { await page.click(".bc-change"); await page.click(".bk-catgrid button:nth-child(5)"); }
    await page.click(".bc-send");
    await page.waitForSelector(".bc-panel[data-step='4'], .bc-panel[data-step='5']", { timeout: 15000 });
    if (await page.$(".bc-panel[data-step='4']")) await page.click(".bc-different");
    await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 15000 });
    const mine = await page.evaluate(async () => {
      const r = await fetch("/api/civic/v2/complaints/mine", { headers: { "X-Birge-Device": localStorage.getItem("birge.device") || "" } });
      const b = await r.json(); const items = b?.data?.items || b?.data || []; return Array.isArray(items) ? items[0] : null;
    });
    check("the complaint is attached to the R12 place (not the approximate cell)", !!mine?.target && mine.target.approximate !== true
      && ["object", "segment", "area"].includes(mine.target.kind), mine && { id: mine.id, target: mine.target, category: mine.category });
    await page.screenshot({ path: path.join(OUT, "b2-1366-resident-sent.png") });
    await page.keyboard.press("Escape");
    await page.click("#birge-header [data-mode=akimat]");
    await page.waitForTimeout(300);

    // ---- step 5: akimat places a proposal in 3D
    await b3dReady(page);
    let st = await b3dState(page);
    check("akimat: 3D catalog (R05) is mounted over the map with the R06 store", st?.phase === "ready" && st?.storeMode === "api", st && { phase: st.phase, storeMode: st.storeMode, count: st.count });
    // B3: каталог свёрнут в одну кнопку «Что построить?» — легенда тепловой карты свободна; по нажатию — 5 видов.
    const closed = await page.evaluate(() => {
      const t = document.querySelector(".birge-b3d-toggle"), d = document.querySelector("#birge-build3d-root .b3d-dock"),
        lg = document.querySelector(".r07-maplegend");
      const box = (n) => (n && n.getClientRects().length && getComputedStyle(n).visibility !== "hidden" ? n.getBoundingClientRect() : null);
      const a = box(t), b = box(lg);
      return { toggle: t?.textContent || null, expanded: t?.getAttribute("aria-expanded"), catalogShown: !!box(d),
        legendShown: !!b, overlap: !!(a && b && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom) };
    });
    check("akimat: catalog folded into one «Что построить?» button, the heat legend is free", closed.toggle === "Что построить?"
      && closed.expanded === "false" && !closed.catalogShown && closed.legendShown && !closed.overlap, closed);
    await page.click(".birge-b3d-toggle");
    await page.waitForTimeout(300);
    const dock = await page.evaluate(() => {
      const d = document.querySelector("#birge-build3d-root .b3d-dock"), p = document.querySelector(".civic-panel");
      if (!d) return null;
      const r = d.getBoundingClientRect(), q = p.getBoundingClientRect();
      return { state: d.dataset.state, kinds: d.querySelectorAll(".b3d-card[data-kind]").length, right: Math.round(r.right), panelLeft: Math.round(q.left),
        bottom: Math.round(r.bottom), vh: innerHeight };
    });
    check("akimat: catalog shows 5 kinds and does not cover the right panel", dock?.state === "catalog" && dock.kinds === 5 && dock.right <= dock.panelLeft, dock);
    const legendWhileOpen = await page.evaluate(() => getComputedStyle(document.querySelector(".r07-maplegend")).visibility);
    check("akimat: while the catalog is open the legend steps aside (no overlap at the bottom of the map)", legendWhileOpen === "hidden", legendWhileOpen);
    await page.screenshot({ path: path.join(OUT, "b2-1366-akimat-catalog.png") });

    const seeded = (await api(page, "/api/civic/v2/proposals")).body?.items || [];
    await page.evaluate(([u, p]) => window.CivicShell.api.login(u, p), [USER, PASSWORD]);
    // R10 B-035: «Сообщения жителей» раунда 13 (v1, без жалоб Birge) у сотрудника не видны без ?tools=all.
    await page.waitForTimeout(500);
    const moderation = await page.evaluate(() => { const b = document.getElementById("civic-moderation-button");
      return b ? getComputedStyle(b).display : "absent"; });
    check("akimat staff: round-13 «Сообщения жителей» (empty v1 list, B-035) is hidden in Birge", moderation === "none" || moderation === "absent", moderation);
    await page.evaluate((p) => map.jumpTo({ center: p, zoom: 17.2, pitch: 50, bearing: -20 }), PLACE);
    await page.waitForTimeout(600);
    await page.click("#birge-build3d-root .b3d-card[data-kind=square]");
    await page.waitForTimeout(800);  // autoZoom / ghost
    const xy = await page.evaluate((p) => { const c = map.getCanvas().getBoundingClientRect(), q = map.project(p); return [c.left + q.x, c.top + q.y]; }, PLACE);
    await page.mouse.move(xy[0], xy[1]);
    await page.mouse.click(xy[0], xy[1]);
    await page.waitForTimeout(400);
    const ghost = (await b3dState(page))?.ghost;
    // Ждём успешный POST (R05 поставки 2 при 422 повторяет базовым телом; R06 поставки 2/3 принимает с первого раза).
    const createResp = page.waitForResponse((r) => /\/api\/civic\/v2\/proposals$/.test(new URL(r.url()).pathname) && r.request().method() === "POST"
      && r.status() < 300, { timeout: 15000 }).catch(() => null);
    await page.click("#birge-build3d-root [data-action=place]");
    const created = await createResp;
    await page.waitForFunction((n) => (window.CivicShell.build3d?.getState?.().count || 0) > n && !window.CivicShell.build3d.getState().animating, st.count, { timeout: 30000 }).catch(() => {});
    const createdBody = created ? await created.json().catch(() => null) : null;
    const newItem = createdBody?.item || createdBody?.proposal || null;
    check("«Поставить»: R06 stores the proposal (201, planned_year 2027)",
      created?.status() === 201 && newItem?.kind === "square" && newItem?.planned_year === 2027,
      { status: created?.status(), item: newItem && { id: newItem.id, kind: newItem.kind, planned_year: newItem.planned_year, district: newItem.district }, ghost: ghost && { valid: ghost.valid } });
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUT, "b2-1366-akimat-placed.png") });
    const after = (await api(page, "/api/civic/v2/proposals")).body?.items || [];
    check("the new proposal is in the public list (+1)", after.length === seeded.length + 1 && after.some((p) => p.id === newItem?.id), { before: seeded.length, after: after.length });

    // ---- resident votes «За»
    await page.click("#birge-header [data-mode=resident]");
    await page.waitForTimeout(300);
    await b3dReady(page);
    st = await b3dState(page);
    // R05 поставки 2: у жителя вместо каталога — подсказка «Нажмите на проект, чтобы проголосовать».
    const residentDock = await page.evaluate(() => { const d = document.querySelector("#birge-build3d-root .b3d-dock");
      return d ? { state: d.dataset.state || null, cards: d.querySelectorAll(".b3d-card[data-kind]").length } : null; });
    check("resident: no catalog (view and vote only)", st?.phase === "ready" && residentDock && residentDock.cards === 0
      && ["empty", "hint"].includes(residentDock.state), { phase: st?.phase, dock: residentDock });
    if (newItem) await page.evaluate((id) => window.CivicShell.build3d.select(id), newItem.id);
    // Голос — в карточке R06 внутри панели 3D (BirgeProposals) или в своей карточке R05, если карточки R06 нет.
    const VOTE_UP = '#birge-build3d-root .r06-vote__btn[data-value="1"], #birge-build3d-root [data-action=vote-up]';
    await page.waitForSelector(VOTE_UP, { timeout: 10000 }).catch(() => {});
    const voteResp = page.waitForResponse((r) => /\/vote$/.test(new URL(r.url()).pathname), { timeout: 15000 }).catch(() => null);
    await page.click(VOTE_UP).catch(() => {});
    const voted = await voteResp;
    await page.waitForTimeout(500);
    const dev = await deviceId(page);
    const one = newItem ? (await api(page, `/api/civic/v2/proposals/${encodeURIComponent(newItem.id)}?device_id=${encodeURIComponent(dev || "")}`)).body?.item : null;
    check("resident «За»: R06 counts one vote of this device", voted?.status() === 200 && one?.votes_up === 1 && one?.my_vote === 1,
      { status: voted?.status(), votes_up: one?.votes_up, my_vote: one?.my_vote });
    const fab = await page.evaluate(() => { const f = document.querySelector(".bc-fab"), d = document.querySelector("#birge-build3d-root .b3d-dock");
      if (!f || !d || getComputedStyle(f).display === "none") return null; const a = f.getBoundingClientRect(), b = d.getBoundingClientRect();
      return { overlap: !(a.bottom <= b.top || a.top >= b.bottom || a.right <= b.left || a.left >= b.right) }; });
    check("resident: the proposal card does not cover «Сообщить о проблеме»", fab && !fab.overlap, fab);
    await page.screenshot({ path: path.join(OUT, "b2-1366-resident-vote.png") });

    // ---- akimat deletes it (R05 DELETE -> R06 withdraw)
    await page.click("#birge-header [data-mode=akimat]");
    await page.waitForTimeout(300);
    await b3dReady(page);
    if (newItem) await page.evaluate((id) => window.CivicShell.build3d.select(id), newItem.id);
    await page.waitForSelector("#birge-build3d-root [data-action=delete]", { timeout: 10000 }).catch(() => {});
    const delResp = page.waitForResponse((r) => /\/proposals\/[^/]+(\/withdraw)?$/.test(new URL(r.url()).pathname) && r.request().method() !== "GET", { timeout: 15000 }).catch(() => null);
    await page.click("#birge-build3d-root [data-action=delete]").catch(() => {});
    const deleted = await delResp;
    await page.waitForTimeout(600);
    const gone = newItem ? (await api(page, `/api/civic/v2/proposals/${encodeURIComponent(newItem.id)}`)).status : null;
    check("akimat «Удалить»: the proposal is withdrawn in R06 (404 afterwards)", deleted?.status() === 200 && gone === 404,
      { request: deleted && `${deleted.request().method()} ${new URL(deleted.url()).pathname}`, status: deleted?.status(), get_after: gone });

    // ---- «Картина дня» hides the 3D dock
    await page.click("#birge-header [data-section=day]");
    await page.waitForTimeout(800);
    const hidden = await page.evaluate(() => { const r = document.getElementById("birge-build3d-root"); return r ? getComputedStyle(r).visibility : null; });
    check("«Картина дня»: the 3D dock is not shown over the day screen", hidden === "hidden", hidden);
    await page.click("#birge-header [data-section=map]");
    await page.waitForTimeout(300);

    // ---- phone
    const phone = await browser.newContext({ viewport: { width: 375, height: 760 }, isMobile: true, hasTouch: true });
    const p2 = await phone.newPage();
    p2.on("pageerror", (e) => errs.push("pageerror(375): " + e.message));
    await p2.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); } catch (e) {} });
    await p2.goto(base);
    await ready(p2);
    await b3dReady(p2);
    const phoneDock = () => p2.evaluate(() => { const d = document.querySelector("#birge-build3d-root .b3d-dock"), s = document.querySelector(".civic-panel");
      if (!d) return null; const r = d.getBoundingClientRect(), q = s.getBoundingClientRect();
      return { sheet: s.dataset.sheet, state: d.dataset.state, shown: getComputedStyle(d).display !== "none", left: Math.round(r.left), right: Math.round(r.right),
        bottom: Math.round(r.bottom), sheetTop: Math.round(q.top), w: innerWidth, scrollX: document.documentElement.scrollWidth > innerWidth }; });
    const half = await phoneDock();
    check("375 px akimat: the catalog does not cover the open «Карта жалоб» sheet", half && half.sheet !== "peek" && !half.shown && !half.scrollX, half);
    // R10 B-022: кнопка «Что построить?» видна над полуоткрытой шторкой; нажатие опускает шторку и раскрывает каталог.
    const toggle = await p2.evaluate(() => { const b = document.querySelector(".birge-b3d-toggle"), s = document.querySelector(".civic-panel");
      if (!b || getComputedStyle(b).display === "none") return null; const r = b.getBoundingClientRect();
      return { text: b.textContent.trim(), h: Math.round(r.height), bottom: Math.round(r.bottom), sheetTop: Math.round(s.getBoundingClientRect().top) }; });
    check("375 px akimat: «Что построить?» is reachable above the half-open sheet (48 px)", !!toggle && toggle.h >= 48
      && toggle.bottom <= toggle.sheetTop + 1, toggle);
    await p2.click(".birge-b3d-toggle");
    await p2.waitForTimeout(600);
    await p2.waitForTimeout(300);
    const peek = await phoneDock();
    check("375 px akimat: sheet collapsed -> catalog above it, within the screen", peek && peek.sheet === "peek" && peek.shown
      && peek.left >= 0 && peek.right <= peek.w && peek.bottom <= peek.sheetTop + 1 && !peek.scrollX, peek);
    await p2.screenshot({ path: path.join(OUT, "b2-375-akimat-catalog.png") });
    await phone.close();

    const real = errs.filter((e) => !R03_RING.test(e));
    check("no page errors or unexpected console errors", real.length === 0, real.slice(0, 6));
    if (errs.length !== real.length) console.log("NOTE known R03 demo-ring race seen:", errs.length - real.length);
  } finally {
    await browser.close();
    srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length };
  fs.writeFileSync(path.join(OUT, "r14_b2.json"), JSON.stringify({ summary, checks }, null, 1));
  console.log(JSON.stringify(summary));
  process.exit(summary.fail ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
