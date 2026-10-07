// R01 round 12: street search helpers of web/civic/shell/explore.js (node --test).
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { normalize, labelStreets, matchStreets, districtAt } = require("../../../web/civic/shell/explore.js");

const REPO = path.resolve(__dirname, "../../..");
const square = (id, name, x0, y0, x1, y1, hole) => ({ type: "Feature", properties: { id, name },
  geometry: { type: "Polygon", coordinates: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], ...(hole ? [hole] : [])] } });
const A = square("a", "Есиль", 0, 0, 10, 10, [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]);
const B = { type: "Feature", properties: { id: "b", name: "Алматы" },
  geometry: { type: "MultiPolygon", coordinates: [[[[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]], [[[40, 0], [50, 0], [50, 10], [40, 10], [40, 0]]]] } };
const box = (x, y) => [x - 0.5, y - 0.5, x + 0.5, y + 0.5];

test("normalize: case, ё, quotes, hyphens and Kazakh letters", () => {
  assert.equal(normalize("Қабанбай батыр даңғылы"), "кабанбай батыр дангылы");
  assert.equal(normalize("улица газеты «Егемен Қазақстан»"), "улица газеты егемен казакстан");
  assert.equal(normalize("Аль-Фараби  ПРОСПЕКТ"), "аль фараби проспект");
  assert.equal(normalize("Ёлочная"), "елочная");
  assert.equal(normalize(null), "");
});

test("districtAt: polygon with a hole and a multipolygon", () => {
  assert.equal(districtAt([1, 1], [A, B]), "Есиль");
  assert.equal(districtAt([5, 5], [A, B]), null, "inside the hole");
  assert.equal(districtAt([45, 5], [A, B]), "Алматы", "second part of the multipolygon");
  assert.equal(districtAt([15, 5], [A, B]), null);
});

test("labelStreets: same-name parts get districts or numbered parts, never raw coordinates", () => {
  const items = labelStreets([
    { name: "1 улица", bbox: box(2, 2) }, { name: "1 улица", bbox: box(25, 5) },
    { name: "Сарыарка", bbox: box(8, 8) }, { name: "Сарыарка", bbox: box(1, 8) }, { name: "Сарыарка", bbox: box(60, 5) },
    { name: "Уникальная", bbox: box(3, 1) }, { name: "битая", bbox: [1, 2, 3] },
  ], [A, B]);
  assert.equal(items.length, 6, "malformed entries are skipped");
  const by = (n) => items.filter((i) => i.name === n).map((i) => i.place);
  assert.deepEqual(by("1 улица"), ["район Есиль", "район Алматы"]);
  assert.deepEqual(by("Сарыарка").sort(), ["окрестности, вне границ районов", "район Есиль · участок 1 из 2", "район Есиль · участок 2 из 2"]);
  const west = items.find((i) => i.name === "Сарыарка" && i.centre[0] === 1);
  assert.match(west.place, /участок 1 из 2/, "numbered west -> east");
  assert.equal(items.find((i) => i.name === "Уникальная").ambiguous, false);
  assert.ok(items.every((i) => !/\d+\.\d{2,}/.test(i.label)), "no coordinates in labels");
});

test("matchStreets: word order, Kazakh spelling, exact first, short query", () => {
  const items = labelStreets([{ name: "проспект Кабанбай Батыра", bbox: box(1, 1) }, { name: "улица Кабанбай батыра", bbox: box(2, 2) },
    { name: "Кабанбай", bbox: box(3, 3) }, { name: "Абай Құнанбаев көшесі", bbox: box(4, 4) }], [A]);
  assert.deepEqual(matchStreets(items, "батыра кабанбай").map((i) => i.name).sort(), ["проспект Кабанбай Батыра", "улица Кабанбай батыра"]);
  assert.equal(matchStreets(items, "Қабанбай")[0].name, "Кабанбай", "exact match ranks first");
  assert.equal(matchStreets(items, "кунанбаев")[0].name, "Абай Құнанбаев көшесі");
  assert.deepEqual(matchStreets(items, "к"), []);
});

test("real index: every R07 street gets a readable place and Кабанбай resolves to districts", () => {
  const streets = JSON.parse(fs.readFileSync(path.join(REPO, "web/civic/map/streets.json"), "utf8")).streets;
  const districts = JSON.parse(fs.readFileSync(path.join(REPO, "data/astana_districts.geojson"), "utf8").replace(/^﻿/, "")).features;
  const items = labelStreets(streets, districts);
  assert.equal(items.length, streets.length);
  const labels = new Set(items.map((i) => i.label));
  assert.equal(labels.size, items.length, "every variant has a distinct label");
  assert.ok(items.every((i) => !/\(\d+\.\d+, \d+\.\d+\)/.test(i.label)));
  const inCity = items.filter((i) => i.district).length;
  assert.ok(inCity > items.length / 2, `most streets fall in one of the six districts (${inCity}/${items.length})`);
  const kab = matchStreets(items, "Кабанбай");
  assert.ok(kab.length >= 2 && kab.every((i) => i.place));
});
