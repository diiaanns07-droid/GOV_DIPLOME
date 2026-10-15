"""Генератор демо-мира Астаны (R02, раунд 15) — один согласованный синтетический набор для всех разделов.

    python3 -m ml.datasets.demo_world                 # data/civic/astana/demo-world/world_v1.json + sample + EXPECTED
    python3 -m ml.datasets.demo_world --check         # пересобрать в памяти и сверить sha256 с файлом (воспроизводимость)
    python3 -m ml.datasets.demo_world --summary       # сводка без записи

ВСЁ СИНТЕТИЧЕСКОЕ (demo: true): жалобы, «Я тоже», статусы, работы, идеи, инициативы, кризис, встречи, вопросы.
Настоящие — только цели из OpenStreetMap (ODbL), которые даёт карта R12: остановки, площадки, дворы, участки улиц
(рёбра пешеходного графа). Тексты жителей — шаблоны R02 (ml/datasets/synth_v3/templates.py), слоты улиц и остановок
заполнены названием САМОЙ цели, чтобы текст не спорил с местом на карте.

Детерминированно: SEED = 15, без сети, без текущего времени. Время в мире относительное («30 ч назад», «через 2 дня»,
SCHEMA.md §1); абсолютным его делает ml/datasets/demo_world_io.materialize(world, now) при засеве.

Модель жизни жалобы (почему числа правдоподобны):
  проблема у цели («нить»: цель × категория × вид проблемы) появляется в момент первой жалобы; пока она не исправлена,
  о ней пишут ещё люди (отдельные жалобы и «Я тоже»); служба принимает, берёт в работу и исправляет СРАЗУ ВСЮ нить
  (одна яма — один ремонт). Сроки — по службам (SERVICE_PACE); у части нитей служба опаздывает — отсюда просрочки.
  После «исправлено» жители проверяют: часть «Да» (проверено жителями), редко «Проблема осталась» (вернули в работу).
Ритмы: неделя (пик в понедельник), сутки (утро и вечер), сезон (август → октябрь: пыль летом, свет и отопление осенью),
снег — только в эпизоды: «первый снег», «утренний гололёд» и «Буран в Нуре» (последние 3 дня, сцена 9).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from ml.datasets import demo_world_io as wio
from ml.datasets.synth_v3 import slots as S
from ml.datasets.synth_v3.build import PLACE_FIXES, alternatives, tidy, typos
from ml.datasets.synth_v3.templates import T

ROOT = wio.ROOT
OUT_DIR = wio.WORLD_DIR
CATEGORIES_JSON = ROOT / "research" / "round-14" / "categories_v2.json"
R07_TARGETS = ROOT / "ui" / "civic_heat" / "fixtures" / "targets_demo.json"
YARDS_JSON = ROOT / "data" / "civic" / "astana" / "geo" / "yards.json"
OBJECTS_JSON = ROOT / "data" / "civic" / "astana" / "geo" / "objects.json"
GRAPH_MANIFEST = ROOT / "engine" / "civic_scenarios" / "graphs" / "MANIFEST.json"
NURA_REAL_CSV = ROOT / "data" / "civic" / "astana" / "nura-real" / "records.csv"

SEED = 15
SCHEMA_VERSION = "1.0.1"
WINDOW_DAYS = 60
MODEL_VERSION = "demo-world-v1"
# Опорный момент для EXPECTED.json (сборка B1 R01 — 16 окт 14:00; берём полдень того же дня).
REFERENCE_NOW = "2026-10-16T12:00:00+05:00"

DISTRICTS = ("nura", "esil", "almaty", "saryarka", "baikonur", "saraishyk")
DISTRICT_NAMES = {"nura": ("Нура", "Нұра"), "esil": ("Есиль", "Есіл"), "almaty": ("Алматы", "Алматы"),
                  "saryarka": ("Сарыарка", "Сарыарқа"), "baikonur": ("Байконур", "Байқоңыр"),
                  "saraishyk": ("Сарайшык", "Сарайшық")}
# Доля жалоб по районам (кроме сцен и эпизодов снега): Нура — главный район демо (~35 % всех жалоб).
DISTRICT_SHARE = {"nura": 0.33, "esil": 0.19, "almaty": 0.13, "saryarka": 0.13, "baikonur": 0.12, "saraishyk": 0.10}
# Обычный поток без снега: ~10,5 жалобы в день по городу.
BASE_PER_DAY = 10.5
# Доли категорий в обычном потоке (без снега), до сезонных множителей.
CATEGORY_SHARE = {"roads": 0.15, "sidewalks": 0.08, "transport": 0.11, "lighting": 0.12, "yards": 0.11,
                  "waste": 0.10, "utilities": 0.10, "smell_air": 0.05, "noise_safety": 0.06, "parking": 0.08,
                  "other": 0.04}
WEEKDAY = (1.35, 1.10, 1.0, 1.0, 0.95, 0.72, 0.68)                    # пн … вс
HOURS = (0.25, 0.15, 0.1, 0.1, 0.15, 0.3, 0.7, 1.4, 2.0, 2.0, 1.6, 1.3, # 0 … 11 ч
         1.2, 1.2, 1.1, 1.1, 1.2, 1.5, 1.8, 1.9, 1.7, 1.3, 0.9, 0.5)  # 12 … 23 ч
LANGS = (("ru", 0.5), ("kk", 0.3), ("mixed", 0.2))

# ---------------------------------------------------------------- виды проблем (семейства шаблонов R02)
# семейство -> (уточнение categories_v2 | None, вид цели, вес в категории)
# Вид цели: road — участок проезжей части; foot — тротуар/дорожка (или проезжая часть, если тротуара нет рядом);
# stop — остановка OSM; signal — светофор OSM; yard — двор; playground — детская площадка; park — парк; waste — место
# для мусора; cell — ячейка «примерное место» (запахи, шум без точного места).
FAMILIES = {
    "roads": {"pothole": ("pothole", "road", 5), "after_digging": ("pothole", "road", 2), "marking": ("marking", "road", 1),
              "traffic_light": ("traffic_light_broken", "signal", 1.5), "speed_bump": ("speed_bump", "road", 0.7),
              "road_water": (None, "road", 0.8), "yard_drive": ("pothole", "yard", 1.2)},
    "snow_ice": {"road_snow": ("snow_not_cleared", "road", 3), "sidewalk_ice": ("ice", "foot", 3),
                 "yard_snow": ("snow_not_cleared", "yard", 3), "stop_ice": ("ice", "stop", 1.5),
                 "snow_dumped": ("snow_not_cleared", "yard", 0.6), "no_sand": ("ice", "road", 1),
                 "icicles": ("icicles", "yard", 0.4)},
    "sidewalks": {"tiles": ("broken_sidewalk", "foot", 4), "ramp": ("accessibility", "foot", 1.2),
                  "sidewalk_water": (None, "foot", 1), "no_sidewalk": (None, "road", 0.8), "fence": (None, "foot", 0.6)},
    "transport": {"pavilion": ("stop_shelter", "stop", 2), "no_shelter": ("stop_shelter", "stop", 1),
                  "stop_bench": ("stop_shelter", "stop", 1), "interval": ("schedule", "stop", 2.5),
                  "board": ("schedule", "stop", 0.8), "skips_stop": ("route", "stop", 1),
                  "stop_moved": ("route", "stop", 0.4)},
    "lighting": {"lamps_off": ("lamp_off", "road", 4), "dark_yard": ("dark_yard", "yard", 3), "flicker": ("blinking", "road", 1),
                 "day_burning": (None, "road", 0.6), "park_dark": ("lamp_off", "park", 1), "stop_dark": ("lamp_off", "stop", 1)},
    "yards": {"playground": ("playground", "playground", 4), "benches": ("benches", "yard", 2), "trees": ("trees_lawn", "yard", 1.5),
              "dry_tree": ("trees_lawn", "yard", 1), "lawn": ("trees_lawn", "yard", 1), "improvement": (None, "yard", 1)},
    "waste": {"bins_full": ("bins_full", "waste", 4), "urns_full": ("bins_full", "park", 1), "illegal_dump": ("dump", "yard", 1.5),
              "construction": ("dump", "yard", 0.7), "schedule": ("not_collected", "yard", 1.2)},
    "utilities": {"heating": ("no_heating", "yard", 4), "water": ("no_water", "yard", 2), "sewer": ("sewage", "yard", 1.2),
                  "pipe_burst": ("no_water", "road", 0.8), "entrance_light": ("power_building", "yard", 0.8),
                  "lift": (None, "yard", 0.8)},
    "smell_air": {"smoke": ("smoke_fire", "cell", 2), "dust": ("dust", "cell", 2), "stench": ("bad_smell", "cell", 1.5),
                  "plant": ("bad_smell", "cell", 0.6)},
    "noise_safety": {"night_construction": ("noise_night", "yard", 2), "stray_dogs": ("stray_dogs", "yard", 2),
                     "open_manhole": ("dangerous_place", "road", 1), "abandoned": ("dangerous_place", "yard", 0.6),
                     "racing": ("noise_night", "road", 0.8), "no_crossing": ("dangerous_place", "road", 0.8)},
    "parking": {"on_lawn": ("yard_cars", "yard", 3), "blocked_exit": ("yard_cars", "yard", 1.2),
                "on_sidewalk": ("sidewalk_parking", "foot", 1.5), "need_parking": ("no_spaces", "yard", 1),
                "on_stop": ("sidewalk_parking", "stop", 0.6), "abandoned_car": (None, "yard", 0.5)},
    "other": {"question_deadline": (None, "yard", 1), "services": (None, "yard", 0.6), "proposal": (None, "yard", 1),
              "thanks": (None, "yard", 0.8)},
}
# Слоты, которые мир не умеет заполнить правдиво (номер автобуса, вторая улица): такие шаблоны не берём.
SKIP_SLOTS = {"bus", "street2", "street2_kk"}

# ---------------------------------------------------------------- службы (CONTRACT §3)
# Темп службы: (ответ, ч: от–до), (взять в работу после ответа, ч), (исправить от первой жалобы, сут), доля «опаздывает».
SERVICE_PACE = {
    "road": ((2, 30), (4, 72), (4, 16), 0.10), "traffic": ((1, 12), (2, 24), (1, 6), 0.06),
    "street_cleaning": ((0.5, 10), (1, 12), (0.6, 3), 0.08), "transport": ((2, 30), (6, 72), (3, 14), 0.12),
    "lighting": ((1, 20), (3, 30), (1.5, 6), 0.08), "landscaping": ((4, 40), (12, 96), (6, 20), 0.12),
    "greenery": ((4, 40), (12, 96), (5, 18), 0.10), "waste": ((1, 12), (1, 10), (0.5, 2.5), 0.06),
    "utilities": ((1, 16), (2, 24), (1, 6), 0.08), "heating": ((0.5, 8), (1, 10), (0.4, 3), 0.06),
    "water": ((0.5, 10), (1, 12), (0.5, 4), 0.06), "power": ((0.5, 8), (1, 8), (0.3, 2), 0.05),
    "gas": ((0.2, 2), (0.3, 3), (0.1, 1), 0.0), "housing": ((2, 30), (6, 48), (2, 9), 0.10),
    "ecology": ((2, 30), (12, 96), (3, 12), 0.10), "emergency": ((0.2, 2), (0.3, 3), (0.2, 1.5), 0.0),
    "police": ((1, 24), (4, 48), (1, 7), 0.08), "animals": ((2, 24), (6, 48), (2, 8), 0.10),
    "parking": ((4, 40), (12, 96), (3, 14), 0.12), "akimat": ((4, 48), (24, 120), (6, 20), 0.12),
}
# Совместные проблемы (CONTRACT §5.1): семейство -> (ведущая, участвующая, причина передачи ru)
JOINT = {
    "after_digging": ("water", "road", "Сначала Водоканал закрывает работы на трубе, затем дорожники восстанавливают асфальт"),
    "pipe_burst": ("water", "road", "Порыв на трубе под дорогой: сначала ремонт трубы, потом покрытие"),
    "tiles": ("heating", "road", "Плитку разобрали при ремонте теплотрассы — сначала Теплосеть закрывает работы"),
    "sewer": ("water", "housing", "Засор в наружной сети — Водоканал, во дворе — управляющая компания"),
    "trees": ("greenery", "landscaping", "Деревья — озеленение, восстановление газона — благоустройство"),
    "construction": ("waste", "akimat", "Вывоз строительного мусора, а нарушителя установит аппарат акима"),
}
JOINT_SHARE = 0.055

# Синтетические отображаемые имена «старших по двору» (одно слово, не реальные люди).
CAPTAINS = ("Айгуль", "Сауле", "Ерлан", "Динара", "Марат", "Гульнар", "Асель", "Нурлан", "Жанар", "Олжас",
            "Ботагоз", "Тимур", "Алия", "Данияр")


# ---------------------------------------------------------------- маленькие помощники
def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return None


def _r(x: float, nd: int = 2) -> float:
    return round(float(x), nd)


def ago_h(hours: float) -> dict:
    """Относительное время «hours часов назад» (SCHEMA §1). Отрицательное нельзя — это ошибка генератора."""
    if hours < 0:
        raise ValueError(f"время в будущем: {hours}")
    return {"ago_hours": _r(hours)}


def weighted(rnd: random.Random, items, weights):
    total = sum(weights)
    x = rnd.random() * total
    for item, w in zip(items, weights):
        x -= w
        if x <= 0:
            return item
    return items[-1]


def lang_pick(rnd: random.Random) -> str:
    return weighted(rnd, [l for l, _ in LANGS], [w for _, w in LANGS])


# ---------------------------------------------------------------- входные данные (только чтение)
class Inputs:
    """Цели из карты R12 (OSM) по районам и видам; подписи — через engine.civic_geo.target_geometry."""

    def __init__(self):
        sys.path.insert(0, str(ROOT))
        from engine.civic_geo import target_geometry
        from engine.civic_geo.graph import get_graph
        from engine.civic_geo.objects import get_layers
        from engine.civic_geo.targets import _street_near
        from ui.civic_feedback.v2 import lifecycle
        from ui.civic_heat import geo as heat_geo

        self.target_geometry = target_geometry
        self.graph = get_graph()
        self._street_near = _street_near
        self.lifecycle = lifecycle
        self.district_of = heat_geo.district_of
        self.categories = json.loads(CATEGORIES_JSON.read_text(encoding="utf-8"))
        self.subtopics = {c["id"]: {s["id"] for s in c.get("subtopics", [])} for c in self.categories["categories"]}
        objects, yards, cells = get_layers()
        self.cells = cells
        self.pools: dict[tuple[str, str], list[str]] = {}
        self.info: dict[str, dict] = {}
        for f in sorted(yards.by_id.values(), key=lambda x: x.id):
            d = self.district_of(f.point)
            if d:
                self._add(d, "yard", f.id, {"kind": "area", "point": list(f.point), "name_ru": f.name_ru})
        kind_map = {"bus_stop": "stop", "playground": "playground", "park": "park", "waste": "waste",
                    "traffic_signal": "signal"}
        for f in sorted(objects.by_id.values(), key=lambda x: x.id):
            if f.kind not in kind_map:
                continue
            if f.kind == "bus_stop" and not f.name_ru:
                continue  # остановка без названия: житель не напишет «на остановке …», а шаблоны R02 его требуют
            d = self.district_of(f.point)
            if d:
                self._add(d, kind_map[f.kind], f.id, {"kind": "object", "point": list(f.point),
                                                       "name_ru": f.name_ru, "name_kk": f.name_kk})
        # Участки улиц: только рёбра с названием (иначе «Участок улицы» без имени — непонятно жителю), длиной ≥ 25 м.
        for e in sorted(self.graph.by_id.values(), key=lambda x: x.idx):
            if not e.name or e.length_m < 25 or e.group not in ("road", "foot"):
                continue
            if e.group == "foot" and not e.name.lower().startswith(_STREET_TYPES_RU):
                continue  # «Лыжероллерная трасса», «Аллея …» — не тротуар улицы; жалобы на тротуар — у улиц
            mid = e.geometry[len(e.geometry) // 2]
            d = self.district_of(mid)
            if d:
                self._add(d, "road" if e.group == "road" else "foot", e.id,
                          {"kind": "segment", "point": [mid[0], mid[1]], "name_ru": e.name, "name_kk": e.name_kk,
                           "way": e.way_id})
        self.r07_targets = json.loads(R07_TARGETS.read_text(encoding="utf-8"))["targets"]

    def _add(self, district: str, kind: str, tid: str, info: dict) -> None:
        self.pools.setdefault((district, kind), []).append(tid)
        self.info[tid] = info

    def label(self, kind: str, tid: str) -> dict:
        """{kind, id, label_ru, label_kk, object_kind?} — подписи с карты R12 (как увидит карточка)."""
        found = self.target_geometry({"kind": kind, "id": tid})
        if not found:
            raise ValueError(f"цель неизвестна карте R12: {tid}")
        target = {"kind": kind, "id": tid, "label_ru": found["label_ru"], "label_kk": found["label_kk"]}
        if kind == "object" and found.get("object_kind"):
            target["object_kind"] = found["object_kind"]
        if found.get("approximate"):
            target["approximate"] = True
        return target

    def geometry(self, kind: str, tid: str) -> dict:
        return self.target_geometry({"kind": kind, "id": tid})

    def street_of(self, tid: str) -> tuple[str | None, str | None]:
        info = self.info.get(tid) or {}
        if info.get("kind") == "segment":
            return info.get("name_ru"), info.get("name_kk")
        point = info.get("point")
        if point is None:
            return None, None
        return self._street_near(self.graph, point)


# ---------------------------------------------------------------- тексты жителей
_STREET_TYPES_RU = ("улица ", "проспект ", "переулок ", "шоссе ", "бульвар ", "площадь ", "набережная ")


def street_slots(name_ru: str | None, name_kk: str | None) -> dict:
    """Слоты улицы для шаблонов R02 из НАСТОЯЩЕГО названия цели. Подходит не всякое название:
    «На улице {street}» годится только для «улица …» (или названия без типа); казахский местный падеж — по окончанию."""
    out = {}
    if name_ru:
        low = name_ru.lower()
        if low.startswith("улица "):
            out["street"] = name_ru[len("улица "):]
        elif not low.startswith(_STREET_TYPES_RU):
            out["street"] = name_ru
    if name_kk:
        for tail, loc in (("көшесі", "көшесінде"), ("даңғылы", "даңғылында"), ("тас жолы", "тас жолында")):
            if name_kk.endswith(tail):
                out["street_kk"] = name_kk
                out["street_kk_loc"] = name_kk[: -len(tail)] + loc
                break
    return out


def stop_slots(target: dict, info: dict) -> dict:
    name_ru = info.get("name_ru")
    if not name_ru:
        return {}
    name_kk = info.get("name_kk") or name_ru
    return {"stop": f"«{name_ru}»", "stop_kk": f"«{name_kk}»"}


_SLOT = re.compile(r"\{(\w+)\}")
_PHONE = re.compile(r"(\+?\d[\d\s\-()]{8,}\d)")


# Шаблоны раунда 15 там, где у synth_v3 все варианты с номером маршрута ({bus}) — номер не придумываем.
WORLD_TEMPLATES = (
    ("w15-int-ru1", "transport", "ru", "interval", "colloquial",
     "Автобусы до остановки {stop} ходят [раз в 40 минут|очень редко|раз в час], люди [мёрзнут|опаздывают на работу]."),
    ("w15-int-ru2", "transport", "ru", "interval", "official",
     "Прошу увеличить число автобусов через остановку {stop}: интервал [больше получаса|не соблюдается]."),
    ("w15-int-kk1", "transport", "kk", "interval", "colloquial",
     "{stop_kk} аялдамасына автобустар [сирек келеді|40 минутта бір келеді], адамдар тоңады."),
    ("w15-int-mx1", "transport", "mixed", "interval", "colloquial",
     "Автобустар {stop_kk} аялдамасына [очень редко ходят|раз в час приходят], тоңып тұрамыз."),
)


class Texts:
    """Шаблоны R02 по (категория, семейство, язык); слоты места — из цели, остальное — нейтрально."""

    def __init__(self):
        self.by_family: dict[tuple[str, str], list[tuple]] = {}
        for tpl in list(T) + [t + (False,) for t in WORLD_TEMPLATES]:
            tid, cat, lang, family, register, text, _hard = tpl
            if register == "short" or _SLOT.findall(text) and set(_SLOT.findall(text)) & SKIP_SLOTS:
                continue
            self.by_family.setdefault((cat, family), []).append(tpl)

    def render(self, rnd: random.Random, cat: str, family: str, lang: str, values: dict) -> tuple[str, str] | None:
        """-> (текст, язык) или None — нет шаблона, который можно заполнить правдиво."""
        pool = self.by_family.get((cat, family), [])
        # нет шаблона на нужном языке — сначала другой «казахский» вариант (kk ↔ смесь), русский — последним
        langs = [lang] + [l for l in ("mixed", "kk") if l != lang] + ([] if lang == "ru" else ["ru"])
        for want in langs:
            fits = [t for t in pool if t[2] == want and set(_SLOT.findall(t[5])) <= set(values)]
            if fits:
                tpl = fits[rnd.randrange(len(fits))]
                text = alternatives(tpl[5], rnd).format(**values)
                for rx, repl in PLACE_FIXES:
                    text = rx.sub(repl, text)
                text = tidy(text)
                if tpl[4] in ("official", "colloquial") and rnd.random() < 0.3:
                    pre, suf = S.FRAME.get(("kk" if want == "kk" else "ru", tpl[4]), ((), ()))
                    head = rnd.choice(pre) if pre else ""
                    if head.endswith((":", ",")) and text[1:2].islower():
                        text = text[:1].lower() + text[1:]   # «Довожу до вашего сведения: прошу …»
                    text = tidy(" ".join(x for x in (head, text, rnd.choice(suf) if suf else "") if x))
                if rnd.random() < 0.08 and want != "kk":
                    text = tidy(typos(text, rnd))
                return text, want
        return None


def text_values(rnd: random.Random, inputs: Inputs, kind_of_target: str, tid: str, district: str,
                event: bool) -> dict:
    """Слоты шаблона: место пустое (цель видно на карте), улица и остановка — настоящие, время — к месту."""
    values = {"place": "", "Place": "", "place_kk": "", "Place_kk": ""}
    d_ru, d_kk = DISTRICT_NAMES[district]
    values.update({"district": d_ru, "district_kk": d_kk})
    if event:
        t_ru, t_kk = rnd.choice((("", ""), ("который день", "бірнеше күннен бері"), ("третий день", "үш күннен бері"),
                                 ("", "")))
    else:
        t_ru, t_kk = rnd.choice(S.TIMES)
    values.update({"time": t_ru, "time_kk": t_kk})
    info = inputs.info.get(tid, {})
    if kind_of_target == "stop":
        values.update(stop_slots({}, info))
    name_ru, name_kk = inputs.street_of(tid)
    values.update(street_slots(name_ru, name_kk))
    return values


# ---------------------------------------------------------------- нити и жалобы
class Thread:
    """Одна проблема у одной цели: все жалобы о ней закрывает один ремонт."""

    __slots__ = ("key", "district", "category", "family", "subtopic", "tkind", "tid", "target", "start",
                 "accepted", "work", "fixed", "late", "service", "hot", "event", "complaints", "joint",
                 "rejected", "scene")

    def __init__(self, **kw):
        for name in self.__slots__:
            setattr(self, name, kw.get(name))
        self.complaints = []


class WorldBuilder:
    def __init__(self, seed: int = SEED):
        self.seed = seed
        self.rnd = random.Random(seed)
        self.inputs = Inputs()
        self.texts = Texts()
        self.threads: list[Thread] = []
        self.complaints: list[dict] = []
        self._ids: set[str] = set()
        self._popularity: dict[tuple[str, str], list[float]] = {}
        self.used_targets: dict[str, int] = {}
        # Цели, занятые сценами: обычный поток их не трогает (числа сцен должны быть ровно такими, как в сценарии).
        self.reserved: set[str] = set()

    # ---------- выбор цели
    def _pool(self, district: str, tkind: str) -> list[str]:
        pool = [t for t in self.inputs.pools.get((district, tkind), []) if t not in self.reserved]
        if not pool and tkind == "foot":
            pool = [t for t in self.inputs.pools.get((district, "road"), []) if t not in self.reserved]
        return pool

    def pick_target(self, rnd: random.Random, district: str, tkind: str, avoid: set[str]) -> str | None:
        """Популярные места выбираются чаще (вес 1 / ранг^0,9): так у города есть «горячие» точки и длинный хвост."""
        if tkind == "cell":
            return self._cell(rnd, district)
        pool = self._pool(district, tkind)
        if not pool:
            return None
        key = (district, tkind)
        if key not in self._popularity:
            order = list(range(len(pool)))
            random.Random(f"{self.seed}-{district}-{tkind}").shuffle(order)
            weights = [0.0] * len(pool)
            for rank, idx in enumerate(order):
                weights[idx] = 1.0 / (rank + 1) ** 0.9
            self._popularity[key] = weights
        weights = self._popularity[key]
        for _ in range(30):
            tid = weighted(rnd, pool, weights)
            if tid not in avoid:
                return tid
        return None

    def _cell(self, rnd: random.Random, district: str) -> str | None:
        """«Примерное место» — ячейка ~150 м сетки R09/R07/R12 у случайного двора района (запахи, дым, пыль)."""
        yards = self._pool(district, "yard")
        if not yards:
            return None
        tid = yards[min(len(yards) - 1, int(rnd.random() ** 2 * len(yards)))]
        lon, lat = self.inputs.info[tid]["point"]
        from ui.civic_feedback.v2.record import cell_id
        cid = cell_id(lon + rnd.uniform(-0.004, 0.004), lat + rnd.uniform(-0.002, 0.002))
        if self.inputs.geometry("area", cid) is None:
            return None
        self.inputs.info.setdefault(cid, {"kind": "area", "point": None})
        return cid

    def target_kind(self, tid: str) -> str:
        if tid.startswith("yard-") or tid.startswith("cell-"):
            return "area"
        if tid.startswith("osm-w") and re.match(r"^osm-w\d+-\d+$", tid):
            return "segment"
        return "object"

    # ---------- точка жалобы рядом с целью
    def point_near(self, rnd: random.Random, tid: str) -> list[float]:
        geom = self.inputs.geometry(self.target_kind(tid), tid)["geometry"]
        t, c = geom["type"], geom["coordinates"]
        if t == "Point":
            ang, dist = rnd.uniform(0, 2 * math.pi), rnd.uniform(4, 25)
            return [round(c[0] + dist * math.cos(ang) / (111320 * math.cos(math.radians(c[1]))), 6),
                    round(c[1] + dist * math.sin(ang) / 110574, 6)]
        if t == "LineString":
            i = rnd.randrange(len(c) - 1)
            f = rnd.random()
            return [round(c[i][0] + (c[i + 1][0] - c[i][0]) * f, 6), round(c[i][1] + (c[i + 1][1] - c[i][1]) * f, 6)]
        ring = c[0]
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        from ui.civic_heat.geo import point_in_ring
        for _ in range(60):
            p = [rnd.uniform(min(xs), max(xs)), rnd.uniform(min(ys), max(ys))]
            if point_in_ring(p, ring):
                return [round(p[0], 6), round(p[1], 6)]
        return [round(sum(xs) / len(xs), 6), round(sum(ys) / len(ys), 6)]

    # ---------- время
    def sample_age_h(self, rnd: random.Random, day_lo: float, day_hi: float) -> float:
        """Возраст жалобы в часах с ритмами недели и суток. Опорная «сейчас» — пятница 12:00 (как REFERENCE_NOW):
        день недели считаем от неё, поэтому «понедельник» в мире — понедельник в день показа ± сдвиг недели.
        (Мир относительный: в другой день недели пик придётся на другой день — это честно записано в DATASHEET.)"""
        while True:
            age_days = rnd.uniform(day_lo, day_hi)
            ref = datetime.fromisoformat(REFERENCE_NOW) - timedelta(days=age_days)
            w = WEEKDAY[ref.weekday()] * HOURS[ref.hour] / 2.0
            if rnd.random() < w / max(WEEKDAY) * 1.0:
                return age_days * 24

    def season(self, category: str, family: str, age_days: float) -> float:
        """Сезонный множитель: август (60 дней назад) → середина октября."""
        if category == "utilities":
            if family == "heating":
                return 2.6 if age_days < 18 else 0.05      # отопительный сезон начался ~1 октября
            return 1.0
        if category == "lighting":
            return 0.7 + 0.8 * (1 - age_days / WINDOW_DAYS)  # вечера темнеют
        if category == "smell_air":
            return 1.5 if (age_days > 35 and family in ("dust", "smoke")) else 0.8
        if category == "yards":
            return 1.3 if age_days > 30 else 0.85
        if category == "roads" and family == "after_digging":
            return 1.2 if age_days > 20 else 0.8               # раскопки — летом и в начале осени
        return 1.0

    # ---------- нити
    def service_for(self, category: str, subtopic: str | None) -> str:
        return self.inputs.lifecycle.default_service(category, subtopic)

    def new_thread(self, rnd: random.Random, district: str, category: str, family: str, start_h: float,
                   *, hot: float = 1.0, event: str | None = None, tid: str | None = None,
                   late: bool | None = None, scene: str | None = None) -> Thread | None:
        subtopic, tkind, _w = FAMILIES[category][family]
        if subtopic is not None and subtopic not in self.inputs.subtopics[category]:
            raise ValueError(f"уточнения {subtopic} нет в categories_v2 для {category}")
        if tid is None:
            # Цель занята, если у неё уже есть открытая в этот момент нить той же категории (жалобы идут по времени).
            busy = {t.tid for t in self.threads if t.category == category and t.start >= start_h
                    and (t.fixed is None or t.fixed < start_h)}
            tid = self.pick_target(rnd, district, tkind, busy)
            if tid is None:
                return None
        kind = self.target_kind(tid)
        target = self.inputs.label(kind, tid)
        service = self.service_for(category, subtopic)
        acc_h, work_h, fix_d, late_share = SERVICE_PACE[service]
        if late is None:
            late = rnd.random() < late_share
        # Часы считаем «назад от сейчас»: start_h — возраст первой жалобы; события нити — меньше по возрасту.
        # Первый ответ: темп службы × 1,8 (в демо FINAL-4 почти всё отвечено за часы — у живого города дольше).
        accepted = start_h - rnd.uniform(*acc_h) * 1.8 * (rnd.uniform(4, 9) if late else 1)
        work = accepted - rnd.uniform(*work_h) * (rnd.uniform(1.5, 3) if late else 1)
        fixed = start_h - rnd.uniform(*fix_d) * 24 * (rnd.uniform(2, 3.5) if late else 1)
        fixed = min(fixed, work - 0.5)
        thread = Thread(key=f"t{len(self.threads):04d}", district=district, category=category, family=family,
                        subtopic=subtopic, tkind=tkind, tid=tid, target=target, start=start_h,
                        accepted=accepted if accepted > 0 else None,
                        work=work if (work > 0 and accepted > 0) else None,
                        fixed=fixed if (fixed > 0 and work > 0 and accepted > 0) else None,
                        late=late, service=service, hot=hot, event=event, joint=None, rejected=False, scene=scene)
        if category == "other" or (category == "parking" and family == "need_parking"):
            # «Не в компетенции» / «запланировано в программе» — отказ с объяснением (не жалоба на работу службы).
            thread.rejected = thread.accepted is not None and rnd.random() < 0.45
        self.threads.append(thread)
        self.used_targets[tid] = self.used_targets.get(tid, 0) + 1
        return thread

    def open_thread(self, district: str, category: str, family: str, age_h: float) -> Thread | None:
        """Нить, открытая в момент age_h (уже есть жалобы, ещё не исправлено), с тем же видом проблемы."""
        open_ = [t for t in self.threads if t.district == district and t.category == category and t.family == family
                 and t.scene is None and t.start >= age_h and (t.fixed is None or t.fixed < age_h)
                 and not t.rejected]
        if not open_:
            return None
        weights = [t.hot * (1 + len(t.complaints)) for t in open_]
        return weighted(self.rnd, open_, weights)

    # ---------- одна жалоба
    def complaint_id(self) -> str:
        n = len(self.complaints) + 1
        cid = f"c-w15{n:05d}"
        self._ids.add(cid)
        return cid

    def add_complaint(self, thread: Thread, age_h: float, *, metoo: int | None = None, text: str | None = None,
                      lang: str | None = None, cid: str | None = None, status: str | None = None,
                      point: list[float] | None = None, metoo_gap_h: float | None = None) -> dict:
        rnd = self.rnd
        if text is None:
            values = text_values(rnd, self.inputs, thread.tkind, thread.tid, thread.district, bool(thread.event))
            want = lang or lang_pick(rnd)
            rendered = self.texts.render(rnd, thread.category, thread.family, want, values)
            if rendered is None:
                if thread.scene:
                    raise ValueError(f"нет шаблона для {thread.category}/{thread.family} у {thread.tid}")
                return None  # цель без нужного названия (улица «проспект …» и т. п.) — поток возьмёт другую
            text, lang = rendered
        record = {
            "id": cid or self.complaint_id(), "schema": "civic-complaint-v2", "created_at": ago_h(age_h),
            "text": text, "lang": lang,
            "category": thread.category, "subtopic": thread.subtopic,
            "category_source": "resident", "model": None,
            "point": point or self.point_near(rnd, thread.tid), "target": dict(thread.target),
            "district": thread.district,
            "status": "new", "status_history": [{"at": ago_h(age_h), "status": "new"}],
            "metoo": 0, "metoo_times": [], "duplicate_of": None, "demo": True,
            "service": thread.service,
        }
        # Подсказка модели классификатора (R04/R03 /classify), как её прислал бы клиент: у части жалоб.
        roll = rnd.random()
        if roll < 0.75:
            score = round(rnd.uniform(0.58, 0.97), 2)
            record["model"] = {"label": thread.category, "score": score, "version": MODEL_VERSION,
                               "needs_review": score < 0.7}
            if roll < 0.3:
                record["category_source"] = "model"
        if thread.event:
            record["event"] = thread.event
        if thread.scene:
            record["scene"] = thread.scene
        # «Я тоже»: горячие нити и буран — больше; нажатия приходят в первые часы, не позже ремонта и «сейчас».
        if metoo is None:
            mean = 0.45 * thread.hot
            metoo = 0
            while rnd.random() < mean / (1 + mean) and metoo < 9:
                metoo += 1
        limit = thread.fixed if thread.fixed is not None and thread.fixed < age_h else 0.05
        times = []
        for n in range(metoo):
            gap = metoo_gap_h * (n + 1) if metoo_gap_h else rnd.expovariate(1 / 9.0)
            at = max(limit, age_h - gap)
            if at >= age_h:
                at = age_h - 0.05
            times.append(max(0.01, at))
        times.sort(reverse=True)
        record["metoo"] = len(times)
        record["metoo_times"] = [ago_h(t) for t in times]
        record["_age"] = age_h
        record["_thread"] = thread
        if status is not None:
            record["_force_status"] = status
        thread.complaints.append(record)
        self.complaints.append(record)
        return record

    # ---------- поток жалоб (все поступления — по времени, от старых к новым)
    def arrivals(self) -> list[dict]:
        """Все поступления жалоб мира: обычный поток + эпизоды снега + всплески бурана. Сортировка — по времени."""
        rnd = self.rnd
        out = []
        cats = sorted(CATEGORY_SHARE)
        for _ in range(int(BASE_PER_DAY * WINDOW_DAYS)):
            age_h = self.sample_age_h(rnd, 0.02, WINDOW_DAYS)
            age_d = age_h / 24
            district = weighted(rnd, list(DISTRICT_SHARE), list(DISTRICT_SHARE.values()))
            cat = weighted(rnd, cats, [CATEGORY_SHARE[c] for c in cats])
            fams = sorted(FAMILIES[cat])
            family = weighted(rnd, fams, [FAMILIES[cat][f][2] * self.season(cat, f, age_d) for f in fams])
            if rnd.random() > min(1.0, self.season(cat, family, age_d)):
                continue  # сезон: летом мало «нет отопления», осенью меньше пыли
            out.append({"age_h": age_h, "district": district, "category": cat, "family": family, "event": None,
                        "hot": 2.6 if rnd.random() < 0.12 else 1.0})
        for ep in SNOW_EPISODES:
            fams = sorted(ep["families"])
            for district in DISTRICTS:
                for _ in range(ep["per_district"].get(district, 0)):
                    out.append({"age_h": rnd.uniform(ep["to_h"], ep["from_h"]), "district": district,
                                "category": ep.get("category", "snow_ice"),
                                "family": weighted(rnd, fams, [ep["families"][f] for f in fams]),
                                "event": ep.get("event"), "hot": ep["hot"]})
        out.sort(key=lambda a: -a["age_h"])
        return out

    def stream(self) -> None:
        rnd = self.rnd
        for a in self.arrivals():
            thread = None
            if rnd.random() < (0.35 if a["event"] else 0.42):
                thread = self.open_thread(a["district"], a["category"], a["family"], a["age_h"])
            for _attempt in range(4):
                if thread is None:
                    thread = self.new_thread(rnd, a["district"], a["category"], a["family"], a["age_h"],
                                             hot=a["hot"], event=a["event"])
                    if thread is None:
                        break
                if self.add_complaint(thread, a["age_h"]) is not None:
                    break
                if not thread.complaints:          # пустую нить (цель без нужного названия) убираем
                    self.threads.remove(thread)
                    self.used_targets[thread.tid] -= 1
                thread = None

    # ---------- статусы по нити
    def finish_statuses(self) -> None:
        rnd = self.rnd
        for c in self.complaints:
            t: Thread = c["_thread"]
            age = c["_age"]
            hist = [{"at": ago_h(age), "status": "new"}]
            force = c.pop("_force_status", None)
            if force == "new":
                c["status"], c["status_history"] = "new", hist
                continue
            # ответ на эту жалобу: если нить уже принята — оператор отвечает быстро; иначе — вместе с нитью
            if t.accepted is not None and t.accepted < age:
                acc = t.accepted if t.accepted < age - 0.2 else age - rnd.uniform(0.2, 3)
            elif t.accepted is not None:
                # проблема уже в работе, пришла ещё одна жалоба: оператор отвечает в течение рабочего дня
                acc = age - rnd.uniform(1.5, 20) * (4 if t.late else 1)
            else:
                acc = None
            if acc is not None and acc <= 0.02:
                acc = None
            if acc is None:
                c["status"], c["status_history"] = "new", hist
                continue
            hist.append({"at": ago_h(acc), "status": "accepted"})
            if t.rejected:
                rej = max(0.02, acc - rnd.uniform(1, 30))
                hist.append({"at": ago_h(rej), "status": "rejected"})
                c["status"], c["status_history"] = "rejected", hist
                c["updates"] = [{"at": ago_h(rej), "kind": "note", "text": REJECT_NOTE.get(t.category, REJECT_NOTE["other"])}]
                continue
            work = None
            if t.work is not None:
                work = min(acc - 0.1, t.work) if t.work < acc else acc - rnd.uniform(0.3, 6)
                if work <= 0.02:
                    work = None
            if work is None:
                c["status"], c["status_history"] = "accepted", hist
                continue
            hist.append({"at": ago_h(work), "status": "in_progress"})
            if t.fixed is None or t.fixed >= work:
                c["status"], c["status_history"] = "in_progress", hist
                continue
            hist.append({"at": ago_h(t.fixed), "status": "fixed"})
            c["status"], c["status_history"] = "fixed", hist

    def resolutions(self) -> None:
        """«Служба сообщила» → «Проверено жителями» / «Проблема осталась» (R09 resolution, волна 2)."""
        rnd = self.rnd
        for t in self.threads:
            if t.fixed is None or not t.complaints or t.scene in ("step2", "scene8"):
                continue
            fixed_cs = [c for c in t.complaints if c["status"] == "fixed"]
            if not fixed_cs:
                continue
            what_ru = WHAT_DONE.get(t.family) or WHAT_DONE_CAT.get(t.category, "Проблему устранили")
            since = t.fixed
            r = rnd.random()
            state = "reported"
            verified_at = reopened_at = None
            votes = {"yes": 0, "no": 0, "cant": 0}
            if since > 14 and r < 0.02 and t.category not in ("other",):
                state, reopened_at = "reopened", since - rnd.uniform(8, min(40.0, since - 2))
                votes["no"] = 1
            elif since > 10 and r < 0.17:
                state, verified_at = "verified", since - rnd.uniform(5, min(48, since - 1))
                votes["yes"] = min(len(fixed_cs) + sum(c["metoo"] for c in fixed_cs), rnd.randint(1, 3))
            for c in fixed_cs:
                res = {"round": 1, "state": state, "reported_at": ago_h(since), "what_done": what_ru,
                       "by": "service", "photos_after": [], "votes": dict(votes),
                       "verified_at": ago_h(verified_at) if verified_at else None,
                       "reopened_at": ago_h(reopened_at) if reopened_at else None,
                       "reopen_count": 1 if state == "reopened" else 0}
                c["resolution"] = res
                c.setdefault("updates", []).append({"at": ago_h(since), "kind": "fixed", "text": what_ru})
                if state == "reopened":
                    c["status"] = "in_progress"
                    c["status_history"].append({"at": ago_h(reopened_at), "status": "in_progress",
                                                "reopened_by_residents": True})
                    c["updates"].append({"at": ago_h(reopened_at), "kind": "reopened", "text": None})

    def joint_parts(self) -> None:
        """~5 % жалоб — две службы (CONTRACT §5.1): части, передача с причиной, подсказка маршрута."""
        rnd = self.rnd
        cands = [t for t in self.threads if t.family in JOINT and not t.scene and t.complaints and not t.rejected]
        cands.sort(key=lambda t: t.key)
        want = int(JOINT_SHARE * len(self.complaints))
        rnd.shuffle(cands)
        made = 0
        for t in cands:
            if made >= want:
                break
            lead, partner, reason = JOINT[t.family]
            t.joint = (lead, partner)
            for c in t.complaints:
                self._make_joint(c, lead, partner, reason, handoff_from=t.service if t.service != lead else partner)
                made += 1

    def _make_joint(self, c: dict, lead: str, partner: str, reason: str, handoff_from: str) -> None:
        rnd = self.rnd
        status = c["status"]
        hist = c["status_history"]
        last_at = hist[-1]["at"]
        lead_status = {"new": "new", "accepted": "accepted", "in_progress": "in_progress", "fixed": "done",
                       "rejected": "accepted"}[status]
        if status == "fixed":
            partner_status = "done"
        elif status == "in_progress":
            partner_status = rnd.choice(("in_progress", "accepted"))
        elif status == "accepted":
            partner_status = "new"
        else:
            partner_status = "new"
        if status == "in_progress" and rnd.random() < 0.5:
            # ведущая уже закончила свою часть, участвующая — в работе (пример CONTRACT §5.1)
            lead_status, partner_status = "done", "in_progress"
        c["service"] = lead
        c["services"] = [
            {"service": lead, "role": "lead", "status": lead_status, "note": PART_NOTE.get((lead, lead_status)),
             "updated_at": last_at},
            {"service": partner, "role": "partner", "status": partner_status,
             "note": PART_NOTE.get((partner, partner_status)), "updated_at": last_at},
        ]
        for part in c["services"]:
            if part["note"] is None:
                del part["note"]
        c["route_hint"] = {"services": [lead, partner], "joint": True, "source": "rules", "model_version": None}
        if len(hist) >= 2 and handoff_from != lead:
            c["handoffs"] = [{"at": hist[1]["at"], "from": handoff_from, "to": lead, "reason": reason,
                              "by_role": "operator"}]
        else:
            c["handoffs"] = []

    def passports(self) -> None:
        """Паспорт решения у части «в работе»: следующий шаг и срок; 3 задержки «нужно решение акима» (R08)."""
        rnd = self.rnd
        open_ = [c for c in self.complaints if c["status"] == "in_progress" and not c.get("scene")]
        open_.sort(key=lambda c: c["id"])
        for c in open_:
            if rnd.random() < 0.35:
                c["passport"] = {"assignee_id": c["service"], "next_step": NEXT_STEP.get(c["category"]),
                                 "fix_eta": {"day": rnd.randint(1, 12)}, "updated_at": c["status_history"][-1]["at"]}
        # «Нужно решение акима»: старые (≥ 12 дней) в работе, у служб без своего решения — 3 примера, как в R08.
        old = [c for c in open_ if c["_age"] > 12 * 24 and c["category"] in DECISIONS]
        # Нура — район демо: два примера там (иначе фильтр «Нура» в «Картине дня» показал бы пример-фикстуру R08).
        old.sort(key=lambda c: (c["district"] != "nura", -c["_age"], c["id"]))
        chosen, cats, nura = [], set(), 0
        for c in old:
            if c["category"] in cats or (c["district"] == "nura" and nura >= 2):
                continue
            chosen.append(c)
            cats.add(c["category"])
            nura += c["district"] == "nura"
            if len(chosen) == 3:
                break
        for c in chosen:
            delay = dict(DECISIONS[c["category"]])
            delay.update({"reason_code": "needs_decision", "needs_decision": True,
                          "next_update_at": {"in_days": 2}})
            c["passport"] = {"assignee_id": c["service"], "next_step": None, "fix_eta": None, "delay": delay,
                             "updated_at": ago_h(max(0.5, c["_age"] - 24 * 5))}


# ---------------------------------------------------------------- тексты служб (ru; kk — в DECISIONS, где их видит аким)
REJECT_NOTE = {
    "other": "Вопрос не относится к работе служб района. Ответ направлен в профильное ведомство.",
    "parking": "Новая парковка — не ремонт: предложение передано в программу благоустройства двора.",
}
WHAT_DONE = {
    "pothole": "Заделали яму на дороге", "after_digging": "Восстановили асфальт после раскопок",
    "marking": "Обновили разметку", "traffic_light": "Отремонтировали светофор", "speed_bump": "Установили неровность",
    "road_water": "Прочистили ливнёвку", "yard_drive": "Заделали яму на проезде во дворе",
    "road_snow": "Расчистили проезжую часть", "sidewalk_ice": "Посыпали тротуар противогололёдной смесью",
    "yard_snow": "Расчистили двор от снега", "stop_ice": "Убрали наледь на остановке", "snow_dumped": "Вывезли снег",
    "no_sand": "Посыпали дорогу", "icicles": "Сбили сосульки", "tiles": "Переложили плитку", "ramp": "Сделали пандус",
    "sidewalk_water": "Убрали воду с тротуара", "no_sidewalk": "Сделали временную дорожку", "fence": "Освободили проход",
    "pavilion": "Отремонтировали павильон", "no_shelter": "Поставили временный навес", "stop_bench": "Поставили скамейку",
    "interval": "Добавили рейсы в часы пик", "board": "Повесили расписание", "skips_stop": "Провели беседу с перевозчиком",
    "stop_moved": "Вернули табличку остановки", "lamps_off": "Заменили лампы", "dark_yard": "Поставили светильник во дворе",
    "flicker": "Заменили светильник", "day_burning": "Настроили включение фонарей", "park_dark": "Включили освещение в парке",
    "stop_dark": "Заменили лампу на остановке", "playground": "Отремонтировали площадку", "benches": "Поставили скамейки",
    "trees": "Высадили деревья", "dry_tree": "Убрали сухое дерево", "lawn": "Восстановили газон",
    "improvement": "Благоустроили двор", "bins_full": "Вывезли мусор, добавили рейс", "urns_full": "Очистили урны",
    "illegal_dump": "Убрали свалку", "construction": "Вывезли строительный мусор", "schedule": "Вывоз по графику восстановлен",
    "heating": "Подача тепла восстановлена", "water": "Подача воды восстановлена", "sewer": "Прочистили канализацию",
    "pipe_burst": "Заменили участок трубы", "entrance_light": "Восстановили свет в подъезде", "lift": "Лифт работает",
    "smoke": "Источник дыма установлен, нарушителю выдано предписание", "dust": "Стройка поливает дорогу",
    "stench": "Очистили источник запаха", "plant": "Проверка предприятия проведена",
    "night_construction": "Ночные работы запрещены, стройке выдано предписание", "stray_dogs": "Животных отловили",
    "open_manhole": "Закрыли люк", "abandoned": "Закрыли доступ в здание", "racing": "Усилили патрулирование",
    "no_crossing": "Поставили временный переход", "on_lawn": "Поставили ограждение газона",
    "blocked_exit": "Освободили выезд", "on_sidewalk": "Поставили столбики", "on_stop": "Нарушители оштрафованы",
    "abandoned_car": "Брошенную машину эвакуировали",
}
WHAT_DONE_CAT = {"other": "Дан ответ", "parking": "Порядок восстановлен"}
NEXT_STEP = {
    "roads": "Ремонт покрытия по графику бригады", "sidewalks": "Ремонт тротуара после поставки плитки",
    "transport": "Заявка перевозчику, ответ в течение недели", "lighting": "Выезд бригады электриков",
    "yards": "Включено в график благоустройства", "waste": "Дополнительный рейс вывоза",
    "utilities": "Выезд аварийной бригады", "smell_air": "Проверка источника экологом",
    "noise_safety": "Выезд участкового", "parking": "Проверка с инспектором", "snow_ice": "Расчистка по графику",
    "other": "Рассматривается",
}
PART_NOTE = {("water", "done"): "Трубу заменили", ("heating", "done"): "Теплотрассу закрыли",
             ("road", "in_progress"): "Восстанавливаем покрытие", ("greenery", "done"): "Деревья высадили",
             ("waste", "done"): "Мусор вывезли"}
# «Нужно решение акима» — то, что служба не может решить сама (как у R08: деньги вне плана, чей объект, согласование).
DECISIONS = {
    "yards": {"problem_ru": "Площадку нужно менять целиком, ремонт не помогает.",
              "problem_kk": "Алаңды толық ауыстыру керек, жөндеу көмектеспейді.",
              "blocker_ru": "Замена площадки не заложена в план этого года.",
              "blocker_kk": "Алаңды ауыстыру биылғы жоспарға енгізілмеген.",
              "options": [{"ru": "Перенести деньги из резерва района — замена в этом году.",
                           "kk": "Аудан резервінен қаражат аудару — биыл ауыстыру."},
                          {"ru": "Включить в план следующего года, сейчас — закрыть опасные элементы.",
                           "kk": "Келесі жылдың жоспарына енгізу, қазір — қауіпті бөліктерін жабу."}],
              "decision_ru": "Выбрать: резерв сейчас или план следующего года.",
              "decision_kk": "Таңдау: қазір резерв немесе келесі жылдың жоспары.",
              "temp_measure_ru": "Опасные качели сняты.", "temp_measure_kk": "Қауіпті әткеншек алынды."},
    "roads": {"problem_ru": "Участок разрушается: ямочный ремонт держится две недели.",
              "problem_kk": "Учаске бұзылып жатыр: шұңқырды жамау екі аптаға ғана жетеді.",
              "blocker_ru": "Капитальный ремонт — другая программа и другой бюджет.",
              "blocker_kk": "Күрделі жөндеу — басқа бағдарлама және басқа бюджет.",
              "options": [{"ru": "Ещё раз заделать ямы до зимы.", "kk": "Қысқа дейін шұңқырларды тағы жамау."},
                          {"ru": "Включить участок в капитальный ремонт весной.",
                           "kk": "Учаскені көктемде күрделі жөндеуге енгізу."}],
              "decision_ru": "Ямочный ремонт или капитальный весной.",
              "decision_kk": "Шұңқырды жамау немесе көктемде күрделі жөндеу.",
              "temp_measure_ru": "Поставлены знаки «Неровная дорога».",
              "temp_measure_kk": "«Тегіс емес жол» белгілері қойылды."},
    "lighting": {"problem_ru": "Опоры освещения во дворе ничьи — не на балансе ни одной службы.",
                 "problem_kk": "Аладағы жарық тіректері ешкімнің балансында жоқ.",
                 "blocker_ru": "Без решения, кто содержит опоры, служба не может их чинить.",
                 "blocker_kk": "Тіректерді кім ұстайтыны шешілмейінше, қызмет оларды жөндей алмайды.",
                 "options": [{"ru": "Принять опоры на баланс района.", "kk": "Тіректерді аудан балансына алу."},
                             {"ru": "Передать опоры объединению собственников дома.",
                              "kk": "Тіректерді үй иелерінің бірлестігіне беру."}],
                 "decision_ru": "Кто будет содержать освещение двора.",
                 "decision_kk": "Аула жарығын кім ұстайды.",
                 "temp_measure_ru": "Поставлен временный прожектор.", "temp_measure_kk": "Уақытша прожектор қойылды."},
    "transport": {"problem_ru": "Павильон остановки нужно переносить: на старом месте его ломает снег с крыши.",
                  "problem_kk": "Аялдама павильонын көшіру керек: ескі орнында шатырдан құлаған қар сындырады.",
                  "blocker_ru": "Перенос остановки требует согласования маршрута.",
                  "blocker_kk": "Аялдаманы көшіру бағытты келісуді талап етеді.",
                  "options": [{"ru": "Перенести остановку на 40 м.", "kk": "Аялдаманы 40 м-ге көшіру."},
                              {"ru": "Оставить и укрепить крышу павильона.", "kk": "Қалдырып, павильон шатырын нығайту."}],
                  "decision_ru": "Перенос или укрепление.", "decision_kk": "Көшіру немесе нығайту.",
                  "temp_measure_ru": "Поставлен временный навес.", "temp_measure_kk": "Уақытша шатыр қойылды."},
}


def strip_private(c: dict) -> dict:
    return {k: v for k, v in c.items() if not k.startswith("_")}


# ---------------------------------------------------------------- эпизоды снега (часы назад)
# Октябрь в Астане: первый снег и утренний гололёд — обычное дело; «Буран в Нуре» — последние ~3 суток (сцена 9).
BURAN = {"id": "ev-w15-buran", "from_h": 70.0, "to_h": 3.0}
SNOW_EPISODES = (
    {"event": "ev-w15-first-snow", "from_h": 13.2 * 24, "to_h": 11.6 * 24, "hot": 1.4,
     "per_district": {"nura": 15, "esil": 6, "almaty": 4, "saryarka": 5, "baikonur": 4, "saraishyk": 4},
     "families": {"road_snow": 3, "sidewalk_ice": 3, "yard_snow": 2, "stop_ice": 1.5, "no_sand": 1}},
    {"event": "ev-w15-ice", "from_h": 9.6 * 24, "to_h": 8.3 * 24, "hot": 1.2,
     "per_district": {"nura": 12, "esil": 5, "almaty": 3, "saryarka": 3, "baikonur": 3, "saraishyk": 3},
     "families": {"sidewalk_ice": 4, "no_sand": 2, "stop_ice": 2}},
    {"event": BURAN["id"], "from_h": BURAN["from_h"], "to_h": BURAN["to_h"], "hot": 2.0,
     "per_district": {"nura": 30, "esil": 6, "almaty": 3, "saryarka": 4, "baikonur": 3, "saraishyk": 4},
     "families": {"road_snow": 3, "sidewalk_ice": 2, "yard_snow": 3, "stop_ice": 1.5, "snow_dumped": 0.6,
                  "no_sand": 1, "icicles": 0.4}},
    # Буран тянет за собой транспорт (автобусы опаздывают) и обрывы освещения — в Нуре.
    {"event": BURAN["id"], "from_h": BURAN["from_h"], "to_h": BURAN["to_h"], "hot": 1.6, "category": "transport",
     "per_district": {"nura": 6}, "families": {"interval": 3, "skips_stop": 1}},
)
EVENTS = (
    # started_at / ended_at — как у кризиса (CONTRACT §5.5): отметки «Хроники» R07 читают те же имена полей.
    {"id": "ev-w15-heating", "kind": "season", "title_ru": "Начало отопительного сезона",
     "title_kk": "Жылыту маусымының басталуы", "district": None, "started_at": {"ago_days": 18}, "ended_at": None},
    {"id": "ev-w15-first-snow", "kind": "snow", "title_ru": "Первый снег", "title_kk": "Алғашқы қар",
     "district": None, "started_at": {"ago_hours": 13.2 * 24}, "ended_at": {"ago_hours": 11.6 * 24}},
    {"id": "ev-w15-ice", "kind": "ice", "title_ru": "Утренний гололёд", "title_kk": "Таңғы көктайғақ",
     "district": None, "started_at": {"ago_hours": 9.6 * 24}, "ended_at": {"ago_hours": 8.3 * 24}},
    {"id": BURAN["id"], "kind": "blizzard", "title_ru": "Буран в Нуре", "title_kk": "Нұрада боран",
     "district": "nura", "started_at": {"ago_hours": BURAN["from_h"]}, "ended_at": {"ago_hours": BURAN["to_h"]}},
)

# ---------------------------------------------------------------- сцены
KHAN_SHATYR_ID = "osm-node-4109037549"


class Scenes:
    """Сцены демо: шаг 2 FINAL-4 («Хан Шатыр»), 7 «Двор вместе», 8 «Ведомства вместе», 9 «Буран»."""

    def __init__(self, b: WorldBuilder):
        self.b = b
        self.out: dict = {}

    def step2_khan_shatyr(self) -> None:
        """Ровно как R09 demo_seed (те же id и тексты): «Об этом уже сообщили 3 человека» → «Я тоже» → 4.
        Плюс две жалобы на интервал автобусов: на значке остановки 12 человек, как в сценарии FINAL-4."""
        from ui.civic_feedback.v2 import demo_seed
        b = self.b
        b.reserved.add(KHAN_SHATYR_ID)
        target = dict(demo_seed.KHAN_SHATYR)
        complaints = []
        for item in demo_seed.DEMO_COMPLAINTS:
            family = "stop_dark" if item["category"] == "lighting" else "pavilion"
            t = b.new_thread(b.rnd, "nura", item["category"], family, float(item["hours_ago"]), tid=KHAN_SHATYR_ID,
                             scene="step2")
            t.target = dict(target)
            t.subtopic = None
            c = b.add_complaint(t, float(item["hours_ago"]), metoo=item["people"] - 1, text=item["text"],
                                lang=None, cid=demo_seed._demo_id(item["key"]), status="new",
                                point=list(item["point"]), metoo_gap_h=2.0)
            c["lang"] = _detect_lang(item["text"])
            c["subtopic"] = None
            c["model"] = None
            c["category_source"] = "resident"
            complaints.append(c["id"])
        for age_h, metoo, lang in ((4.6 * 24, 3, "ru"), (3.2 * 24, 2, "kk")):
            t = b.new_thread(b.rnd, "nura", "transport", "interval", age_h, tid=KHAN_SHATYR_ID, scene="step2", late=False)
            t.target = dict(target)
            c = b.add_complaint(t, age_h, metoo=metoo, lang=lang)
            complaints.append(c["id"])
        self.out["step2"] = {"target": KHAN_SHATYR_ID, "label_ru": target["label_ru"], "label_kk": target["label_kk"],
                             "complaints": complaints, "lighting_people": 3, "stop_people": 12,
                             "note": "шаг 2 FINAL-4: «сообщили 3 человека» → «Я тоже» → 4 (освещение у остановки)"}

    def pick_yard(self, district: str, rank: int = 0) -> str:
        """Двор с названием и заметным размером — для сцен (детерминированно)."""
        b = self.b
        cands = []
        for tid in b.inputs.pools.get((district, "yard"), []):
            info = b.inputs.info[tid]
            if tid in b.reserved or not info.get("name_ru"):
                continue
            geom = b.inputs.geometry("area", tid)["geometry"]["coordinates"][0]
            area = _ring_area_m2(geom)
            if 6000 <= area <= 60000:
                cands.append((round(area), tid))
        cands.sort(key=lambda x: (-x[0], x[1]))
        return cands[rank][1]

    def scene7_yard(self) -> str:
        b = self.b
        yard = self.pick_yard("nura", 0)
        b.reserved.add(yard)
        story = (  # (категория, семейство, возраст ч, «Я тоже», язык, событие)
            ("snow_ice", "yard_snow", 40.0, 3, "ru", BURAN["id"]),
            ("snow_ice", "yard_snow", 18.0, 2, "kk", BURAN["id"]),
            ("lighting", "dark_yard", 6.2 * 24, 1, "mixed", None),
            ("yards", "playground", 21 * 24, 2, "ru", None),
            ("waste", "bins_full", 3.1 * 24, 0, "kk", None),
        )
        ids = []
        for cat, fam, age_h, metoo, lang, event in story:
            t = b.new_thread(b.rnd, "nura", cat, fam, age_h, tid=yard, event=event, scene="scene7", late=False,
                             hot=1.5)
            c = b.add_complaint(t, age_h, metoo=metoo, lang=lang)
            ids.append(c["id"])
        self.out["scene7"] = {"yard": yard, "complaints": ids}
        return yard

    def scene8_street(self) -> dict:
        """Улица Нуры с недавней раскопкой Водоканала: жалоба «яма после раскопок» (2 службы) и план следующего
        сезона «асфальт в мае, сети в июле» на тех же участках — конфликт «копаем дважды»."""
        b = self.b
        run = street_run(b.inputs, "nura", min_edges=6, max_edges=8, rank=0, prefer_prefix="улица ")
        for e in run:
            b.reserved.add(e)
        mid = run[len(run) // 2]
        t = b.new_thread(b.rnd, "nura", "roads", "after_digging", 20.0, tid=mid, scene="scene8", late=False)
        c = b.add_complaint(t, 20.0, metoo=2, lang="ru", status="new")
        c["route_hint"] = {"services": ["water", "road"], "joint": True, "source": "rules", "model_version": None}
        self.out["scene8"] = {"complaint": c["id"], "segments": run, "street_ru": b.inputs.info[mid]["name_ru"],
                              "street_kk": b.inputs.info[mid]["name_kk"]}
        return self.out["scene8"]


def _detect_lang(text: str) -> str:
    from ui.civic_feedback.v2.record import detect_lang
    return detect_lang(text)


def _ring_area_m2(ring) -> float:
    lat0 = ring[0][1]
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110574
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        s += (x1 * kx) * (y2 * ky) - (x2 * kx) * (y1 * ky)
    return abs(s) / 2


def street_run(inputs: Inputs, district: str, *, min_edges: int, max_edges: int, rank: int = 0,
               prefer_prefix: str | None = None, exclude_ways: set | None = None, group: str = "road") -> list[str]:
    """Участок улицы из подряд идущих рёбер ОДНОЙ линии OSM (way) в районе: настоящая форма, без «от руки»."""
    by_way: dict[int, list[tuple[int, str]]] = {}
    for tid in inputs.pools.get((district, group), []):
        info = inputs.info[tid]
        m = re.match(r"^osm-w(\d+)-(\d+)$", tid)
        if not m:
            continue
        if prefer_prefix and not (info.get("name_ru") or "").lower().startswith(prefer_prefix):
            continue
        if exclude_ways and info.get("way") in exclude_ways:
            continue
        by_way.setdefault(int(m.group(1)), []).append((int(m.group(2)), tid))
    runs = []
    for way in sorted(by_way):
        idx = sorted(by_way[way])
        cur = [idx[0]]
        for item in idx[1:]:
            if item[0] == cur[-1][0] + 1:
                cur.append(item)
            else:
                if len(cur) >= min_edges:
                    runs.append((way, cur))
                cur = [item]
        if len(cur) >= min_edges:
            runs.append((way, cur))
    if not runs and group != "road":
        # у пешеходных дорожек редко есть названия — тогда благоустройство идёт вдоль проезжей части
        return street_run(inputs, district, min_edges=min_edges, max_edges=max_edges, rank=rank,
                          prefer_prefix=prefer_prefix, exclude_ways=exclude_ways, group="road")
    if not runs:
        raise ValueError(f"нет участка улицы из {min_edges}+ рёбер в районе {district}")
    # Длиннее и «ровнее» — раньше; детерминированный порядок.
    runs.sort(key=lambda r: (-min(len(r[1]), max_edges), r[0]))
    way, items = runs[rank]
    return [tid for _, tid in items[:max_edges]]


# ---------------------------------------------------------------- работы (CONTRACT §5.6)
WORK_KINDS_R14 = {"dig": "construction", "surface": "roadworks", "closure": "roadworks", "landscape": "landscaping",
                  "lighting": "lighting", "other": "other"}
WORK_TITLES = {
    ("dig", "water"): ("Замена водопровода", "Су құбырын ауыстыру"),
    ("dig", "heating"): ("Ремонт теплотрассы", "Жылу трассасын жөндеу"),
    ("dig", "gas"): ("Перекладка газопровода", "Газ құбырын қайта төсеу"),
    ("dig", "power"): ("Прокладка кабеля", "Кабель төсеу"),
    ("surface", "road"): ("Укладка асфальта", "Асфальт төсеу"),
    ("closure", "road"): ("Перекрытие проезда", "Жолды жабу"),
    ("closure", "traffic"): ("Перекрытие для разметки", "Жол таңбасы үшін жабу"),
    ("landscape", "landscaping"): ("Благоустройство вдоль улицы", "Көше бойын абаттандыру"),
    ("landscape", "greenery"): ("Посадка деревьев вдоль улицы", "Көше бойына ағаш отырғызу"),
    ("lighting", "lighting"): ("Замена уличного освещения", "Көше жарығын ауыстыру"),
}
WHY = {
    "dig": ("Старые трубы часто рвутся", "Ескі құбырлар жиі жарылады", "Трубы меняют до холодов",
            "Құбырларды суыққа дейін ауыстырады", "Меньше аварий зимой", "Қыста апат азаяды",
            "Раскопка на проезжей части, проезд сужен", "Жүру бөлігінде қазу, жол тарылған"),
    "surface": ("Покрытие разрушено, много ям", "Жабын бұзылған, шұңқыр көп", "Ямочный ремонт уже не держится",
                "Шұңқырды жамау енді көмектеспейді", "Ровная дорога на годы", "Ұзақ жылға тегіс жол",
                "Полосы закрывают по очереди", "Жолақтар кезекпен жабылады"),
    "closure": ("Нужно безопасно провести работы", "Жұмысты қауіпсіз жүргізу керек",
                "Работы нельзя вести под движением", "Жұмысты қозғалыс кезінде жүргізуге болмайды",
                "Работы закончат быстрее", "Жұмыс тезірек бітеді", "Объезд по соседним улицам",
                "Көрші көшелер арқылы айналып өту"),
    "landscape": ("Вдоль улицы нет тени и скамеек", "Көше бойында көлеңке мен орындық жоқ",
                  "Работы — до заморозков", "Жұмыс — аязға дейін", "Удобная пешеходная зона",
                  "Ыңғайлы жаяу жүргіншілер аймағы", "Тротуар частично закрыт", "Тротуар ішінара жабық"),
    "lighting": ("Фонари старые, часто гаснут", "Шамдар ескі, жиі сөнеді", "Ставят экономичные светильники",
                 "Үнемді шамдар қояды", "Светло вечером и ночью", "Кешке және түнде жарық",
                 "Ночью возможны отключения света на улице", "Түнде көше жарығы сөнуі мүмкін"),
}


class Works:
    def __init__(self, b: WorldBuilder):
        self.b = b
        self.items: list[dict] = []
        self.conflicts: list[dict] = []
        self.used_ways: set[int] = set()
        self.n = 0

    def _way_of(self, tid: str) -> int:
        return int(re.match(r"^osm-w(\d+)-", tid).group(1))

    def add(self, district: str, segments: list[str], service: str, kind: str, starts_on: dict, ends_on: dict,
            status: str, scene: str | None = None) -> dict:
        b = self.b
        self.n += 1
        wid = f"w-w15-{self.n:03d}"
        info = b.inputs.info[segments[0]]
        coords, length = [], 0.0
        for tid in segments:
            e = b.inputs.graph.by_id[tid]
            coords.append([[round(x, 6), round(y, 6)] for x, y in e.geometry])
            length += e.length_m
        title_ru, title_kk = WORK_TITLES[(kind, service)]
        why = WHY[kind]
        street_ru, street_kk = info.get("name_ru"), info.get("name_kk")
        item = {
            "id": wid, "type": "work", "service": service, "kind": kind, "segments": list(segments),
            "street_ru": street_ru, "street_kk": street_kk, "district": district,
            "starts_on": starts_on, "ends_on": ends_on, "status": status, "work_kind": WORK_KINDS_R14[kind],
            "title_ru": f"{title_ru}: {street_ru}", "title_kk": f"{title_kk}: {street_kk or street_ru}",
            "why": {"problem_ru": why[0], "problem_kk": why[1], "reason_ru": why[2], "reason_kk": why[3],
                    "result_ru": why[4], "result_kk": why[5], "inconvenience_ru": why[6], "inconvenience_kk": why[7]},
            "geometry": {"type": "MultiLineString", "coordinates": coords}, "length_m": round(length),
            "source": "demo", "demo": True,
        }
        if scene:
            item["scene"] = scene
        self.items.append(item)
        for tid in segments:
            self.used_ways.add(self._way_of(tid))
        return item

    def outage(self, district: str, utility: str, source: str, starts_h: float, ends_h: float, near: str,
               title_ru: str, title_kk: str, why: tuple) -> dict:
        """Отключение («Рядом» раунда 14): starts_h/ends_h — часы от «сейчас» (минус — в прошлом)."""
        self.n += 1
        b = self.b
        name_ru, name_kk = b.inputs.street_of(near)
        rel = lambda h: {"in_hours": _r(h)} if h >= 0 else {"ago_hours": _r(-h)}  # noqa: E731
        item = {"id": f"w-w15-{self.n:03d}", "type": "outage", "utility": utility, "service": source,
                "district": district, "starts_at": rel(starts_h), "ends_at": rel(ends_h),
                "zone_ru": f"Дома у участка: {name_ru}" if name_ru else "Дома рядом",
                "zone_kk": f"Учаске маңындағы үйлер: {name_kk or name_ru}" if name_ru else "Маңайдағы үйлер",
                "title_ru": title_ru, "title_kk": title_kk,
                "why": {"problem_ru": why[0], "problem_kk": why[1], "reason_ru": why[2], "reason_kk": why[3],
                        "result_ru": why[4], "result_kk": why[5], "inconvenience_ru": why[6], "inconvenience_kk": why[7]},
                "near": near, "source": "demo", "demo": True}
        self.items.append(item)
        return item

    def conflict(self, kind: str, works: list[dict], segments: list[str], severity: str, advice_ru: str,
                 advice_kk: str) -> dict:
        cf = {"id": f"cf-w15-{len(self.conflicts) + 1:02d}", "kind": kind, "works": [w["id"] for w in works],
              "segments": list(segments), "severity": severity, "advice_ru": advice_ru, "advice_kk": advice_kk,
              "demo": True}
        self.conflicts.append(cf)
        return cf

    def build(self, scene8: dict) -> None:
        b = self.b
        rnd = random.Random(f"{b.seed}-works")
        # Сцена 8: раскопка Водоканала закончилась 9 дней назад (на месте — «яма после раскопок»),
        # следующий сезон: асфальт в мае, а сети на тех же участках — в июле (копаем дважды).
        seg = scene8["segments"]
        self.add("nura", seg, "water", "dig", {"day": -30}, {"day": -9}, "done", scene="scene8")
        surface = self.add("nura", seg, "road", "surface", {"season": {"month": 5, "day": 4}},
                           {"season": {"month": 5, "day": 22}}, "planned", scene="scene8")
        dig = self.add("nura", seg[1:-1], "water", "dig", {"season": {"month": 7, "day": 6}},
                       {"season": {"month": 7, "day": 31}}, "planned", scene="scene8")
        cf8 = self.conflict("dig_after_surface", [surface, dig], seg[1:-1], "high",
                            "Сначала заменить трубу (апрель), потом класть асфальт (май) — не копать новый асфальт.",
                            "Алдымен құбырды ауыстыру (сәуір), содан кейін асфальт төсеу (мамыр) — жаңа асфальтты қазбау.")
        scene8["works"] = [surface["id"], dig["id"]]
        scene8["conflict"] = cf8["id"]
        # Ещё два «асфальт раньше сетей»: Есиль (асфальт положили 20 дней назад, раскопка через 15 дней) и Сарыарка.
        run = street_run(b.inputs, "esil", min_edges=5, max_edges=6, rank=0, exclude_ways=self.used_ways)
        a = self.add("esil", run, "road", "surface", {"day": -34}, {"day": -20}, "done")
        d = self.add("esil", run[1:4], "heating", "dig", {"day": 15}, {"day": 32}, "planned")
        self.conflict("dig_after_surface", [a, d], run[1:4], "high",
                      "Перенести ремонт теплотрассы на весну и сразу восстановить новый асфальт за счёт подрядчика "
                      "раскопки — или проложить трубу методом прокола без вскрытия.",
                      "Жылу трассасын жөндеуді көктемге ауыстыру немесе құбырды жолды ашпай тесу әдісімен төсеу.")
        run = street_run(b.inputs, "saryarka", min_edges=5, max_edges=6, rank=0, exclude_ways=self.used_ways)
        a = self.add("saryarka", run, "road", "surface", {"season": {"month": 6, "day": 1}},
                     {"season": {"month": 6, "day": 20}}, "planned")
        d = self.add("saryarka", run[:3], "gas", "dig", {"season": {"month": 8, "day": 10}},
                     {"season": {"month": 8, "day": 28}}, "planned")
        self.conflict("dig_after_surface", [a, d], run[:3], "medium",
                      "Поменять очерёдность: газопровод в мае, асфальт после него.",
                      "Кезекті ауыстыру: газ құбыры мамырда, асфальт одан кейін.")
        # Два перекрытия соседних участков одной улицы в одни дни (Нура) — «параллельные перекрытия».
        run = street_run(b.inputs, "nura", min_edges=6, max_edges=6, rank=0, exclude_ways=self.used_ways)
        c1 = self.add("nura", run[:3], "road", "closure", {"day": 5}, {"day": 9}, "planned")
        c2 = self.add("nura", run[3:], "traffic", "closure", {"day": 7}, {"day": 11}, "planned")
        self.conflict("parallel_closures", [c1, c2], run, "medium",
                      "Развести перекрытия по датам: сначала один участок, потом второй — иначе объезда нет.",
                      "Жабуларды күн бойынша бөлу: алдымен бір учаске, сосын екіншісі — әйтпесе айналма жол жоқ.")
        # Свет и благоустройство на одних участках одновременно (Алматы) — «одно и то же место дважды».
        run = street_run(b.inputs, "almaty", min_edges=4, max_edges=5, rank=0, exclude_ways=self.used_ways)
        l1 = self.add("almaty", run, "lighting", "lighting", {"day": -6}, {"day": 12}, "in_progress")
        l2 = self.add("almaty", run[1:], "landscaping", "landscape", {"day": 2}, {"day": 25}, "planned")
        self.conflict("same_segment_overlap", [l1, l2], run[1:], "medium",
                      "Объединить в один заход: кабель освещения проложить до благоустройства тротуара.",
                      "Бір кезеңге біріктіру: жарық кабелін тротуарды абаттандыруға дейін төсеу.")
        # Остальные работы — без конфликтов, на разных улицах; сроки: прошлое, сейчас, ближайшие недели.
        plan = (("nura", "water", "dig"), ("nura", "lighting", "lighting"), ("nura", "road", "surface"),
                ("nura", "greenery", "landscape"), ("nura", "heating", "dig"), ("nura", "power", "dig"),
                ("nura", "road", "surface"), ("nura", "landscaping", "landscape"),
                ("esil", "water", "dig"), ("esil", "lighting", "lighting"), ("esil", "road", "surface"),
                ("esil", "greenery", "landscape"), ("esil", "power", "dig"),
                ("almaty", "heating", "dig"), ("almaty", "road", "surface"), ("almaty", "water", "dig"),
                ("saryarka", "lighting", "lighting"), ("saryarka", "water", "dig"), ("saryarka", "road", "surface"),
                ("baikonur", "road", "surface"), ("baikonur", "heating", "dig"), ("baikonur", "lighting", "lighting"),
                ("baikonur", "landscaping", "landscape"),
                ("saraishyk", "road", "surface"), ("saraishyk", "water", "dig"), ("saraishyk", "greenery", "landscape"),
                ("nura", "road", "closure"), ("esil", "road", "closure"))
        for k, (district, service, kind) in enumerate(plan):
            run = street_run(b.inputs, district, min_edges=3, max_edges=rnd.choice((3, 4, 5)), rank=0,
                             exclude_ways=self.used_ways, group="foot" if kind == "landscape" else "road")
            phase = k % 4
            if phase == 0:      # уже закончили
                s, e, st = -rnd.randint(25, 45), -rnd.randint(2, 20), "done"
            elif phase == 1:    # идут сейчас
                s, e, st = -rnd.randint(2, 20), rnd.randint(3, 25), "in_progress"
            elif phase == 2:    # скоро
                s = rnd.randint(3, 25)
                e, st = s + rnd.randint(5, 25), "planned"
            else:               # перекрытия короткие, остальное — в этом сезоне до заморозков
                s = rnd.randint(1, 10)
                e, st = s + (rnd.randint(1, 4) if kind == "closure" else rnd.randint(7, 20)), "planned"
            if s > 0 and st != "planned":
                st = "planned"
            self.add(district, run, service, kind, {"day": s}, {"day": e}, st)
        # Отключения («Рядом»): вода завтра, тепло сегодня, свет — ночью, газ — через 3 дня.
        near = lambda d, kind: b.inputs.pools[(d, kind)][3]  # noqa: E731
        self.outage("nura", "water", "water", 20, 26, near("nura", "yard"), "Отключение холодной воды",
                    "Суық су өшіріледі", ("Замена задвижки на сети", "Желідегі ысырманы ауыстыру",
                                          "Без замены зимой возможна авария", "Ауыстырмаса, қыста апат болуы мүмкін",
                                          "Надёжная подача воды", "Сенімді су беру",
                                          "Наберите воду заранее", "Суды алдын ала жинап алыңыз"))
        self.outage("esil", "heating", "heating", -4, 8, near("esil", "yard"), "Отопление включат позже",
                    "Жылу кейінірек қосылады", ("Промывка труб перед зимой", "Қыс алдында құбырларды жуу",
                                                "Без промывки батареи греют хуже", "Жуусыз батареялар нашар жылытады",
                                                "Ровное тепло всю зиму", "Қыс бойы біркелкі жылу",
                                                "Несколько часов будет прохладно", "Бірнеше сағат салқын болады"))
        self.outage("almaty", "power", "power", 30, 34, near("almaty", "yard"), "Отключение света ночью",
                    "Түнде жарық өшіріледі", ("Замена трансформатора", "Трансформаторды ауыстыру",
                                              "Старый перегружен", "Ескісі шамадан тыс жүктелген",
                                              "Без перепадов напряжения", "Кернеу ауытқуынсыз",
                                              "С 01:00 до 05:00 без света", "01:00-ден 05:00-ге дейін жарық жоқ"))
        self.outage("baikonur", "gas", "gas", 70, 76, near("baikonur", "yard"), "Отключение газа",
                    "Газ өшіріледі", ("Плановая проверка газопровода", "Газ құбырын жоспарлы тексеру",
                                      "Проверка обязательна перед зимой", "Қыс алдында тексеру міндетті",
                                      "Безопасный газ дома", "Үйде қауіпсіз газ",
                                      "Плиты не работают 6 часов", "Плиталар 6 сағат істемейді"))


# ---------------------------------------------------------------- дворы, идеи, инициативы, кризис, встречи, вопросы
def build_yards(b: WorldBuilder, must: list[str], want: int = 32) -> list[dict]:
    rnd = random.Random(f"{b.seed}-yards")
    counts: dict[str, int] = {}
    for c in b.complaints:
        tid = c["target"]["id"]
        if tid.startswith("yard-"):
            counts[tid] = counts.get(tid, 0) + 1
    ranked = sorted(counts, key=lambda t: (-counts[t], t))
    chosen = []
    for tid in list(must) + ranked:
        if tid not in chosen:
            chosen.append(tid)
        if len(chosen) >= want:
            break
    out = []
    for k, tid in enumerate(chosen):
        target = b.inputs.label("area", tid)
        geom = b.inputs.geometry("area", tid)
        area = _ring_area_m2(geom["geometry"]["coordinates"][0])
        members = int(max(6, min(160, area / 260 * rnd.uniform(0.6, 1.4))))
        captain = None
        if k == 0 or rnd.random() < 0.4:
            captain = {"display_name": CAPTAINS[k % len(CAPTAINS)], "since": {"ago_days": rnd.randint(9, 50)}}
        out.append({"id": tid, "osm": "osm-way-" + tid.split("-", 1)[1], "label_ru": target["label_ru"],
                    "label_kk": target["label_kk"], "district": b.inputs.district_of(b.inputs.info[tid]["point"]),
                    "point": [round(v, 6) for v in b.inputs.info[tid]["point"]], "members": members,
                    "captain": captain, "demo": True})
    if out:
        out[0]["members"] = 37   # двор сцены 7: «37 соседей в Birge»
    return out


# Идеи жителей (R06): тексты придуманы. self_doable — «сделайте вместе, поддержим инвентарём» (→ инициатива R16).
IDEAS = (
    # (статус, голоса, вид объекта | None, жители сами?, ru-название, kk-название, ru-описание, kk-описание, язык)
    ("voting", 34, None, True, "Клумбы у подъездов", "Кіреберіс алдындағы гүлзарлар",
     "Хотим посадить цветы у подъездов, нужны саженцы и земля.", "Кіреберістердің алдына гүл отырғызғымыз келеді, "
     "көшет пен топырақ керек.", "ru"),
    ("voting", 58, "sports", False, "Спортплощадка для подростков", "Жасөспірімдерге спорт алаңы",
     "Подросткам негде играть в футбол — играют на парковке.", "Жасөспірімдерге футбол ойнайтын орын жоқ — "
     "тұрақта ойнайды.", "ru"),
    ("voting", 41, "lighting", False, "Свет на дорожке к школе", "Мектепке баратын жолға жарық",
     "Утром зимой дети идут в школу в темноте.", "Қыста таңертең балалар мектепке қараңғыда барады.", "kk"),
    ("voting", 19, None, True, "Покрасить лавочки и беседку", "Орындықтар мен беседканы бояу",
     "Лавочки облезли, покрасим сами, если дадут краску.", "Орындықтардың бояуы түсіп қалған, бояу берсе, "
     "өзіміз бояймыз.", "ru"),
    ("voting", 27, "square", False, "Сквер с деревьями во дворе", "Аулада ағашы бар гүлзар",
     "Во дворе нет тени, летом жарко.", "Аулада көлеңке жоқ, жазда ыстық.", "kk"),
    ("project", 63, "playground", False, "Новая детская площадка", "Жаңа балалар алаңы",
     "Старая площадка опасна, качели шатаются.", "Ескі алаң қауіпті, әткеншектер шайқалады.", "ru"),
    ("project", 45, "lighting", False, "Освещение двора", "Ауланы жарықтандыру",
     "Вечером во дворе темно, нет ни одного фонаря.", "Кешке аула қараңғы, бірде-бір шам жоқ.", "kk"),
    ("rejected", 12, None, False, "Платная парковка во дворе", "Аулада ақылы тұрақ",
     "Сделать шлагбаум и платные места для чужих машин.", "Бөгде көліктерге шлагбаум мен ақылы орын жасау.", "ru"),
    ("rejected", 21, None, True, "Каток с искусственным льдом", "Жасанды мұзы бар каток",
     "Зимой детям негде кататься.", "Қыста балаларға сырғанайтын орын жоқ.", "ru"),
    ("review", 0, None, False, "Велопарковка у подъезда", "Кіреберіс жанында велотұрақ",
     "Велосипеды пристёгивают к деревьям.", "Велосипедтерді ағаштарға байлайды.", "ru"),
    ("review", 0, None, False, "Пандус у подъезда", "Кіреберіске пандус",
     "Маме с коляской трудно спуститься.", "Арбасы бар анаға түсу қиын.", "kk"),
    ("voting", 23, None, True, "Субботник и вывоз старой мебели", "Сенбілік және ескі жиһазды шығару",
     "Во дворе много старой мебели, вынесем вместе, нужен вывоз.", "Аулада ескі жиһаз көп, бірге шығарамыз, "
     "шығарып әкету керек.", "ru"),
)
IDEA_DECISIONS = {
    "Платная парковка во дворе": ("Двор — общая территория дома, платные места в нём не вводятся",
                                  "Аула — үйдің ортақ аумағы, онда ақылы орын енгізілмейді",
                                  "Предложите разметку мест для жителей — её делают по решению собственников",
                                  "Тұрғындарға арналған орындарды белгілеуді ұсыныңыз — оны меншік иелерінің шешімімен жасайды"),
    "Каток с искусственным льдом": ("Искусственный лёд дорого содержать для одного двора",
                                    "Жасанды мұзды бір аулаға ұстау қымбат",
                                    "Залейте обычный каток вместе с соседями — дадим шланг и инвентарь",
                                    "Көршілермен бірге қарапайым каток құйыңыз — шланг пен құрал береміз"),
}


def build_ideas(b: WorldBuilder, yards: list[dict]) -> list[dict]:
    rnd = random.Random(f"{b.seed}-ideas")
    out = []
    for k, (status, votes, obj, self_doable, t_ru, t_kk, d_ru, d_kk, lang) in enumerate(IDEAS):
        yard = yards[(k * 3 + 1) % len(yards)]
        age_d = rnd.uniform(8, 50)
        item = {"id": f"idea-w15-{k + 1:02d}", "status": status, "votes": votes, "district": yard["district"],
                "geometry": {"type": "Point", "coordinates": list(yard["point"])},
                "target": {"kind": "area", "id": yard["id"], "label_ru": yard["label_ru"], "label_kk": yard["label_kk"]},
                "object": {"kind": obj} if obj else None,
                "title_ru": t_ru, "title_kk": t_kk, "description_ru": d_ru, "description_kk": d_kk, "lang": lang,
                "created_at": {"ago_days": _r(age_d)}, "decided_at": None, "check": None,
                "self_doable": self_doable, "to_initiative": None, "demo": True}
        if status in ("project", "rejected"):
            item["decided_at"] = {"ago_days": _r(age_d * rnd.uniform(0.2, 0.6))}
            yes, no = "yes", "no"
            item["check"] = ({"land": yes, "networks": yes, "access": yes, "maintenance": yes} if status == "project"
                             else {"land": yes, "networks": yes, "access": yes, "maintenance": no})
        if t_ru in IDEA_DECISIONS:
            r_ru, r_kk, c_ru, c_kk = IDEA_DECISIONS[t_ru]
            item.update({"reason_ru": r_ru, "reason_kk": r_kk, "can_improve_ru": c_ru, "can_improve_kk": c_kk})
        out.append(item)
    return out


def build_initiatives(b: WorldBuilder, yards: list[dict], ideas: list[dict], scene7_yard: str) -> list[dict]:
    """10 инициатив §5.2: сцена 7 (субботник, 14 → 15), сделанная посадка в том же дворе, расчистка после бурана…"""
    by_id = {y["id"]: y for y in yards}
    others = [y for y in yards if y["id"] != scene7_yard]
    nura = [y for y in others if y["district"] == "nura"]
    def yard_of(district, k):  # noqa: E306
        pool = [y for y in others if y["district"] == district] or others
        return pool[k % len(pool)]
    idea_flowers = ideas[0]
    idea_paint = ideas[3]
    idea_furniture = ideas[11]
    plan = [
        # id, kind, двор, title, text, lang, starts_at, ends_at, bring, status, joined, support, report, from_idea
        ("cleanup", by_id[scene7_yard], "Субботник во дворе", "Соседи, в субботу в 10:00 убираем двор и площадку. "
         "Встречаемся у детской площадки.", "ru", {"next_weekday": {"weekday": 5, "hour": 10, "minute": 0}},
         {"next_weekday": {"weekday": 5, "hour": 13, "minute": 0}}, ["перчатки", "мешки для мусора", "грабли"],
         "published", 14, None, None, None),
        ("greening", by_id[scene7_yard], "Посадим деревья у подъездов", "Сажаем саженцы вдоль дорожки, "
         "нужны лопаты и вода.", "ru", {"ago_days": 26.0}, {"ago_days": 25.85}, ["лопаты", "вёдра"], "done", 15,
         {"by_akimat": True, "inventory": True, "pickup_service": "waste", "note": "Саженцы, лопаты и вывоз мусора"},
         {"text": "Посадили 6 саженцев и покрасили скамейки — сделано вместе: 15 соседей", "photo_ids": [],
          "at": {"ago_days": 25.8}}, None),
        ("snow", nura[0], "Расчистим двор после бурана", "Аулада қар көп, балалар мектепке әрең шығады. Ертең "
         "таңертең бірге тазалайық!", "kk", {"in_hours": 19.0}, {"in_hours": 22.0}, ["күрек", "қолғап"], "published", 9,
         {"by_akimat": True, "inventory": True, "pickup_service": "street_cleaning", "note": "Лопаты и вывоз снега"},
         None, None),
        ("help", nura[1 % len(nura)], "Поможем пожилым соседям в буран", "Пока метёт, принесём продукты и лекарства "
         "соседям старше 70 лет. Пишите в группу двора, кому нужна помощь.", "ru", {"ago_hours": 30.0},
         {"in_hours": 30.0}, ["тёплая одежда"], "published", 6, None, None, None),
        ("repair", yard_of("esil", 0), "Покрасим лавочки и беседку", "Краску обещал акимат, кисти — свои.", "ru",
         {"next_weekday": {"weekday": 6, "hour": 11, "minute": 0}}, {"next_weekday": {"weekday": 6, "hour": 14,
                                                                                         "minute": 0}},
         ["кисти", "перчатки"], "published", 7,
         {"by_akimat": True, "inventory": True, "pickup_service": None, "note": "Краска для лавочек"}, None,
         idea_paint["id"]),
        ("greening", yard_of("saryarka", 0), "Посадка деревьев во дворе", "Отырғызу күні: 12 көшет, барлығы келіңіздер!",
         "kk", {"ago_days": 31.0}, {"ago_days": 30.85}, ["күрек", "шелек"], "done", 22,
         {"by_akimat": True, "inventory": True, "pickup_service": "waste", "note": "Саженцы от службы озеленения"},
         {"text": "Отырғызылды 12 көшет — бірге жасадық: 22 көрші", "photo_ids": [], "at": {"ago_days": 30.8}}, None),
        ("cleanup", yard_of("almaty", 0), "Уборка двора к холодам", "Уберём листья и мусор перед снегом.", "ru",
         {"ago_days": 18.0}, {"ago_days": 17.88}, ["перчатки", "мешки"], "done", 11,
         {"by_akimat": True, "inventory": True, "pickup_service": "waste", "note": "Мешки и вывоз в 14:00"},
         {"text": "Убрали двор и вывезли 30 мешков листьев", "photo_ids": [], "at": {"ago_days": 17.8}}, None),
        ("other", nura[2 % len(nura)], "Зальём каток во дворе", "Как только будет мороз, зальём каток для детей.", "ru",
         {"in_days": 12.0}, {"in_days": 12.2}, ["шланг", "лопаты"], "on_review", 1, None, None, None),
        ("cleanup", yard_of("baikonur", 0), "Субботник у школы", "Перенесли из-за дождя.", "ru", {"ago_days": 5.0},
         {"ago_days": 4.9}, ["перчатки"], "cancelled", 8, None, None, None),
        ("greening", yard_of("saraishyk", 0), "Клумбы у подъездов", "Кіреберістердің алдына гүл отырғызамыз.", "kk",
         {"next_weekday": {"weekday": 5, "hour": 11, "minute": 0}},
         {"next_weekday": {"weekday": 5, "hour": 13, "minute": 0}}, ["көшет", "қолғап"], "published", 5,
         {"by_akimat": True, "inventory": True, "pickup_service": None, "note": "Саженцы и земля"}, None,
         idea_flowers["id"]),
    ]
    out = []
    for k, (kind, yard, title, text, lang, starts, ends, bring, status, joined, support, report, from_idea) in \
            enumerate(plan):
        iid = f"i-w15-{k + 1:02d}"
        out.append({"id": iid, "kind": kind, "title": title, "text": text, "lang": lang,
                    "target": {"kind": "area", "id": yard["id"], "label_ru": yard["label_ru"],
                               "label_kk": yard["label_kk"]},
                    "point": list(yard["point"]), "district": yard["district"], "starts_at": starts, "ends_at": ends,
                    "bring": bring, "status": status, "joined": joined, "support": support, "report": report,
                    "from_idea": from_idea, "demo": True})
        if from_idea:
            for idea in ideas:
                if idea["id"] == from_idea:
                    idea["to_initiative"] = iid
                    # идея и инициатива — про один двор
                    idea["target"] = dict(out[-1]["target"])
                    idea["geometry"] = {"type": "Point", "coordinates": list(yard["point"])}
                    idea["district"] = yard["district"]
    # Идея «вывоз старой мебели» ещё не стала инициативой — её превращают на показе (R06 → R16).
    assert idea_furniture["to_initiative"] is None
    return out


def build_incidents(b: WorldBuilder, yards: list[dict]) -> list[dict]:
    esil_targets = [y["id"] for y in yards if y["district"] == "esil"][:3]
    return [
        {"id": "inc-w15-buran", "kind": "blizzard", "title_ru": "Буран в Нуре", "title_kk": "Нұрада боран",
         "zone": {"kind": "district", "district": "nura", "targets": [], "geometry": None},
         "started_at": {"ago_hours": 62.0}, "status": "active", "event": BURAN["id"],
         "tasks": [
             {"id": "t-1", "service": "street_cleaning", "text_ru": "Расчистить главные улицы и подходы к школам",
              "text_kk": "Басты көшелер мен мектептерге баратын жолдарды тазалау", "status": "doing"},
             {"id": "t-2", "service": "transport", "text_ru": "Автобусы — по зимнему графику, объявления на остановках",
              "text_kk": "Автобустар — қысқы кестемен, аялдамаларда хабарландыру", "status": "doing"},
             {"id": "t-3", "service": "heating", "text_ru": "Дежурные бригады на случай аварий теплосети",
              "text_kk": "Жылу желісіндегі апатқа кезекші бригадалар", "status": "doing"},
             {"id": "t-4", "service": "akimat", "text_ru": "Пункт обогрева и помощь пожилым жителям",
              "text_kk": "Жылыну пункті және егде тұрғындарға көмек", "status": "done"},
         ],
         "updates": [
             {"at": {"ago_hours": 61.0}, "public": True, "text_ru": "Штаб открыт: техника выходит на главные улицы.",
              "text_kk": "Штаб ашылды: техника басты көшелерге шығады."},
             {"at": {"ago_hours": 33.0}, "public": True, "text_ru": "Главные улицы расчищены, дворы — по очереди.",
              "text_kk": "Басты көшелер тазартылды, аулалар — кезекпен."},
             {"at": {"ago_hours": 6.0}, "public": True, "text_ru": "Автобусы ходят по зимнему графику, интервал до 20 минут.",
              "text_kk": "Автобустар қысқы кестемен жүреді, аралығы 20 минутқа дейін."},
         ],
         "result": None, "demo": True},
        {"id": "inc-w15-heat-esil", "kind": "heat_outage", "title_ru": "Авария на теплосети",
         "title_kk": "Жылу желісіндегі апат",
         "zone": {"kind": "targets", "district": "esil", "targets": esil_targets, "geometry": None},
         "started_at": {"ago_days": 16.2}, "status": "closed", "event": None,
         "tasks": [{"id": "t-1", "service": "heating", "text_ru": "Найти и устранить порыв",
                    "text_kk": "Жарылған жерді тауып, жөндеу", "status": "done"},
                   {"id": "t-2", "service": "water", "text_ru": "Проверить подвалы на подтопление",
                    "text_kk": "Жертөлелерді су басуын тексеру", "status": "done"}],
         "updates": [{"at": {"ago_days": 16.1}, "public": True, "text_ru": "Порыв найден, бригада работает.",
                      "text_kk": "Жарылған жер табылды, бригада жұмыс істеп жатыр."},
                     {"at": {"ago_days": 15.6}, "public": True, "text_ru": "Тепло возвращается в дома.",
                      "text_kk": "Үйлерге жылу қайтып келеді."}],
         "result": {"text_ru": "Тепло дали через 14 часов, подвалы сухие.",
                    "text_kk": "Жылу 14 сағаттан кейін берілді, жертөлелер құрғақ."}, "demo": True},
        {"id": "inc-w15-water-almaty", "kind": "water_outage", "title_ru": "Прорыв водопровода",
         "title_kk": "Су құбырының жарылуы",
         "zone": {"kind": "district", "district": "almaty", "targets": [], "geometry": None},
         "started_at": {"ago_days": 33.0}, "status": "closed", "event": None,
         "tasks": [{"id": "t-1", "service": "water", "text_ru": "Перекрыть и заменить участок трубы",
                    "text_kk": "Құбыр бөлігін жауып, ауыстыру", "status": "done"},
                   {"id": "t-2", "service": "road", "text_ru": "Восстановить покрытие после раскопки",
                    "text_kk": "Қазудан кейін жабынды қалпына келтіру", "status": "done"}],
         "updates": [{"at": {"ago_days": 32.9}, "public": True, "text_ru": "Подвоз воды — у школы, с 12:00.",
                      "text_kk": "Су тасу — мектеп жанында, 12:00-ден бастап."}],
         "result": {"text_ru": "Воду дали вечером того же дня, асфальт восстановлен через 5 дней.",
                    "text_kk": "Су сол күні кешке берілді, асфальт 5 күннен кейін қалпына келтірілді."}, "demo": True},
    ]


QUESTIONS = (
    # (район, язык, текст, голоса, опубликован (дней назад), ответ ru, ответ kk, встреча)
    ("nura", "ru", "Когда во дворах Нуры будут убирать снег так же быстро, как на главных улицах?", 46, 1.5, None, None, 2),
    ("nura", "kk", "Буран кезінде автобустар неге кешігеді, кесте қайда жазылады?", 31, 1.2, None, None, 2),
    ("nura", "ru", "Будет ли свет на дорожке к школе до зимы?", 27, 4.0, None, None, 2),
    ("nura", "ru", "Можно ли сделать во дворах площадки для выгула собак?", 12, 6.0, None, None, 2),
    ("nura", "ru", "Почему после раскопок на нашей улице до сих пор яма?", 38, 14.0,
     "Водоканал закончил работы, восстановление асфальта передано дорожной службе — срок до конца месяца.",
     "Су қызметі жұмысты аяқтады, асфальтты қалпына келтіру жол қызметіне берілді — ай соңына дейін.", 1),
    ("nura", "kk", "Ауладағы балалар алаңын қашан жөндейді?", 29, 15.0,
     "Площадку отремонтировали, жители уже проверили ремонт.",
     "Алаң жөнделді, тұрғындар жөндеуді тексерді.", 1),
    ("esil", "ru", "Когда закончат ремонт теплотрассы у нас во дворе?", 18, 3.0, None, None, 3),
    ("esil", "kk", "Аулаға қосымша қоқыс жәшіктері қойыла ма?", 9, 2.0, None, None, 3),
    ("almaty", "ru", "Кто отвечает за освещение во дворе, если фонари ничьи?", 14, 9.0,
     "Вопрос вынесен на решение акима: принять опоры на баланс района или передать собственникам.",
     "Мәселе әкімнің шешіміне шығарылды: тіректерді аудан балансына алу немесе меншік иелеріне беру.", None),
    ("saryarka", "ru", "Можно ли продлить вечерние рейсы автобуса?", 0, 0.2, None, None, None),
)


def build_meetings_questions(b: WorldBuilder, yards: list[dict], works: list[dict]) -> tuple[list[dict], list[dict]]:
    nura_yards = [y for y in yards if y["district"] == "nura"]
    esil_yards = [y for y in yards if y["district"] == "esil"]
    questions = []
    for k, (district, lang, text, votes, pub_d, ans_ru, ans_kk, meeting) in enumerate(QUESTIONS):
        q = {"id": f"q-w15-{k + 1:02d}", "district": district, "lang": lang, "text": text,
             "status": "pending" if votes == 0 else "published",
             "created_at": {"ago_days": _r(pub_d + 0.1)}, "published_at": None if votes == 0 else {"ago_days": _r(pub_d)},
             "base_votes": votes, "answer_ru": ans_ru, "answer_kk": ans_kk,
             "answered_at": {"ago_days": _r(max(0.3, pub_d - 2))} if ans_ru else None,
             "meeting": f"m-w15-{meeting}" if meeting else None, "demo": True}
        questions.append(q)

    def pick(pred):
        for c in b.complaints:
            if pred(c):
                return c
        return None

    c_light = pick(lambda c: c["district"] == "nura" and c["category"] == "lighting" and c["status"] == "in_progress"
                   and not c.get("scene"))
    c_play = pick(lambda c: c.get("scene") == "scene7" and c["category"] == "yards")
    c_pit = pick(lambda c: c["district"] == "nura" and c["category"] == "roads" and c["status"] == "fixed"
                 and not c.get("scene"))
    w_road = next(w for w in works if w.get("district") == "nura" and w.get("kind") == "surface"
                  and w.get("status") == "planned" and not w.get("scene"))
    orders = [
        {"id": "o-1", "text_ru": "Отремонтировать детскую площадку во дворе", "text_kk": "Ауладағы балалар алаңын жөндеу",
         "service": "landscaping", "due": {"day": -10}, "status": "done",
         "link": {"kind": "complaint", "id": c_play["id"]} if c_play else None},
        {"id": "o-2", "text_ru": "Восстановить освещение улицы", "text_kk": "Көше жарығын қалпына келтіру",
         "service": "lighting", "due": {"day": 5}, "status": "in_progress",
         "link": {"kind": "complaint", "id": c_light["id"]} if c_light else None},
        {"id": "o-3", "text_ru": "Заделать ямы на улице после раскопок", "text_kk": "Қазудан кейінгі шұңқырларды жабу",
         "service": "road", "due": {"day": -2}, "status": "done",
         "link": {"kind": "complaint", "id": c_pit["id"]} if c_pit else None},
        {"id": "o-4", "text_ru": "Включить улицу в план ремонта покрытия", "text_kk": "Көшені жабын жөндеу жоспарына енгізу",
         "service": "road", "due": {"day": 20}, "status": "todo", "link": {"kind": "work", "id": w_road["id"]}},
    ]
    q_of = lambda m: [q["id"] for q in questions if q["meeting"] == m]  # noqa: E731
    meetings = [
        {"id": "m-w15-1", "district": "nura", "title_ru": "Встреча акима района с жителями Нуры",
         "title_kk": "Аудан әкімінің Нұра тұрғындарымен кездесуі", "at": {"ago_days": 12.3},
         "place": {"kind": "area", "id": nura_yards[0]["id"], "label_ru": nura_yards[0]["label_ru"],
                   "label_kk": nura_yards[0]["label_kk"]},
         "registered": 54, "questions": q_of("m-w15-1"), "orders": orders, "demo": True},
        {"id": "m-w15-2", "district": "nura", "title_ru": "Встреча акима района: зима во дворах",
         "title_kk": "Аудан әкімімен кездесу: аулалардағы қыс",
         "at": {"next_weekday": {"weekday": 3, "hour": 18, "minute": 30}},
         "place": {"kind": "area", "id": nura_yards[1]["id"], "label_ru": nura_yards[1]["label_ru"],
                   "label_kk": nura_yards[1]["label_kk"]},
         "registered": 31, "questions": q_of("m-w15-2"), "orders": [], "demo": True},
        {"id": "m-w15-3", "district": "esil", "title_ru": "Встреча акима района с жителями Есиля",
         "title_kk": "Аудан әкімінің Есіл тұрғындарымен кездесуі", "at": {"in_days": 9.3},
         "place": {"kind": "area", "id": esil_yards[0]["id"], "label_ru": esil_yards[0]["label_ru"],
                   "label_kk": esil_yards[0]["label_kk"]},
         "registered": 12, "questions": q_of("m-w15-3"), "orders": [], "demo": True},
    ]
    return meetings, questions


# ---------------------------------------------------------------- сборка мира
def build_world(seed: int = SEED) -> dict:
    b = WorldBuilder(seed)
    scenes = Scenes(b)
    scenes.step2_khan_shatyr()
    yard7 = scenes.scene7_yard()
    scene8 = scenes.scene8_street()
    b.stream()
    b.finish_statuses()
    b.resolutions()
    b.joint_parts()
    b.passports()
    # Сцена 7: площадка двора отремонтирована и проверена жителями (история «до/после» на странице двора).
    for c in b.complaints:
        if c.get("scene") == "scene7" and c["category"] == "yards":
            _force_fixed(c, fixed_h=c["_age"] - 4 * 24, verified_h=c["_age"] - 5.5 * 24, what="Отремонтировали площадку")
    works = Works(b)
    works.build(scene8)
    yards = build_yards(b, [yard7])
    ideas = build_ideas(b, yards)
    initiatives = build_initiatives(b, yards, ideas, yard7)
    incidents = build_incidents(b, yards)
    meetings, questions = build_meetings_questions(b, yards, works.items)
    complaints = sorted((strip_private(c) for c in b.complaints), key=lambda c: c["id"])
    scenes.out["scene7"].update({"initiative": "i-w15-01", "initiative_done": "i-w15-02", "joined_before": 14,
                                 "joined_after": 15, "support": {"inventory": True, "pickup_service": "waste",
                                                                 "note": "Мешки и вывоз в 14:00"}})
    scenes.out["scene9"] = {"incident": "inc-w15-buran", "event": BURAN["id"], "district": "nura",
                            "category": "snow_ice", "pulse": "расчёт — EXPECTED.json → scene9"}
    world = {
        "schema": wio.SCHEMA_ID, "schema_version": SCHEMA_VERSION, "seed": seed, "synthetic": True, "demo": True,
        "generator": "ml/datasets/demo_world.py",
        "note_ru": "Синтетический демо-мир Birge: все записи придуманы (demo: true, «Пример»). Настоящие — только "
                   "цели OpenStreetMap (ODbL, © OpenStreetMap contributors). Время — относительно засева.",
        "inputs": {str(p.relative_to(ROOT)): _sha(p) for p in (CATEGORIES_JSON, R07_TARGETS, YARDS_JSON, OBJECTS_JSON,
                                                               GRAPH_MANIFEST)},
        "counts": {},
        "districts": [{"id": d, "ru": DISTRICT_NAMES[d][0], "kk": DISTRICT_NAMES[d][1]} for d in DISTRICTS],
        "services": [{"id": sid, "ru": names["ru"], "kk": names["kk"]}
                     for sid, names in b.inputs.lifecycle.SERVICES.items()],
        "events": [dict(e, demo=True) for e in EVENTS],
        "yards": yards, "complaints": complaints, "works": works.items, "planned_conflicts": works.conflicts,
        "ideas": ideas, "initiatives": initiatives, "incidents": incidents, "meetings": meetings,
        "questions": questions, "scenes": scenes.out,
    }
    world["counts"] = {k: len(world[k]) for k in ("yards", "complaints", "works", "planned_conflicts", "ideas",
                                                 "initiatives", "incidents", "meetings", "questions", "events")}
    return world


def _force_fixed(c: dict, *, fixed_h: float, verified_h: float, what: str) -> None:
    hist = c["status_history"][:1]
    age = c["_age"]
    hist += [{"at": ago_h(age - 3), "status": "accepted"}, {"at": ago_h(age - 30), "status": "in_progress"},
             {"at": ago_h(fixed_h), "status": "fixed"}]
    c["status"], c["status_history"] = "fixed", hist
    c["resolution"] = {"round": 1, "state": "verified", "reported_at": ago_h(fixed_h), "what_done": what,
                       "by": "service", "photos_after": [], "votes": {"yes": 2, "no": 0, "cant": 0},
                       "verified_at": ago_h(verified_h), "reopened_at": None, "reopen_count": 0}
    c["updates"] = [{"at": ago_h(fixed_h), "kind": "fixed", "text": what}]


# ---------------------------------------------------------------- образец для ролей
SAMPLE_SIZE = 15


def sample_of(world: dict) -> dict:
    """Образец: те же записи, что в мире (не выдуманные отдельно), по 10–20 каждого вида + всё, на что ссылаются сцены."""
    out = {k: v for k, v in world.items() if not isinstance(v, list) or k in ("districts", "services", "events")}
    scene_ids = set()
    for scene in world["scenes"].values():
        for value in scene.values():
            if isinstance(value, str):
                scene_ids.add(value)
            elif isinstance(value, list):
                scene_ids.update(v for v in value if isinstance(v, str))
    cs = world["complaints"]
    picked = [c for c in cs if c["id"] in scene_ids]
    # разнообразие: по одному каждого статуса, совместная, с передачей, «проверено», «вернули», «нужно решение»
    want = [lambda c: c["status"] == "new", lambda c: c["status"] == "accepted", lambda c: c["status"] == "in_progress",
            lambda c: c["status"] == "fixed", lambda c: c["status"] == "rejected", lambda c: bool(c.get("services")),
            lambda c: bool(c.get("handoffs")), lambda c: (c.get("resolution") or {}).get("state") == "verified",
            lambda c: (c.get("resolution") or {}).get("state") == "reopened",
            lambda c: ((c.get("passport") or {}).get("delay") or {}).get("needs_decision") is True,
            lambda c: c.get("event") == BURAN["id"], lambda c: c["lang"] == "kk", lambda c: c["lang"] == "mixed"]
    for pred in want:
        for c in cs:
            if pred(c) and c not in picked:
                picked.append(c)
                break
    out["complaints"] = sorted(picked, key=lambda c: c["id"])[:max(20, len(picked))]
    for key in ("yards", "works", "planned_conflicts", "ideas", "initiatives", "incidents", "meetings", "questions"):
        items = world[key]
        chosen = [x for x in items if x["id"] in scene_ids]
        for x in items:
            if len(chosen) >= SAMPLE_SIZE:
                break
            if x not in chosen:
                chosen.append(x)
        out[key] = chosen
    _close_references(out, world)
    out["sample"] = True
    out["sample_note_ru"] = ("Образец — подмножество world_v1.json (те же записи и id). Ссылки на записи вне образца "
                             "(например, работа в поручении встречи) могут вести в полный мир.")
    out["counts"] = {k: len(out[k]) for k in world["counts"]}
    return out


def _close_references(out: dict, world: dict) -> None:
    """Образец замкнут: всё, на что ссылаются его записи (двор инициативы, жалоба в поручении, работы конфликта,
    идея ↔ инициатива, вопросы встречи), тоже в образце — тесты ролей не упираются в «нет такой записи»."""
    index = {key: {x["id"]: x for x in world[key]} for key in ("yards", "complaints", "works", "ideas", "initiatives",
                                                                "questions", "meetings", "incidents")}
    def need(key, item_id):  # noqa: E306
        if item_id in index[key] and all(x["id"] != item_id for x in out[key]):
            out[key].append(index[key][item_id])
            return True
        return False
    changed = True
    while changed:
        changed = False
        for i in list(out["initiatives"]):
            changed |= need("yards", i["target"]["id"])
            if i.get("from_idea"):
                changed |= need("ideas", i["from_idea"])
        for idea in list(out["ideas"]):
            if (idea.get("target") or {}).get("id"):
                changed |= need("yards", idea["target"]["id"])
            if idea.get("to_initiative"):
                changed |= need("initiatives", idea["to_initiative"])
        for m in list(out["meetings"]):
            if m["place"]["id"].startswith("yard-"):
                changed |= need("yards", m["place"]["id"])
            for q in m.get("questions") or []:
                changed |= need("questions", q)
            for o in m.get("orders") or []:
                link = o.get("link") or {}
                if link.get("kind") == "complaint":
                    changed |= need("complaints", link["id"])
                elif link.get("kind") == "work":
                    changed |= need("works", link["id"])
        for q in list(out["questions"]):
            if q.get("meeting"):
                changed |= need("meetings", q["meeting"])
        for cf in list(out["planned_conflicts"]):
            for wid in cf["works"]:
                changed |= need("works", wid)
        for inc in list(out["incidents"]):
            for tid in inc["zone"].get("targets") or []:
                if tid.startswith("yard-"):
                    changed |= need("yards", tid)
    for key in index:
        out[key].sort(key=lambda x: x["id"])


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def summary(world: dict) -> str:
    from collections import Counter
    cs = world["complaints"]
    lines = [f"жалоб {len(cs)}; людей (жалобы + «Я тоже») {sum(1 + c['metoo'] for c in cs)}"]
    by_d = Counter(c["district"] for c in cs)
    lines.append("районы: " + ", ".join(f"{d} {by_d[d]} ({by_d[d] / len(cs):.0%})" for d in DISTRICTS))
    lines.append("статусы: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(c["status"] for c in cs).items())))
    lines.append("категории: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(c["category"] for c in cs).items())))
    lines.append("языки: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(c["lang"] for c in cs).items())))
    res = Counter((c.get("resolution") or {}).get("state") for c in cs if c.get("resolution"))
    lines.append(f"проверено жителями {res['verified']} ({res['verified'] / len(cs):.1%}), ждут проверки "
                 f"{res['reported']}, вернули {res['reopened']}; совместных {sum(1 for c in cs if c.get('services'))}; "
                 f"с передачей {sum(1 for c in cs if c.get('handoffs'))}")
    lines.append("прочее: " + ", ".join(f"{k} {v}" for k, v in world["counts"].items() if k != "complaints"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Демо-мир Астаны (R02, раунд 15) — синтетика, seed 15, без сети")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--check", action="store_true", help="сверить пересборку с файлом (воспроизводимость)")
    ap.add_argument("--summary", action="store_true", help="только сводка")
    args = ap.parse_args(argv)
    world = build_world(args.seed)
    text = dump(world)
    if args.summary:
        print(summary(world))
        return 0
    path = args.out / "world_v1.json"
    if args.check:
        have = path.read_text(encoding="utf-8") if path.exists() else ""
        same = hashlib.sha256(have.encode()).hexdigest() == hashlib.sha256(text.encode()).hexdigest()
        print(("OK: " if same else "РАЗЛИЧАЕТСЯ: ") + f"{path} sha256 {hashlib.sha256(text.encode()).hexdigest()}")
        return 0 if same else 1
    args.out.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    (args.out / "world_v1.sample.json").write_text(dump(sample_of(world)), encoding="utf-8")
    print(summary(world))
    print(f"записано: {path} ({len(text.encode()) // 1024} КБ), sha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
