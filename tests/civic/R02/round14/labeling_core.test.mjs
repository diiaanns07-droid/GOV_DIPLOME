// R02 · раунд 14 · чистые функции web/labeling/core.js (без браузера).
//   node --test tests/civic/R02/round14/labeling_core.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const C = createRequire(import.meta.url)(path.join(ROOT, "web/labeling/core.js"));

test("CSV: кавычки, \"\" внутри поля, перевод строки в поле, CRLF, BOM", () => {
  const csv = '﻿id,text\r\n1,"Яма, большая"\r\n2,"Он сказал ""стоп""\nи ушёл"\r\n';
  assert.deepEqual(C.parseCSV(csv), [["id", "text"], ["1", "Яма, большая"], ["2", 'Он сказал "стоп"\nи ушёл']]);
});

test("CSV: разделитель ; (Excel с русской локалью) и табуляция", () => {
  assert.equal(C.detectDelimiter("id;text\n1;a,b"), ";");
  assert.equal(C.detectDelimiter("id\ttext\n1\ta"), "\t");
  assert.equal(C.detectDelimiter('"a;b",c\n'), ",");
});

test("CSV Google-формы: столбец текста находится по заголовку на двух языках", () => {
  const csv = '"Отметка времени","Текст жалобы / Шағым мәтіні","Язык / Тіл","Район Астаны / Аудан"\n"1","Аулада шам жоқ","қазақша","Есиль"\n';
  const { records, textColumn } = C.csvToRecords(csv);
  assert.equal(textColumn, "Текст жалобы / Шағым мәтіні");
  assert.equal(records[0].text, "Аулада шам жоқ");
  assert.equal(C.normLang(records[0].lang), "kk");
  assert.equal(records[0].district, "Есиль");
});

test("CSV без известного заголовка: берётся самый длинный столбец", () => {
  const { records } = C.csvToRecords("a,b\n1,очень длинный текст жалобы\n2,ещё один текст\n");
  assert.equal(records[0].text, "очень длинный текст жалобы");
});

test("JSONL: битые строки считаются, повторы id убираются, пустые тексты пропускаются", () => {
  const p = C.parseFile("x.jsonl", '{"id":"a","text":"яма"}\nmusor\n{"id":"a","text":"повтор"}\n{"id":"b","text":"  "}\n{"text":"без id"}\n');
  assert.equal(p.items.length, 2);
  assert.equal(p.badLines, 1);
  assert.equal(p.duplicates, 1);
  assert.equal(p.empty, 1);
  assert.match(p.items[1].id, /^t-[0-9a-f]{8}$/);
});

test("id по содержанию стабилен: регистр, ё/е и пробелы не меняют id", () => {
  assert.equal(C.textId("Ёлка  у Дома"), C.textId("елка у дома"));
  assert.notEqual(C.textId("яма"), C.textId("ямы"));
});

test("чужая метка (синтетический корпус) не загружается; своя (birge-labels-v1) — загружается", () => {
  const p = C.parseFile("x.jsonl", '{"id":"a","text":"яма","label":"roads"}\n{"id":"b","text":"снег","label":"snow_ice","schema":"birge-labels-v1"}\n');
  assert.equal(p.items[0].prior, undefined);
  assert.equal(p.items[1].prior.label, "snow_ice");
  assert.equal(C.blindItems(p.items)[1].prior, undefined);
});

test("поднабор детерминирован, не зависит от порядка строк, размер ограничен", () => {
  const items = Array.from({ length: 50 }, (_, i) => ({ id: "id" + i, text: "t" + i }));
  const a = C.selectSubset(items, 10, "k").map((x) => x.id);
  const b = C.selectSubset(items.slice().reverse(), 10, "k").map((x) => x.id).sort();
  assert.equal(a.length, 10);
  assert.deepEqual(a.slice().sort(), b);
  assert.notDeepEqual(C.selectSubset(items, 10, "other").map((x) => x.id).sort(), a.slice().sort());
  assert.equal(C.selectSubset(items, 999, "k").length, 50);
});

test("язык: казахские буквы → kk; с русскими служебными словами → mixed; «не» не делает текст смешанным", () => {
  assert.equal(C.guessLang("Аулада шам жанбайды"), "kk");
  assert.equal(C.guessLang("Бағдаршам не работает уже неделю"), "mixed");
  assert.equal(C.guessLang("Не болды? Аулада қараңғы"), "kk");
  assert.equal(C.guessLang("Яма на дороге"), "ru");
  assert.equal(C.guessLang("yama na doroge"), "");
});

test("навигация: следующий открытый текст с переходом через конец; -1, когда всё сделано", () => {
  const items = [{ id: "a" }, { id: "b" }, { id: "c" }];
  assert.equal(C.nextOpenIndex(items, { b: { label: "x" } }, {}, 0), 2);
  assert.equal(C.nextOpenIndex(items, { c: { label: "x" } }, {}, 1), 0);
  assert.equal(C.nextOpenIndex(items, { a: 1, b: 1 }, { c: true }, 0), -1);
});

test("экспорт: только размеченные, поля схемы, поднабор у второго разметчика", () => {
  const state = { items: [{ id: "a", text: "яма", lang: "ru" }, { id: "b", text: "снег", lang: "ru" }],
    labels: { a: { label: "roads", unsure: true, at: "2026-10-11T10:00:00Z", ms: 4000 } }, skipped: { b: true },
    annotator: "B", mode: "second", subsetSeed: "k", fileName: "f.jsonl" };
  const rows = C.exportLines(state).trim().split("\n").map((l) => JSON.parse(l));
  assert.equal(rows.length, 1);
  assert.deepEqual(Object.keys(rows[0]).sort(), ["annotator", "id", "label", "labeled_at", "lang", "ms", "role", "schema", "source", "subset", "text", "unsure"]);
  assert.equal(rows[0].role, "second");
  assert.deepEqual(rows[0].subset, { seed: "k", size: 2 });
  assert.equal(C.exportLines({ ...state, labels: {} }), "");
});

test("горячие клавиши: 12 разных физических клавиш, без букв (раскладка не важна)", () => {
  const codes = C.CATEGORY_KEYS.map((k) => k.code);
  assert.equal(new Set(codes).size, 12);
  assert.ok(codes.every((c) => /^(Digit\d|Minus|Equal)$/.test(c)));
});
