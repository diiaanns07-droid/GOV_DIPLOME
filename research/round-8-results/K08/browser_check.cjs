// K08 R8: открыть report.html в Chromium (file://): ошибки консоли/страницы, сетевые запросы, ширина 380 px.
// Usage: NODE_PATH=$(npm root -g) node browser_check.cjs <report.html>...
const { chromium } = require("playwright"); const path = require("path");
(async () => {
  const b = await chromium.launch(); let bad = 0; const out = [];
  for (const f of process.argv.slice(2)) {
    for (const width of [1200, 380]) {
      const pg = await b.newPage({ viewport: { width, height: 900 } }); const errs = [], reqs = [];
      pg.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); }); pg.on("pageerror", (e) => errs.push(String(e)));
      const url = "file://" + path.resolve(f);
      pg.on("request", (r) => { if (r.url() !== url) reqs.push(r.url()); });
      await pg.goto(url);
      const info = await pg.evaluate(() => ({ title: document.title, h2: document.querySelectorAll("h2").length,
        scripts: document.scripts.length, docW: document.documentElement.scrollWidth }));
      const r = { file: f, width, ...info, console_errors: errs, extra_requests: reqs };
      if (errs.length || reqs.length || info.scripts || info.docW > width) bad++;
      out.push(r); await pg.close();
    }
  }
  await b.close(); console.log(JSON.stringify(out, null, 1)); process.exit(bad ? 1 : 0);
})();
