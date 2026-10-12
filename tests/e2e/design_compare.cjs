#!/usr/bin/env node
// R10 · раунд 14 · дизайн-марафон: сравнение «книг экранов» (design_book.cjs) нескольких сборок — кадры рядом
// («эталон | FINAL-3 | сейчас») и таблица замечаний чек-листа по экранам: стало лучше / хуже / так же.
//   NODE_PATH="$(npm root -g)" node tests/e2e/design_compare.cjs --books 8e67c65=<папка>,FINAL-3=<папка>,сейчас=<папка>
//        --out <папка> [--shots 1366-ru,375-ru,375-kk]   (какие варианты склеивать в кадры; по умолчанию — все)
// Итог: <out>/COMPARE.md, COMPARE.json, кадры <вариант>/<id>.jpg (слева направо — сборки в порядке --books).
"use strict";
// Микро-отклик (100–170 мс, только цвет/тень/сжатие) — не замечание (то же правило, что в design_book.cjs с круга 2).
const MICRO = /^переход ((?:transform|scale|translate|background-color|background|color|box-shadow|opacity|filter|border-color|outline-color)(?:, )?)+ (1[0-6]\d) мс/;
// Радиус 18 px — токен ui-kit --r-glass-menu (R11 b39e586d), в книгах до круга 3 считался «вне токенов».
// «Кнопка закрыта другой» — проверка с круга 6: в сравнении с книгами до неё не считается (нечего сравнивать).
const keep = (w) => !MICRO.test(w) && !/^радиус 18 px/.test(w) && !/^кнопка «.*» закрыта «/.test(w);
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const L = require("./r10_lib.cjs");

const args = L.parseArgs(process.argv.slice(2));
const BOOKS = String(args.books || "").split(",").filter(Boolean).map((x) => { const i = x.indexOf("="); return { name: x.slice(0, i), dir: path.resolve(x.slice(i + 1)) }; });
const OUT = path.resolve(String(args.out || "design-compare"));
const SHOTS = args.shots ? new Set(String(args.shots).split(",")) : null;
if (BOOKS.length < 2) { console.error("нужно --books имя=папка,имя=папка[,…]"); process.exit(2); }

// Те же пункты, что в BOOK.md (design_book.cjs points()).
function points(rec) {
  const p = {};
  if (!rec || !rec.reached) return null;
  const d = rec.design || {}, u = rec.ui || {};
  for (const o of Object.values(d.owners || {})) for (const [k, v] of Object.entries(o)) { const n = v.filter(keep).length; if (n) p[k] = (p[k] || 0) + n; }
  if (u.fonts && u.fonts.length) p["3 типографика"] = (p["3 типографика"] || 0) + u.fonts.length;
  if (u.taps && u.taps.length) p["10 нажатия"] = (p["10 нажатия"] || 0) + u.taps.length;
  if (u.contrast && u.contrast.length) p["4 цвет"] = (p["4 цвет"] || 0) + u.contrast.length;
  if (u.keys && u.keys.length) p["11 тексты"] = (p["11 тексты"] || 0) + u.keys.length;
  if (u.cut && u.cut.length) p["3 типографика"] = (p["3 типографика"] || 0) + u.cut.length;
  if (rec.focus && rec.focus.without && rec.focus.without.length) p["10 нажатия"] = (p["10 нажатия"] || 0) + rec.focus.without.length;
  if (rec.press && (rec.press.feedback === false || rec.press.jumps)) p["10 нажатия"] = (p["10 нажатия"] || 0) + 1;
  return p;
}
const total = (p) => (p ? Object.values(p).reduce((a, b) => a + b, 0) : null);
const ITEMS = ["1 иерархия", "2 сетка", "3 типографика", "4 цвет", "6 глубина", "7 движение", "10 нажатия", "11 тексты"];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const books = BOOKS.map((b) => ({ ...b, data: JSON.parse(fs.readFileSync(path.join(b.dir, "BOOK.json"), "utf8")) }));
  const variants = [...new Set(books.flatMap((b) => Object.keys(b.data.variants)))];
  const ids = []; const names = {};
  for (const b of books) for (const v of Object.values(b.data.variants)) for (const [id, r] of Object.entries(v)) if (!id.startsWith("_") && !ids.includes(id)) { ids.push(id); names[id] = { name: r.name, owner: r.owner }; }
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent("<html><body></body></html>");
  const rows = [], json = {};
  try {
    for (const v of variants) {
      fs.mkdirSync(path.join(OUT, v), { recursive: true });
      for (const id of ids) {
        const recs = books.map((b) => (b.data.variants[v] || {})[id]);
        const pts = recs.map(points);
        json[`${v} ${id}`] = books.map((b, i) => ({ build: b.name, reached: !!(recs[i] && recs[i].reached), points: pts[i] }));
        rows.push({ v, id, pts, recs });
        if (SHOTS && !SHOTS.has(v)) continue;
        // Кадр: сборки рядом, подпись сверху; не открылось — серый прямоугольник с пометкой.
        const imgs = books.map((b, i) => { const r = recs[i]; const f = r && r.reached && r.shot ? path.join(b.dir, r.shot) : null;
          return { name: b.name, src: f && fs.existsSync(f) ? "data:image/jpeg;base64," + fs.readFileSync(f).toString("base64") : null, n: total(pts[i]) }; });
        const phone = v.startsWith("375");
        const b64 = await page.evaluate(async ([imgs, phone, title]) => {
          const W = phone ? 300 : 683, H = phone ? 650 : 384, PAD = 8, TOP = 30, HEAD = 26;
          const c = document.createElement("canvas"); c.width = imgs.length * (W + PAD) + PAD; c.height = HEAD + TOP + H + PAD;
          const g = c.getContext("2d"); g.fillStyle = "#ffffff"; g.fillRect(0, 0, c.width, c.height);
          g.fillStyle = "#152c26"; g.font = "600 15px sans-serif"; g.fillText(title, PAD, 19);
          for (let i = 0; i < imgs.length; i++) {
            const x = PAD + i * (W + PAD), y = HEAD + TOP;
            g.fillStyle = "#4c5853"; g.font = "600 14px sans-serif";
            g.fillText(imgs[i].name + (imgs[i].n === null ? " · не открылось" : ` · замечаний ${imgs[i].n}`), x, HEAD + 19);
            if (imgs[i].src) { const im = new Image(); im.src = imgs[i].src; await im.decode(); g.drawImage(im, x, y, W, H); g.strokeStyle = "#dfe3e1"; g.strokeRect(x + 0.5, y + 0.5, W - 1, H - 1); }
            else { g.fillStyle = "#eff1f2"; g.fillRect(x, y, W, H); g.fillStyle = "#4c5853"; g.font = "15px sans-serif"; g.fillText("нет этого состояния", x + 16, y + H / 2); }
          }
          return c.toDataURL("image/jpeg", 0.72).split(",")[1];
        }, [imgs, phone, `${v} · ${names[id].name} (${id}) · ${names[id].owner}`]);
        fs.writeFileSync(path.join(OUT, v, id + ".jpg"), Buffer.from(b64, "base64"));
      }
    }
  } finally { await browser.close(); }
  // Отчёт: по экрану и варианту — число замечаний в каждой сборке; последняя сборка против предпоследней — лучше/хуже.
  const last = books.length - 1, prev = last - 1;
  const md = [`# R10 · сравнение экранов · ${books.map((b) => `${b.name} \`${b.data.meta.sha}\``).join(" → ")}`, "",
    `Замечания автоматического чек-листа (design_book.cjs) по экрану; «—» — состояния нет в сборке. Итог — ${books[last].name} против ${books[prev].name}.`,
    "Кадры: `<вариант>/<id>.jpg` — сборки слева направо в этом порядке.", "",
    `| Вариант | Экран | Роль | ${books.map((b) => b.name).join(" | ")} | Итог |`, `|---|---|---|${books.map(() => "---:").join("|")}|---|`];
  const worse = [], better = [];
  for (const r of rows) {
    const t = r.pts.map(total);
    let verdict = "";
    if (t[last] !== null && t[prev] !== null) {
      verdict = t[last] > t[prev] ? "**хуже**" : t[last] < t[prev] ? "лучше" : "так же";
      const grew = ITEMS.filter((k) => ((r.pts[last] || {})[k] || 0) > ((r.pts[prev] || {})[k] || 0));
      if (grew.length) { verdict += ` (${grew.map((k) => k.split(" ")[0] + "↑").join(" ")})`; worse.push({ ...r, grew }); }
      if (t[last] < t[prev]) better.push(r);
    } else if (t[last] !== null && t[prev] === null) verdict = "новое";
    else if (t[last] === null && t[prev] !== null) verdict = "**пропало**";
    md.push(`| ${r.v} | ${names[r.id].name} | ${names[r.id].owner} | ${t.map((x) => (x === null ? "—" : x)).join(" | ")} | ${verdict} |`);
  }
  md.push("", `## Стало хуже (${books[last].name} против ${books[prev].name}) — по пунктам`, "");
  for (const w of worse) {
    const a = w.recs[last], b = w.recs[prev];
    const list = (rec, k) => Object.entries((rec && rec.design && rec.design.owners) || {}).flatMap(([o, p]) => (p[k] || []).filter(keep).map((x) => `${o}: ${x}`));
    for (const k of w.grew) {
      const was = new Set(list(b, k)); const now = list(a, k).filter((x) => !was.has(x));
      md.push(`- ${w.v} · ${names[w.id].name} · ${k}: ${(now.length ? now : list(a, k)).slice(0, 4).join("; ") || "(замер ui: шрифт/зона/контраст)"}`);
    }
  }
  md.push("", `Стало лучше: ${better.length} экранов-вариантов; хуже: ${worse.length}.`);
  fs.writeFileSync(path.join(OUT, "COMPARE.md"), md.join("\n") + "\n");
  fs.writeFileSync(path.join(OUT, "COMPARE.json"), JSON.stringify({ books: books.map((b) => ({ name: b.name, sha: b.data.meta.sha, dir: b.dir })), rows: json }, null, 1));
  console.log("ГОТОВО →", OUT, `лучше ${better.length}, хуже ${worse.length}`);
})().catch((e) => { console.error(e); process.exit(2); });
