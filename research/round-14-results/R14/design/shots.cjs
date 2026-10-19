// R14 · скриншоты сборки для рисунков диплома и BRAND.md (только чтение: свой сервер, временная база).
// node shots.cjs <папка сборки> <папка кадров> [порт]
// Кадры: 1366×768 и 375×812 × ru/kk × экраны; стекло держится ?glass=on (в облаке нет GPU — без этого
// оболочка сама включает белый вид при < 30 кадров/с); отдельный кадр ?glass=off — запасной белый вид.
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs"), path = require("path"), os = require("os"), http = require("http");

const ROOT = path.resolve(process.argv[2] || ".");
const OUT = path.resolve(process.argv[3] || "shots");
const PORT = Number(process.argv[4] || 8771);
const BASE = `http://127.0.0.1:${PORT}/`;
fs.mkdirSync(OUT, { recursive: true });

function waitServer(ms) {
  const t0 = Date.now();
  return new Promise((ok, bad) => {
    const ping = () => http.get(BASE, r => { r.resume(); ok(); }).on("error", () => {
      if (Date.now() - t0 > ms) bad(new Error("server timeout")); else setTimeout(ping, 500);
    });
    ping();
  });
}

const SIZES = [{ w: 1366, h: 768, tag: "1366" }, { w: 375, h: 812, tag: "375", mobile: true }];
const LANGS = ["ru", "kk"];
// [имя, вид, хэш, действие]
const SCREENS = [
  ["map-akimat", "akimat", "", null],
  ["map-resident", "resident", "", null],
  ["target-khan-shatyr", "akimat", "#target=object:osm-node-4109037549&days=30", null],
  ["day", "akimat", "#day", null],
  ["inbox", "akimat", "#inbox", null],
  ["nearby", "resident", "#nearby", null],
  ["ideas", "resident", "#ideas", null],
  ["questions", "resident", "#questions", null],
  ["wizard", "resident", "", async (page) => { await page.click(".bc-fab", { timeout: 8000 }); await page.waitForTimeout(1500); }],
  ["avatar-menu", "akimat", "", async (page) => { await page.click(".birge-avatar", { timeout: 8000 }); await page.waitForTimeout(700); }],
];

(async () => {
  const db = path.join(os.tmpdir(), `r14shots-${PORT}.sqlite3`);
  for (const f of [db, db + "-wal", db + "-shm"]) { try { fs.unlinkSync(f); } catch (e) {} }
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(PORT), "--civic-db", db],
    { cwd: ROOT, env: { ...process.env, CIVIC_DEMO: "1" }, stdio: "ignore" });
  const log = [];
  try {
    await waitServer(60000);
    const browser = await chromium.launch({ executablePath: process.env.PW_CHROMIUM || undefined });
    for (const size of SIZES) for (const lang of LANGS) {
      for (const [name, mode, hash, act] of SCREENS) {
        const ctx = await browser.newContext({ viewport: { width: size.w, height: size.h }, deviceScaleFactor: 1,
          isMobile: !!size.mobile, hasTouch: !!size.mobile, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
        await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) {} }, [mode, lang]);
        const page = await ctx.newPage();
        const errors = [];
        page.on("pageerror", e => errors.push(String(e)));
        const url = `${BASE}?lang=${lang}&glass=on${hash}`;
        const t0 = Date.now();
        try {
          await page.goto(url, { waitUntil: "load", timeout: 60000 });
          await page.waitForTimeout(6000);
          if (act) await act(page);
          const file = path.join(OUT, `${size.tag}-${lang}-${name}.jpg`);
          await page.screenshot({ path: file, type: "jpeg", quality: 82 });
          log.push({ file: path.basename(file), url, ms: Date.now() - t0, errors });
        } catch (e) {
          log.push({ file: `${size.tag}-${lang}-${name}`, url, error: String(e).slice(0, 300), errors });
        }
        await ctx.close();
      }
    }
    // запасной белый вид (?glass=off), ноутбук, ru
    for (const [name, mode, hash] of [["map-akimat-glass-off", "akimat", ""], ["day-glass-off", "akimat", "#day"]]) {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      await ctx.addInitScript((m) => { try { localStorage.setItem("birge.mode", m); } catch (e) {} }, mode);
      const page = await ctx.newPage();
      await page.goto(`${BASE}?lang=ru&glass=off${hash}`, { waitUntil: "load", timeout: 60000 });
      await page.waitForTimeout(6000);
      const file = path.join(OUT, `1366-ru-${name}.jpg`);
      await page.screenshot({ path: file, type: "jpeg", quality: 82 });
      log.push({ file: path.basename(file) });
      await ctx.close();
    }
    await browser.close();
  } finally {
    srv.kill("SIGTERM");
    fs.writeFileSync(path.join(OUT, "SHOTS.json"), JSON.stringify({ root: ROOT, base: BASE, shots: log }, null, 1));
  }
  console.log(JSON.stringify(log.map(x => [x.file, x.error ? "ERR " + x.error.slice(0, 80) : (x.errors && x.errors.length ? "pageerror " + x.errors.length : "ok")])));
})().catch(e => { console.error(e); process.exit(1); });
