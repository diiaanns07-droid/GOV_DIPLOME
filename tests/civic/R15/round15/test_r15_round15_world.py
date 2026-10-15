"""R15 раунд 15 · R02 демо-мир (data/civic/astana/demo-world/world_v1.json) — THREATS_R15 T-R02-01, P8.

Демо-мир засевается во все модули и показывается жюри, поэтому:
- каждая запись мира — demo: true (на экране «Пример»);
- в текстах нет телефонов, ИИН, e-mail, ссылок, HTML, номеров квартир (id OSM и участков улиц — не в счёт);
- нет полей устройств и авторов (засев не создаёт «жителей», которых можно подменить через API — S20, P8);
- «старший по двору» — только имя одним словом; у встреч нет имени ведущего («аким района»).
Нет файла в сборке — NOT_RUN.
"""

from __future__ import annotations

import json
import re

import pytest

from r15_common import ROOT
from r15_round15 import not_run

WORLD = ROOT / "data" / "civic" / "astana" / "demo-world" / "world_v1.json"
RECORDS = ("events", "yards", "complaints", "works", "planned_conflicts", "ideas", "initiatives", "incidents",
           "meetings", "questions")
ID_KEYS = re.compile(r"(^|_)(id|ids|osm|segments|targets|scene|link|from_idea|duplicate_of)$")
PATTERNS = {
    "phone": re.compile(r"(?<![\w-])(?:\+?7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?![\w-])"),
    "long_number": re.compile(r"(?<![\w-])\d(?:[\s-]?\d){9,}(?![\w-])"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "url": re.compile(r"https?://|www\.|t\.me/|wa\.me/"),
    "html": re.compile(r"<\s*[a-zA-Z/!]"),
    "apartment": re.compile(r"(?i)\bкв\.?\s*\d|квартир\w*\s*\d|пәтер\s*\d|\d+\s*-?\s*пәтер"),
}


@pytest.fixture(scope="module")
def world():
    if not WORLD.exists():
        not_run(f"в сборке нет демо-мира R02 ({WORLD.relative_to(ROOT)})")
    return json.loads(WORLD.read_text(encoding="utf-8"))


def _strings(node, key=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, str(k))
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, key)
    elif isinstance(node, str):
        yield key, node


def test_every_world_record_is_demo(world):
    """Синтетика помечена: на экране «Пример» (COMMON «Честность»)."""
    missing = [f"{k}[{i}]" for k in RECORDS for i, r in enumerate(world.get(k) or [])
               if isinstance(r, dict) and r.get("demo") is not True]
    assert not missing, missing[:10]


def test_no_personal_data_in_world_texts(world):
    """T-R02-01: ни телефонов, ни ИИН, ни почты, ни ссылок, ни HTML, ни квартир в синтетических текстах."""
    found = []
    for name in RECORDS:
        for key, text in _strings(world.get(name) or []):
            if ID_KEYS.search(key):
                continue
            for kind, rx in PATTERNS.items():
                if rx.search(text):
                    found.append(f"{name}.{key} [{kind}]: {text[:80]}")
    assert not found, "\n".join(found[:15])


def test_no_device_or_author_fields(world):
    """P8 / S20: засев не несёт устройств и авторов — «Я приду», «Я живу здесь» — числами."""
    bad = sorted({f"{name}.{k}" for name in RECORDS for r in world.get(name) or [] if isinstance(r, dict)
                  for k in r if re.search(r"device|author|phone|email|login|username", k)})
    assert not bad, bad


def test_captains_first_name_only_and_hosts_without_names(world):
    """CONTRACT §5.3, §5.7: старший — отображаемое имя одним словом; ведущий встречи — должность, без имени."""
    for yard in world.get("yards") or []:
        captain = yard.get("captain")
        if captain:
            name = captain.get("display_name") or ""
            assert re.fullmatch(r"[А-ЯЁӘҒҚҢӨҰҮҺІA-Z][а-яёәғқңөұүһіa-z]{1,19}", name), (yard.get("id"), name)
    for meeting in world.get("meetings") or []:
        assert not any(k in meeting for k in ("host", "host_name", "akim", "akim_name")), meeting.get("id")
