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
// R03's intermittent "Image civic-r03-demo-ring could not be loaded" (race after the offline style
// swap; R03-owned, fix proposed in research/round-13-results/R01/proposed/r03_r01_proposal.patch) is
// reported as its own FAIL so it neither hides other page errors nor masquerades as an R01 error.
const R03_RING = /Image "civic-r03-demo-ring" could not be loaded/;
function checkPageErrors(name, errs) {
  const ring = errs.filter((e) => R03_RING.test(e)), other = errs.filter((e) => !R03_RING.test(e));
  check(name, other.length === 0, other);
  if (ring.length) check(name + " — R03 demo-ring image race (R03-owned)", false, ring.length + " warning(s)");
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1" };
  // R05 synthetic Astana slice (demo=true) through R02's seed-demo; the real slice (0 records in this
  // environment) goes through `import`, which only ever creates drafts.
  execSync(`python3 -B -m ui.civic_store --db "${db}" init`, { cwd: REPO, env, stdio: ["ignore", "ignore", "inherit"] });
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
    // ?tools=all: this flow also checks the round-13 assistant and scenarios, hidden from Birge by default.
    const { ctx, page } = await openPage(browser, base + "?tools=all", { width: 1440, height: 900 });
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
    // R04 >= 69d5691: the place precision is chosen first; the drawing tools appear after it.
    if (await page.locator(fk("place-approximate")).count()) await page.check(fk("place-approximate"));
    await page.click(fk("tool-point"));
    await page.evaluate(() => document.activeElement?.blur());
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);
    check("Escape with the map tool active cancels the tool, not the editor", await page.locator("#civic-editor").isVisible()
      && await page.locator(fk("title")).inputValue() !== "");
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

    // ---- R10-D010: a stale save shows R04's conflict panel; its action must be reachable by pointer
    // (not hidden under the sticky action bar). The bump comes from a "second tab" (same session, API).
    await page.fill(fk("description"), "Создано смоуком R01. Правка для проверки конфликта версий.");
    await page.click(fk("save"));
    await page.click(fk("chip-0")).catch(() => null);
    if (await page.locator(fk("reason")).count()) await page.fill(fk("reason"), "Уточнение описания (смоук R01, конфликт)");
    const revNow = (await apiFetch(page, "GET", "/staff/objects/" + encodeURIComponent(createdId))).body?.data?.item?.revision;
    const bump = await apiFetch(page, "POST", `/staff/objects/${encodeURIComponent(createdId)}/update`,
      { expected_revision: revNow, changes: { evidence_notes: "Правка из второй вкладки (смоук R01)." }, reason: "Вторая вкладка (смоук R01)" }, { "X-CSRF-Token": csrf });
    await page.click(fk("save"));
    const conflictShown = await page.waitForSelector('#civic-editor [aria-label="Конфликт версий"]', { timeout: 15000 }).then(() => true).catch(() => false);
    const conflictReach = conflictShown && await page.locator(fk("rebase")).click({ trial: true, timeout: 5000 }).then(() => true).catch(() => false);
    const conflictGeo = await page.evaluate(() => {
      const a = document.querySelector("#civic-editor .civic-r04-actions")?.getBoundingClientRect();
      const b = document.querySelector("#civic-editor .civic-r04-body")?.getBoundingClientRect();
      return { actions: a ? Math.round(a.height) : null, body: b ? Math.round(b.height) : null,
        descriptionKept: document.querySelector('#civic-editor [data-fk="description"]')?.value.includes("конфликта версий") };
    });
    await page.screenshot({ path: path.join(OUT, "03b_editor_conflict_1440.png") });
    check("409 in the editor: conflict panel shown, typed text kept, action reachable by pointer (R10-D010)",
      bump.status === 200 && conflictShown && conflictReach && conflictGeo.descriptionKept, { bump: bump.status, conflictShown, conflictReach, ...conflictGeo });
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
    const btnColors = await page.evaluate(() => { const b = document.querySelector("#civic-map-root [data-r03-action=feedback]"); const cs = b && getComputedStyle(b);
      return cs ? { color: cs.color, bg: cs.backgroundColor, text: b.textContent.trim() } : null; });
    check("card action button text is visible (color differs from background)", !!btnColors && btnColors.color !== btnColors.bg && /\S/.test(btnColors.text), btnColors);
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
    check("moderation button only for a signed-in editor", await page.isVisible("#civic-moderation-button"));
    await page.click("#civic-moderation-button");
    await page.waitForSelector("#civic-moderation-root .civic-r06-queue-item", { timeout: 10000 });
    const deskFoot = await page.evaluate(() => { const f = document.querySelector(".civic-foot"), p = document.getElementById("civic-panel");
      return { footScroll: f.scrollWidth, footClient: f.clientWidth, panelScrollLeft: p.scrollLeft,
        out: [...f.querySelectorAll("button")].filter((b) => b.offsetParent).filter((b) => b.getBoundingClientRect().right > p.getBoundingClientRect().right + 0.5).length }; });
    check("desktop staff footer: no clipping, panel not scrolled sideways (R10-D011)", deskFoot.footScroll <= deskFoot.footClient && deskFoot.panelScrollLeft === 0 && deskFoot.out === 0, deskFoot);
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
    await page.click("#civic-moderation [data-close=moderation]");
    await page.click("#civic-map-root [data-r03-action=feedback]");
    await page.waitForSelector("#civic-feedback-root .civic-r06-public-item", { timeout: 10000 });
    const xssState = await page.evaluate(() => ({ fired: !!window.__xss, injected: !!document.querySelector("#civic-feedback-root .civic-r06-public-item b, #civic-feedback-root .civic-r06-public-item img") }));
    check("untrusted text rendered as text (no XSS)", !xssState.fired && !xssState.injected, xssState);
    await page.screenshot({ path: path.join(OUT, "07_public_message_1440.png") });

    // ---- logout closes staff actions on the server
    await page.evaluate(() => window.CivicShell.api.logout());
    check("moderation button hidden after logout", await page.locator("#civic-moderation-button").isHidden());
    const afterLogout = await apiFetch(page, "POST", "/staff/objects", { title: "x", kind: "event", evidence_type: "synthetic" }, { "X-CSRF-Token": csrf });
    check("after logout staff create is refused", afterLogout.status === 401 || afterLogout.status === 403, afterLogout.status);
    check("anonymous staff list refused", (await apiFetch(page, "GET", "/staff/objects")).status === 401);

    // ---- F5 keeps civic mode and the permalinked card
    await page.reload();
    await page.waitForFunction(() => window.CivicShell?.mode === "civic" && mapReady, null, { timeout: 30000 });
    const f5 = await page.waitForFunction(() => document.querySelector("#civic-map-root .civic-r03-card")?.textContent.includes("Проверочный ремонт тротуара R01"), null, { timeout: 15000 }).then(() => true).catch(() => false);
    check("F5 restores civic mode and the selected card", f5);

    // ---- modes on the same map (round 14: «Учебная модель» и «Школы» убраны из меню карты — только по ссылке)
    const menu = await page.evaluate(() => ({ modes: getComputedStyle(document.getElementById("civic-modes")).display,
      birge: !!document.querySelector("#birge-header") && getComputedStyle(document.querySelector("#birge-header")).display !== "none" }));
    check("civic map: old mode switch hidden, Birge header shown", menu.modes === "none" && menu.birge, menu);
    await page.evaluate(() => { location.hash = "#training"; });
    await page.waitForTimeout(900);
    const training = await page.evaluate(() => ({ district: map.getLayoutProperty("district-fill", "visibility"), score: document.getElementById("city-score").textContent,
      civicLayers: map.getStyle().layers.filter((l) => l.id.startsWith("civic-")).length, canvases: document.querySelectorAll("canvas").length }));
    const header = await page.evaluate(() => { const bar = document.querySelector(".topbar").getBoundingClientRect();
      const kids = [...document.querySelectorAll(".topbar .top-center *, .topbar .brand *")].filter((e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden");
      const outside = kids.map((e) => e.getBoundingClientRect()).filter((r) => r.height > 0 && (r.top < bar.top - 0.5 || r.bottom > bar.bottom + 0.5));
      return { bar: [Math.round(bar.top), Math.round(bar.bottom)], outside: outside.length, scrollW: document.documentElement.scrollWidth }; });
    check("training mode header text stays inside the top bar at 1440 (R10-D012)", header.outside === 0 && header.scrollW <= 1440, header);
    await page.screenshot({ path: path.join(OUT, "07b_training_mode_1440.png") });
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
    await page.evaluate(() => { location.hash = "#training"; });
    const hashTraining = await page.waitForFunction(() => window.CivicShell.mode === "training", null, { timeout: 5000 }).then(() => true).catch(() => false);
    await page.evaluate((id) => { location.hash = "#object=" + encodeURIComponent(id); }, createdId);
    const hashCard = await page.waitForFunction(() => window.CivicShell.mode === "civic"
      && document.querySelector("#civic-map-root .civic-r03-card")?.textContent.includes("Проверочный ремонт тротуара R01"), null, { timeout: 15000 }).then(() => true).catch(() => false);
    check("in-page #training / #object= links switch mode and open the card", hashTraining && hashCard, { hashTraining, hashCard });
    await page.evaluate(() => { location.hash = "#object=no-such-object-r01"; });
    // Адрес очищается после ответа 404 модуля карты — ждём условие, а не паузу (B3: запасной фон грузит оси улиц).
    await page.waitForFunction(() => !location.hash.includes("no-such"), null, { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(300);
    const unknownLink = await page.evaluate(() => ({ assistantHidden: document.getElementById("civic-assistant-box").hidden,
      assistantEmpty: !document.getElementById("civic-assistant-root").textContent.trim(), hash: location.hash }));
    check("unknown/draft permalink: no assistant mounted, hash cleared", unknownLink.assistantHidden && unknownLink.assistantEmpty && !unknownLink.hash.includes("no-such"), unknownLink);
    checkPageErrors("no page errors (desktop)", page.errs);
    await ctx.close();

    // ---- mobile 390x844
    const m = await openPage(browser, base + "?tools=all", { width: 390, height: 844 }, { isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
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
    // Round 14: a phone opens in the resident view — akimat tools hidden, sign-in kept; the ≡ menu switches to «Акимат».
    const resident = await m.page.evaluate(() => ({ mode: window.BirgeShell?.mode,
      scen: getComputedStyle(document.getElementById("civic-scenarios-button")).display,
      staff: getComputedStyle(document.getElementById("civic-staff-button")).display }));
    check("mobile: resident view by default, akimat tools hidden, sign-in kept", resident.mode === "resident" && resident.scen === "none" && resident.staff !== "none", resident);
    await m.page.click("#birge-header .birge-menu-btn");
    await m.page.click("#birge-header [data-mode=akimat]");
    const akimat = await m.page.evaluate(() => ({ mode: window.BirgeShell.mode, menu: document.getElementById("birge-header").dataset.menu,
      scen: getComputedStyle(document.getElementById("civic-scenarios-button")).display }));
    check("mobile: ≡ menu switches to the akimat view and closes", akimat.mode === "akimat" && akimat.menu === "closed" && akimat.scen !== "none", akimat);
    const attribSlot = () => m.page.evaluate(() => {
      const holder = document.querySelector(".maplibregl-ctrl-bottom-right");
      if (!holder) return { ok: false, reason: "no control container" };
      let el = holder.querySelector(".maplibregl-ctrl-attrib");
      const injected = !el || el.getBoundingClientRect().width === 0;
      if (injected && !document.getElementById("r01-test-attrib")) {
        el = document.createElement("div");
        el.id = "r01-test-attrib";
        el.className = "maplibregl-ctrl";
        el.style.cssText = "background:#fff;font-size:11px;padding:2px 6px";
        el.textContent = "© тестовая атрибуция R01";
        holder.appendChild(el);
      }
      el = document.getElementById("r01-test-attrib") || el;
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return { ok: !!hit && (el === hit || el.contains(hit)) && r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth,
        injected, rect: [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)],
        sheet: document.body.dataset.civicSheet || null, drawer: document.body.dataset.civicDrawer || null,
        _cleanup: document.getElementById("r01-test-attrib")?.remove() };
    });
    const slots = [await attribSlot()];
    await m.page.click(`#civic-map-root .civic-r03-item[data-id="${createdId}"]`);
    await m.page.waitForSelector("#civic-map-root .civic-r03-card", { timeout: 10000 });
    await m.page.waitForTimeout(800);
    await m.page.screenshot({ path: path.join(OUT, "10_card_390.png") });
    await m.page.click("#civic-sheet-handle");
    await m.page.waitForTimeout(500);
    await m.page.screenshot({ path: path.join(OUT, "11_card_full_390.png") });
    slots.push(await attribSlot());
    // Signed-in editor on a phone: footer gains the moderation button; nothing may overflow.
    await m.page.evaluate(([u, p]) => window.CivicShell.api.login(u, p), [USER, PASSWORD]);
    await m.page.waitForSelector("#civic-moderation-button:not([hidden])", { timeout: 10000 });
    const foot = await m.page.evaluate(() => ({ scrollW: document.documentElement.scrollWidth,
      out: [...document.querySelectorAll(".civic-foot button")].filter((b) => b.offsetParent).map((b) => b.getBoundingClientRect())
        .filter((r) => r.right > innerWidth + 0.5 || r.left < -0.5).length }));
    check("mobile: staff footer fits (3 buttons, no overflow)", foot.scrollW <= 390 && foot.out === 0, foot);
    await m.page.screenshot({ path: path.join(OUT, "12_staff_footer_390.png") });
    // R04 form on a phone: its sticky action bar must leave room for the form/conflict panel (R10-D010).
    await m.page.evaluate(() => window.CivicShell.openEditor());
    await m.page.click(fk("new"));
    await m.page.waitForSelector("#civic-editor .civic-r04-actions", { timeout: 10000 });
    const barGeo = await m.page.evaluate(() => ({ bar: parseFloat(getComputedStyle(document.querySelector("#civic-editor .civic-r04-actions")).maxHeight),
      body: document.querySelector("#civic-editor .civic-r04-body").getBoundingClientRect().height,
      drawerTop: document.getElementById("civic-editor").getBoundingClientRect().top }));
    check("mobile editor: action bar capped below the form body height, map visible above the drawer", barGeo.bar < barGeo.body * 0.75 && barGeo.drawerTop > 844 * 0.3, barGeo);
    await m.page.screenshot({ path: path.join(OUT, "12b_editor_390.png") });
    await m.page.click("#civic-editor [data-close=editor]");
    // Drawers are bottom sheets on a phone: map stays visible above, attribution moves above the drawer.
    await m.page.click("#civic-scenarios-button");
    await m.page.waitForTimeout(600);
    const drawer = await m.page.evaluate(() => ({ top: document.getElementById("civic-scenarios").getBoundingClientRect().top,
      flag: document.body.dataset.civicDrawer || null }));
    slots.push(await attribSlot());
    check("mobile: drawer is a bottom sheet, map visible above it", drawer.flag === "open" && drawer.top > 844 * 0.3, drawer);
    check("mobile: attribution slot visible in half/full sheet and with a drawer (test element if none rendered)", slots.every((x) => x.ok), slots);
    await m.page.screenshot({ path: path.join(OUT, "13_drawer_390.png") });
    await m.page.click("#civic-scenarios [data-close=scenarios]");
    await m.page.evaluate(() => document.getElementById("r01-test-attrib")?.remove());
    // F5 with a valid HttpOnly session cookie: the shell learns the session on boot (no re-login).
    await m.page.reload();
    await m.page.waitForFunction(() => window.CivicShell?.mode === "civic" && mapReady, null, { timeout: 30000 });
    const f5staff = await m.page.waitForSelector("#civic-moderation-button:not([hidden])", { timeout: 10000 }).then(() => true).catch(() => false);
    check("F5 with a valid session: staff buttons return without re-login", f5staff);
    checkPageErrors("no page errors (mobile)", m.page.errs);
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
