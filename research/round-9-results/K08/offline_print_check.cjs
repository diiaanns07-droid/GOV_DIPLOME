// K08 R9: открыть отчёты (file://) в Chromium без сети: все запросы кроме самого файла блокируются и считаются;
// экран 1100 и 380 px (без горизонтальной прокрутки страницы), печать (emulateMedia print + page.pdf).
// Usage: NODE_PATH=$(npm root -g) node offline_print_check.cjs --pdf-dir DIR report1.html [report2.html ...]
"use strict";
const { chromium } = require("playwright"); const path = require("path"); const fs = require("fs");
const i = process.argv.indexOf("--pdf-dir"); const pdfDir = path.resolve(process.argv[i + 1]); fs.mkdirSync(pdfDir, { recursive: true });
const files = process.argv.slice(i + 2);
(async () => {
  const b = await chromium.launch(); const out = []; let bad = 0;
  for (const f of files) {
    const url = "file://" + path.resolve(f);
    for (const width of [1100, 380]) {
      const ctx = await b.newContext({ viewport: { width, height: 900 }, offline: true });
      const pg = await ctx.newPage(); const blocked = [], errs = [];
      await pg.route("**/*", (r) => (r.request().url() === url ? r.continue() : (blocked.push(r.request().url()), r.abort())));
      pg.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); }); pg.on("pageerror", (e) => errs.push(String(e)));
      await pg.goto(url);
      const info = await pg.evaluate(() => ({ title: document.title, scripts: document.scripts.length, docW: document.documentElement.scrollWidth,
        textLen: document.body.innerText.length, h2: document.querySelectorAll("h2").length }));
      let pdfBytes = null;
      if (width === 1100) {
        await pg.emulateMedia({ media: "print" });
        const pdf = await pg.pdf({ format: "A4", printBackground: false });
        pdfBytes = pdf.length; fs.writeFileSync(path.join(pdfDir, path.basename(path.dirname(f)) + "_" + path.basename(f, ".html") + ".pdf"), pdf);
      }
      const r = { file: f, width, ...info, blocked, console_errors: errs, pdf_bytes: pdfBytes };
      if (blocked.length || errs.length || info.scripts || info.docW > width || info.textLen < 200 || (width === 1100 && !(pdfBytes > 1000))) bad++;
      out.push(r); await ctx.close();
    }
  }
  await b.close(); console.log(JSON.stringify(out, null, 1)); process.exit(bad ? 1 : 0);
})();
