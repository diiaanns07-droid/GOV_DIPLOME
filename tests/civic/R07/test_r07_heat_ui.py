"""R07 раунд 14: словарь интерфейса тепловой карты (ru/kk) — одинаковые ключи и подстановки.

Нужен Node.js (есть в облаке и у Codex); без него тест пропускается с причиной.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HEAT_JS = ROOT / "web/civic/heat/heat.js"
TECH_WORDS = ("ребро", "граф", "геометри", "сценари", "payload", "demo-ring", "feature", "target", "undefined", "демо")  # «демо» — UX_BRIEF №4, R11 день 3 №7


def load_dict():
    node = shutil.which("node")
    if not node:
        pytest.skip("NOT_RUN: нет node")
    code = ("global.window={fetch(){}};global.document={};require(process.argv[1]);"
            "process.stdout.write(JSON.stringify(window.CivicHeat.messages))")
    out = subprocess.run([node, "-e", code, str(HEAT_JS)], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


def forms(v):
    return list(v.values()) if isinstance(v, dict) else [v]


def test_ru_and_kk_have_same_keys_and_placeholders():
    d = load_dict()
    assert set(d["ru"]) == set(d["kk"])
    for key in d["ru"]:
        ph_ru = {p for f in forms(d["ru"][key]) for p in re.findall(r"\{(\w+)\}", f)}
        ph_kk = {p for f in forms(d["kk"][key]) for p in re.findall(r"\{(\w+)\}", f)}
        assert ph_ru == ph_kk, key
        for f in forms(d["kk"][key]) + forms(d["ru"][key]):
            assert f.strip(), key


def test_russian_plurals_have_three_forms_and_kazakh_one():
    d = load_dict()
    for key, v in d["ru"].items():
        if isinstance(v, dict):
            assert set(v) == {"one", "few", "many"}, key
            assert set(d["kk"][key]) == {"other"}, key


def test_no_technical_words_and_no_exclamations():
    d = load_dict()
    for lang in ("ru", "kk"):
        for key, v in d[lang].items():
            for f in forms(v):
                low = re.sub(r"\{\w+\}", "", f).lower()  # имена подстановок — не видимый текст
                assert not any(w in low for w in TECH_WORDS), (lang, key, f)
                assert "!" not in f and "Ошибка:" not in f, (lang, key, f)
