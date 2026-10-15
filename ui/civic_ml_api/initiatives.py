"""similar_initiatives(text, point, days) — похожая инициатива соседей рядом (для R16: «Присоединиться к существующей»).

    from ui.civic_ml_api import similar_initiatives
    similar_initiatives("Субботник во дворе в субботу", [71.41, 51.10], 30)
    # -> {"items": [{"id": "i-…", "score": 0.71, "distance_m": 140, "kind": "cleanup", "title": "…", "starts_at": "…",
    #                "joined": 14, "why_ru": "Тоже уборка двора, 140 м, 18 окт", "why_kk": "…"}], "source": "r16", …}

Правило (как у поиска дублей жалоб раунда 14, но для дел соседей):
    похожая = опубликована И ещё не прошла И начинается не позже чем через days дней И ближе radius_m (800 м)
              И (сходство текста ≥ 0.30 ИЛИ то же дело по смыслу: «субботник» = «уборка» = «сенбілік»).
Сходство — n-граммы символов (ml.civic_dedup.scorers, как у дублей) + словарь видов дел ru/kk (INIT_CONCEPTS ниже):
    score = 0.6 · косинус n-грамм + 0.4 · совпадение видов дел (+0.1, если тот же kind) − штраф за расстояние.

Откуда инициативы (первое, что есть):
    1. records=[…] — список записей CONTRACT §5.2, если сосед передал его сам;
    2. set_initiative_source(fn) — функция fn(point, radius_m, days) -> list[dict], которую подключил R01 или R16;
    3. ui.civic_together.default_service().store.list(...) — только чтение опубликованных (TogetherStore R16);
    4. ничего нет — {"items": [], "source": "not_connected"} (R16 показывает свои «рядом и того же вида»).
Наружу — только id, вид, публичный заголовок, дата, число «Я приду» и расстояние; тексты и авторы не отдаются.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone

from ml.civic_dedup.normalize import normalize
from ml.civic_dedup.scorers import _ngram_vector, sparse_cosine

LOGGER = logging.getLogger(__name__)
VERSION = "r04-similar-initiatives-1"
ASTANA_TZ = timezone(timedelta(hours=5))
DEFAULT_DAYS = 30
MAX_DAYS = 120
RADIUS_M = 800.0
MIN_SCORE = 0.30
LIMIT = 3
LIVE = ("published",)

# Виды дел соседей: понятие -> сведённые корни ru/kk (как normalize: қ -> к, і -> и, й -> и).
# Корень из 3 букв и короче («кар» — снег, «лед», «муз») совпадает только с целым словом: иначе «кар» поймал бы
# «карта», а «карт» (қарт — пожилой) — «картина». «Сосед» и «площадка» не понятия: они есть почти в каждом деле.
INIT_CONCEPTS = {
    "cleanup": ("субботник", "уборк", "убрат", "убира", "чистот", "мусор", "сенбилик", "тазала", "тазалык", "кокыс",
                "жинау"),
    "greening": ("посад", "сажа", "саженц", "дерев", "озелен", "клумб", "цвет", "газон", "агаш", "отыргыз", "кошет",
                 "когалдандыр", "гул"),
    "snow": ("снег", "сугроб", "расчист", "гололед", "лед", "кар", "карды", "муз", "куреу"),
    "repair": ("ремонт", "покрас", "почин", "лавочк", "скамей", "забор", "качел", "жонде", "сырла", "орындык",
               "коршау"),
    "help": ("помощ", "помочь", "пожил", "пенсионер", "ветеран", "комек", "карт", "карттар", "зейнеткер"),
}
_WORD = re.compile(r"\w+")

_source = None   # set_initiative_source


def set_initiative_source(fn) -> None:
    """Подключить источник инициатив: fn(point, radius_m, days) -> list[dict] (записи §5.2). None — отключить."""
    global _source
    _source = fn


def _concepts(norm: str) -> frozenset:
    words = _WORD.findall(norm)
    found = set()
    for concept, roots in INIT_CONCEPTS.items():
        if any((w == root) if len(root) <= 4 else w.startswith(root) for w in words for root in roots):
            found.add(concept)
    return frozenset(found)


def _point(value):
    if value is None:
        return None
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        raise ValueError("point: нужна точка [lon, lat].")
    lon, lat = float(value[0]), float(value[1])
    if not (70.9 <= lon <= 72.0 and 50.8 <= lat <= 51.5):
        raise ValueError("point: точка вне Астаны.")
    return lon, lat


def _distance_m(a, b) -> float:
    lat0 = math.radians((a[1] + b[1]) / 2)
    dx = (a[0] - b[0]) * 111_320.0 * math.cos(lat0)
    dy = (a[1] - b[1]) * 110_574.0
    return math.hypot(dx, dy)


def _parse_time(value):
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA_TZ)


def _record_point(rec: dict):
    point = rec.get("point")
    if isinstance(point, (list, tuple)) and len(point) == 2:
        return float(point[0]), float(point[1])
    if isinstance(rec.get("lon"), (int, float)) and isinstance(rec.get("lat"), (int, float)):
        return float(rec["lon"]), float(rec["lat"])
    return None


def _public_title(rec: dict) -> str:
    """Публичный заголовок (после модерации R16) — его и сравниваем, и отдаём."""
    return str(rec.get("title_public") or rec.get("title") or "")[:160]


def _public_text(rec: dict) -> str:
    return str(rec.get("text_public") or rec.get("text") or "")[:600] if rec.get("text_public") or rec.get("text") else ""


def _from_r16(point, radius_m: float, days: int) -> list[dict] | None:
    """Опубликованные инициативы R16 в прямоугольнике вокруг точки (только чтение через TogetherStore)."""
    try:
        from ui.civic_together import default_service
    except Exception:  # noqa: BLE001 — модуля R16 нет в сборке
        return None
    try:
        service = default_service()
        store = getattr(service, "store", None)
        if store is None:
            return None
        dlat = radius_m / 110_574.0
        dlon = radius_m / (111_320.0 * math.cos(math.radians(point[1])))
        bbox = (point[0] - dlon, point[1] - dlat, point[0] + dlon, point[1] + dlat)
        return list(store.list(statuses=LIVE, bbox=bbox, upcoming_only=True, limit=60))
    except Exception:  # noqa: BLE001 — сбой соседа: похожих просто нет
        LOGGER.warning("similar_initiatives: R16 не ответил", exc_info=True)
        return None


def _when_label(moment) -> tuple[str, str]:
    if moment is None:
        return "", ""
    months_ru = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
    months_kk = ("қаң", "ақп", "нау", "сәу", "мам", "мау", "шіл", "там", "қыр", "қаз", "қар", "жел")
    local = moment.astimezone(ASTANA_TZ)
    return f"{local.day} {months_ru[local.month - 1]}", f"{local.day} {months_kk[local.month - 1]}"


_KIND_RU = {"cleanup": "уборка", "greening": "озеленение", "snow": "расчистка снега", "repair": "ремонт",
            "help": "помощь соседям"}
_KIND_KK = {"cleanup": "тазалық", "greening": "көгалдандыру", "snow": "қар тазалау", "repair": "жөндеу",
            "help": "көршілерге көмек"}


def similar_initiatives(text, point=None, days=DEFAULT_DAYS, *, records=None, kind=None, radius_m=RADIUS_M,
                        limit=LIMIT, now=None, exclude_id=None, body=None, **_ignored) -> dict:
    """Похожие инициативы рядом. text — заголовок (и описание) новой инициативы; point — [lon, lat]; days — окно."""
    if isinstance(body, dict):
        text = body.get("text", text)
        point = body.get("point", point)
        days = body.get("days", days)
        kind = body.get("kind", kind)
    if not isinstance(text, str) or len(text.strip()) < 3:
        raise ValueError("text: нужен заголовок инициативы (от 3 символов).")
    if isinstance(days, bool) or not isinstance(days, (int, float)):
        raise ValueError("days: число дней.")
    days = max(1, min(MAX_DAYS, int(days)))
    where = _point(point)
    moment = now or datetime.now(ASTANA_TZ)
    base = {"items": [], "radius_m": radius_m, "days": days, "method": VERSION}
    if where is None:
        return {**base, "source": "no_point"}

    source = "records"
    rows = records
    if rows is None and _source is not None:
        try:
            rows, source = list(_source(list(where), radius_m, days) or []), "registered"
        except Exception:  # noqa: BLE001
            LOGGER.warning("similar_initiatives: подключённый источник упал", exc_info=True)
            rows = None
    if rows is None:
        rows, source = _from_r16(where, radius_m, days), "r16"
    if rows is None:
        return {**base, "source": "not_connected"}

    query_norm = normalize(text[:600])
    query_vec = _ngram_vector(query_norm, 3, 5)
    query_concepts = _concepts(query_norm)
    horizon = moment + timedelta(days=days)
    items = []
    for rec in rows:
        if not isinstance(rec, dict) or rec.get("id") in (None, exclude_id):
            continue
        if rec.get("status", "published") not in LIVE:
            continue
        start = _parse_time(rec.get("starts_at"))
        end = _parse_time(rec.get("ends_at")) or (start + timedelta(hours=3) if start else None)
        if start is not None and (start > horizon or (end is not None and end < moment)):
            continue
        rp = _record_point(rec)
        if rp is None:
            continue
        dist = _distance_m(where, rp)
        if dist > radius_m:
            continue
        rec_norm = normalize((_public_title(rec) + " " + _public_text(rec))[:800])
        ng = sparse_cosine(query_vec, _ngram_vector(rec_norm, 3, 5))
        rec_concepts = _concepts(rec_norm) | ({rec["kind"]} if rec.get("kind") in INIT_CONCEPTS else set())
        q_concepts = query_concepts | ({kind} if kind in INIT_CONCEPTS else set())
        overlap = len(q_concepts & rec_concepts) / len(q_concepts | rec_concepts) if q_concepts and rec_concepts else 0.0
        same_kind = bool(kind) and rec.get("kind") == kind
        score = 0.6 * ng + 0.4 * overlap + (0.1 if same_kind else 0.0) - 0.1 * (dist / radius_m)
        if score < MIN_SCORE and not (overlap >= 0.5 and dist <= radius_m / 2):
            continue
        when_ru, when_kk = _when_label(start)
        rkind = rec.get("kind") if rec.get("kind") in _KIND_RU else next(iter(sorted(rec_concepts & set(_KIND_RU))), None)
        what_ru = f"Тоже {_KIND_RU[rkind]}" if rkind and rkind in q_concepts else "Похожее дело"
        what_kk = f"Бұл да {_KIND_KK[rkind]}" if rkind and rkind in q_concepts else "Ұқсас іс"
        tail_ru = ", ".join(x for x in (f"{round(dist)} м", when_ru) if x)
        tail_kk = ", ".join(x for x in (f"{round(dist)} м", when_kk) if x)
        items.append({"id": rec["id"], "score": round(max(0.0, min(1.0, score)), 3), "distance_m": round(dist),
                      "kind": rec.get("kind"), "title": _public_title(rec), "starts_at": rec.get("starts_at"),
                      "joined": rec.get("joined") if isinstance(rec.get("joined"), int) else None,
                      "why_ru": f"{what_ru}, {tail_ru}", "why_kk": f"{what_kk}, {tail_kk}"})
    items.sort(key=lambda item: (-item["score"], item["distance_m"]))
    return {**base, "items": items[:max(1, int(limit))], "source": source}
