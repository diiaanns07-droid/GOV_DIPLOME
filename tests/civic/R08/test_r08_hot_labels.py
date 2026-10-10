"""R08: в «Горячих местах» — понятные названия мест, а не общие слова «Двор или квартал» / «Нысан».

Найдено ночью 10 окт в сборке R01 (d9a8895 + R07 35e6feb): данные R12 data/civic/astana/geo/*.json читаются
TargetResolver R07 после его готовых подписей (fixtures/targets_demo.json) и стирают их, если у R12 нет названия
(двор yard-1071933339: name_ru = null) → на экране «Двор или квартал», в ҚАЗ у остановок «Нысан».
Исправление — patch research/round-14-results/R08/patches/r07_registry_labels.patch (применяет R01 / R07).
Тест работает там, где есть и R07, и данные R12 (общая сборка); в ветке R08 без них — пропуск с причиной.
"""
import json
from pathlib import Path

import pytest

civic_heat = pytest.importorskip("ui.civic_heat", reason="нет модуля R07 ui/civic_heat в сборке")

ROOT = Path(__file__).resolve().parents[3]
R12_GEO = ROOT / "data" / "civic" / "astana" / "geo"
FIXTURE = ROOT / "ui" / "civic_heat" / "fixtures" / "targets_demo.json"
GENERIC = {"Двор или квартал", "Аула немесе орам", "Объект", "Нысан", "Участок улицы", "Көше бөлігі"}


@pytest.fixture(scope="module")
def curated():
    if not (R12_GEO / "yards.json").is_file() or not FIXTURE.is_file():
        pytest.skip("нет данных R12 geo/*.json или подписей R07 — проверка только в общей сборке")
    targets = json.loads(FIXTURE.read_text("utf-8"))["targets"]
    return {tid: t for tid, t in targets.items() if t.get("label_ru") and t.get("label_kk")
            and t["label_ru"] not in GENERIC and t["label_kk"] not in GENERIC}


def test_resolver_keeps_curated_labels_when_r12_has_no_name(curated):
    from ui.civic_heat.targets import TargetResolver

    resolver = TargetResolver()
    lost = []
    for tid, t in curated.items():
        got = resolver.resolve({"kind": t.get("kind") or "area", "id": tid}, None)
        if got and (got.get("label_ru") in GENERIC or got.get("label_kk") in GENERIC):
            lost.append((tid, t["label_ru"], got.get("label_ru"), got.get("label_kk")))
    assert not lost, f"готовые подписи стёрты данными R12 ({len(lost)}), напр. {lost[:3]} — patch r07_registry_labels.patch"
