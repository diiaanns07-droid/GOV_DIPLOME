// R01 P0 browser flow on the real page: editor creates -> publishes -> resident sees the card on the
// light map -> deadline moves with history -> resident sends a message -> moderation -> public.
// Usage: node tests/civic/R01/browser/p0_flow.cjs <out_dir> [--backend double|real]
//   double: starts tests/civic/R01/serve_double.py (in-memory TEST DOUBLE, not a backend)
//   real:   starts `python -B app.py` with a temp CIVIC_DB; needs an editor created beforehand via
//           CIVIC_EDITOR_SETUP (shell command run once with CIVIC_DB/CIVIC_TEST_PASSWORD in env).
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "p0-out");
const BACKEND = (process.argv.find((a) => a.startsWith("--backend=")) || "--backend=double").split("=")[1];
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff/i;
const PASSWORD = "p0-" + Math.random().toString(36).slice(2, 12);
const USER = process.env.CIVIC_TEST_USER || "test-editor";
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null }); console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + JSON.stringify(detail) : "")); };
const notRun = (name, reason) => { checks.push({ name, status: "NOT_RUN", detail: reason }); console.log("NOT_RUN " + name + " — " + reason); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, dbDir) {
  const env = { ...process.env, CIVIC_TEST_PASSWORD: PASSWORD, CIVIC_DB: path.join(dbDir, "civic.sqlite3"), PYTHONDONTWRITEBYTECODE: "1" };
  if (BACKEND === "real" && process.env.CIVIC_EDITOR_SETUP) execSync(process.env.CIVIC_EDITOR_SETUP, { cwd: REPO, env, stdio: "inherit" });
  const args = BACKEND === "double" ? ["-B", "tests/civic/R01/serve_double.py", "--port", String(port)]
    : ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)];
  const srv = spawn("python3", args, { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

async function openPage(browser, base, viewport, extra) {
  const ctx = await browser.newContext({ viewport, ...(extra || {}) });
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) page.errs.push(m.type() + ": " + m.text()); });
  await page.goto(base);
  await page.evaluate(() => localStorage.clear());
  await page.goto(base);
  await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady, null, { timeout: 40000 });
  return { ctx, page };
}
const apiFetch = (page, method, p, body, headers) => page.evaluate(async ([method, p, body, headers]) => {
  const r = await fetch("/api/civic/v1" + p, { method, headers: { "Content-Type": "application/json", ...(headers || {}) }, body: body ? JSON.stringify(body) : undefined, credentials: "same-origin" });
  let j = null; try { j = await r.json(); } catch {}
  return { status: r.status, body: j };
}, [method, p, body, headers]);

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "civic-p0-"));
  const port = await freePort(), base = `http://127.0.0.1:${port}/`;
  const srv = await startServer(port, dbDir);
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const result = { backend: BACKEND, base, started_at: new Date().toISOString(), checks };
  let createdId = null;
  try {
    // ---------------- desktop
    const { ctx, page } = await openPage(browser, base, { width: 1440, height: 900 });
    await page.waitForSelector("#civic-map-root .civic-item, #civic-map-root [data-civic-object]", { timeout: 20000 }).catch(() => null);
    const start = await page.evaluate(() => ({
      canvases: document.querySelectorAll("canvas").length, iframes: document.querySelectorAll("iframe").length,
      district: map.getLayer("district-fill") ? map.getLayoutProperty("district-fill", "visibility") : "absent",
      offline: document.body.classList.contains("offline-basemap"), title: document.title,
      synthetic: /синтетическ/i.test(document.getElementById("civic-map-root").textContent),
      mapModule: window.CivicShell.isFallback("map") ? "R01 fallback" : "CivicMap",
    }));
    check("default mode is civic (Astana city)", start.title.includes("Астана"), start);
    check("one map canvas, no iframe", start.canvases === 1 && start.iframes === 0, start);
    check("training district layer hidden in civic mode", start.district === "none", start.district);
    check("synthetic fixture visibly labelled", start.synthetic);
    if (start.offline) notRun("basemap + 3D buildings", "OpenFreeMap host not reachable in this environment (offline background)");
    await page.screenshot({ path: path.join(OUT, "01_civic_start_1440.png") });

    // editor: login, create draft
    await page.click("#civic-staff-button");
    await page.waitForSelector("#civic-editor input[name=username]", { timeout: 10000 });
    await page.fill("#civic-editor input[name=username]", USER);
    await page.fill("#civic-editor input[name=password]", "wrong-password");
    await page.click("#civic-editor button[type=submit]");
    await page.waitForFunction(() => /не выполнен/i.test(document.querySelector("#civic-editor .civic-form-status")?.textContent || ""), null, { timeout: 10000 });
    check("wrong password rejected, form stays", await page.isVisible("#civic-editor input[name=username]"));
    await page.fill("#civic-editor input[name=password]", PASSWORD);
    await page.click("#civic-editor button[type=submit]");
    await page.waitForFunction(() => window.CivicShell.api.session.authenticated, null, { timeout: 10000 });
    check("editor login via session API", true);
    const storage = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
    check("no session/CSRF token in web storage", !/csrf|civic_session|token/i.test(storage), storage.slice(0, 200));
    await page.click("#civic-editor .civic-tabs button:nth-child(2)");
    const ed = "#civic-editor ";
    await page.fill(ed + "input[name=title]", "Проверочная запись R01 — синтетическая");
    await page.selectOption(ed + "select[name=kind]", "roadworks");
    await page.selectOption(ed + "select[name=status]", "planned");
    await page.fill(ed + "textarea[name=description]", "Создано автоматическим смоуком R01. Не сведения о реальных работах.");
    await page.fill(ed + "input[name=planned_start]", "2026-10-14");
    await page.fill(ed + "input[name=original_planned_end]", "2026-10-30");
    await page.fill(ed + "input[name=current_planned_end]", "2026-10-30");
    await page.selectOption(ed + "select[name=evidence_type]", "synthetic");
    await page.fill(ed + "input[name=lon]", "71.4304");
    await page.fill(ed + "input[name=lat]", "51.1282");
    await page.click(ed + "button[type=submit]");
    await page.waitForFunction(() => /id\s+\S+/.test(document.querySelector("#civic-editor header p")?.textContent || ""), null, { timeout: 10000 });
    createdId = await page.evaluate(() => (document.querySelector("#civic-editor header p").textContent.match(/id\s+(\S+)/) || [])[1]);
    check("draft created with server id", !!createdId, createdId);
    const draftPublic = await apiFetch(page, "GET", "/objects/" + encodeURIComponent(createdId));
    check("draft not visible by direct public ID", draftPublic.status === 404, draftPublic.status);
    const listBefore = await apiFetch(page, "GET", "/objects");
    check("draft not in public list", !(listBefore.body?.data?.items || []).some((i) => i.id === createdId));
    const noCsrf = await apiFetch(page, "POST", `/staff/objects/${encodeURIComponent(createdId)}/publish`, { expected_revision: 1, reason: "x" });
    check("publish without CSRF header rejected", noCsrf.status === 403, noCsrf.status);
    const badCsrf = await apiFetch(page, "POST", `/staff/objects/${encodeURIComponent(createdId)}/publish`, { expected_revision: 1, reason: "x" }, { "X-CSRF-Token": "forged" });
    check("publish with wrong CSRF rejected", badCsrf.status === 403, badCsrf.status);

    // publish
    await page.click("#civic-editor .civic-actions button:has-text('Опубликовать')");
    await page.waitForFunction(() => /Опубликовано/.test(document.querySelector("#civic-editor header p")?.textContent || ""), null, { timeout: 10000 });
    const pub = await apiFetch(page, "GET", "/objects/" + encodeURIComponent(createdId));
    check("published object readable publicly", pub.status === 200 && pub.body?.data?.item?.publication === "published", pub.status);
    check("public DTO has no internal fields", pub.status === 200 && !("internal_notes" in pub.body.data.item) && !JSON.stringify(pub.body).includes("actor\""), Object.keys(pub.body?.data?.item || {}));

    // stale revision (another editor changed it): expected_revision=1 after publish -> 409
    const csrf = await page.evaluate(async () => (await (await fetch("/api/civic/v1/session")).json()).data.csrf_token);
    const stale = await apiFetch(page, "POST", `/staff/objects/${encodeURIComponent(createdId)}/update`, { expected_revision: 1, changes: { title: "x" }, reason: "stale" }, { "X-CSRF-Token": csrf });
    check("stale revision -> 409", stale.status === 409, stale.status);

    // move deadline with reason via the editor form
    await page.fill(ed + "input[name=current_planned_end]", "2026-11-15");
    await page.fill(ed + "input[name=reason]", "Перенос срока: проверка истории (смоук R01)");
    await page.click(ed + "button[type=submit]");
    await page.waitForSelector("#civic-editor .civic-actions button:has-text('Опубликовать изменения')", { timeout: 10000 });
    const beforeRepublish = await apiFetch(page, "GET", "/objects/" + encodeURIComponent(createdId));
    check("saved change not public until published", beforeRepublish.body?.data?.item?.schedule?.current_planned_end === "2026-10-30", beforeRepublish.body?.data?.item?.schedule);
    await page.click("#civic-editor .civic-actions button:has-text('Опубликовать изменения')");
    await page.waitForFunction(() => /Опубликовано/.test(document.querySelector("#civic-editor .civic-form-status")?.textContent || ""), null, { timeout: 10000 });
    const moved = await apiFetch(page, "GET", "/objects/" + encodeURIComponent(createdId));
    const sch = moved.body?.data?.item?.schedule || {};
    check("deadline moved, original kept", sch.original_planned_end === "2026-10-30" && sch.current_planned_end === "2026-11-15", sch);
    const hist = moved.body?.data?.history || [];
    check("public history has the reason", hist.some((h) => /Перенос срока/.test(h.reason || "")), hist.map((h) => h.reason));
    await page.screenshot({ path: path.join(OUT, "02_editor_after_move_1440.png") });
    await page.click("#civic-editor [data-close=editor]");

    // resident: card from the public list
    await page.evaluate((id) => window.CivicShell.refresh(), createdId);
    await page.waitForFunction((id) => [...document.querySelectorAll("#civic-map-root .civic-item b")].some((b) => /Проверочная запись R01/.test(b.textContent)), createdId, { timeout: 10000 });
    await page.click("#civic-map-root .civic-item:has-text('Проверочная запись R01')");
    await page.waitForFunction(() => /срок перенесён/.test(document.querySelector("#civic-map-root .civic-card")?.textContent || ""), null, { timeout: 10000 });
    const cardText = await page.textContent("#civic-map-root .civic-card");
    check("card shows original and current deadline", /30\.10\.2026/.test(cardText) && /15\.11\.2026/.test(cardText), null);
    check("card shows history reason", /Перенос срока/.test(cardText));
    check("card shows synthetic label", /Синтетический пример/.test(cardText));
    check("selected object permalink in URL", (await page.evaluate(() => location.hash)).includes(encodeURIComponent(createdId)));
    await page.screenshot({ path: path.join(OUT, "03_resident_card_1440.png") });

    // resident message
    await page.click("#civic-map-root .civic-ask");
    await page.waitForSelector("#civic-feedback-root textarea[name=text]");
    const xss = "Яма у входа <img src=x onerror=window.__xss=1> <b>тест</b>";
    await page.selectOption("#civic-feedback-root select[name=category]", "roads");
    await page.fill("#civic-feedback-root textarea[name=text]", xss);
    await page.check("#civic-feedback-root input[name=consent_public]");
    await page.click("#civic-feedback-root button[type=submit]");
    await page.waitForSelector("#civic-feedback-root .civic-receipt", { timeout: 10000 });
    check("resident gets a receipt", /Номер/.test(await page.textContent("#civic-feedback-root .civic-receipt")));
    const pending = await apiFetch(page, "GET", `/objects/${encodeURIComponent(createdId)}/feedback`);
    check("pending message not public", pending.status === 200 && (pending.body?.data?.items || []).length === 0, pending.body?.data);
    await page.screenshot({ path: path.join(OUT, "04_feedback_receipt_1440.png") });

    // moderation
    await page.click("#civic-staff-button");
    await page.click("#civic-editor .civic-tabs button:nth-child(3)");
    await page.waitForSelector("#civic-editor .civic-msg input[name=reason]", { timeout: 10000 });
    await page.fill("#civic-editor .civic-msg input[name=reason]", "Сообщение по существу");
    await page.fill("#civic-editor .civic-msg input[name=public_reply]", "Спасибо, передано подрядчику (тест).");
    await page.click("#civic-editor .civic-msg button:has-text('Одобрить')");
    await page.waitForFunction(() => /одобрено/i.test(document.querySelector("#civic-editor .civic-form-status")?.textContent || ""), null, { timeout: 10000 });
    const approved = await apiFetch(page, "GET", `/objects/${encodeURIComponent(createdId)}/feedback`);
    const items = approved.body?.data?.items || [];
    check("approved message public", items.length === 1 && items[0].text.includes("<b>тест</b>"), items.length);
    check("public feedback has no private fields", items.every((i) => !("consent_public" in i) && !("ip" in i) && !("contact" in i)));
    await page.click("#civic-editor [data-close=editor]");
    await page.click("#civic-map-root .civic-ask");
    await page.waitForSelector("#civic-feedback-root .civic-msg", { timeout: 10000 });
    const xssState = await page.evaluate(() => ({ fired: !!window.__xss, injected: !!document.querySelector("#civic-feedback-root .civic-msg b, #civic-feedback-root .civic-msg img") }));
    check("untrusted text rendered as text (no XSS)", !xssState.fired && !xssState.injected, xssState);
    await page.screenshot({ path: path.join(OUT, "05_public_message_1440.png") });

    // logout closes staff actions on the server
    await page.evaluate(() => window.CivicShell.api.logout());
    const afterLogout = await apiFetch(page, "POST", "/staff/objects", { title: "x", kind: "event", evidence_type: "synthetic" }, { "X-CSRF-Token": csrf });
    check("after logout staff create is refused", afterLogout.status === 401 || afterLogout.status === 403, afterLogout.status);
    const anonStaff = await apiFetch(page, "GET", "/staff/objects");
    check("anonymous staff list refused", anonStaff.status === 401, anonStaff.status);

    // F5 keeps the selection (permalink) and civic mode
    await page.reload();
    await page.waitForFunction(() => window.CivicShell?.mode === "civic" && mapReady, null, { timeout: 30000 });
    await page.waitForFunction(() => /срок перенесён/.test(document.querySelector("#civic-map-root .civic-card")?.textContent || ""), null, { timeout: 15000 }).catch(() => null);
    check("F5 restores civic mode and selected card", /Проверочная запись R01/.test(await page.textContent("#civic-map-root")) && await page.isVisible("#civic-map-root .civic-card"));

    // modes on the same map
    await page.click("#civic-modes [data-mode=training]");
    await page.waitForTimeout(800);
    const training = await page.evaluate(() => ({ district: map.getLayoutProperty("district-fill", "visibility"), score: document.getElementById("city-score").textContent,
      civicLayers: map.getStyle().layers.filter((l) => l.id.startsWith("civic-")).length, canvases: document.querySelectorAll("canvas").length }));
    check("training mode restores district layers, score 52,56, removes civic layers", training.district === "visible" && training.score.includes("52,56") && training.civicLayers === 0 && training.canvases === 1, training);
    await page.click("#civic-modes [data-mode=school]");
    await page.waitForTimeout(1200);
    const school = await page.evaluate(() => ({ active: window.GOVTECH?.active, school: window.GOVTECH?.school, modes: getComputedStyle(document.getElementById("civic-modes")).display }));
    check("school mode reachable, mode switch stays visible", school.active === true && school.school === true && school.modes !== "none", school);
    await page.screenshot({ path: path.join(OUT, "06_school_mode_1440.png") });
    await page.click("#civic-modes [data-mode=civic]");
    await page.waitForTimeout(1500);
    const back = await page.evaluate(() => ({ gov: window.GOVTECH?.active, district: map.getLayoutProperty("district-fill", "visibility"),
      civicLayers: map.getStyle().layers.filter((l) => l.id.startsWith("civic-")).length }));
    check("back to civic: GOVTECH off, districts hidden, civic layers back", back.gov === false && back.district === "none" && back.civicLayers > 0, back);
    check("no page errors (desktop)", page.errs.length === 0, page.errs);
    await ctx.close();

    // ---------------- mobile 390x844
    const m = await openPage(browser, base, { width: 390, height: 844 }, { isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
    await m.page.waitForSelector("#civic-map-root .civic-item", { timeout: 20000 });
    const mob = await m.page.evaluate(() => {
      const attrib = document.querySelector(".maplibregl-ctrl-attrib");
      let attribVisible = null;
      if (attrib && attrib.getBoundingClientRect().width > 0) {
        const r = attrib.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        attribVisible = !!hit && (attrib.contains(hit) || hit === attrib);
      }
      const small = [...document.querySelectorAll("#civic-root button:not([hidden])")].filter((b) => b.offsetParent && b.getBoundingClientRect().height < 36).map((b) => b.textContent.trim().slice(0, 20));
      return { canvases: document.querySelectorAll("canvas").length, scrollW: document.documentElement.scrollWidth, attribVisible,
        panel: document.getElementById("civic-panel").getBoundingClientRect().top, small };
    });
    check("mobile: one canvas, no horizontal scroll", mob.canvases === 1 && mob.scrollW <= 390, mob);
    if (mob.attribVisible === null) notRun("mobile attribution not covered", "no attribution element rendered (offline basemap has no attributed source)");
    else check("mobile attribution not covered", mob.attribVisible, mob);
    check("mobile: bottom sheet below the map", mob.panel > 844 * 0.4, mob.panel);
    check("mobile: tap targets ≥36px", mob.small.length === 0, mob.small);
    await m.page.screenshot({ path: path.join(OUT, "07_civic_start_390.png") });
    await m.page.click("#civic-map-root .civic-item:has-text('Проверочная запись R01')");
    await m.page.waitForSelector("#civic-map-root .civic-card:not([hidden])", { timeout: 10000 });
    await m.page.waitForTimeout(600);
    await m.page.screenshot({ path: path.join(OUT, "08_card_390.png") });
    await m.page.click("#civic-sheet-handle");
    await m.page.waitForTimeout(500);
    await m.page.screenshot({ path: path.join(OUT, "09_card_full_390.png") });
    check("no page errors (mobile)", m.page.errs.length === 0, m.page.errs);
    await m.ctx.close();
  } catch (error) {
    check("flow completed without exception", false, String(error && error.stack || error).slice(0, 1500));
  } finally {
    await browser.close();
    srv.kill();
    result.server_tail = srv.log.split("\n").filter((l) => !/password/i.test(l)).slice(-15);
    fs.rmSync(dbDir, { recursive: true, force: true });
  }
  result.created_id = createdId;
  result.summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length, not_run: checks.filter((c) => c.status === "NOT_RUN").length };
  fs.writeFileSync(path.join(OUT, "p0_flow.json"), JSON.stringify(result, null, 1) + "\n");
  console.log(JSON.stringify(result.summary));
  process.exit(result.summary.fail ? 1 : 0);
})();
