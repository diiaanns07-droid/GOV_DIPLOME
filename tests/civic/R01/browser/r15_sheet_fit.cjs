// R01 round 15+ (amendment P3, «все экраны-листы: ширина листа = ширине содержимого, без пустых белых полей»):
// opens every section screen of both views at 1366 / 1024 / 375 and measures the sheet against what it shows.
// Starts a stand with the R02 demo world and a staff account (as r15_frames.cjs). For each screen:
//   sheet   — the box of #birge-screen (#birge-day for «Картина дня») and its padding;
//   content — the union of what paints inside it: text, form controls, images, svg, and boxes with a background,
//             border or shadow (a transparent wrapper does not count);
//   empty   — sheet edge → content edge minus the padding, left and right. Over SLACK px on a side is a FAIL;
//             a screen showing its empty state (.bk-empty / .birge-day-empty — small icon, text, one button) is a WARN:
//             the empty state is centred in the module's column, the sheet itself still fits the column.
// Usage: node tests/civic/R01/browser/r15_sheet_fit.cjs <out_dir> [sizes=1366,1024,375] [lang=ru]
// Writes <out_dir>/sheet_fit.json and a frame per screen (<size>_<view>_<section>.jpg). Writes nothing into the repo.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r15-sheet-fit-out");
const SIZES = (process.argv[3] || "1366,1024,375").split(",").map(Number);
const LANG = process.argv[4] || "ru";
const SLACK = 24;   // пустое поле сверх отступа листа, которое ещё не видно как «белая полоса»
const USER = "operator", PASSWORD = "Birge-Stend-Kokshetau-77";
// Разделы-страницы (registerScreen с href) — не лист оболочки; «Мои обращения» — окно R09, не раздел.
const PAGES = new Set(["board", "qr", "mine", "more"]);
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|\[i18n\] неизвестный ключ/i;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, dir) {
  const db = path.join(dir, "civic.sqlite3");
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", CIVIC_DEMO_WORLD: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: ["pipe", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run(`create-editor ${USER} --password-stdin`, PASSWORD + "\n" + PASSWORD + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const ready = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && window.BirgeShell && typeof mapReady !== "undefined" && mapReady
  && document.querySelector("#birge-header"), null, { timeout: 45000 }).then(() => page.waitForTimeout(1200));

// Замер в странице: лист, его отступы и рамка того, что в нём нарисовано.
function measure(section) {
  const sheet = document.getElementById(section === "day" ? "birge-day" : "birge-screen");
  if (!sheet || sheet.hidden || !sheet.getClientRects().length) return { missing: true };
  const s = sheet.getBoundingClientRect(), cs = getComputedStyle(sheet);
  const padL = parseFloat(cs.paddingLeft) + parseFloat(cs.borderLeftWidth), padR = parseFloat(cs.paddingRight) + parseFloat(cs.borderRightWidth);
  const box = { left: Infinity, right: -Infinity, n: 0 };
  const add = (r) => {
    if (!r || r.width < 1 || r.height < 1) return;
    const left = Math.max(r.left, s.left), right = Math.min(r.right, s.right);
    if (right - left < 1) return;
    box.left = Math.min(box.left, left); box.right = Math.max(box.right, right); box.n += 1;
  };
  const shown = (e) => { const c = getComputedStyle(e); return c.display !== "none" && c.visibility !== "hidden" && parseFloat(c.opacity) > 0.01; };
  const paints = (e) => {
    const c = getComputedStyle(e);
    if (/^(INPUT|SELECT|TEXTAREA|BUTTON|IMG|SVG|CANVAS|VIDEO|svg|HR)$/.test(e.tagName)) return true;
    const bg = c.backgroundColor, img = c.backgroundImage;
    if ((bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(bg)) || (img && img !== "none")) return true;
    if (["Top", "Right", "Bottom", "Left"].some((k) => parseFloat(c["border" + k + "Width"]) > 0 && !/rgba\(0, 0, 0, 0\)|transparent/.test(c["border" + k + "Color"]))) return true;
    return c.boxShadow && c.boxShadow !== "none";
  };
  const root = sheet.querySelector("#birge-screen-root") || sheet;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (node.nodeType === 1) {
        if (!shown(node)) return NodeFilter.FILTER_REJECT;
        if (node.getAttribute("aria-hidden") === "true" && node.classList.contains("sr-only")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
      return node.textContent.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
    },
  });
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.nodeType === 3) {
      const range = document.createRange(); range.selectNodeContents(node);
      for (const r of range.getClientRects()) add(r);
    } else if (node !== root && paints(node)) {
      // Элемент, закрашенный во всю ширину листа (липкая шапка, разделитель), — тоже содержимое: он и есть «полоса».
      add(node.getBoundingClientRect());
    }
  }
  const empty = box.n ? { left: Math.round(box.left - s.left - padL), right: Math.round(s.right - padR - box.right) } : null;
  const emptyState = [...root.querySelectorAll(".bk-empty, .birge-day-empty, [class*='-empty']")].some((e) => shown(e) && e.getClientRects().length);
  return { emptyState, sheet: { left: Math.round(s.left), right: Math.round(s.right), width: Math.round(s.width), padL, padR },
    content: box.n ? { left: Math.round(box.left), right: Math.round(box.right), width: Math.round(box.right - box.left) } : null,
    empty, viewport: innerWidth };
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r01-r15-fit-"));
  const port = await freePort();
  const srv = await startServer(port, tmp);
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch({ env: { ...process.env, LANG: "ru_RU.UTF-8", LC_ALL: "ru_RU.UTF-8" } });
  const rows = [];
  try {
    for (const w of SIZES) for (const mode of ["akimat", "resident"]) {
      const mobile = w < 761, h = mobile ? 812 : 768;
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile });
      await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) { /* без хранилища */ } }, [mode, LANG]);
      const page = await ctx.newPage();
      const errs = [];
      page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
      page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errs.push(m.text().slice(0, 200)); });
      await page.goto(base);
      await ready(page);
      if (mode === "akimat") await page.evaluate(([u, p]) => window.CivicShell.api.login(u, p), [USER, PASSWORD]).catch(() => null);
      const ids = (await page.evaluate(() => ["day", ...window.BirgeShell.sections()])).filter((id, i, all) => all.indexOf(id) === i && !PAGES.has(id)
        && (id !== "day" || mode === "akimat"));
      for (const id of ids) {
        await page.evaluate((s) => window.BirgeShell.setSection(s), id);
        await page.waitForTimeout(1800);
        const m = await page.evaluate(measure, id);
        const over = !m.missing && !!m.empty && (m.empty.left > SLACK || m.empty.right > SLACK);
        const status = m.missing ? "NOT_RUN" : over ? (m.emptyState ? "WARN" : "FAIL") : "PASS";
        const file = `${w}_${mode}_${id}.jpg`;
        await page.screenshot({ path: path.join(OUT, file), type: "jpeg", quality: 70 });
        rows.push({ size: w, mode, section: id, status, file, ...m });
      }
      rows.push({ page: `${w}_${mode}`, errors: errs });
      await ctx.close();
    }
  } finally {
    await browser.close();
    srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const checks = rows.filter((r) => r.section);
  const summary = { pass: checks.filter((r) => r.status === "PASS").length, fail: checks.filter((r) => r.status === "FAIL").length,
    warn: checks.filter((r) => r.status === "WARN").length, not_run: checks.filter((r) => r.status === "NOT_RUN").length, slack_px: SLACK };
  fs.writeFileSync(path.join(OUT, "sheet_fit.json"), JSON.stringify({ summary, rows }, null, 1));
  for (const r of checks) console.log(`${r.status} ${r.size} ${r.mode} ${r.section}: sheet ${r.sheet ? r.sheet.width : "-"} content ${r.content ? r.content.width : "-"} empty L${r.empty ? r.empty.left : "-"} R${r.empty ? r.empty.right : "-"}`);
  for (const r of rows.filter((x) => x.errors && x.errors.length)) console.log("ERRORS " + r.page + ": " + r.errors.slice(0, 3).join(" | "));
  console.log(JSON.stringify(summary));
  process.exit(summary.fail ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
