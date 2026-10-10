// R01 round 14: the Birge header — brand, ҚАЗ/РУС, «Акимат / Житель», «Карта / Картина дня» — at 1366x768
// (laptop, main demo screen) and 375x812 (phone), in both languages. Old modes are reachable only by link.
// Usage: node tests/civic/R01/browser/r14_shell.cjs <out_dir>
// Starts `python3 -B app.py` on a free port with a temporary SQLite file (R02 init + synthetic demo slice).
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r14-shell-out");
// Environment noise: offline basemap, software WebGL in headless Chromium, missing local font files (LOCAL task R11).
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet/i;
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined && detail !== null ? " — " + JSON.stringify(detail).slice(0, 400) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

async function openPage(browser, url, w, h) {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) page.errs.push(m.type() + ": " + m.text()); });
  await page.goto(url);
  await ready(page);
  return { ctx, page };
}
const ready = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && window.BirgeShell && typeof mapReady !== "undefined" && mapReady
  && document.querySelector("#birge-header"), null, { timeout: 40000 }).then(() => page.waitForTimeout(900));

// What the header shows now: labels, pressed buttons, language, overflow.
const header = (page) => page.evaluate(() => {
  const bar = document.querySelector(".topbar").getBoundingClientRect();
  const visible = (e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden" && getComputedStyle(e).display !== "none";
  const buttons = [...document.querySelectorAll("#birge-header button")].filter(visible);
  const out = buttons.map((b) => b.getBoundingClientRect()).filter((r) => r.right > innerWidth + 0.5 || r.left < -0.5);
  const pressed = Object.fromEntries(["section", "mode", "lang"].map((g) =>
    [g, document.querySelector(`#birge-header [data-${g}][aria-pressed="true"]`)?.dataset[g] || null]));
  return {
    htmlLang: document.documentElement.lang, title: document.title,
    brand: document.querySelector(".brand-title")?.textContent, tagline: document.querySelector(".brand-sub")?.textContent,
    labels: buttons.map((b) => b.textContent.trim()), pressed, out: out.length, minHeight: Math.min(...buttons.map((b) => b.getBoundingClientRect().height)),
    oldModes: getComputedStyle(document.getElementById("civic-modes")).display, scrollW: document.documentElement.scrollWidth,
    mode: document.body.dataset.birgeMode, section: document.body.dataset.birgeSection, hash: location.hash,
    keys: document.body.innerText.match(/\b(shell|common|akim)\.[a-z_.]+\b/g) || [],
  };
});

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r01-r14-"));
  const port = await freePort();
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch();
  try {
    // ---------------------------------------------------------------- laptop 1366x768
    const { ctx, page } = await openPage(browser, base, 1366, 768);
    let h = await header(page);
    check("1366: Birge brand, old mode switch hidden, akimat view and map by default",
      h.brand === "Birge" && h.oldModes === "none" && h.mode === "akimat" && h.pressed.section === "map" && h.pressed.mode === "akimat", h);
    check("1366: header fits (no overflow, no horizontal scroll), segment buttons ≥ 40 px", h.out === 0 && h.scrollW <= 1366 && h.minHeight >= 40, h);
    check("1366: ru labels, no raw translation keys", h.htmlLang === "ru" && h.labels.includes("Картина дня") && h.labels.includes("Акимат") && h.keys.length === 0, h);
    await page.screenshot({ path: path.join(OUT, "01_map_1366_ru.png") });

    // ҚАЗ: labels, brand, <html lang>; choice survives reload
    await page.click("#birge-header [data-lang=kk]");
    await page.waitForFunction(() => document.documentElement.lang === "kk", null, { timeout: 5000 }).catch(() => null);
    h = await header(page);
    check("1366: ҚАЗ switches header, tagline and <html lang>",
      h.htmlLang === "kk" && h.pressed.lang === "kk" && h.labels.includes("Күн қорытындысы") && h.labels.includes("Әкімдік") && /бірге/.test(h.tagline || "") && h.keys.length === 0, h);
    check("1366: Kazakh header still fits", h.out === 0 && h.scrollW <= 1366, h);
    const panel = await page.evaluate(() => ({ title: document.querySelector("#civic-panel h1")?.textContent,
      area: document.querySelector(".civic-explore-row label span")?.textContent, view: document.querySelector(".civic-explore-view")?.textContent,
      staff: document.getElementById("civic-staff-button")?.textContent, find: document.querySelector(".civic-explore-go")?.textContent,
      placeholder: document.querySelector(".civic-explore-field input")?.placeholder,
      district: [...document.querySelectorAll(".civic-explore select option")].map((o) => o.textContent).join(",") }));
    check("1366: ҚАЗ also switches the shell panel and city navigation",
      panel.title === "Қалада не өзгеріп жатыр" && panel.area === "Аумақ" && /Шолу: бүкіл Астана/.test(panel.view || "") && panel.staff === "Қызметкерлерге"
      && panel.find === "Табу" && panel.placeholder === "Астана көшесі" && /Нұра/.test(panel.district), panel);
    await page.screenshot({ path: path.join(OUT, "02_map_1366_kk.png") });
    await page.reload();
    await ready(page);
    h = await header(page);
    check("1366: language remembered after reload", h.htmlLang === "kk" && h.pressed.lang === "kk", h);
    const panelAfter = await page.evaluate(() => document.querySelector("#civic-panel h1")?.textContent);
    check("1366: shell panel opens in Kazakh after reload", panelAfter === "Қалада не өзгеріп жатыр", panelAfter);

    // «Картина дня»: hash, overlay with an understandable empty state and a way back
    await page.click("#birge-header [data-section=day]");
    await page.waitForTimeout(400);
    const day = await page.evaluate(() => { const d = document.getElementById("birge-day");
      return { visible: !!d && !d.hidden && d.getBoundingClientRect().height > 200, title: d?.querySelector("h1")?.textContent,
        empty: d?.querySelector(".birge-day-empty")?.innerText || "", button: d?.querySelector(".bk-btn")?.textContent, hash: location.hash }; });
    check("1366: «Картина дня» opens with title, explanation and «back to map» button (kk)",
      day.visible && day.hash === "#day" && day.title === "Күн қорытындысы" && day.empty.length > 20 && day.button === "Картаға оралу", day);
    await page.screenshot({ path: path.join(OUT, "03_day_1366_kk.png") });
    await page.click("#birge-day .bk-btn");
    await page.waitForTimeout(400);
    h = await header(page);
    check("1366: back to map clears #day", h.section === "map" && h.hash === "" && h.pressed.section === "map", h);
    await page.goBack();
    await page.waitForTimeout(500);
    h = await header(page);
    check("1366: browser Back returns to «Картина дня»", h.section === "day" && h.hash === "#day", h);
    await page.goForward();
    await page.waitForTimeout(500);

    // РУС back; «Житель» hides akimat tools, survives reload; «Картина дня» from resident switches to akimat
    await page.click("#birge-header [data-lang=ru]");
    await page.waitForFunction(() => document.documentElement.lang === "ru", null, { timeout: 5000 }).catch(() => null);
    await page.click("#birge-header [data-mode=resident]");
    await page.waitForTimeout(300);
    const res = await page.evaluate(() => ({ mode: document.body.dataset.birgeMode,
      scen: getComputedStyle(document.getElementById("civic-scenarios-button")).display,
      staff: getComputedStyle(document.getElementById("civic-staff-button")).display }));
    check("1366: «Житель» hides akimat tools, keeps sign-in", res.mode === "resident" && res.scen === "none" && res.staff !== "none", res);
    await page.screenshot({ path: path.join(OUT, "04_map_1366_resident.png") });
    await page.reload();
    await ready(page);
    h = await header(page);
    check("1366: view «Житель» remembered after reload", h.mode === "resident" && h.pressed.mode === "resident" && h.htmlLang === "ru", h);
    await page.click("#birge-header [data-section=day]");
    await page.waitForTimeout(300);
    h = await header(page);
    check("1366: «Картина дня» is an akimat screen — opening it switches the view to «Акимат»", h.section === "day" && h.mode === "akimat", h);
    await page.click("#birge-header [data-section=map]");

    // Keyboard: Tab reaches the header with a visible focus ring
    await page.evaluate(() => document.activeElement?.blur());
    let focus = null;
    for (let i = 0; i < 25 && !focus; i++) {
      await page.keyboard.press("Tab");
      focus = await page.evaluate(() => { const a = document.activeElement;
        if (!a?.closest?.("#birge-header")) return null;
        const s = getComputedStyle(a); return { text: a.textContent.trim(), outline: s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0, shadow: s.boxShadow !== "none" }; });
    }
    check("1366: Tab reaches the header, focus ring visible", !!focus && (focus.outline || focus.shadow), focus);

    // Old modes only by link; «Город» returns to the Birge map and clears the link
    await page.evaluate(() => { location.hash = "#training"; });
    const training = await page.waitForFunction(() => window.CivicShell.mode === "training", null, { timeout: 5000 }).then(() => true).catch(() => false);
    const inTraining = await page.evaluate(() => ({ modes: getComputedStyle(document.getElementById("civic-modes")).display,
      birge: getComputedStyle(document.getElementById("birge-header")).display }));
    check("#training link opens the old model; its own switch is shown, Birge header hidden", training && inTraining.modes !== "none" && inTraining.birge === "none", inTraining);
    await page.click("#civic-modes [data-mode=civic]");
    await page.waitForFunction(() => window.CivicShell.mode === "civic", null, { timeout: 5000 }).catch(() => null);
    await page.waitForTimeout(800);
    h = await header(page);
    check("«Город» returns to the Birge map and clears #training", h.brand === "Birge" && h.hash === "" && h.oldModes === "none", h);
    await page.reload();
    await ready(page);
    check("reload after visiting the old model opens the Birge map", (await page.evaluate(() => window.CivicShell.mode)) === "civic");

    // API v2 is reachable from the page (same origin) and reports module states
    const v2 = await page.evaluate(async () => { const r = await fetch("/api/civic/v2/modules"); return { status: r.status, keys: Object.keys((await r.json()).modules || {}).length }; });
    check("API v2 /modules answers from the page", v2.status === 200 && v2.keys === 14, v2);
    check("1366: no page errors or warnings", page.errs.length === 0, page.errs);
    await ctx.close();

    // ---------------------------------------------------------------- phone 375x812 and tablet 768x1024 (< 1024: ≡ menu)
    for (const [w, hgt, lang] of [[375, 812, "ru"], [375, 812, "kk"], [768, 1024, "kk"]]) {
      const tag = `${w} ${lang}`;
      const m = await openPage(browser, base + "?lang=" + lang, w, hgt);
      let p = await header(m.page);
      const startMode = w < 761 ? "resident" : "akimat";
      check(`${tag}: ${startMode} view by default, ҚАЗ/РУС and ≡ visible, sections and view in the menu`,
        p.mode === startMode && p.htmlLang === lang && p.labels.length === 3 && p.pressed.lang === lang, p);
      check(`${tag}: header fits, no horizontal scroll`, p.out === 0 && p.scrollW <= w, p);
      await m.page.screenshot({ path: path.join(OUT, `05_map_${w}_${lang}.png`) });
      await m.page.click("#birge-header .birge-menu-btn");
      await m.page.waitForTimeout(300);
      const menu = await m.page.evaluate(() => { const box = document.getElementById("birge-menu").getBoundingClientRect();
        const items = [...document.querySelectorAll("#birge-menu button")];
        const hit = items.every((b) => { const r = b.getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return e === b || b.contains(e); });
        return { open: document.getElementById("birge-header").dataset.menu, expanded: document.querySelector(".birge-menu-btn").getAttribute("aria-expanded"),
          inside: box.left >= 0 && box.right <= innerWidth, clickable: hit, items: items.map((b) => b.textContent.trim()) }; });
      check(`${tag}: ≡ opens the menu on top of the map, all items clickable and inside the screen`,
        menu.open === "open" && menu.expanded === "true" && menu.inside && menu.clickable && menu.items.length === 4, menu);
      await m.page.screenshot({ path: path.join(OUT, `06_menu_${w}_${lang}.png`) });
      await m.page.click("#birge-header [data-section=day]");
      await m.page.waitForTimeout(400);
      p = await header(m.page);
      const dayBox = await m.page.evaluate(() => { const d = document.getElementById("birge-day").getBoundingClientRect(); return { l: d.left, r: d.right, t: d.top }; });
      check(`${tag}: «Картина дня» from the menu: menu closed, view akimat, screen inside the window`,
        p.section === "day" && p.mode === "akimat" && dayBox.l >= 0 && dayBox.r <= w && p.scrollW <= w, { p, dayBox });
      await m.page.screenshot({ path: path.join(OUT, `07_day_${w}_${lang}.png`) });
      await m.page.keyboard.press("Escape");
      check(`${tag}: no page errors or warnings`, m.page.errs.length === 0, m.page.errs);
      await m.ctx.close();
    }
  } finally {
    await browser.close();
    srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length };
  fs.writeFileSync(path.join(OUT, "r14_shell.json"), JSON.stringify({ summary, checks }, null, 1));
  console.log(JSON.stringify(summary));
  process.exit(summary.fail ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
