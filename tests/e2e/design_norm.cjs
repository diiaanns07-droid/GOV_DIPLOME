// R10 · норма «эталон A» (13 окт, research/round-14/design/REFERENCE.html вариант A + правила Linear) для замечаний книги
// экранов (design_book.cjs писала их по токенам марафона 12 окт). Значения взяты из CSS эталона: то, что эталон рисует сам,
// — не замечание. Критерии владельца 12 окт (шрифт ≥ 13 px, зоны 44 px, контраст 4,5:1) этим фильтром НЕ снимаются — они
// считаются по замеру ui (fonts/taps/contrast), а не по этим строкам.
"use strict";
const REF_RADII = [3, 6, 8, 9, 11, 12, 14, 16, 18, 20, 26, 36];          // border-radius эталона (+ 999 — таблетка)
const REF_SCALE = [12, 13, 14, 15, 16, 18, 19, 22, 26, 34, 40];          // font-size эталона
const REF_SPACE = [2, 3, 4, 6, 7, 8, 9, 10, 12, 13, 14, 16, 18, 19, 24, 28, 48]; // padding / margin / gap эталона
// Светлые плашки статусов и уровней эталона (#faeeda «На проверке», #eaf3de, #fcebeb, …).
const REF_TINTS = ["#faeeda", "#eaf3de", "#fcebeb", "#e7f0de", "#e1ecd6", "#f3f1ec", "#f5f4f0", "#f8f7f4", "#efede8", "#e9e5dd", "#ece8e2", "#e6dcc8", "#fac775"];
const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const near = (h) => REF_TINTS.some((t) => { const a = rgb(h), b = rgb(t); return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]) <= 24; });
const num = (re, w) => { const m = w.match(re); return m ? Number(m[1]) : null; };
// true — замечание остаётся при норме эталона A.
function keepRef(w) {
  let n;
  if ((n = num(/^радиус (\d+) px вне токенов/, w)) !== null && REF_RADII.some((t) => Math.abs(t - n) <= 0.6)) return false;
  if ((n = num(/^(\d+(?:\.\d+)?) px вне шкалы/, w)) !== null && REF_SCALE.includes(Math.round(n))) return false;
  if (/^вес 500:/.test(w)) return false;
  if (/^вес 700: «[\d\s·.,%+−-]+»/.test(w)) return false;                // числа на значках и плашках — 700, как в эталоне
  if ((n = num(/^отступ (\d+(?:\.\d+)?) px не кратен 4/, w)) !== null && REF_SPACE.includes(Math.round(n))) return false;
  if ((n = num(/ (\d+) мс \(норма 200–350\)/, w)) !== null && n >= 120 && n <= 330) return false;  // движение: 150–250 (±30), эталон — до 300
  const b = w.match(/^бежевая плашка (#[0-9a-f]{6})/i); if (b && near(b[1].toLowerCase())) return false;
  return true;
}
module.exports = { keepRef, REF_RADII, REF_SCALE, REF_SPACE };
