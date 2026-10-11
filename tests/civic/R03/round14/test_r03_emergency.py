"""R03 для R09: срочные случаи по тексту (emergency.py, emergency_rules.json, emergency_ref.mjs) — без ML-библиотек."""

from __future__ import annotations

import json
import re
import shutil

import pytest

import r03_markers  # noqa: F401  (sys.path на корень репозитория)
from ml.civic_classifier_v2 import emergency as E

CASES = E.load_cases()
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="NOT_RUN: нет node")


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:40] for c in CASES])
def test_cases(case):
    kinds = [h["kind"] for h in E.detect(case["text"])]
    if case["expect"] is None:
        assert kinds == [], case.get("why")
    else:
        assert case["expect"] in kinds


def test_cases_cover_every_kind_language_and_negatives():
    kinds = {c["expect"] for c in CASES}
    assert {"gas", "fire", "wire", None} <= kinds
    for kind in ("gas", "fire", "wire"):
        langs = {c["lang"] for c in CASES if c["expect"] == kind}
        assert {"ru", "kk", "translit"} <= langs, kind
    assert sum(c["expect"] is None for c in CASES) >= 20


def test_naive_substring_is_worse():
    """Буквальное «газ/горит/пожар/оборван провод» подстрокой ошибается на газоне, фонарях и пожарной машине."""
    res = E.score_cases(CASES)
    assert res["rules_ok"] == res["n"]
    assert res["naive_ok"] < res["n"] * 0.7
    assert E.naive("Машины паркуются на газоне у дома")


def test_demo_phrases_have_no_banner():
    # B-004 (R10) и демо-фраза освещения R04: баннер «звоните 104» на них был бы заметной ошибкой демо.
    for text in ("Машины паркуются на газоне у дома", "Аялдамада жарық жоқ, кешке қараңғы",
                 "Не горит фонарь у остановки"):
        assert E.detect(text) == [], text


def test_phone_and_subtopic_come_from_categories_file():
    tel = E.phones()
    assert tel[("smell_air", "gas")] == "104"
    hit = E.detect("В подъезде пахнет газом")[0]
    assert (hit["kind"], hit["category"], hit["subtopic"], hit["phone"]) == ("gas", "smell_air", "gas", "104")
    assert E.detect("Оборван провод, лежит на тротуаре")[0]["phone"] == tel[("lighting", "wire_down")]
    assert E.detect("В соседнем подъезде пожар")[0]["phone"] == tel[("smell_air", "smoke_fire")]


def test_several_kinds_keep_kinds_order():
    kinds = [h["kind"] for h in E.detect("Провод искрит, загорелся щиток, пахнет газом")]
    assert kinds == ["gas", "fire", "wire"]


def test_rules_are_portable_to_js():
    """В JS \\b не видит кириллицу, а просмотра назад нет в Safari < 16.4 — в правилах их быть не должно."""
    raw = json.loads(E.RULES_PATH.read_text(encoding="utf-8"))
    sources = [r["re"] for r in raw["rules"]] + [r["veto"] for r in raw["rules"] if r.get("veto")]
    sources += [e["re"] for e in raw["except"]] + list(raw["defs"].values())
    for src in sources:
        assert "\\b" not in src and "(?<" not in src and "\\w" not in src, src
        full = E._expand(src, raw["defs"])
        assert full == full.lower(), f"текст нормализован в нижний регистр: {src}"
    for r in raw["rules"]:
        assert r["kind"] in raw["kinds"]
        re.compile(E._expand(r["re"], raw["defs"]))
    ids = [r["id"] for r in raw["rules"]]
    assert len(ids) == len(set(ids))


def test_normalize():
    assert E.normalize("  ПАХНЕТ\tгазом\nЁлка ") == "пахнет газом елка"
    assert E.normalize(None) == ""


@needs_node
def test_js_reference_matches_python():
    texts = [c["text"] for c in CASES] + ["", "   ", "ГАЗ!!!", "газон газель газета", "Провод искрит, пахнет газом"]
    js = E.detect_js(texts)
    assert js == [[h["kind"] for h in E.detect(t)] for t in texts]
