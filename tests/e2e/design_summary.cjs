#!/usr/bin/env node
// R10 · дизайн-марафон: выжимка «книги экранов» (design_book.cjs BOOK.json) по ролям и пунктам чек-листа —
// одинаковые замечания сведены (значение → сколько экранов-вариантов → примеры), плюс сводка по экрану
// (размеров шрифта, главных кнопок, фокус, отклик нажатия, скелетон при загрузке, текст ошибки).
//   node tests/e2e/design_summary.cjs --book <папка с BOOK.json> [--out <файл SUMMARY.md>]
"use strict";
// Микро-отклик (100–170 мс, только цвет/тень/сжатие) — не замечание (то же правило, что в design_book.cjs с круга 2).
const MICRO = /^переход ((?:transform|scale|translate|background-color|background|color|box-shadow|opacity|filter|border-color|outline-color)(?:, )?)+ (1[0-6]\d) мс/;
const keep = (w) => !MICRO.test(w);
const fs = require("fs"), path = require("path");
const L = require("./r10_lib.cjs");
const args = L.parseArgs(process.argv.slice(2));
const DIR = path.resolve(String(args.book || "."));
const OUT = path.resolve(String(args.out || path.join(DIR, "SUMMARY.md")));
const book = JSON.parse(fs.readFileSync(path.join(DIR, "BOOK.json"), "utf8"));

// Ключ замечания без подписи (для сведения): «отступ 6 px не кратен 4: «…»» → «отступ 6 px не кратен 4».
const keyOf = (w) => w.replace(/:\s*«.*$/, "").replace(/«[^»]*»/g, "«…»").trim();
const byOwner = {};
const screens = {};
for (const [variant, states] of Object.entries(book.variants)) {
  for (const [id, r] of Object.entries(states)) {
    if (id.startsWith("_") || !r.reached) continue;
    const d = r.design || {}, u = r.ui || {};
    for (const [owner, pts] of Object.entries(d.owners || {})) for (const [pt, list] of Object.entries(pts)) for (const w of list.filter(keep)) {
      const o = (byOwner[owner] = byOwner[owner] || {}), p = (o[pt] = o[pt] || {}), k = keyOf(w);
      const e = (p[k] = p[k] || { n: 0, where: new Set(), ex: new Set() });
      e.n++; e.where.add(`${variant} ${id}`); const m = w.match(/«([^»]*)»?\s*$/); if (m && m[1].trim() && e.ex.size < 4) e.ex.add(m[1].trim().slice(0, 28));
    }
    // Замер ux_lib (шрифт < 13, зоны < 44, контраст): владелец не известен — к экрану.
    const s = (screens[id] = screens[id] || { name: r.name, owner: r.owner, v: {} });
    s.v[variant] = {
      sizes: d.type ? d.type.distinct : null, size_list: d.type ? Object.keys(d.type.sizes).map(Number).sort((a, b) => a - b) : [],
      primary: d.hierarchy ? d.hierarchy.primary : null, fonts13: (u.fonts || []).length, taps44: (u.taps || []).length, contrast: (u.contrast || []).length,
      focus: r.focus ? `${r.focus.with_ring}/${r.focus.tabbed}` : null, press: r.press ? (r.press.jumps ? `прыгает ${r.press.jump_px} px` : r.press.feedback ? "есть" : "нет") : null,
      skeleton: d.states ? d.states.skeleton : null, glass: d.glass ? d.glass.length : null, beige: d.color ? d.color.beige.length : 0,
      strokes: d.icons ? Object.keys(d.icons.stroke_px).join("/") : "", motion: d.motion ? Object.keys(d.motion.durations).join(", ") : "",
    };
  }
}
const md = [`# R10 · выжимка книги экранов · ${book.meta.sha}`, "", "```", JSON.stringify(book.meta), "```", "",
  "Одинаковые замечания сведены: «×N» — сколько экранов-вариантов (экран × размер × язык), в скобках — примеры подписей.", ""];
md.push("## По ролям", "");
for (const [owner, pts] of Object.entries(byOwner).sort()) {
  md.push(`### ${owner}`, "");
  for (const [pt, items] of Object.entries(pts).sort()) {
    const list = Object.entries(items).sort((a, b) => b[1].where.size - a[1].where.size);
    md.push(`- **${pt}** — ${list.slice(0, 10).map(([k, e]) => `${k} ×${e.where.size}${e.ex.size ? ` (${[...e.ex].join("; ")})` : ""}`).join(" · ")}${list.length > 10 ? ` · ещё ${list.length - 10}` : ""}`);
  }
  md.push("");
}
md.push("## По экранам (1366-ru / 375-ru / 375-kk)", "",
  "| Экран | Роль | размеров шрифта | главных кнопок | шрифт < 13 / зоны < 44 / контраст | фокус · нажатие | скелетон | стекло | иконки, px | движение |",
  "|---|---|---|---|---|---|---|---|---|---|");
const V = ["1366-ru", "375-ru", "375-kk"];
for (const [id, s] of Object.entries(screens)) {
  const g = (f) => V.map((v) => (s.v[v] ? f(s.v[v]) : "—")).join(" / ");
  md.push(`| ${s.name} \`${id}\` | ${s.owner} | ${g((x) => `${x.sizes} (${x.size_list.join(",")})`)} | ${g((x) => x.primary)} | ${g((x) => `${x.fonts13}/${x.taps44}/${x.contrast}`)} | ${g((x) => [x.focus, x.press].filter(Boolean).join(" · ") || "·")} | ${g((x) => x.skeleton)} | ${g((x) => x.glass)} | ${g((x) => x.strokes || "·")} | ${(s.v["1366-ru"] || {}).motion || ""} |`);
}
fs.writeFileSync(OUT, md.join("\n") + "\n");
console.log("→", OUT);
