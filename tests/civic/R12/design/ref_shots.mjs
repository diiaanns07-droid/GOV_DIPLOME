// Эталон (вариант A) — кадры экранов в точном размере 1366×768 и 375×812.
import { createRequire } from "node:module"; import fs from "node:fs"; import path from "node:path";
const require = createRequire(path.join(process.env.NODE_PATH, "x.js"));
const pw = require("playwright");
const [URL, OUT] = process.argv.slice(2); fs.mkdirSync(OUT, { recursive: true });
const b = await pw.chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1414, height: 1000 }, deviceScaleFactor: 1 })).newPage();
await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
await p.goto(URL); await p.waitForTimeout(400);
for (const f of ["home", "obj", "proj"]) {
  await p.click(`.switch button[data-f="${f}"]`); await p.waitForTimeout(300);
  await p.locator("#stage").screenshot({ path: path.join(OUT, `ref-${f}-1366.png`) });
}
await p.click('.switch button[data-f="phone"]'); await p.waitForTimeout(300);
await p.locator("#stagePhone").screenshot({ path: path.join(OUT, "ref-phone-375.png") });
console.log(await p.evaluate(() => ({ stage: document.getElementById("stage").clientWidth, phone: document.getElementById("stagePhone").clientWidth })));
await b.close();
