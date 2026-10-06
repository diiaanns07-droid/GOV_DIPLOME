// R01 P0 browser flow on the integrated page (R02 store + R03 map/cards + R04 editor + R06 feedback):
// editor creates -> publishes -> resident sees the card on the light map -> deadline moves with history
// -> resident sends a message -> moderation -> public reply; plus security, F5, modes and mobile.
// Usage: node tests/civic/R01/browser/p0_flow.cjs <out_dir>
// Starts `python3 -B app.py` on a free port with a temporary SQLite file (R02), seeds R05's synthetic
// Astana slice, imports R05's real slice as drafts, and creates an editor through R02's CLI (password
// via stdin, never argv). Nothing is written into the repository.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os"), crypto = require("crypto");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "p0-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff/i;
const PASSWORD = "p0-Esil-" + crypto.randomBytes(9).toString("base64url");
const USER = "p0_editor";
const fk = (k) => `[data-fk="${k}"]`;
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null }); console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined && detail !== null ? " — " + JSON.stringify(detail).slice(0, 400) : "")); };
const notRun = (name, reason) => { checks.push({ name, status: "NOT_RUN", detail: reason }); console.log("NOT_RUN " + name + " — " + reason); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1" };
  // R05 synthetic Astana slice (demo=true) through R02's seed-demo; the real slice (0 records in this
  // environment) goes through `import`, which only ever creates drafts.
  execSync(`python3 -B -m ui.civic_store --db "${db}" seed-demo --package data/civic/astana/demo_synthetic.json`, { cwd: REPO, env, stdio: ["ignore", "ignore", "inherit"] });
  execSync(`python3 -B -m ui.civic_store --db "${db}" import data/civic/astana/objects.json`, { cwd: REPO, env, stdio: ["ignore", "ignore", "inherit"] });
  execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${USER} --password-stdin --display-name "Редактор смоука"`,
    { cwd: REPO, env, input: PASSWORD + "\n", stdio: ["pipe", "ignore", "inherit"] });
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
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
  await page.waitForSelector("#civic-map-root .civic-r03-item", { timeout: 20000 });
  return { ctx, page };
}
const apiFetch = (page, method, p, body, headers) => page.evaluate(async ([method, p, body, headers]) => {
  const r = await fetch("/api/civic/v1" + p, { method, headers: { "Content-Type": "application/json", ...(headers || {}) }, body: body ? JSON.stringify(body) : undefined, credentials: "same-origin" });
  let j = null; try { j = await r.json(); } catch {}
  return { status: r.status, body: j };
}, [method, p, body, headers]);
const okNotice = (page, text) => page.waitForSelector(`#civic-editor-root .civic-r04-msg-ok:has-text("${text}")`, { timeout: 15000 });

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "civic-p0-"));
  const port = await freePort(), base = `http://127.0.0.1:${port}/`;
  const srv = await startServer(port, path.join(dbDir, "civic.sqlite3"));
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const result = { backend: "R02 SQLite (temp) + R06", base, started_at: new Date().toISOString(), checks };
  let createdId = null;
  try {
    const { ctx, page } = await openPage(browser, base, { width: 1440, height: 900 });
    const start = await page.evaluate(() => ({
      modules: { map: window.CivicShell.isFallback("map") ? "R01 fallback" : "R03", editor: window.CivicShell.isFallback("editor") ? "R01 fallback" : "R04",
        feedback: window.CivicShell.isFallback("feedback") ? "R01 fallback" : "R06" },
      canvases: document.querySelectorAll("canvas").length, iframes: document.querySelectorAll("iframe").length,
      district: map.getLayer("district-fill") ? map.getLayoutProperty("district-fill", "visibility") : "absent",
      r03layers: map.getStyle().layers.filter((l) => l.id.startsWith("civic-r03-")).length,
      offline: document.body.classList.contains("offline-basemap"), title: document.title,
      demoLabel: /Демо|синтет/i.test(document.getElementById("civic-map-root").textContent),
    }));
    result.modules = start.modules;
    check("integrated modules in use (R03 map, R04 editor, R06 feedback)", start.modules.map === "R03" && start.modules.editor === "R04" && start.modules.feedback === "R06", start.modules);
    check("default mode is civic (Astana city)", start.title.includes("Астана"), start.title);
    check("one map canvas, no iframe; R03 layers on it", start.canvases === 1 && start.iframes === 0 && start.r03layers > 0, start);
    check("training district layer hidden in civic mode", start.district === "none", start.district);
    check("synthetic demo records visibly labelled", start.demoLabel);
    const pubList = await apiFetch(page, "GET", "/objects");
    const pubItems = pubList.body?.data?.items || [];
    check("R05 demo slice published only as synthetic; drafts/archived hidden", pubItems.length >= 6 && pubItems.every((i) => i.evidence_type === "synthetic")
      && !pubItems.some((i) => /draft-hidden|archived/.test(i.id)), pubItems.map((i) => i.id));
    if (start.offline) notRun("basemap + 3D buildings", "OpenFreeMap host not reachable in this environment (offline background)");
    await page.screenshot({ path: path.join(OUT, "01_civic_start_1440.png") });

    // ---- editor (R04): wrong password, login
    await page.click("#civic-staff-button");
    await page.waitForSelector(fk("login-user"), { timeout: 10000 });
    await page.fill(fk("login-user"), USER);
    await page.fill(fk("login-pass"), "wrong-password-123");
    await page.click(fk("login-submit"));
    await page.waitForTimeout(1200);
    check("wrong password rejected, still on login form", await page.isVisible(fk("login-user")) && !(await page.evaluate(() => window.CivicShell.api.session.authenticated)));
    await page.fill(fk("login-pass"), PASSWORD);
    await page.click(fk("login-submit"));
    await page.waitForSelector(fk("new"), { timeout: 10000 });
    check("editor login via session API", await page.evaluate(() => window.CivicShell.api.session.authenticated));
    const storage = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
    check("no session/CSRF token in web storage", !/csrf|civic_session|token/i.test(storage), storage.slice(0, 160));

    // ---- create draft
    await page.click(fk("new"));
    await page.fill(fk("title"), "Проверочный ремонт тротуара R01 (синтетика)");
    await page.selectOption(fk("kind"), "roadworks");
    await page.selectOption(fk("status"), "planned");
    await page.fill(fk("description"), "Создано смоуком R01. Не сведения о реальных работах.");
    await page.check("#civic-editor-root input[type=radio][value=synthetic]");
    await page.fill(fk("planned_start"), "2026-10-14");
    await page.fill(fk("original_planned_end"), "2026-10-30");
    await page.click(fk("tool-point"));
    const box = await page.locator("#map").boundingBox();
    await page.mouse.click(box.x + box.width * 0.55, box.y + box.height * 0.5);
    await page.check(fk("geometry_confirmed")).catch(() => null);
    await page.click(fk("save"));
    await okNotice(page, "Черновик создан");
    createdId = ((await page.textContent("#civic-editor-root .civic-r04-meta")).match(/ID (\S+)/) || [])[1];
    check("draft created with server id", !!createdId, createdId);
    check("draft not visible by direct public ID", (await apiFetch(page, "GET", "/objects/" + encodeURIComponent(createdId))).status === 404);
    const listBefore = await apiFetch(page, "GET", "/objects");
    check("draft not in public list", !(listBefore.body?.data?.items || []).some((i) => i.id === createdId));
    const noCsrf = await apiFetch(page, "POST", `/staff/objects/${encodeURIComponent(createdId)}/publish`, { expected_revision: 1, reason: "x" });
    check("publish without CSRF header rejected", noCsrf.status === 403, noCsrf.status);
    const badCsrf = await apiFetch(page, "POST", `/staff/objects/${encodeURIComponent(createdId)}/publish`, { expected_revision: 1, reason: "x" }, { "X-CSRF-Token": "forged" });
    check("publish with wrong CSRF rejected", badCsrf.status === 403, badCsrf.status);
    await page.screenshot({ path: path.join(OUT, "02_editor_draft_1440.png") });

    // ---- publish with a reason
    await page.click(fk("publish"));
    await page.click(fk("chip-0"));
    await page.click(fk("confirm"));
    await okNotice(page, "Опубликовано");
    const pub = await apiFetch(page, "GET", "/objects/" + encodeURIComponent(createdId));
    check("published object readable publicly", pub.status === 200 && pub.body?.data?.item?.publication === "published", pub.status);
    check("public DTO has no internal/staff fields", pub.status === 200 && !("internal_notes" in pub.body.data.item) && !("staff" in pub.body.data.item), Object.keys(pub.body?.data?.item || {}));
    const csrf = await page.evaluate(async () => (await (await fetch("/api/civic/v1/session")).json()).data.csrf_token);
    const stale = await apiFetch(page, "POST", `/staff/objects/${encodeURIComponent(createdId)}/update`, { expected_revision: 1, changes: { title: "x" }, reason: "stale" }, { "X-CSRF-Token": csrf });
    check("stale revision -> 409", stale.status === 409, stale.status);

    // ---- move the deadline with a reason, then publish the change
    await page.fill(fk("current_planned_end"), "2026-11-15");
    await page.click(fk("save"));
    await page.click(fk("chip-0")).catch(() => null);
    await page.fill(fk("reason"), "Перенос срока: проверка истории (смоук R01)");
    await page.click(fk("save"));
    await okNotice(page, "Жители пока видят опубликованную версию");
    const beforeRepublish = await apiFetch(page, "GET", "/objects/" + encodeURIComponent(createdId));
    check("saved change not public until published", beforeRepublish.body?.data?.item?.schedule?.current_planned_end === "2026-10-30", beforeRepublish.body?.data?.item?.schedule);
    await page.click(fk("publish"));
    await page.fill(fk("reason"), "Перенос срока: подрядчик сообщил о задержке (смоук R01)");
    await page.click(fk("confirm"));
    await okNotice(page, "Изменения опубликованы");
    const moved = await apiFetch(page, "GET", "/objects/" + encodeURIComponent(createdId));
    const sch = moved.body?.data?.item?.schedule || {};
    check("deadline moved, original kept", sch.original_planned_end === "2026-10-30" && sch.current_planned_end === "2026-11-15", sch);
    check("public history has the reason", (moved.body?.data?.history || []).some((h) => /задержке/.test(h.reason || "")), (moved.body?.data?.history || []).map((h) => h.reason));
    check("public history has no login names", !JSON.stringify(moved.body?.data?.history || []).includes(USER));
    await page.screenshot({ path: path.join(OUT, "03_editor_published_change_1440.png") });
    await page.click("#civic-editor [data-close=editor]");

    // ---- resident card (R03)
    // onPublished -> the shell already selected the object in R03 (card open); otherwise pick it in the list.
    const cardOpen = await page.waitForFunction(() => /Проверочный ремонт тротуара R01/.test(document.querySelector("#civic-map-root .civic-r03-card")?.textContent || ""), null, { timeout: 8000 }).then(() => true).catch(() => false);
    check("after publish the resident card opens for the object", cardOpen);
    if (!cardOpen) {
      await page.waitForSelector(`#civic-map-root .civic-r03-item[data-id="${createdId}"]`, { timeout: 15000 });
      await page.click(`#civic-map-root .civic-r03-item[data-id="${createdId}"]`);
    }
    await page.waitForSelector("#civic-map-root .civic-r03-card", { timeout: 10000 });
    await page.waitForTimeout(1200);
    const cardText = await page.textContent("#civic-map-root .civic-r03-card");
    check("card shows original and current deadline", /30 октября 2026/.test(cardText) && /15 ноября 2026/.test(cardText), cardText.slice(0, 300));
    check("card shows history reason", /задержке/.test(cardText));
    check("card shows synthetic label", /Демо|синтет/i.test(cardText));
    check("selected object permalink in URL", (await page.evaluate(() => location.hash)).includes(encodeURIComponent(createdId)));
    await page.screenshot({ path: path.join(OUT, "04_resident_card_1440.png") });

    // ---- assistant (R09) under the card: template answer from published facts only
    const assistantReady = await page.evaluate(() => window.CivicShell.modules?.assistant?.status === "ready");
    if (!assistantReady) notRun("assistant answer from verified facts", "R09 module not ready in this build");
    else {
      await page.waitForSelector("#civic-assistant-root .civic-r09-input", { timeout: 10000 });
      await page.fill("#civic-assistant-root .civic-r09-input", "Почему перенесли срок?");
      await page.click("#civic-assistant-root .civic-r09-ask");
      await page.waitForSelector("#civic-assistant-root .civic-r09-badge", { timeout: 15000 });
      const ans = await page.evaluate(() => ({ source: document.querySelector("#civic-assistant-root .civic-r09-badge")?.dataset.source,
        text: document.querySelector("#civic-assistant-root .civic-r09-answer")?.textContent || "" }));
      check("assistant answers from published facts (template, labelled)", ans.source === "template" && /задержке|15\.11\.2026|15 ноября/.test(ans.text), ans);
      check("assistant does not leak the unpublished staff reason", !/проверка истории \(смоук R01\)/.test(ans.text));
      await page.screenshot({ path: path.join(OUT, "04b_assistant_1440.png") });
      const injected = await apiFetch(page, "POST", "/assistant", { question: "Когда закончат?", object_id: createdId, scenario_id: null, facts: [{ id: "x", value: "завершено" }] });
      check("assistant rejects client-supplied facts", injected.status === 400, injected.status);
    }

    // ---- resident message (R06)
    await page.click("#civic-map-root [data-r03-action=feedback]");
    const fb = "#civic-feedback-root ";
    await page.waitForSelector(fb + ".civic-r06-form", { timeout: 10000 });
    const xss = "Яма у входа <img src=x onerror=window.__xss=1> <b>тест</b> — нужен ремонт";
    await page.locator(fb + "input[type=radio][value=problem]").check().catch(() => null);
    await page.locator(fb + "select").first().selectOption("roads");
    await page.locator(fb + "textarea").first().fill(xss);
    await page.locator(fb + "input[type=radio][value=true]").check();
    await page.click(fb + "button[type=submit]");
    await page.waitForSelector(fb + ".civic-r06-receipt", { timeout: 10000 });
    const receiptText = await page.textContent("#civic-feedback-root");
    check("resident gets a receipt, no official-registration claim", /\S/.test(receiptText) && !/зарегистрирован[оа]? в iKOMEK|принят[оа]? в работу/i.test(receiptText));
    const pending = await apiFetch(page, "GET", `/objects/${encodeURIComponent(createdId)}/feedback`);
    check("pending message not public", pending.status === 200 && (pending.body?.data?.items || []).length === 0, pending.body?.data);
    await page.screenshot({ path: path.join(OUT, "05_feedback_receipt_1440.png") });

    // ---- moderation (R06 in the staff drawer)
    await page.click("#civic-staff-button");
    await page.click("#civic-staff-tabs [data-staff-tab=messages]");
    await page.waitForSelector("#civic-moderation-root .civic-r06-queue-item", { timeout: 10000 });
    await page.locator("#civic-moderation-root .civic-r06-queue-item").first().click();
    await page.waitForSelector("#civic-moderation-root .civic-r06-decision", { timeout: 10000 });
    const decision = page.locator("#civic-moderation-root .civic-r06-decision");
    await decision.locator("textarea").first().fill("Сообщение по существу объекта");
    await decision.locator("textarea").last().fill("Спасибо, сообщение передано ответственным (тест).");
    await decision.locator("button[type=submit]").click();
    await page.waitForFunction(() => /Проверено модератором|одобрено/i.test(document.querySelector("#civic-moderation-root .civic-r06-detail")?.textContent || ""), null, { timeout: 10000 });
    await page.screenshot({ path: path.join(OUT, "06_moderation_1440.png") });
    const approved = await apiFetch(page, "GET", `/objects/${encodeURIComponent(createdId)}/feedback`);
    const items = approved.body?.data?.items || [];
    check("approved message public with reply", items.length === 1 && JSON.stringify(items[0]).includes("<b>тест</b>") && /передано/.test(JSON.stringify(items[0])), items.length);
    check("public feedback has no private fields", items.every((i) => !("ip" in i) && !("client_hash" in i) && !("contact" in i) && !("reason" in i) && !("moderated_by" in i)), items.map((i) => Object.keys(i)));
    await page.click("#civic-editor [data-close=editor]");
    await page.click("#civic-map-root [data-r03-action=feedback]");
    await page.waitForSelector("#civic-feedback-root .civic-r06-public-item", { timeout: 10000 });
    const xssState = await page.evaluate(() => ({ fired: !!window.__xss, injected: !!document.querySelector("#civic-feedback-root .civic-r06-public-item b, #civic-feedback-root .civic-r06-public-item img") }));
    check("untrusted text rendered as text (no XSS)", !xssState.fired && !xssState.injected, xssState);
    await page.screenshot({ path: path.join(OUT, "07_public_message_1440.png") });

    // ---- logout closes staff actions on the server
    await page.evaluate(() => window.CivicShell.api.logout());
    const afterLogout = await apiFetch(page, "POST", "/staff/objects", { title: "x", kind: "event", evidence_type: "synthetic" }, { "X-CSRF-Token": csrf });
    check("after logout staff create is refused", afterLogout.status === 401 || afterLogout.status === 403, afterLogout.status);
    check("anonymous staff list refused", (await apiFetch(page, "GET", "/staff/objects")).status === 401);

    // ---- F5 keeps civic mode and the permalinked card
    await page.reload();
    await page.waitForFunction(() => window.CivicShell?.mode === "civic" && mapReady, null, { timeout: 30000 });
    const f5 = await page.waitForFunction(() => document.querySelector("#civic-map-root .civic-r03-card")?.textContent.includes("Проверочный ремонт тротуара R01"), null, { timeout: 15000 }).then(() => true).catch(() => false);
    check("F5 restores civic mode and the selected card", f5);

    // ---- modes on the same map
    await page.click("#civic-modes [data-mode=training]");
    await page.waitForTimeout(900);
    const training = await page.evaluate(() => ({ district: map.getLayoutProperty("district-fill", "visibility"), score: document.getElementById("city-score").textContent,
      civicLayers: map.getStyle().layers.filter((l) => l.id.startsWith("civic-")).length, canvases: document.querySelectorAll("canvas").length }));
    check("training mode: district layers, score 52,56, no civic layers, one canvas", training.district === "visible" && training.score.includes("52,56") && training.civicLayers === 0 && training.canvases === 1, training);
    await page.click("#civic-modes [data-mode=school]");
    await page.waitForTimeout(1200);
    const school = await page.evaluate(() => ({ active: window.GOVTECH?.active, school: window.GOVTECH?.school, modes: getComputedStyle(document.getElementById("civic-modes")).display }));
    check("school mode reachable, mode switch stays visible", school.active === true && school.school === true && school.modes !== "none", school);
    await page.screenshot({ path: path.join(OUT, "08_school_mode_1440.png") });
    await page.click("#civic-modes [data-mode=civic]");
    await page.waitForTimeout(1500);
    const back = await page.evaluate(() => ({ gov: window.GOVTECH?.active, district: map.getLayoutProperty("district-fill", "visibility"),
      civicLayers: map.getStyle().layers.filter((l) => l.id.startsWith("civic-r03-")).length }));
    check("back to civic: GOVTECH off, districts hidden, R03 layers back", back.gov === false && back.district === "none" && back.civicLayers > 0, back);
    check("no page errors (desktop)", page.errs.length === 0, page.errs);
    await ctx.close();

    // ---- mobile 390x844
    const m = await openPage(browser, base, { width: 390, height: 844 }, { isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
    const mob = await m.page.evaluate(() => {
      const attrib = document.querySelector(".maplibregl-ctrl-attrib");
      let attribVisible = null;
      if (attrib && attrib.getBoundingClientRect().width > 0) {
        const r = attrib.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        attribVisible = !!hit && (attrib.contains(hit) || hit === attrib);
      }
      const small = [...document.querySelectorAll("#civic-root button")].filter((b) => b.offsetParent && b.getBoundingClientRect().height < 36 && b.getBoundingClientRect().width > 0).map((b) => (b.className + ":" + b.textContent.trim()).slice(0, 40));
      return { canvases: document.querySelectorAll("canvas").length, scrollW: document.documentElement.scrollWidth, attribVisible,
        panelTop: document.getElementById("civic-panel").getBoundingClientRect().top, small };
    });
    check("mobile: one canvas, no horizontal scroll", mob.canvases === 1 && mob.scrollW <= 390, mob);
    if (mob.attribVisible === null) notRun("mobile attribution not covered", "no attribution element rendered (offline basemap has no attributed source)");
    else check("mobile attribution not covered", mob.attribVisible, mob);
    check("mobile: bottom sheet leaves the map visible", mob.panelTop > 844 * 0.4, mob.panelTop);
    check("mobile: tap targets ≥36px", mob.small.length === 0, mob.small);
    await m.page.screenshot({ path: path.join(OUT, "09_civic_start_390.png") });
    await m.page.click(`#civic-map-root .civic-r03-item[data-id="${createdId}"]`);
    await m.page.waitForSelector("#civic-map-root .civic-r03-card", { timeout: 10000 });
    await m.page.waitForTimeout(800);
    await m.page.screenshot({ path: path.join(OUT, "10_card_390.png") });
    await m.page.click("#civic-sheet-handle");
    await m.page.waitForTimeout(500);
    await m.page.screenshot({ path: path.join(OUT, "11_card_full_390.png") });
    check("no page errors (mobile)", m.page.errs.length === 0, m.page.errs);
    await m.ctx.close();
  } catch (error) {
    check("flow completed without exception", false, String(error && error.stack || error).slice(0, 1500));
  } finally {
    await browser.close();
    srv.kill();
    result.server_tail = srv.log.split("\n").filter((l) => !/password/i.test(l)).slice(-12);
    fs.rmSync(dbDir, { recursive: true, force: true });
  }
  result.created_id = createdId;
  result.summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length, not_run: checks.filter((c) => c.status === "NOT_RUN").length };
  fs.writeFileSync(path.join(OUT, "p0_flow.json"), JSON.stringify(result, null, 1) + "\n");
  console.log(JSON.stringify(result.summary));
  process.exit(result.summary.fail ? 1 : 0);
})();
