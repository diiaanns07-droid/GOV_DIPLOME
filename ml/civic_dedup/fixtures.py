"""Синтетические обращения (demo: true) для замера скорости, тестов и стенда без базы.

Тексты — короткие фразы R04 на ru/kk (не реальные жители). Точки — случайные внутри района,
цели — условные id по CONTRACT §4 (segment/object/area). Генератор детерминирован (seed).
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from ml.civic_dedup.search import ASTANA_TZ

# (категория, тексты) — по 3–4 формулировки на тему, чтобы были и дубли, и разные проблемы.
PHRASES = {
    "roads": ["Большая яма на дороге, машины объезжают по встречке", "Жолда үлкен шұңқыр бар, көліктер айналып өтеді",
              "Разбит асфальт на проезжей части", "Не работает светофор на перекрёстке"],
    "snow_ice": ["Не убран снег на остановке, люди падают", "Аялдамада қар тазаланбаған, тайғақ",
                 "Гололёд на тротуаре, ничем не посыпано", "С крыши свисают сосульки над входом"],
    "sidewalks": ["Разбита плитка на тротуаре", "Жаяу жүргінші жолында плитка сынған",
                  "Нет пандуса, коляска не проезжает", "Высокий бордюр на переходе"],
    "transport": ["На остановке нет навеса, люди стоят под дождём", "Аялдамада шатыр жоқ, адамдар жаңбырда тұрады",
                  "Автобус 21 не приходит по расписанию", "Не работает табло на остановке"],
    "lighting": ["Во дворе не горят фонари, очень темно", "Ауладағы шамдар жанбайды, қараңғы",
                 "Фонарь мигает всю ночь", "Нет освещения на пешеходной дорожке"],
    "yards": ["Сломаны качели на детской площадке", "Балалар алаңындағы әткеншек сынған",
              "Спилили деревья во дворе", "Сломана скамейка во дворе"],
    "waste": ["Мусорные баки переполнены, не вывозят неделю", "Қоқыс жәшіктері толып кетті, шығарылмайды",
              "Стихийная свалка за гаражами"],
    "utilities": ["Нет горячей воды третий день", "Ыстық су үш күннен бері жоқ", "В квартире холодно, батареи еле тёплые"],
    "smell_air": ["Сильный запах гари по вечерам", "Кешке қатты түтін иісі шығады", "Пыль от стройки, невозможно дышать"],
    "noise_safety": ["Стая бездомных собак у школы", "Мектептің жанында қаңғыбас иттер жүр", "Громкая музыка по ночам"],
    "parking": ["Машины паркуются на газоне во дворе", "Аулада көліктер көгалға тұрады", "Брошенная машина стоит полгода"],
    "other": ["Спасибо за ремонт двора", "Подскажите, когда откроют поликлинику"],
}
NURA_CENTER = (71.42, 51.09)   # условный центр района Нура (для синтетики)
CITY_BOX = (71.30, 51.05, 71.55, 51.20)
STATUSES = ("new", "new", "new", "accepted", "in_progress", "fixed", "rejected")


def offset(point: tuple[float, float], dx_m: float, dy_m: float) -> list[float]:
    lon, lat = point
    return [round(lon + dx_m / (111_320.0 * math.cos(math.radians(lat))), 7), round(lat + dy_m / 111_320.0, 7)]


def make_records(n: int, *, seed: int = 20261011, now: datetime | None = None, box=CITY_BOX,
                 hotspot: tuple[float, float] | None = None, hotspot_radius_m: float = 150.0,
                 n_targets: int | None = None, max_age_days: int = 30, texts: list[str] | None = None) -> list[dict]:
    """n записей CONTRACT §5. hotspot — все точки в круге hotspot_radius_m (худший случай для поиска)."""
    rng = random.Random(seed)
    now = now or datetime.now(ASTANA_TZ)
    pool = texts or [(cat, t) for cat, ts in PHRASES.items() for t in ts]
    n_targets = n_targets or max(1, n // 10)
    out = []
    for i in range(n):
        item = rng.choice(pool)
        cat, text = item if isinstance(item, tuple) else ("other", item)
        if hotspot is not None:
            r = hotspot_radius_m * math.sqrt(rng.random())
            a = rng.random() * 2 * math.pi
            point = offset(hotspot, r * math.cos(a), r * math.sin(a))
        else:
            point = [round(rng.uniform(box[0], box[2]), 7), round(rng.uniform(box[1], box[3]), 7)]
        created = now - timedelta(days=rng.uniform(0, max_age_days))
        tnum = rng.randrange(n_targets)
        kind = ("segment", "object", "area")[tnum % 3]
        tid = {"segment": f"osm-w{100000 + tnum}-1", "object": f"osm-node-{900000 + tnum}", "area": f"cell-{tnum}"}[kind]
        status = rng.choice(STATUSES)
        out.append({
            "id": f"c-demo{i:06d}", "created_at": created.replace(microsecond=0).isoformat(), "text": text,
            "lang": "ru", "category": cat, "category_source": "resident", "model": None,
            "point": point, "target": {"kind": kind, "id": tid}, "district": "nura", "status": status,
            "status_history": [{"at": created.replace(microsecond=0).isoformat(), "status": status}],
            "metoo": rng.choice((0, 0, 0, 1, 2, 5)), "duplicate_of": None, "demo": True,
        })
    return out
