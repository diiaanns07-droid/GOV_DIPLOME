"""Набор «обращения за ночь» (R02, раунд 15+, поправка П3) — синтетические тексты для «ИИ-разбора пачки» R04 и эталон.

    python3 -m ml.datasets.demo_intake               # data/civic/astana/demo-world/intake_night_v1.json + .gold.json
    python3 -m ml.datasets.demo_intake --check       # пересобрать в памяти и сверить оба файла байт в байт
    python3 -m ml.datasets.demo_intake --summary     # сводка без записи

ВСЁ СИНТЕТИЧЕСКОЕ (demo: true). Настоящие — только места из OpenStreetMap (ODbL), которые даёт карта R12 и уже
использует демо-мир: дворы, остановки, улицы, перекрёстки со светофорами, парк. Сцены демо (остановка «Хан Шатыр»,
двор сцены 7, улица сцены 8, снег в Нуре — сцена 9) в набор не входят: «Создать задачи» не меняет их числа.

Тексты — ml/datasets/demo_intake_texts.py, написаны вручную для этого набора (не synth_v3, на котором учится R04).
Эталон размечен ПРАВИЛАМИ, без прогона моделей R04:
  категория и уточнение — у вида проблемы; службы — таблица Birge (ui/civic_feedback/v2/lifecycle.SERVICE_RULES =
  умолчания R08), две службы — пары CONTRACT §5.1 (как в демо-мире); место — цель карты R12, названная в тексте;
  повторы — одна проблема у одного места (группа); срочность — классы demo_intake_texts.URGENT.
Детерминированно: SEED = 15, без сети, без текущего времени; время приёма — прошлая ночь (day_at, SCHEMA.md §1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from ml.datasets import demo_world_io as wio
from ml.datasets import demo_intake_texts as TX
from ml.datasets.demo_world import street_slots

ROOT = wio.ROOT
OUT_DIR = wio.WORLD_DIR
TEXTS_FILE = OUT_DIR / "intake_night_v1.json"
GOLD_FILE = OUT_DIR / "intake_night_v1.gold.json"
SEARCH_INDEX = ROOT / "web" / "civic" / "map" / "search_index.json"
# Входы чужих путей: другой файл — другие цели и подписи (как inputs мира, demo_world.input_hashes).
INPUTS = (ROOT / "data" / "civic" / "astana" / "geo" / "objects.json", ROOT / "data" / "civic" / "astana" / "geo" / "yards.json",
          SEARCH_INDEX, ROOT / "engine" / "civic_scenarios" / "graphs" / "MANIFEST.json")
SEED = 15
SCHEMA = "birge-intake-night-v1"
GOLD_SCHEMA = "birge-intake-night-gold-v1"
# Ночь: вчера 21:30 — сегодня 07:30 по Астане (минуты от начала окна).
NIGHT_START = (21, 30)
NIGHT_MINUTES = 600
LANG_WEIGHTS = (("ru", 0.44), ("kk", 0.30), ("mixed", 0.16), ("latin", 0.10))
TYPO_SHARE = 0.12

# ---------------------------------------------------------------- места (из мира и карты R12)
# Дворы с названием в OSM (есть в поиске карты); формы — вручную. jk: название несклоняемое («ЖК …»).
YARDS = {
    "yard-1026285033": ("ЖК Grand Champion", "в ЖК Grand Champion", "во дворе ЖК Grand Champion",
                        "Grand Champion ЖК", "Grand Champion ЖК-да", "Grand Champion ЖК ауласында", True, 6),
    "yard-1454510529": ("ЖК «Алтын шар»", "в ЖК «Алтын шар»", "во дворе ЖК «Алтын шар»",
                        "«Алтын шар» ЖК", "«Алтын шар» ЖК-да", "«Алтын шар» ЖК ауласында", True, 4),
    "yard-1460088066": ("ЖК Galamat Towers", "в ЖК Galamat Towers", "во дворе ЖК Galamat Towers",
                        "Galamat Towers ЖК", "Galamat Towers ЖК-да", "Galamat Towers ЖК ауласында", True, 3),
    "yard-1460088061": ("ЖК Alau", "в ЖК Alau", "во дворе ЖК Alau",
                        "Alau ЖК", "Alau ЖК-да", "Alau ЖК ауласында", True, 5),
    "yard-577076055": ("ЖК «Статус»", "в ЖК «Статус»", "во дворе ЖК «Статус»",
                       "«Статус» ЖК", "«Статус» ЖК-да", "«Статус» ЖК ауласында", True, 4),
    "yard-1424189336": ("ЖК Respublika", "в ЖК Respublika", "во дворе ЖК Respublika",
                        "Respublika ЖК", "Respublika ЖК-да", "Respublika ЖК ауласында", True, 8),
    "yard-1460088069": ("ЖК «Научный»", "в ЖК «Научный»", "во дворе ЖК «Научный»",
                        "«Научный» ЖК", "«Научный» ЖК-да", "«Научный» ЖК ауласында", True, 5),
    "yard-257962279": ("микрорайон Жагалау", "в микрорайоне Жагалау", "во дворе дома в микрорайоне Жагалау",
                       "Жағалау шағын ауданы", "Жағалау шағын ауданында", "Жағалау шағын ауданының ауласында", False, 9),
    "yard-1531192452": ("ЖК «Бухар Жырау De Luxe»", "в ЖК «Бухар Жырау De Luxe»", "во дворе ЖК «Бухар Жырау De Luxe»",
                        "«Бұқар Жырау De Luxe» ЖК", "«Бұқар Жырау De Luxe» ЖК-да",
                        "«Бұқар Жырау De Luxe» ЖК ауласында", True, 3),
    "yard-1159981866": ("1-й микрорайон", "в 1-м микрорайоне", "во дворе дома в 1-м микрорайоне",
                        "1-ші шағын аудан", "1-ші шағын ауданда", "1-ші шағын аудан ауласында", False, 12),
    "yard-1222028654": ("ЖК «Акбулак-3»", "в ЖК «Акбулак-3»", "во дворе ЖК «Акбулак-3»",
                        "«Ақбұлақ-3» ЖК", "«Ақбұлақ-3» ЖК-да", "«Ақбұлақ-3» ЖК ауласында", True, 4),
    "yard-1104998691": ("ЖК «Энергетик»", "в ЖК «Энергетик»", "во дворе ЖК «Энергетик»",
                        "«Энергетик» ЖК", "«Энергетик» ЖК-да", "«Энергетик» ЖК ауласында", True, 3),
    "yard-1168876409": ("4-й микрорайон", "в 4-м микрорайоне", "во дворе дома в 4-м микрорайоне",
                        "4-ші шағын аудан", "4-ші шағын ауданда", "4-ші шағын аудан ауласында", False, 14),
}
# Улицы: русская форма «на …» по типу; особые — вручную.
STREET_ON = {"Коргалжинское шоссе": "на Коргалжинском шоссе", "Одесский переулок": "в Одесском переулке"}
STREET_PREFIX = (("улица ", "на улице "), ("проспект ", "на проспекте "), ("переулок ", "в переулке "))
CROSSING_RADIUS_M = 60.0
SAME_CROSSING_M = 150.0
EXCLUDED = {"osm-node-4109037549", "yard-1454082640"}           # сцена 2 (Хан Шатыр), двор сцены 7
EXCLUDED_STREETS = {"улица Баян Сулу"}                           # сцена 8


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def input_hashes() -> dict:
    """sha256 входов карты R12 (объекты, дворы, поиск карты, граф) и мира: набор собирается только на них."""
    out = {str(p.relative_to(ROOT)): _sha(p) for p in INPUTS}
    out[str(wio.world_path().relative_to(ROOT))] = _sha(wio.world_path())
    return out


class Places:
    """Цели и подписи: карта R12 (target_geometry, поиск карты) + демо-мир (какие места в нём есть)."""

    def __init__(self, world: dict):
        sys.path.insert(0, str(ROOT))
        from engine.civic_geo import geo, target_geometry
        from engine.civic_geo.graph import get_graph
        from engine.civic_geo.objects import get_layers
        from ui.civic_heat import geo as heat_geo

        self.target_geometry = target_geometry
        self.haversine_m = geo.haversine_m
        self.graph = get_graph()
        self.signals = sorted((f.id, f.point) for f in get_layers()[0].items if f.kind == "traffic_signal")
        self.district_of = heat_geo.district_of
        self.index = json.loads(SEARCH_INDEX.read_text(encoding="utf-8"))
        self.world_targets: dict[str, dict] = {}
        self.street_segments: dict[tuple[str, str], Counter] = {}
        for c in world["complaints"]:
            t = c["target"]
            self.world_targets.setdefault(t["id"], {"target": t, "district": c["district"], "point": c.get("point")})
            if t["kind"] == "segment":
                e = self.graph.by_id.get(t["id"])
                if e and e.name:
                    self.street_segments.setdefault((e.name, c["district"]), Counter())[t["id"]] += 1
        for y in world["yards"]:
            self.world_targets.setdefault(y["id"], {"target": {"kind": "area", "id": y["id"]}, "district": y["district"]})
        self.streets_kk = {}
        for s in self.index["streets"]:
            self.streets_kk.setdefault(s["ru"], s["kk"])

    def target(self, kind: str, tid: str) -> dict:
        found = self.target_geometry({"kind": kind, "id": tid})
        if not found:
            raise ValueError(f"цель неизвестна карте R12: {tid}")
        out = {"kind": kind, "id": tid, "label_ru": found["label_ru"], "label_kk": found["label_kk"]}
        if found.get("object_kind"):
            out["object_kind"] = found["object_kind"]
        return out

    def _district(self, tid: str) -> str:
        return self.world_targets[tid]["district"]

    def yard(self, yid: str) -> dict:
        if yid in EXCLUDED or yid not in self.world_targets:
            raise ValueError(f"двор не из демо-мира или в сцене: {yid}")
        ru, ru_in, ru_yard, kk, kk_in, kk_yard, jk, blocks = YARDS[yid]
        return {"type": "yard", "target": self.target("area", yid), "accept_ids": [yid], "district": self._district(yid),
                "slots": {"Y": ru, "Yin": ru_in, "Yd": ru_yard, "Yk": kk, "Ykin": kk_in, "Ykd": kk_yard},
                "jk": jk, "blocks": blocks}

    def stop(self, sid: str) -> dict:
        if sid in EXCLUDED or sid not in self.world_targets:
            raise ValueError(f"остановка не из демо-мира или в сцене: {sid}")
        t = self.target("object", sid)
        name_ru = re.search(r"«(.+)»", t["label_ru"]).group(1)
        name_kk = re.search(r"«(.+)»", t["label_kk"]).group(1)
        accept = [sid]
        for o in self.index["objects"]:
            if o["k"] == "bus_stop" and (o["id"] == sid or sid in o.get("also", [])):
                accept = sorted({o["id"], *o.get("also", [])})
                break
        return {"type": "stop", "target": t, "accept_ids": accept, "district": self._district(sid),
                "slots": {"S": name_ru, "Sk": name_kk}}

    def street(self, name: str, district: str) -> dict:
        if name in EXCLUDED_STREETS:
            raise ValueError(f"улица сцены: {name}")
        segs = self.street_segments.get((name, district))
        if not segs:
            raise ValueError(f"улицы нет в демо-мире: {name} ({district})")
        sid = sorted(segs.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        on = STREET_ON.get(name)
        if on is None:
            for pre, prep in STREET_PREFIX:
                if name.startswith(pre):
                    on = prep + name[len(pre):]
                    break
        kk = self.streets_kk.get(name)
        kk_loc = street_slots(None, kk).get("street_kk_loc")
        if not (on and kk and kk_loc):
            raise ValueError(f"нет формы улицы: {name}")
        return {"type": "street", "target": self.target("segment", sid), "accept_ids": [sid], "street_ru": name,
                "district": district, "slots": {"St": name, "Ston": on, "Stk": kk, "Stkl": kk_loc}}

    def crossing(self, sid: str) -> dict:
        t = self.target("object", sid)
        x = t["label_ru"].split("на перекрёстке ", 1)[1]
        xk = t["label_kk"].split(": ", 1)[1]
        if not xk.endswith("қиылысы"):
            raise ValueError(f"нет формы перекрёстка: {sid}")
        # Светофоров нет в поиске карты, а у большого перекрёстка их несколько (у каждого подхода): верен любой светофор
        # с той же подписью R12 не дальше 150 м и участки ДВУХ улиц перекрёстка не дальше 60 м от любого из них.
        point = self.world_targets[sid]["point"]
        same = [(oid, pt) for oid, pt in self.signals if self.haversine_m(pt, point) <= SAME_CROSSING_M
                and self.target_geometry({"kind": "object", "id": oid})["label_ru"] == t["label_ru"]]
        cores = [re.sub(r"^(ул|пр|пер)\.\s*|\s*ш\.$", "", part).strip() for part in x.split(" и ")]
        near = set()
        for _, pt in same:
            near |= {e.id for _, e, _ in self.graph.nearest(
                pt, CROSSING_RADIUS_M, accept=lambda e: bool(e.name) and any(c in e.name for c in cores))}
        others = sorted(oid for oid, _ in same if oid != sid)
        return {"type": "crossing", "target": t, "accept_ids": [sid] + others + sorted(near),
                "district": self._district(sid), "slots": {"X": x, "Xkl": xk + "нда"}}

    def park(self, pid: str, ru: str, ru_in: str, kk: str, kk_loc: str) -> dict:
        return {"type": "park", "target": self.target("object", pid), "accept_ids": [pid], "district": self._district(pid),
                "slots": {"P": ru, "Pin": ru_in, "Pk": kk, "Pkl": kk_loc}}


# ---------------------------------------------------------------- план ночи
# (вид проблемы, место, число текстов, окно: (с, по) в минутах от 21:30 или имя профиля)
def plan(p: Places) -> list[dict]:
    Y, S, St, X = p.yard, p.stop, p.street, p.crossing
    park = p.park("osm-relation-15957444", "парк Астана", "в парке Астана", "Астана саябағы", "Астана саябағында")
    g = [
        # большие повторы: одно место — много людей
        ("heat_off", Y("yard-1026285033"), 40, (130, 600, "late")),     # с 23:40, к утру всё больше
        ("water_off", Y("yard-1454510529"), 24, (460, 600, "late")),    # с 05:10
        ("signal_off", X("osm-node-14162863855"), 13, (160, 600, "even")),
        ("bus_wait", S("osm-node-13915790157"), 14, ((0, 120), (540, 600))),
        ("street_dark", St("улица Сыганак", "nura"), 9, (0, 240, "even")),
        ("bins_full", Y("yard-577076055"), 9, (0, 600, "night")),
        ("shelter_broken", S("osm-node-4107301245"), 6, (0, 600, "night")),
        ("night_noise", Y("yard-1424189336"), 6, (90, 330, "even")),
        ("open_manhole", St("улица Омара Хаяма", "nura"), 5, (0, 600, "night")),
        ("lawn_cars", Y("yard-1460088061"), 5, (0, 600, "night")),
        ("dogs", Y("yard-1460088069"), 5, (0, 600, "night")),
        ("after_digging", St("улица Кайыма Мухамедханова", "nura"), 4, (0, 600, "night")),
        ("gas_smell", Y("yard-1460088066"), 4, (380, 430, "even")),
        ("pole_down", St("проспект Улы Дала", "nura"), 4, (250, 330, "even")),
        ("yard_dark", Y("yard-257962279"), 4, (0, 180, "even")),
        ("sewage", Y("yard-1159981866"), 4, (0, 600, "night")),
        ("bus_wait", S("osm-node-4894180331"), 4, (480, 600, "even")),
        ("pothole", St("улица Жумекена Нажимеденова", "saraishyk"), 4, (0, 600, "night")),
        ("bins_fire", Y("yard-257962279"), 3, (300, 320, "even")),
        ("playground_danger", Y("yard-1460088061"), 3, (0, 150, "even")),
        ("pipe_burst", St("улица Амины Умурзаковой", "nura"), 3, (420, 600, "even")),
        ("road_snow", St("улица Алькея Маргулана", "esil"), 3, (300, 600, "even")),
        ("street_dark", St("улица Айнаколь", "almaty"), 4, (0, 200, "even")),
        ("pothole", St("Коргалжинское шоссе", "nura"), 4, (0, 600, "night")),
        ("bus_wait", S("osm-node-2616721263"), 3, (500, 600, "even")),
        ("entrance_dark", Y("yard-1531192452"), 3, (0, 240, "even")),
        ("bins_full", Y("yard-1222028654"), 3, (0, 600, "night")),
        ("lift", Y("yard-1460088066"), 2, (0, 600, "night")),
        ("yard_dark", Y("yard-1424189336"), 2, (0, 200, "even")),
        ("after_digging", St("улица Сыпатай батыр", "nura"), 2, (0, 600, "night")),
        ("tiles_heating", St("улица Бекет Ата", "nura"), 2, (0, 600, "night")),
        ("lawn_heating", Y("yard-1531192452"), 2, (0, 600, "night")),
        ("sidewalk_ice", St("улица Арай", "esil"), 2, (420, 600, "even")),
        ("dump", St("улица Николая Гоголя", "baikonur"), 2, (0, 600, "night")),
        ("park_dark", park, 2, (0, 150, "even")),
        ("signal_off", X("osm-node-260035229"), 2, (200, 600, "even")),
        ("shelter_broken", S("osm-node-5851574955"), 2, (0, 600, "night")),
        ("bus_wait", S("osm-node-11109477266"), 2, (520, 600, "even")),
        ("sidewalk_cars", St("улица Габита Мусрепова", "almaty"), 2, (0, 600, "night")),
        ("yard_dark", Y("yard-1104998691"), 2, (0, 200, "even")),
        ("road_snow", St("улица Габита Мусрепова", "almaty"), 3, (240, 600, "even")),
        ("sidewalk_ice", St("улица Коксай", "saraishyk"), 2, (400, 600, "even")),
        ("dogs", Y("yard-1104998691"), 2, (0, 600, "night")),
        ("bins_full", Y("yard-1460088061"), 2, (0, 600, "night")),
        ("lawn_cars", Y("yard-1460088066"), 2, (0, 600, "night")),
        ("shelter_broken", S("osm-node-4894180331"), 2, (0, 600, "night")),   # та же остановка, другая проблема
        # одиночные обращения: одна проблема — один человек
        ("pothole", St("улица Е-308", "nura"), 1, None),
        ("pothole", St("улица Виктора Гюго", "nura"), 1, None),
        ("pothole", St("улица Коксай", "saraishyk"), 1, None),
        ("street_dark", St("улица Е-308", "nura"), 1, None),
        ("street_dark", St("улица Уали Халфина", "nura"), 1, None),
        ("street_dark", St("проспект Абылай Хан", "almaty"), 1, None),
        ("street_dark", St("улица Камбар ата", "nura"), 1, None),
        ("after_digging", St("улица Жантай батыр", "nura"), 1, None),
        ("pipe_burst", St("улица Чингиза Айтматова", "nura"), 1, None),
        ("tiles_heating", St("проспект Туран", "nura"), 1, None),
        ("lawn_heating", Y("yard-1168876409"), 1, None),
        ("pothole", St("улица Уали Халфина", "nura"), 1, None),
        ("tiles_heating", St("улица Виктора Гюго", "nura"), 1, None),
        ("entrance_dark", Y("yard-1026285033"), 1, None),                # тот же двор, что без отопления, — другая проблема
        ("lift", Y("yard-1026285033"), 1, None),
        ("bus_wait", S("osm-node-13970789267"), 1, None),
        ("dump", St("Одесский переулок", "baikonur"), 1, None),
        ("sidewalk_cars", St("улица Е-308", "nura"), 1, None),
        ("street_dark", St("улица Чингиза Айтматова", "nura"), 1, None),
        ("signal_off", X("osm-node-1500911786"), 1, None),
        ("bus_wait", S("osm-node-4107301222"), 1, None),
        ("bus_wait", S("osm-node-4166909990"), 1, None),
        ("bus_wait", S("osm-node-10957524217"), 1, None),
        ("bus_wait", S("osm-node-5744091192"), 1, None),
        ("shelter_broken", S("osm-node-4107228575"), 1, None),
        ("shelter_broken", S("osm-node-14006763392"), 1, None),
        ("shelter_broken", S("osm-node-6536624224"), 1, None),
        ("bins_full", Y("yard-1460088069"), 1, None),
        ("bins_full", Y("yard-1104998691"), 1, None),
        ("dump", St("улица Коксай", "saraishyk"), 1, None),
        ("night_noise", Y("yard-1026285033"), 1, None),
        ("night_noise", Y("yard-577076055"), 1, None),
        ("dogs", Y("yard-1222028654"), 1, None),
        ("dogs", Y("yard-1159981866"), 1, None),
        ("lawn_cars", Y("yard-577076055"), 1, None),
        ("lawn_cars", Y("yard-1424189336"), 1, None),
        ("sidewalk_cars", St("проспект Туран", "nura"), 1, None),
        ("entrance_dark", Y("yard-1424189336"), 1, None),
        ("lift", Y("yard-1424189336"), 1, None),
        ("sewage", Y("yard-1168876409"), 1, None),
        ("road_snow", St("проспект Абылай Хан", "almaty"), 1, None),
        ("sidewalk_ice", St("улица Алькея Маргулана", "esil"), 1, None),
        ("park_urns", park, 1, None),
        ("benches", Y("yard-1222028654"), 1, None),
        ("benches", Y("yard-1159981866"), 1, None),
        ("yard_dark", Y("yard-1460088069"), 1, None),
        ("thanks_heat", Y("yard-1460088069"), 1, None),
        ("thanks_heat", Y("yard-1460088061"), 1, None),
        ("question_road", St("улица Сыганак", "nura"), 1, None),
        ("question_road", St("улица Николая Гоголя", "baikonur"), 1, None),
        ("sewage", Y("yard-1104998691"), 1, None),
    ]
    out = []
    for family, place, n, window in g:
        if n <= 0:
            continue
        spec = TX.FAMILIES[family]
        if spec["place"] != place["type"]:
            raise ValueError(f"{family}: место {place['type']}, а вид проблемы ждёт {spec['place']}")
        out.append({"family": family, "place": place, "n": n, "window": window})
    return out


# ---------------------------------------------------------------- латиница, опечатки
_RU_LAT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
           "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
           "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
           "э": "e", "ю": "yu", "я": "ya"}
_KK_LAT = dict(_RU_LAT, **{"ж": "j", "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u", "ү": "u",
                           "һ": "h", "і": "i", "ы": "y", "й": "i", "х": "h", "у": "u"})


def latin(text: str, base: str) -> str:
    """Как пишут с телефона без кириллицы: транслит без диакритики, кавычки «» — без них."""
    table = _KK_LAT if base == "kk" else _RU_LAT
    out = []
    for ch in text.replace("«", "").replace("»", "").replace("—", "-"):
        low = ch.lower()
        if low in table:
            rep = table[low]
            out.append(rep.capitalize() if ch != low and rep else rep)
        else:
            out.append(ch)
    return "".join(out)


_WORD = re.compile(r"[A-Za-zА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]{5,}")


def typos(text: str, rnd: random.Random, protected: list[str]) -> str:
    """1–2 опечатки в словах вне названий мест (пропуск, перестановка, удвоение буквы)."""
    spans = []
    for name in protected:
        for m in re.finditer(re.escape(name), text, flags=re.IGNORECASE):
            spans.append((m.start(), m.end()))
    words = [m for m in _WORD.finditer(text) if not any(a <= m.start() < b for a, b in spans)]
    if not words:
        return text
    chars = list(text)
    for m in sorted(rnd.sample(words, min(len(words), rnd.randint(1, 2))), key=lambda m: -m.start()):
        w = m.group(0)
        j = rnd.randrange(1, len(w) - 1)
        op = rnd.choice(("drop", "swap", "dup"))
        if op == "drop":
            w = w[:j] + w[j + 1:]
        elif op == "swap":
            w = w[:j - 1] + w[j] + w[j - 1] + w[j + 1:]
        else:
            w = w[:j] + w[j] + w[j:]
        chars[m.start():m.end()] = list(w)
    return "".join(chars)


# ---------------------------------------------------------------- время
NIGHT_WEIGHT = (1.6, 1.4, 1.2, 0.9, 0.6, 0.35, 0.25, 0.25, 0.4, 0.9, 1.5)   # по часам от 21:30


def _minute(rnd: random.Random, window) -> int:
    if window is None or window == "night":
        window = (0, NIGHT_MINUTES, "night")
    if isinstance(window[0], tuple):                      # несколько окон
        a, b = rnd.choice(window)
        return rnd.randint(a, b)
    a, b, shape = window
    if shape == "late":                                   # к утру всё больше
        return a + int((b - a) * max(rnd.random(), rnd.random()))
    if shape == "night":
        while True:
            m = rnd.randint(a, b)
            if rnd.random() * 1.6 <= NIGHT_WEIGHT[min(m // 60, len(NIGHT_WEIGHT) - 1)]:
                return m
    return rnd.randint(a, b)


def day_at(minute: int) -> dict:
    total = NIGHT_START[0] * 60 + NIGHT_START[1] + minute
    day = -1 if total < 24 * 60 else 0
    total %= 24 * 60
    return {"day_at": {"day": day, "hour": total // 60, "minute": total % 60}}


def part_of_night(minute: int) -> str:
    """вечер — до полуночи, ночь — до 05:00, утро — после."""
    return "evening" if minute < 150 else "night" if minute < 450 else "morning"


def since_slots(start: int, rnd: random.Random) -> dict:
    """«С какого часа» по началу проблемы — у каждого жителя своя формулировка."""
    t = day_at(start)["day_at"]
    words = TX.SINCE[part_of_night(start)]
    ru = rnd.choice(words["ru"]).format(hm=f"{t['hour']:02d}:{t['minute']:02d}", hw=TX.HOUR_WORDS[t["hour"]])
    return {"since": ru, "sincek": rnd.choice(words["kk"])}


# ---------------------------------------------------------------- сборка
class Builder:
    def __init__(self, seed: int = SEED):
        self.rnd = random.Random(seed)
        self.seen: set[str] = set()

    def lang(self) -> str:
        x, acc = self.rnd.random(), 0.0
        for lang, w in LANG_WEIGHTS:
            acc += w
            if x < acc:
                return lang
        return LANG_WEIGHTS[-1][0]

    def render(self, family: str, place: dict, lang: str, start: int, minute: int, used: Counter) -> tuple[str, dict]:
        spec = TX.FAMILIES[family]
        base = lang if lang != "latin" else ("ru" if self.rnd.random() < 0.6 else "kk")
        pool = spec[base]
        slots = dict(place["slots"])
        rnd = self.rnd
        part = part_of_night(minute)
        closers = TX.CLOSE_URGENT if spec["urgent"] else TX.CLOSE
        for _ in range(60):
            slots.update(since_slots(start, rnd))
            least = min(used[(base, t)] for t in pool)
            tpl = rnd.choice([t for t in pool if used[(base, t)] == least])
            if place["type"] == "yard":
                n = rnd.randint(1, place["blocks"])
                if place["jk"]:
                    slots["b"] = rnd.choice((f"блок {n}", f"{n}-й подъезд", f"блок {n}, подъезд {rnd.randint(1, 4)}"))
                    slots["bk"] = rnd.choice((f"{n}-блок", f"{n}-подъезд"))
                else:
                    slots["b"] = rnd.choice((f"дом {n}", f"дом {n}, {rnd.randint(1, 6)}-й подъезд"))
                    slots["bk"] = f"{n}-үй"
            text = re.sub(r"\s+", " ", tpl.format(**slots)).strip()
            text = text[:1].upper() + text[1:]
            say = "kk" if base == "kk" else "ru"
            if base == "mixed":
                say = rnd.choice(("ru", "kk"))
            if rnd.random() < 0.22 and not text.startswith(TX.GREETINGS):
                text = rnd.choice(TX.OPEN[say][part]) + " " + text
            if rnd.random() < 0.18:
                text = text.rstrip() + " " + rnd.choice(closers[say])
            protected = list(place["slots"].values())
            typo = lang != "latin" and rnd.random() < TYPO_SHARE
            if typo:
                text = typos(text, rnd, protected)
            if lang == "latin":
                text = latin(text, base)
                if rnd.random() < 0.5:
                    text = text.lower()
                if rnd.random() < 0.5:
                    text = text.replace(",", "").replace("!", "").rstrip(".")
                typo = rnd.random() < TYPO_SHARE
                if typo:
                    text = typos(text, rnd, [latin(v, base) for v in protected] + [latin(v, base).lower() for v in protected])
            if text not in self.seen:
                self.seen.add(text)
                used[(base, tpl)] += 1
                return text, {"lang": lang, "base_lang": base if base != "mixed" else "mixed",
                              "script": "latin" if lang == "latin" else "cyrillic", "typos": typo}
        raise RuntimeError(f"не удалось получить новый текст: {family}")

    def render_noaddr(self, family: str, lang: str) -> tuple[str, dict] | None:
        bank = TX.NOADDR[family]
        base = lang if lang != "latin" else ("ru" if "ru" in bank else "kk")
        pool = [t for t in bank.get(base, []) if t not in self.seen and (latin(t, base) if lang == "latin" else t) not in self.seen]
        if not pool:
            return None
        text = self.rnd.choice(pool)
        self.seen.add(text)
        typo = False
        if lang == "latin":
            text = latin(text, base).lower()
            self.seen.add(text)
        return text, {"lang": lang, "base_lang": base, "script": "latin" if lang == "latin" else "cyrillic",
                      "typos": typo}


def _family_labels(family: str) -> dict:
    spec = TX.FAMILIES.get(family) or TX.NOADDR_FAMILIES[family]
    services = [{"id": s, "role": r} for s, r in spec["services"]]
    return {"category": spec["category"], "subtopic": spec["subtopic"], "services": services,
            "two_services": len(services) > 1, "urgent": spec["urgent"] is not None, "urgent_why": spec["urgent"]}


def build(seed: int = SEED, world: dict | None = None) -> tuple[dict, dict]:
    world = world or wio.load_world()
    places = Places(world)
    b = Builder(seed)
    rows = []                                   # (minute, text, meta, group_key)
    groups = []
    for gi, item in enumerate(plan(places)):
        family, place, n, window = item["family"], item["place"], item["n"], item["window"]
        start = _minute(b.rnd, window) if n == 1 else (window[0][0] if isinstance(window[0], tuple) else window[0])
        used: Counter = Counter()
        minutes = sorted(_minute(b.rnd, window) for _ in range(n)) if n > 1 else [start]
        key = f"{family}:{place['target']['id']}"
        groups.append({"key": key, "family": family, "place": place})
        for m in minutes:
            text, meta = b.render(family, place, b.lang(), start, m, used)
            rows.append((m, text, meta, key))
    # без места: каждый текст — своя задача («адрес уточнить»)
    for family in sorted(TX.NOADDR):
        bank = TX.NOADDR[family]
        for lang in ("ru", "kk", "mixed"):
            for _ in bank.get(lang, []):
                want = lang
                if lang == "ru" and b.rnd.random() < 0.2:
                    want = "latin"
                got = b.render_noaddr(family, want if want != "mixed" else "mixed")
                if not got:
                    continue
                text, meta = got
                key = f"{family}:none:{len(rows)}"
                groups.append({"key": key, "family": family, "place": None})
                rows.append((_minute(b.rnd, None), text, meta, key))
    rows.sort(key=lambda r: (r[0], r[1]))
    ids = {}
    items, gold_items = [], []
    for i, (m, text, meta, key) in enumerate(rows, 1):
        tid = f"night-{i:03d}"
        ids.setdefault(key, []).append(tid)
        items.append({"id": tid, "text": text, "lang": meta["lang"], "received": day_at(m), "demo": True})
        gold_items.append({"id": tid, "group": key, **meta})
    # группы: номер по первому тексту
    order = sorted(groups, key=lambda g: ids[g["key"]][0])
    gid = {g["key"]: f"g-{k:03d}" for k, g in enumerate(order, 1)}
    gold_groups = []
    for g in order:
        labels = _family_labels(g["family"])
        place = g["place"]
        if place is None:
            district = (TX.NOADDR_FAMILIES.get(g["family"]) or {}).get("district")
            gplace = {"type": "district" if district else "none", "target": None, "accept_ids": [], "district": district,
                      "mentions": []}
        else:
            gplace = {"type": place["type"], "target": place["target"], "accept_ids": place["accept_ids"],
                      "district": place["district"], "mentions": sorted(set(place["slots"].values()))}
            if place.get("street_ru"):
                gplace["street_ru"] = place["street_ru"]
        gold_groups.append({"id": gid[g["key"]], "family": g["family"], **labels, "place": gplace,
                            "no_address": place is None, "text_ids": ids[g["key"]]})
    by_key = {g["key"]: gg for g, gg in zip(order, gold_groups)}
    for it in gold_items:
        gg = by_key[it.pop("group")]
        it.update({"group": gg["id"], "category": gg["category"], "subtopic": gg["subtopic"],
                   "services": gg["services"], "two_services": gg["two_services"],
                   "place_type": gg["place"]["type"], "target_id": (gg["place"]["target"] or {}).get("id"),
                   "no_address": gg["no_address"], "urgent": gg["urgent"], "urgent_why": gg["urgent_why"]})
    texts = {
        "schema": SCHEMA, "schema_version": "1.0", "synthetic": True, "demo": True, "seed": seed,
        "generator": "ml/datasets/demo_intake.py (R02, раунд 15+, поправка П3)",
        "world": {"schema": world.get("schema"), "file": "data/civic/astana/demo-world/world_v1.json",
                  "sha256": _sha(wio.world_path())},
        "inputs": input_hashes(),
        "note_ru": ("Синтетические обращения жителей «за ночь» для «ИИ-разбора пачки» (сцена 0): ru / kk / вперемешку / "
                    "латиница, с опечатками и повторами. Места — дворы, остановки, улицы, перекрёстки и парк демо-мира "
                    "(OpenStreetMap через карту R12). Форма — по контракту R04 (INTEGRATION R04 п. 9.4): texts — то, что "
                    "разбирает экран; gold — краткий эталон для оценки (экрану не показывать). Полный эталон с группами, "
                    "местами и правилами — intake_night_v1.gold.json, оценщик — ml/datasets/demo_intake_eval.py."),
        "night": {"from": day_at(0), "to": day_at(NIGHT_MINUTES),
                  "note_ru": "время приёма — прошлая ночь (day_at); ml.datasets.demo_world_io.materialize(texts, now)"},
        "limits": {"texts": len(items), "max_texts_per_batch": 500, "max_bytes_per_batch": 300_000},
        "texts": items,
        "gold": [{"id": it["id"], "category": it["category"], "subtopic": it["subtopic"],
                  "services": [x["id"] for x in it["services"]], "target_id": it["target_id"], "group": it["group"],
                  "urgent": it["urgent"], "urgent_why": it["urgent_why"], "place_type": it["place_type"],
                  "no_address": it["no_address"]} for it in gold_items],
    }
    texts_bytes = dump(texts).encode("utf-8")
    gold = {
        "schema": GOLD_SCHEMA, "schema_version": "1.0", "synthetic": True, "demo": True, "seed": seed,
        "for": {"file": "data/civic/astana/demo-world/intake_night_v1.json",
                "sha256": hashlib.sha256(texts_bytes).hexdigest()},
        "generator": "ml/datasets/demo_intake.py (R02, раунд 15+, поправка П3)",
        "labeling_ru": {
            "who": "R02 — правилами генератора, без прогона моделей R04 и без подгонки под их ответы",
            "category": "категория и уточнение categories_v2 (research/round-14/categories_v2.json) — у вида проблемы",
            "services": ("таблица Birge ui/civic_feedback/v2/lifecycle.SERVICE_RULES (= умолчания R08); две службы — пары "
                         "CONTRACT §5.1, как в демо-мире: вода+дорога (раскоп, порыв трубы), теплосеть+дорога (плитка), "
                         "теплосеть+озеленение (газон), электросети+освещение (опора с проводами); role lead | support"),
            "place": ("цель карты R12, названная в тексте: двор (area), остановка (object, accept_ids — все стороны остановки "
                      "из поиска карты), участок улицы (segment; засчитывать любой участок той же улицы — street_ru), "
                      "перекрёсток со светофором (object; accept_ids — любой светофор этого перекрёстка с той же подписью R12 "
                      "≤ 150 м и участки двух его улиц ≤ 60 м от них), "
                      "парк (object); type none — места в тексте нет, district — назван только район: верный ответ — "
                      "«адрес уточнить»"),
            "group": ("повторы: одна проблема у одного места — одна группа (одна задача); тексты без места — каждый своя "
                      "группа; одно место с разными проблемами — разные группы"),
            "urgent": {k: v for k, v in TX.URGENT.items()},
            "hard_cases": ("благодарность за отопление (other), вопрос о сроке ремонта (other), опасные слова без срочного "
                           "класса (светофор, стекло павильона), латиница, «Бухар Жырау» вместо «Бұқар Жырау» на карте"),
        },
        "summary": summarize(gold_items, gold_groups),
        "groups": gold_groups,
        "items": gold_items,
    }
    return texts, gold


def summarize(items: list[dict], groups: list[dict]) -> dict:
    lead = {s["id"] for g in groups for s in g["services"] if s["role"] == "lead"}
    every = {s["id"] for g in groups for s in g["services"]}
    urgent = [g for g in groups if g["urgent"]]
    two = [g for g in groups if g["two_services"]]
    return {
        "texts": len(items), "groups": len(groups), "merged": len(items) - len(groups),
        "groups_with_repeats": sum(1 for g in groups if len(g["text_ids"]) > 1),
        "largest_group": max(len(g["text_ids"]) for g in groups),
        "services_lead": len(lead), "services_all": len(every),
        "urgent_groups": len(urgent), "urgent_texts": sum(len(g["text_ids"]) for g in urgent),
        "urgent_by_class": dict(sorted(Counter(g["urgent_why"] for g in urgent).items())),
        "two_service_groups": len(two), "two_service_texts": sum(len(g["text_ids"]) for g in two),
        "no_address_texts": sum(1 for i in items if i["no_address"]),
        "place_types": dict(sorted(Counter(g["place"]["type"] for g in groups).items())),
        "place_texts": dict(sorted(Counter(i["place_type"] for i in items).items())),
        "langs": dict(sorted(Counter(i["lang"] for i in items).items())),
        "latin_base": dict(sorted(Counter(i["base_lang"] for i in items if i["lang"] == "latin").items())),
        "typos": sum(1 for i in items if i["typos"]),
        "districts": dict(sorted(Counter(g["place"]["district"] or "—" for g in groups).items())),
        "categories": dict(sorted(Counter(i["category"] for i in items).items())),
    }


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="demo_intake", description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="пересобрать в памяти и сверить с файлами")
    ap.add_argument("--summary", action="store_true", help="сводка без записи")
    a = ap.parse_args(argv)
    texts, gold = build()
    out_t, out_g = dump(texts), dump(gold)
    if a.summary:
        print(json.dumps(gold["summary"], ensure_ascii=False, indent=1))
        return 0
    if a.check:
        if TEXTS_FILE.exists():
            recorded = json.loads(TEXTS_FILE.read_text(encoding="utf-8")).get("inputs") or {}
            now = input_hashes()
            other = sorted(k for k in recorded if recorded[k] != now.get(k))
            if other:
                print("набор собран на других входах (данные карты R12 или мир): " + ", ".join(other) +
                      " — сверка байт в байт возможна только на тех же входах (сборка R01 FINAL-5 и новее)")
                return 2
        ok = True
        for path, body in ((TEXTS_FILE, out_t), (GOLD_FILE, out_g)):
            same = path.exists() and path.read_text(encoding="utf-8") == body
            ok &= same
            print(("OK: " if same else "ОТЛИЧАЕТСЯ: ") + str(path))
        return 0 if ok else 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TEXTS_FILE.write_text(out_t, encoding="utf-8")
    GOLD_FILE.write_text(out_g, encoding="utf-8")
    s = gold["summary"]
    print(f"{TEXTS_FILE.relative_to(ROOT)}: {s['texts']} текстов, {len(out_t.encode('utf-8'))} байт")
    print(f"{GOLD_FILE.relative_to(ROOT)}: групп {s['groups']}, повторов {s['merged']}, срочных групп {s['urgent_groups']}, "
          f"двух служб {s['two_service_groups']}, без адреса {s['no_address_texts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
