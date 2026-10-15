"""Фикстура «Календаря работ» R12 (раунд 15): СИНТЕТИЧЕСКИЕ работы служб на НАСТОЯЩИХ улицах Нуры.

    python3 -m engine.civic_geo build-works-fixture [--out data/civic/astana/geo/works_fixture.json]

Работы придуманы (demo: true, на экране «Пример»), улицы и форма — из графа OSM: каждая работа задана улицей и двумя
точками, участок строится только по рёбрам этой улицы (works.segment_on_street) и записывается списком рёбер
`segments` (CONTRACT §5.6). Пока у R06 нет работ v2, а у R02 — демо-мира, календарь в демо-режиме показывает эту фикстуру.

Даты записаны для дня сборки (anchor); календарь сдвигает их на целые годы, если показ позже чем через год.
Нарочные конфликты (для сцены 8 и проверки всех трёх видов):
  01 + 02  ул. Сыганак: асфальт в мае, водопровод в июле на том же участке — dig_after_surface, high («копаем дважды»);
  03 + 04  ул. Кайыма Мухамедханова: теплосеть и электросети на одном участке, 9 дней вместе — same_segment_overlap;
  05 + 06  ул. Айтеке Би и ул. Култегин: перекрытия параллельных улиц одновременно — parallel_closures;
  07 + 08  ул. Е-308: асфальт и газопровод одновременно — same_segment_overlap, high (сначала сети);
  09 + 10  пр. Улы Дала: летом новое покрытие, в ноябре раскопка теплосети рядом — dig_after_surface, medium.
  11 + 12  ул. Акын Сара: сначала водопровод, потом асфальт — правильный порядок, конфликта нет.
  15       двор у ул. Култегин — только точка: «примерное место», без линии.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import names
from .graph import get_graph
from .paths import GEO_DIR
from .works import KIND_LABELS, segment_on_street

ANCHOR = "2026-10-15"
OUT = GEO_DIR / "works_fixture.json"

# (id, служба, вид, статус, начало, конец, улица, точка A, точка B, начало названия ru, kk)
SPEC = (
    ("w-demo-r12-01", "road", "surface", "planned", "2027-05-04", "2027-05-20", "улица Сыганак",
     (71.381544, 51.130024), (71.372275, 51.131209), "Ремонт покрытия", "Жабынды жөндеу"),
    ("w-demo-r12-02", "water", "dig", "planned", "2027-07-20", "2027-08-14", "улица Сыганак",
     (71.381544, 51.130024), (71.372275, 51.131209), "Замена водопровода", "Су құбырын ауыстыру"),
    ("w-demo-r12-03", "heating", "dig", "planned", "2027-06-01", "2027-06-30", "улица Кайыма Мухамедханова",
     (71.383582, 51.140772), (71.390063, 51.139608), "Замена теплотрассы", "Жылу трассасын ауыстыру"),
    ("w-demo-r12-04", "power", "dig", "planned", "2027-06-22", "2027-07-12", "улица Кайыма Мухамедханова",
     (71.383582, 51.140772), (71.390063, 51.139608), "Прокладка кабеля", "Кабель төсеу"),
    ("w-demo-r12-05", "road", "closure", "planned", "2027-08-03", "2027-08-24", "улица Айтеке Би",
     (71.374344, 51.131209), (71.379555, 51.136412), "Перекрытие на время ремонта", "Жөндеу кезінде жабу"),
    ("w-demo-r12-06", "traffic", "closure", "planned", "2027-08-17", "2027-08-31", "улица Култегин",
     (71.372182, 51.131467), (71.373845, 51.135989), "Перекрытие для разметки", "Жол таңбасы үшін жабу"),
    ("w-demo-r12-07", "road", "surface", "planned", "2027-08-02", "2027-08-20", "улица Е-308",
     (71.399944, 51.131949), (71.401721, 51.134546), "Асфальт", "Асфальт"),
    ("w-demo-r12-08", "gas", "dig", "planned", "2027-08-09", "2027-08-27", "улица Е-308",
     (71.399944, 51.131949), (71.401721, 51.134546), "Перекладка газопровода", "Газ құбырын қайта төсеу"),
    ("w-demo-r12-09", "road", "surface", "done", "2026-07-06", "2026-08-14", "проспект Улы Дала",
     (71.389604, 51.100891), (71.393879, 51.100277), "Ремонт покрытия", "Жабынды жөндеу"),
    ("w-demo-r12-10", "heating", "dig", "planned", "2026-11-02", "2026-11-25", "проспект Улы Дала",
     (71.389081, 51.100833), (71.393350, 51.100241), "Ремонт теплосети", "Жылу желісін жөндеу"),
    ("w-demo-r12-11", "water", "dig", "planned", "2027-04-12", "2027-05-14", "улица Акын Сара",
     (71.393568, 51.146966), (71.400477, 51.145927), "Замена водопровода", "Су құбырын ауыстыру"),
    ("w-demo-r12-12", "road", "surface", "planned", "2027-06-01", "2027-06-18", "улица Акын Сара",
     (71.393568, 51.146966), (71.400477, 51.145927), "Асфальт после замены сетей",
     "Желілер ауыстырылғаннан кейін асфальт"),
    ("w-demo-r12-13", "lighting", "lighting", "in_progress", "2026-10-05", "2026-11-10", "улица Хусейн бен Талал",
     (71.391838, 51.083553), (71.398073, 51.082672), "Замена фонарей", "Шамдарды ауыстыру"),
    ("w-demo-r12-14", "landscaping", "landscape", "in_progress", "2026-09-01", "2026-10-30", "улица Е 753",
     (71.370452, 51.137526), (71.374385, 51.136853), "Благоустройство", "Абаттандыру"),
)
# Работа без участка: только точка — «примерное место» (CONTRACT §8: без уверенной линии).
APPROX = (
    {"id": "w-demo-r12-15", "service": "landscaping", "kind": "landscape", "status": "planned",
     "starts_on": "2027-05-15", "ends_on": "2027-06-15", "point": [71.3731, 51.1342],
     "title_ru": "Благоустройство двора у ул. Култегин", "title_kk": "Күлтегін көшесі маңындағы ауланы абаттандыру",
     "district": "nura", "demo": True, "source": "demo"},
)


def build() -> dict:
    g = get_graph()
    works = []
    for wid, service, kind, status, start, end, street, a, b, title_ru, title_kk in SPEC:
        seg = segment_on_street(street, a, b, g)
        e = g.by_id[seg["edge_ids"][0]]
        street_ru, street_kk = names.ru_short(e.name), e.label_kk()
        works.append({
            "id": wid, "service": service, "kind": kind, "status": status, "starts_on": start, "ends_on": end,
            "segments": seg["edge_ids"], "district": "nura",
            "title_ru": f"{title_ru}: {street_ru}", "title_kk": f"{title_kk}: {street_kk}",
            "street": street, "from": list(a), "to": list(b), "length_m": seg["length_m"],
            "demo": True, "source": "demo",
        })
    works.extend(dict(w) for w in APPROX)
    return {
        "schema": "birge-works-v2-fixture/1",
        "anchor": ANCHOR,
        "about": ("СИНТЕТИКА (demo: true, «Пример»): работы и даты придуманы; улицы и форма участков — граф OSM "
                  f"{g.id} ({g.snapshot_at}), рёбра osm-w<way>-<n>. Собрано: python3 -m engine.civic_geo build-works-fixture."),
        "license": "ODbL-1.0 (геометрия OSM), © OpenStreetMap contributors",
        "kinds": {k: {"ru": v[0], "kk": v[1]} for k, v in KIND_LABELS.items()},
        "works": works,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build-works-fixture")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    data = build()
    Path(a.out).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"{len(data['works'])} работ → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
