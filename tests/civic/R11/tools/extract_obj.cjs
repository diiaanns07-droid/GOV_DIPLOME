// Достаёт объектный литерал `<name> = { … }` из исходника модуля (скобки — с учётом строк и комментариев) и
// печатает {ключ: {ru, kk, where}} для i18n_tools add. Формат словаря модуля: {ru: {…}, kk: {…}}.
const fs = require("fs"), vm = require("vm");
const [file, name, where] = process.argv.slice(2);
const src = fs.readFileSync(file, "utf8");
const m = new RegExp("\\b" + name + "\\s*=\\s*\\{").exec(src);
if (!m) { console.error("нет " + name); process.exit(1); }
let i = m.index + m[0].length - 1, depth = 0, q = null;
for (; i < src.length; i++) {
  const c = src[i], n = src[i + 1];
  if (q) { if (c === "\\") { i++; continue; } if (c === q) q = null; continue; }
  if (c === "/" && n === "/") { i = src.indexOf("\n", i); continue; }
  if (c === "/" && n === "*") { i = src.indexOf("*/", i) + 1; continue; }
  if (c === '"' || c === "'" || c === "`") { q = c; continue; }
  if (c === "{") depth++;
  if (c === "}") { depth--; if (depth === 0) break; }
}
const text = src.slice(m.index + m[0].length - 1, i + 1);
const obj = vm.runInNewContext("(" + text + ")", {});
const ru = obj.ru || {}, kk = obj.kk || {};
const out = {};
for (const [k, v] of Object.entries(ru)) out[k] = { ru: v, kk: kk[k] != null ? kk[k] : "", where };
process.stdout.write(JSON.stringify(out, null, 1));
