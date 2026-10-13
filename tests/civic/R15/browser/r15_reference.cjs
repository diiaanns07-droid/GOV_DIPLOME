// R15: безопасность экранов «по эталону A + качество Linear» (research/round-14/design/README.md, 13 окт).
// Эталон добавляет на экраны чужой текст: цитату жалобы в карточке объекта, названия и описания идей в листе проектов,
// горячие места в сводке и подсказках поиска, вопросы жителей; плюс поиск с подсказками и командную палитру Ctrl+K.
// Проверка: жители (без входа, свои id устройства) пишут HTML-нагрузку во все эти поля, сотрудник публикует идею и
// вопрос, затем браузер проходит экраны акимата (1366×768) и жителя (375×812). После каждого шага считаются:
//   injected — элементы [data-r15x] в DOM (текст стал HTML; CSP скрипт заблокирует, но разметка уже чужая),
//   ran      — сработавшие обработчики нагрузки (window.__r15xss),
//   csp      — нарушения CSP на странице (securitypolicyviolation),
//   private  — у жителя виден текст чужой жалобы (метка R15XTEXT) — личное в публичном виде.
// Шага нет в сборке (нет палитры, нет вкладок) — он пропускается и пишется в отчёт как NOT_RUN, а не PASS.
// Запуск: NODE_PATH=<node_modules с playwright> node tests/civic/R15/browser/r15_reference.cjs <сборка> <out_dir>
// Только локальный экземпляр: сервер сборки на 127.0.0.1, временная SQLite, синтетические демо-данные.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync, execFileSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(process.argv[2] || path.resolve(__dirname, "../../../.."));
const OUT = path.resolve(process.argv[3] || "r15-reference-out");
const USER = "operator", PASSWORD = "Tz7-qerB-91vk-Lmsd";
const POINT = [71.4148, 51.1131];
const PAY = (tag) => `<img src=x data-r15x="${tag}" onerror="window.__r15xss=(window.__r15xss||0)+1"><b data-r15x="${tag}b">R15X</b>`;
const PRIVATE = "R15XTEXT";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const steps = [];

const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });
async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: ["pipe", "ignore", "inherit"] });
  run("init"); run("seed-demo --package data/civic/astana/demo_synthetic.json");
  try { run("seed-r14-demo"); } catch { /* старые сборки без демо раунда 14 */ }
  run(`create-editor ${USER} --password-stdin`, PASSWORD + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

// Счётчики на странице: элементы нагрузки (и в shadow DOM), сработавшие обработчики, нарушения CSP, личное.
const probe = (page, resident) => page.evaluate(([mark, resident]) => {
  let injected = 0;
  const walk = (root) => { injected += root.querySelectorAll("[data-r15x]").length;
    for (const el of root.querySelectorAll("*")) if (el.shadowRoot) walk(el.shadowRoot); };
  walk(document);
  const text = document.body ? document.body.innerText : "";
  return { injected, ran: window.__r15xss || 0, csp: (window.__r15csp || []).slice(0, 5),
    private: resident ? text.includes(mark) : false, shows_payload_text: text.includes("R15X") };
}, [PRIVATE, resident]);

async function step(page, name, resident, action) {
  let note = null, run = true;
  try { const r = await action(); if (r === false) run = false; else if (typeof r === "string") note = r; }
  catch (e) { run = false; note = "ошибка шага: " + String(e.message || e).split("\n")[0].slice(0, 160); }
  await sleep(500);
  const p = await probe(page, resident);
  const bad = p.injected > 0 || p.ran > 0 || p.private || p.csp.some((v) => !/img-src|connect-src/.test(v));
  const status = !run ? "NOT_RUN" : bad ? "FAIL" : "PASS";
  steps.push({ name, status, note, ...p });
  console.log(`${status} ${name}${note ? " — " + note : ""} ${JSON.stringify(p)}`);
  await page.screenshot({ path: path.join(OUT, name.replace(/[^a-z0-9]+/gi, "_") + ".png") }).catch(() => null);
}

// Кликнуть самый близкий «кликабельный» предок текста R15X (карточка идеи, строка списка, горячее место).
const clickPayloadText = (page, scope) => page.evaluate((scope) => {
  const root = scope ? document.querySelector(scope) : document.body;
  if (!root) return false;
  const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = tw.nextNode(); n; n = tw.nextNode()) {
    if (!n.nodeValue.includes("R15X") || !n.parentElement || !n.parentElement.getClientRects().length) continue;
    const hit = n.parentElement.closest("button, a, [role=button], [role=option], [role=row], li, article, [tabindex]");
    if (hit) {
      hit.click();
      const el = n.parentElement;   // после клика запись могла перерисоваться — к тексту нагрузки ведём заново
      setTimeout(() => { const again = [...root.querySelectorAll("*")].find((x) => x.childElementCount === 0 && (x.textContent || "").includes("R15X")) || el;
        again.scrollIntoView({ block: "center" }); }, 300);
      return true;
    }
  }
  return false;
}, scope || null);

// Раздел: открыть, затем пройти все видимые вкладки ([role=tab]) и в каждой открыть запись с нагрузкой.
// Снимок в момент, когда нагрузка на экране: доказательство «показана текстом» (evidence-<раздел>-<n>.png).
async function evidence(page, name) {
  if (!(await clickPayloadText(page))) return 0;
  await sleep(700);
  await page.screenshot({ path: path.join(OUT, `evidence-${name}.png`) }).catch(() => null);
  return 1;
}
async function visit(page, id, who) {
  const r = await section(page, id); await sleep(1800);
  let opened = await evidence(page, `${who}-${id}-0`);
  const tabs = await page.evaluate(() => [...document.querySelectorAll("[role=tab]")].filter((x) => x.getClientRects().length).length);
  for (let i = 0; i < tabs; i++) {
    await page.evaluate((i) => { const x = [...document.querySelectorAll("[role=tab]")].filter((y) => y.getClientRects().length)[i]; x && x.click(); }, i);
    await sleep(900);
    opened += await evidence(page, `${who}-${id}-${i + 1}`);
  }
  return (r === "hash" ? "через адрес" : "кнопка") + `, вкладок ${tabs}, открыто записей с нагрузкой ${opened}`;
}
async function ready(page) {
  await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady
    && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => null);
  await sleep(800);
}
const section = (page, id) => page.evaluate((id) => {
  const b = document.querySelector(`#birge-header [data-section=${id}]`);
  if (b) { b.click(); return true; }
  location.hash = "#" + id; return "hash";
}, id);

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r15-ref-"));
  const port = await freePort();
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const base = `http://127.0.0.1:${port}`;
  const seed = { repo: REPO, head: (() => { try { return execSync("git rev-parse --short=8 HEAD", { cwd: REPO }).toString().trim(); } catch { return null; } })() };
  const post = (p, body, dev) => fetch(base + "/api/civic/v2" + p, { method: "POST",
    headers: { "Content-Type": "application/json", Origin: base, "X-Birge-Device": dev }, body: JSON.stringify({ ...body, device_id: dev }) })
    .then(async (r) => ({ status: r.status, body: await r.json().catch(() => null) }));
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  try {
    // 1) Жители пишут нагрузку во все поля, которые эталон выводит на экраны.
    const c = await post("/complaints", { text: `${PAY("complaint")} ${PRIVATE} третий день не горит свет у остановки`,
      category: "lighting", point: POINT }, "device-r15-ref-author-0001");
    const complaint = c.body?.data?.complaint || c.body?.item || null;
    seed.complaint = { status: c.status, id: complaint?.id || null, target: complaint?.target || null };
    let metoo = 0;
    for (let i = 0; complaint && i < 6; i++) metoo += (await post(`/complaints/${complaint.id}/metoo`, {}, `device-r15-ref-voter-${String(i).padStart(6, "0")}`)).status === 200 ? 1 : 0;
    seed.metoo = metoo;
    const ideaBody = (title, description) => ({ title, description, geometry: { type: "Point", coordinates: POINT } });
    const hostile = await post("/ideas", ideaBody(`${PAY("idea-title")} Сквер у дома`, `${PAY("idea-text")} Деревья и скамейки`), "device-r15-ref-idea-0001");
    seed.idea = { hostile_status: hostile.status, hostile_error: hostile.status >= 400 ? hostile.body?.fields || hostile.body : undefined };
    let ideaId = hostile.body?.item?.id || null;
    if (!ideaId) {
      // Сервер R06 HTML не принимает — проверяем экран отдельно: обычная идея, затем нагрузка прямо в базе
      // (как запись из старого импорта или другой версии модуля). Экран обязан показать её только текстом.
      const plain = await post("/ideas", ideaBody("Сквер у дома R15", "Деревья, дорожки и скамейки во дворе"), "device-r15-ref-idea-0002");
      ideaId = plain.body?.item?.id || null;
      seed.idea.plain_status = plain.status;
      if (ideaId) {
        const py = `import json,sqlite3,sys\ndb=sqlite3.connect(sys.argv[1]);row=db.execute("SELECT texts_json FROM civic_ideas WHERE id=?",(sys.argv[2],)).fetchone()\n` +
          `t=json.loads(row[0])\ndef put(v,tag):\n    return {k:(put(x,tag) if isinstance(x,dict) else (sys.argv[3].replace("TAG",tag+"-"+k)+" "+x if isinstance(x,str) else x)) for k,x in v.items()}\n` +
          `db.execute("UPDATE civic_ideas SET texts_json=? WHERE id=?",(json.dumps(put(t,"idea"),ensure_ascii=False),sys.argv[2]));db.commit();print("ok")`;
        seed.idea.db_injected = execFileSync("python3", ["-I", "-c", py, path.join(tmp, "civic.sqlite3"), ideaId, PAY("TAG")]).toString().trim();
      }
    }
    seed.idea.id = ideaId;
    const q = await post("/questions", { text: `${PAY("question")} Когда отремонтируют двор и парковку у школы?`, district: "nura" }, "device-r15-ref-ask-0001");
    seed.question = { status: q.status, id: q.body?.question?.id || q.body?.item?.id || null, error: q.status >= 400 ? q.body : undefined };

    // 2) Акимат, 1366×768: сотрудник входит, публикует идею и вопрос, проходит экраны эталона.
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    await ctx.addInitScript(() => {
      try { localStorage.setItem("birge.mode", "akimat"); } catch (e) {}
      document.addEventListener("securitypolicyviolation", (e) => (window.__r15csp = window.__r15csp || []).push(e.violatedDirective + " " + (e.blockedURI || "")));
    });
    const page = await ctx.newPage();
    await page.goto(base + "/"); await ready(page);
    seed.login = await page.evaluate(([u, p]) => window.CivicShell.api.login(u, p).then(() => "ok", (e) => String(e)), [USER, PASSWORD]);
    const v2 = (m, p, b) => page.evaluate(([m, p, b]) => window.BirgeShell.api.v2(m, p, b).then(() => "ok", (e) => String(e.status || e)), [m, p, b]);
    if (seed.idea.id) seed.idea.publish = await v2("POST", `/ideas/${seed.idea.id}/decide`, { action: "publish" });
    if (seed.question.id) {
      seed.question.publish = await v2("POST", `/questions/${seed.question.id}/publish`, {});
      seed.question.answer = await v2("POST", `/questions/${seed.question.id}/answer`, { answer_ru: `${PAY("answer")} Разметят в мае.` });
    }
    await page.reload(); await ready(page);
    await step(page, "akimat-home", false, async () => "главная: сводка, горячие места, легенда");
    await step(page, "akimat-card", false, async () => {
      const t = seed.complaint.target; if (!t?.kind) return false;
      await page.evaluate(([k, i]) => window.CivicShell.heat.focusTarget(k, i), [t.kind, t.id]); await sleep(1500);
      return "карточка объекта (цитата жалобы)";
    });
    await step(page, "akimat-card-tabs", false, async () => {
      const n = await page.evaluate(() => { const tabs = [...document.querySelectorAll("[role=tab]")].filter((x) => x.getClientRects().length);
        tabs.forEach((x) => x.click()); return tabs.length; });
      return n ? `вкладок нажато: ${n}` : false;
    });
    await page.keyboard.press("Escape");
    for (const id of ["day", "inbox", "projects", "questions"]) {
      await step(page, "akimat-" + id, false, () => visit(page, id, "akimat"));
      await page.keyboard.press("Escape");
    }
    await section(page, "map"); await sleep(600);
    await step(page, "akimat-search", false, async () => {
      const found = await page.evaluate(() => {
        const el = [...document.querySelectorAll(".civic-explore-field input, input[role=combobox], input[type=search]")].find((x) => x.getClientRects().length);
        if (!el) return null; el.focus(); el.value = ""; return el.className || el.getAttribute("aria-label") || "input";
      });
      if (!found) return false;
      await page.keyboard.type("Ост"); await sleep(500);
      await page.keyboard.press("Control+A"); await page.keyboard.type(PAY("search")); await sleep(500);
      await page.keyboard.press("ArrowDown"); await page.keyboard.press("Enter"); await sleep(800);
      return "подсказки поиска и Enter (" + found + ")";
    });
    await page.keyboard.press("Escape");
    await step(page, "akimat-ctrl-k", false, async () => {
      await page.evaluate(() => document.activeElement?.blur?.());
      await page.keyboard.press("Control+K"); await sleep(400);
      const typing = await page.evaluate(() => { const a = document.activeElement; return !!a && /INPUT|TEXTAREA/.test(a.tagName) && !a.closest(".civic-explore-field"); });
      if (!typing) return false;
      await page.keyboard.type(PAY("palette")); await sleep(400); await page.keyboard.press("ArrowDown");
      return "командная палитра";
    });
    await page.keyboard.press("Escape");
    for (const [name, url] of [["akimat-url-q", "/?q="], ["akimat-url-hash-q", "/#q="], ["akimat-url-search", "/?search="]]) {
      await step(page, name, false, async () => { await page.goto(base + url + encodeURIComponent(PAY(name))); await ready(page); return "адрес со строкой поиска"; });
    }
    await ctx.close();

    // 3) Житель, телефон 375×812, без входа: чужой текст жалобы не виден, нагрузка — только текстом.
    const rctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
    await rctx.addInitScript(() => {
      try { localStorage.setItem("birge.mode", "resident"); } catch (e) {}
      document.addEventListener("securitypolicyviolation", (e) => (window.__r15csp = window.__r15csp || []).push(e.violatedDirective + " " + (e.blockedURI || "")));
    });
    const rp = await rctx.newPage();
    await rp.goto(base + "/"); await ready(rp);
    await step(rp, "resident-home", true, async () => "шторка «Рядом с вами», поиск, кнопка «Сообщить»");
    await step(rp, "resident-place", true, async () => {
      const t = seed.complaint.target; if (!t?.kind) return false;
      await rp.evaluate(([k, i]) => window.CivicShell.heat.focusTarget(k, i), [t.kind, t.id]); await sleep(1500);
      return "карточка места у жителя";
    });
    await rp.keyboard.press("Escape");
    for (const id of ["nearby", "ideas", "questions"]) {
      await step(rp, "resident-" + id, true, () => visit(rp, id, "resident"));
      await rp.keyboard.press("Escape");
    }
    await step(rp, "resident-passport", true, async () => {
      const t = seed.complaint.target; if (!t?.id) return false;
      await rp.goto(base + "/?report=" + encodeURIComponent(t.id)); await ready(rp); await sleep(1200); return "паспорт объекта по QR";
    });
    await rctx.close();
  } finally {
    await browser.close(); srv.kill(); fs.rmSync(tmp, { recursive: true, force: true });
  }
  const summary = { seed, steps, pass: steps.filter((s) => s.status === "PASS").length,
    fail: steps.filter((s) => s.status === "FAIL").length, not_run: steps.filter((s) => s.status === "NOT_RUN").length };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(summary, null, 1));
  console.log(JSON.stringify({ seed, pass: summary.pass, fail: summary.fail, not_run: summary.not_run }, null, 1));
  process.exit(summary.fail ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
