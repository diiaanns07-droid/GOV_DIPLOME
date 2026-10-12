/*
 * Birge · инструмент разметки (R02, раунд 14) — чистые функции без DOM.
 *
 * Работает и в браузере (window.BirgeLabelCore), и в node (module.exports) —
 * так функции разбора файлов, поднабора и экспорта проверяются тестами
 * tests/civic/R02/round14/labeling_core.test.mjs без браузера.
 *
 * Здесь нет сети и нет внешних библиотек: страница открывается двойным щелчком
 * по web/labeling/index.html (file://) на ноутбуке без интернета.
 */
(function (root) {
  "use strict";

  var SCHEMA = "birge-labels-v1";
  var NOT_COMPLAINT = "not_complaint";
  // Строка жалобы из Google-формы может быть очень длинной; ограничение защищает
  // localStorage и экран от случайно вставленной простыни текста.
  var MAX_TEXT = 4000;

  // Горячие клавиши по ФИЗИЧЕСКИМ клавишам (event.code), а не по символу (event.key):
  // в казахской раскладке верхний ряд печатает «ә і ң ғ ү ұ қ ө һ» вместо цифр,
  // в русской — буквы. event.code одинаков в любой раскладке.
  var CATEGORY_KEYS = [
    { code: "Digit1", alt: "Numpad1", label: "1" },
    { code: "Digit2", alt: "Numpad2", label: "2" },
    { code: "Digit3", alt: "Numpad3", label: "3" },
    { code: "Digit4", alt: "Numpad4", label: "4" },
    { code: "Digit5", alt: "Numpad5", label: "5" },
    { code: "Digit6", alt: "Numpad6", label: "6" },
    { code: "Digit7", alt: "Numpad7", label: "7" },
    { code: "Digit8", alt: "Numpad8", label: "8" },
    { code: "Digit9", alt: "Numpad9", label: "9" },
    { code: "Digit0", alt: "Numpad0", label: "0" },
    { code: "Minus", alt: "NumpadSubtract", label: "-" },
    { code: "Equal", alt: "NumpadAdd", label: "=" }
  ];

  /* ---------- хеш и отпечаток файла ---------- */

  // FNV-1a 32 бит по UTF-16 кодам: быстро, детерминированно, одинаково в node и браузере.
  // Не криптография — только стабильные id и отпечаток набора.
  function fnv1a(str) {
    var h = 0x811c9dc5;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return ("0000000" + h.toString(16)).slice(-8);
  }

  function normalizeForId(text) {
    return String(text).normalize("NFC").toLowerCase().replace(/ё/g, "е").replace(/\s+/g, " ").trim();
  }

  // id по содержанию: тот же текст даёт тот же id в любом файле и у любого разметчика.
  function textId(text) {
    return "t-" + fnv1a(normalizeForId(text));
  }

  function fingerprint(items) {
    var parts = [];
    for (var i = 0; i < items.length; i++) parts.push(items[i].id + "\u0001" + items[i].text);
    return fnv1a(parts.join("\u0002")) + "-" + items.length;
  }

  /* ---------- CSV ---------- */

  // Разделитель по первой строке вне кавычек: Excel с русской локалью сохраняет «;».
  function detectDelimiter(text) {
    var counts = { ",": 0, ";": 0, "\t": 0 };
    var inQ = false;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (ch === '"') inQ = !inQ;
      else if (!inQ && (ch === "\n" || ch === "\r")) break;
      else if (!inQ && counts.hasOwnProperty(ch)) counts[ch]++;
    }
    var best = ",";
    if (counts[";"] > counts[best]) best = ";";
    if (counts["\t"] > counts[best]) best = "\t";
    return best;
  }

  // RFC 4180: кавычки, удвоенные кавычки, переводы строк внутри поля, CRLF, BOM.
  function parseCSV(text, delimiter) {
    text = String(text).replace(/^﻿/, "");
    var d = delimiter || detectDelimiter(text);
    var rows = [], row = [], field = "", inQ = false, i = 0;
    while (i < text.length) {
      var ch = text[i];
      if (inQ) {
        if (ch === '"') {
          if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
          inQ = false; i++; continue;
        }
        field += ch; i++; continue;
      }
      if (ch === '"') { inQ = true; i++; continue; }
      if (ch === d) { row.push(field); field = ""; i++; continue; }
      if (ch === "\r") { i++; continue; }
      if (ch === "\n") { row.push(field); rows.push(row); row = []; field = ""; i++; continue; }
      field += ch; i++;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    // Пустые строки в конце файла не считаются записями.
    return rows.filter(function (r) { return r.some(function (c) { return c.trim() !== ""; }); });
  }

  function findColumn(header, names) {
    var low = header.map(function (h) { return String(h).toLowerCase().trim(); });
    for (var n = 0; n < names.length; n++) {
      var idx = low.indexOf(names[n]);
      if (idx >= 0) return idx;
    }
    for (n = 0; n < names.length; n++) {
      for (var k = 0; k < low.length; k++) if (names[n].length > 3 && low[k].indexOf(names[n]) >= 0) return k;
    }
    return -1;
  }

  var TEXT_COLS = ["text", "текст", "текст жалобы", "шағым мәтіні", "complaint", "message", "сообщение", "жалоба"];
  var ID_COLS = ["id"];
  var LANG_COLS = ["lang", "language", "язык", "тіл"];
  var DISTRICT_COLS = ["district", "район", "аудан"];

  function csvToRecords(text) {
    var rows = parseCSV(text);
    if (!rows.length) return { records: [], textColumn: null };
    var header = rows[0];
    var body = rows.slice(1);
    var ti = findColumn(header, TEXT_COLS);
    if (ti < 0) {
      // Запасной путь: самый «длинный» столбец по средней длине — это и есть текст.
      var best = -1, bestLen = -1;
      for (var c = 0; c < header.length; c++) {
        var sum = 0;
        for (var r = 0; r < body.length; r++) sum += (body[r][c] || "").length;
        if (sum > bestLen) { bestLen = sum; best = c; }
      }
      ti = best;
    }
    var ii = findColumn(header, ID_COLS), li = findColumn(header, LANG_COLS), di = findColumn(header, DISTRICT_COLS);
    var li2 = findColumn(header, ["label"]);
    var records = body.map(function (r) {
      var rec = { text: r[ti] || "" };
      if (ii >= 0 && r[ii]) rec.id = r[ii];
      if (li >= 0 && r[li]) rec.lang = r[li];
      if (di >= 0 && r[di]) rec.district = r[di];
      if (li2 >= 0 && r[li2]) rec.label = r[li2];
      return rec;
    });
    return { records: records, textColumn: header[ti] };
  }

  /* ---------- JSONL / JSON ---------- */

  function jsonlToRecords(text) {
    text = String(text).replace(/^﻿/, "").trim();
    if (!text) return { records: [], badLines: 0 };
    if (text[0] === "[") {
      var arr = JSON.parse(text);
      return { records: arr.filter(function (x) { return x && typeof x === "object"; }), badLines: 0 };
    }
    var out = [], bad = 0;
    text.split(/\r?\n/).forEach(function (line) {
      line = line.trim();
      if (!line) return;
      try {
        var obj = JSON.parse(line);
        if (obj && typeof obj === "object" && !Array.isArray(obj)) out.push(obj); else bad++;
      } catch (e) { bad++; }
    });
    return { records: out, badLines: bad };
  }

  /* ---------- приведение к единому виду ---------- */

  function normLang(v) {
    if (!v) return "";
    var s = String(v).toLowerCase().trim();
    if (s === "kk" || s === "kz" || s.indexOf("қаз") === 0 || s.indexOf("каз") === 0) return "kk";
    if (s === "ru" || s.indexOf("рус") === 0 || s.indexOf("orys") === 0) return "ru";
    if (s === "mixed" || s.indexOf("арал") === 0 || s.indexOf("смеш") === 0 || s.indexOf("mix") === 0) return "mixed";
    return "";
  }

  var KK_LETTERS = /[әғқңөұүһіӘҒҚҢӨҰҮҺІ]/;
  // Русские служебные слова, которых нет в казахском как отдельных слов.
  // «не» сюда не входит: по-казахски это «что» («не болды?»).
  var RU_WORDS = { "нет": 1, "уже": 1, "что": 1, "очень": 1, "просим": 1, "когда": 1, "почему": 1, "и": 1,
    "в": 1, "на": 1, "это": 1, "как": 1, "опять": 1, "снова": 1, "или": 1, "но": 1, "у": 1, "с": 1, "по": 1 };
  // Частые казахские слова без «особых» букв: «Аулада шам жанбайды» иначе выглядел бы русским.
  var KK_WORDS = { "аулада": 1, "аула": 1, "шам": 1, "жол": 1, "жолда": 1, "жоқ": 1, "бар": 1, "емес": 1, "мен": 1,
    "бен": 1, "пен": 1, "су": 1, "жылу": 1, "сынған": 1, "жанында": 1, "бойында": 1, "қала": 1, "тұрғындар": 1 };
  var KK_SUFFIX = /(байды|бейді|майды|мейді|пайды|пейді)$/; // отрицание глагола: «жанбайды», «тазаламайды»
  // Грубая подсказка языка для показа на экране; разметчик может поправить клавишей L.
  // \b в JavaScript не понимает кириллицу, поэтому делим текст на слова вручную.
  function guessLang(text) {
    var low = String(text).toLowerCase();
    var words = low.split(/[^a-zа-яёәғқңөұүһі]+/);
    var kk = KK_LETTERS.test(low), ru = false;
    for (var i = 0; i < words.length; i++) {
      if (KK_WORDS[words[i]] || KK_SUFFIX.test(words[i])) kk = true;
      if (RU_WORDS[words[i]]) ru = true;
    }
    if (kk) return ru ? "mixed" : "kk";
    if (/[а-яё]/.test(low)) return "ru";
    return "";
  }

  /**
   * Записи файла → элементы разметки {id, text, lang, district, prior}.
   * prior — готовая метка ИЗ НАШЕГО экспорта (schema birge-labels-v1); чужие поля label
   * (например, у синтетического корпуса) не сохраняются, чтобы разметка была «вслепую».
   */
  function normalizeRecords(records) {
    var seen = {}, items = [], dupes = 0, empty = 0, truncated = 0;
    for (var i = 0; i < records.length; i++) {
      var r = records[i];
      var text = r.text != null ? r.text : (r.message != null ? r.message : r["текст"]);
      text = text == null ? "" : String(text).trim();
      if (!text) { empty++; continue; }
      if (text.length > MAX_TEXT) { text = text.slice(0, MAX_TEXT) + " …"; truncated++; }
      var id = r.id != null && String(r.id).trim() ? String(r.id).trim() : textId(text);
      if (seen[id]) { dupes++; continue; }
      seen[id] = true;
      var item = { id: id, text: text, lang: normLang(r.lang || r.language) || guessLang(text) };
      if (r.district) item.district = String(r.district);
      if (r.schema === SCHEMA && r.label) {
        item.prior = { label: String(r.label), unsure: !!r.unsure, at: r.labeled_at || null, annotator: r.annotator || "" };
      }
      items.push(item);
    }
    return { items: items, duplicates: dupes, empty: empty, truncated: truncated };
  }

  function parseFile(name, text) {
    var isCsv = /\.(csv|tsv|txt)$/i.test(name);
    var parsed, bad = 0, textColumn = null;
    if (isCsv) {
      parsed = csvToRecords(text);
      textColumn = parsed.textColumn;
    } else {
      parsed = jsonlToRecords(text);
      bad = parsed.badLines;
    }
    var norm = normalizeRecords(parsed.records);
    norm.badLines = bad;
    norm.textColumn = textColumn;
    norm.format = isCsv ? "csv" : "jsonl";
    return norm;
  }

  /* ---------- поднабор для второго разметчика ---------- */

  // Детерминированный поднабор: порядок по fnv1a(seed + id). Один и тот же файл
  // и одно и то же «зерно» дают одинаковый поднабор на любом компьютере.
  function selectSubset(items, size, seed) {
    var keyed = items.map(function (it) { return { k: fnv1a(String(seed) + "\u0001" + it.id), it: it }; });
    keyed.sort(function (a, b) { return a.k < b.k ? -1 : a.k > b.k ? 1 : 0; });
    var n = Math.max(0, Math.min(items.length, size | 0));
    var chosen = {};
    keyed.slice(0, n).forEach(function (x) { chosen[x.it.id] = true; });
    // Сохраняем исходный порядок файла внутри поднабора — так удобнее сверять.
    return items.filter(function (it) { return chosen[it.id]; });
  }

  // Второму разметчику — только текст: никакой prior-метки первого разметчика.
  function blindItems(items) {
    return items.map(function (it) {
      var b = { id: it.id, text: it.text, lang: it.lang };
      if (it.district) b.district = it.district;
      return b;
    });
  }

  /* ---------- навигация ---------- */

  function nextOpenIndex(items, labels, skipped, from) {
    var n = items.length;
    for (var step = 1; step <= n; step++) {
      var i = (from + step) % n;
      var id = items[i].id;
      if (!labels[id] && !skipped[id]) return i;
    }
    return -1;
  }

  function counts(items, labels, skipped) {
    var done = 0, skip = 0, byLabel = {};
    for (var i = 0; i < items.length; i++) {
      var id = items[i].id;
      if (labels[id]) {
        done++;
        byLabel[labels[id].label] = (byLabel[labels[id].label] || 0) + 1;
      } else if (skipped[id]) skip++;
    }
    return { total: items.length, done: done, skipped: skip, open: items.length - done - skip, byLabel: byLabel };
  }

  function median(values) {
    if (!values.length) return null;
    var s = values.slice().sort(function (a, b) { return a - b; });
    var m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  /* ---------- экспорт ---------- */

  function exportLines(state) {
    var lines = [];
    for (var i = 0; i < state.items.length; i++) {
      var it = state.items[i];
      var l = state.labels[it.id];
      if (!l) continue;
      var row = {
        schema: SCHEMA, id: it.id, text: it.text, lang: l.lang || it.lang || "",
        label: l.label, unsure: !!l.unsure, annotator: state.annotator || "",
        role: state.mode === "second" ? "second" : "first",
        labeled_at: l.at || null, ms: l.ms == null ? null : l.ms, source: state.fileName || ""
      };
      if (it.district) row.district = it.district;
      if (state.mode === "second") row.subset = { seed: state.subsetSeed, size: state.items.length };
      lines.push(JSON.stringify(row));
    }
    return lines.join("\n") + (lines.length ? "\n" : "");
  }

  // Поднабор без меток — отдать второму разметчику, у которого нет исходного файла.
  function exportSubsetLines(items) {
    return blindItems(items).map(function (it) { return JSON.stringify(it); }).join("\n") + (items.length ? "\n" : "");
  }

  function safeName(s) {
    return String(s || "").replace(/[^\w\-а-яёәғқңөұүһі]+/gi, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "x";
  }

  var api = {
    SCHEMA: SCHEMA, NOT_COMPLAINT: NOT_COMPLAINT, CATEGORY_KEYS: CATEGORY_KEYS, MAX_TEXT: MAX_TEXT,
    fnv1a: fnv1a, textId: textId, fingerprint: fingerprint,
    detectDelimiter: detectDelimiter, parseCSV: parseCSV, csvToRecords: csvToRecords,
    jsonlToRecords: jsonlToRecords, normalizeRecords: normalizeRecords, parseFile: parseFile,
    normLang: normLang, guessLang: guessLang,
    selectSubset: selectSubset, blindItems: blindItems,
    nextOpenIndex: nextOpenIndex, counts: counts, median: median,
    exportLines: exportLines, exportSubsetLines: exportSubsetLines, safeName: safeName
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BirgeLabelCore = api;
})(typeof window !== "undefined" ? window : this);
