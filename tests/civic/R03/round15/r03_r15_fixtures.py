"""Фикстуры R03 раунда 15: соседи-заглушки строго в форматах CONTRACT §5 (пока их модулей нет в сборке).

Числа здесь выбраны так, чтобы их было легко проверить глазами; ни одно не берётся из реальных обращений.
Модуль с уникальным именем (не conftest): тесты разных ролей запускаются вместе (просьба R01, раунд 14).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
for _p in (str(ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ASTANA = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=ASTANA)
STAFF = {"username": "operator", "role": "editor"}
# Текст жителя с персональными данными: не должен появиться ни в одном ответе аналитика.
RESIDENT_TEXT = "Снег не убран у подъезда, звоните 8 701 555 12 34, ИИН 900101300123"


def _target(kind, tid, ru, kk):
    return {"kind": kind, "id": tid, "label_ru": ru, "label_kk": kk}


HEAT_TARGETS = [
    {"target": _target("segment", "osm-w100-1", "Участок ул. Е-308", "Е-308 көшесінің бөлігі"), "count": 8, "level": 3,
     "color": "#E24B4A", "weight": 7.8, "state": "active", "district": "nura", "category": "snow_ice",
     "by_category": {"snow_ice": 8}, "anchor": [71.35, 51.1], "demo": True},
    {"target": _target("segment", "osm-w100-2", "Участок ул. Достык", "Достық көшесінің бөлігі"), "count": 3, "level": 2,
     "color": "#EF9F27", "weight": 2.9, "state": "active", "district": "nura", "category": "snow_ice",
     "by_category": {"snow_ice": 3}, "anchor": [71.36, 51.11], "demo": True},
    {"target": _target("area", "yard-7", "Двор у ул. Коксенгир", "Коксенгир көшесі маңындағы аула"), "count": 2, "level": 1,
     "color": "#F2C94C", "weight": 1.5, "state": "active", "district": "nura", "category": "snow_ice",
     "by_category": {"snow_ice": 2}, "anchor": [71.37, 51.12], "demo": True},
    {"target": _target("segment", "osm-w100-3", "Участок пр. Кабанбай Батыра", "Қабанбай Батыр даңғылының бөлігі"),
     "count": 5, "level": 2, "color": "#EF9F27", "weight": 4.0, "state": "active", "district": "esil",
     "category": "roads", "by_category": {"roads": 5}, "anchor": [71.42, 51.09], "demo": True},
    {"target": _target("segment", "osm-w100-4", "Участок ул. Сыганак", "Сығанақ көшесінің бөлігі"), "count": 4, "level": 1,
     "color": "#F2C94C", "weight": 2.0, "state": "fixed", "district": "nura", "category": "snow_ice",
     "by_category": {"snow_ice": 4}, "anchor": [71.38, 51.1], "demo": True},
]


class FakeHeat:
    """Как HeatService R07: heat(days, district, category), districts(days, category), records(since), is_demo."""

    is_demo = True

    def __init__(self, targets=None, records=None):
        self.targets = list(HEAT_TARGETS if targets is None else targets)
        self._records = list(records or [])
        self.calls = []

    def heat(self, *, days=None, district=None, category=None, **_kw):
        self.calls.append(("heat", days, district, category))
        items = [dict(t) for t in self.targets if (district is None or t["district"] == district)
                 and (category is None or t["category"] == category)]
        items.sort(key=lambda t: -t["weight"])
        return {"items": items, "demo": True}

    def districts(self, *, days=None, category=None, **_kw):
        self.calls.append(("districts", days, category))
        acc = {}
        for t in self.targets:
            if category is not None and t["category"] != category or t["state"] == "fixed":
                continue
            a = acc.setdefault(t["district"], {"count": 0, "weight": 0.0, "top": None})
            a["count"] += t["count"]
            a["weight"] += t["weight"]
            if a["top"] is None or t["weight"] > a["top"]["weight"]:
                a["top"] = {"target": t["target"], "weight": t["weight"], "count": t["count"]}
        out = [{"target": {"kind": "district", "id": d, "label_ru": d, "label_kk": d}, "count": a["count"],
                "weight": a["weight"], "level": 2, "color": "#EF9F27", "state": "active", "top": a["top"], "district": d}
               for d, a in acc.items()]
        out.sort(key=lambda it: -it["weight"])
        return out

    def records(self, since=None):
        return list(self._records)


def complaint(cid, category, district, created, status="in_progress", subtopic=None, text=RESIDENT_TEXT, metoo=0):
    return {"id": cid, "category": category, "subtopic": subtopic, "district": district,
            "created_at": created.isoformat(), "status": status, "text": text, "metoo": metoo,
            "status_history": [{"status": "new", "at": created.isoformat()},
                               *([{"status": status, "at": (created + timedelta(hours=2)).isoformat()}]
                                 if status != "new" else [])],
            "target": {"kind": "segment", "id": "osm-w100-1"}, "demo": True}


def summary_fixture(district=None):
    """Как ui.civic_akim.summary(district): только поля, которые читает аналитик."""
    return {
        "district": district,
        "kpi": {"new_day": {"value": 39, "prev": 32, "trend": "up"}, "in_progress": {"value": 67, "trend": "up"},
                "overdue": {"value": 5, "trend": "up"}},
        "topics": {"items": [
            {"category": "snow_ice", "ru": "Снег и гололёд", "kk": "Қар және көктайғақ", "value": 15, "prev": 10,
             "abs": 5, "pct": 50, "ratio": None, "trend": "up", "mode": "pct"},
            {"category": "transport", "ru": "Остановки и транспорт", "kk": "Аялдамалар мен көлік", "value": 10,
             "prev": 16, "abs": 6, "pct": 38, "ratio": None, "trend": "down", "mode": "pct"},
            {"category": "lighting", "ru": "Освещение", "kk": "Жарықтандыру", "value": 6, "prev": 1, "abs": 5,
             "pct": None, "ratio": 6.0, "trend": "up", "mode": "ratio"}]},
        "districts": {"items": [
            {"district": "nura", "ru": "Нура", "kk": "Нұра", "value": 60, "prev": 42, "abs": 18, "pct": 43,
             "ratio": None, "trend": "up", "mode": "pct"},
            {"district": "baikonur", "ru": "Байконур", "kk": "Байқоңыр", "value": 28, "prev": 12, "abs": 16,
             "pct": 133, "ratio": 2.3, "trend": "up", "mode": "ratio"},
            {"district": "esil", "ru": "Есиль", "kk": "Есіл", "value": 16, "prev": 13, "abs": 3, "pct": 23,
             "ratio": None, "trend": "up", "mode": "pct"}]},
        "overdue": {"count": 5, "places": 2, "items": [
            {"id": "c-1", "category": "roads", "district": "nura", "place_ru": "Участок пр. Кабанбай Батыра",
             "place_kk": "Қабанбай Батыр даңғылының бөлігі", "target": {"kind": "segment", "id": "osm-w100-3"},
             "on_map": True, "people": 3, "timer": {"unit": "work", "days": 7, "overdue_by": 6, "state": "overdue"},
             "service": {"id": "road", "ru": "Дорожная служба", "kk": "Жол қызметі"}, "complaints": 2, "demo": True},
            {"id": "c-2", "category": "transport", "district": "nura", "place_ru": "Остановка «Нурлы жол»",
             "place_kk": "«Нұрлы жол» аялдамасы", "target": {"kind": "object", "id": "osm-node-5"}, "on_map": True,
             "people": 1, "timer": {"unit": "work", "days": 5, "overdue_by": 3, "state": "overdue"},
             "service": {"id": "transport", "ru": "Служба общественного транспорта", "kk": "Қоғамдық көлік қызметі"},
             "complaints": 3, "demo": True}]},
        "pulse": {"available": True, "items": [
            {"kind": "spike", "category": "snow_ice", "district": "nura", "value": 43, "base": 9.8, "ratio": 4.4,
             "target": {"kind": "segment", "id": "osm-w100-1", "label_ru": "Участок ул. Е-308",
                        "label_kk": "Е-308 көшесінің бөлігі"},
             "districts": [{"district": "nura", "value": 43, "ru": "Нура", "kk": "Нұра"}],
             "text": {"ru": "«Снег и гололёд» в районе Нура: 43 сообщения за 7 дней — в 4,4 раза больше обычного.",
                      "kk": "Нұра ауданында «Қар және көктайғақ»: 7 күнде 43 хабарлама — әдеттегіден 4,4 есе көп."}}]},
        "hot": {"items": [{"target": {"kind": "segment", "id": "osm-w100-1"}}]},
        "text_parts": {"ru": [{"role": "new", "text": "Сегодня 39 новых обращений."},
                              {"role": "main", "text": "Больше всего жалоб — «Снег и гололёд» в районе Нура."},
                              {"role": "overdue", "text": "Просрочено 5 обращений."}],
                       "kk": [{"role": "new", "text": "Бүгін 39 жаңа өтініш түсті."},
                              {"role": "main", "text": "Ең көп шағым — «Қар және көктайғақ», Нұра ауданында."},
                              {"role": "overdue", "text": "Мерзімі өткен өтініш: 5."}]},
        "demo": {"complaints": True, "any": True},
    }


def board_fixture(**_kw):
    """Табло служб R17 (предполагаемый вид: services[] с id службы и счётчиками)."""
    return {"days": 30, "demo": True, "services": [
        {"service": "street_cleaning", "open": 21, "overdue": 4, "median_answer_days": 2.5, "verified_pct": 61, "demo": True},
        {"service": "road", "open": 13, "overdue": 2, "median_answer_days": 3.0, "verified_pct": 70, "demo": True},
        {"service": "lighting", "open": 3, "overdue": 0, "median_answer_days": 1.0, "verified_pct": 90, "demo": True}]}


def incidents_fixture(**_kw):
    """Кризис R17 — CONTRACT §5.5."""
    return {"items": [{
        "id": "inc-blizzard-1", "kind": "blizzard", "title_ru": "Буран", "title_kk": "Боран",
        "zone": {"kind": "district", "district": "nura", "targets": ["yard-7"], "geometry": None},
        "started_at": (NOW - timedelta(hours=6)).isoformat(), "status": "active",
        "tasks": [{"id": "t-1", "service": "street_cleaning", "text_ru": "Расчистить дворы", "text_kk": "Ауланы тазалау",
                   "status": "done"},
                  {"id": "t-2", "service": "road", "text_ru": "Посыпать дороги", "text_kk": "Жолға құм себу",
                   "status": "doing"},
                  {"id": "t-3", "service": "transport", "text_ru": "Изменить маршруты", "text_kk": "Бағыттарды өзгерту",
                   "status": "done"},
                  {"id": "t-4", "service": "power", "text_ru": "Проверить линии", "text_kk": "Желілерді тексеру",
                   "status": "todo"}],
        "updates": [{"at": NOW.isoformat(), "text_ru": "Дворы расчищают", "text_kk": "Аулалар тазаланып жатыр",
                     "public": True},
                    {"at": NOW.isoformat(), "text_ru": "Служебная заметка", "text_kk": "Қызметтік жазба", "public": False}],
        "result": None, "demo": True}]}


def conflicts_fixture(**_kw):
    """Конфликты работ R12 — CONTRACT §5.6."""
    return {"items": [
        {"id": "cf-1", "kind": "dig_after_surface", "works": ["w-1", "w-2"], "segments": ["osm-w123-4"],
         "severity": "high", "advice_ru": "Сначала сети, потом асфальт: перенесите укладку асфальта после работ Водоканала.",
         "advice_kk": "Алдымен желілер, содан кейін асфальт.", "demo": True},
        {"id": "cf-2", "kind": "parallel_closures", "works": ["w-3", "w-4"], "segments": ["osm-w9-1", "osm-w9-2"],
         "severity": "medium", "advice_ru": "Разнесите перекрытия по времени.", "advice_kk": "Жабуларды уақытқа бөліңіз.",
         "demo": True}]}


def initiatives_fixture(**_kw):
    """Инициативы R16 — CONTRACT §5.2 (author_device наружу не отдаётся)."""
    return {"items": [
        {"id": "i-1", "kind": "cleanup", "title": "Субботник во дворе", "lang": "ru",
         "target": {"kind": "area", "id": "yard-7", "label_ru": "Двор у ул. Коксенгир", "label_kk": "Коксенгир көшесі маңындағы аула"},
         "district": "nura", "status": "published", "joined": 15,
         "support": {"by_akimat": True, "inventory": True, "pickup_service": "waste"}, "demo": True},
        {"id": "i-2", "kind": "greening", "title": "Посадим деревья", "lang": "ru",
         "target": {"kind": "area", "id": "yard-8", "label_ru": "Двор у ул. Сыганак", "label_kk": "Сығанақ көшесі маңындағы аула"},
         "district": "nura", "status": "done", "joined": 9, "support": None, "demo": True},
        {"id": "i-3", "kind": "help", "title": "Скрытая", "district": "nura", "status": "hidden", "joined": 99, "demo": True}]}


def meetings_fixture(**_kw):
    """Встречи R13 — CONTRACT §5.7."""
    return {"items": [{
        "id": "m-1", "district": "nura", "title_ru": "Встреча с жителями Нуры", "title_kk": "Нұра тұрғындарымен кездесу",
        "at": (NOW - timedelta(days=10)).isoformat(), "registered": 54, "questions": ["q-1"],
        "orders": [{"id": "o-1", "text_ru": "Осветить проход у школы", "text_kk": "Мектеп жанындағы өтпе жолды жарықтандыру",
                    "service": "lighting", "due": "2026-10-10", "status": "in_progress"},
                   {"id": "o-2", "text_ru": "Убрать мусор у остановки", "text_kk": "Аялдама маңындағы қоқысты шығару",
                    "service": "waste", "due": "2026-10-20", "status": "done"},
                   {"id": "o-3", "text_ru": "Отремонтировать лавочки", "text_kk": "Орындықтарды жөндеу",
                    "service": "landscaping", "due": "2026-10-30", "status": "todo"}],
        "demo": True}]}


def full_config(**extra):
    """Все соседи на месте (как будто R17, R12, R16, R13 уже сдали работу)."""
    cfg = {"heat": FakeHeat(), "akim_summary": summary_fixture, "agencies_board": board_fixture,
           "agencies_incidents": incidents_fixture, "works_conflicts": conflicts_fixture,
           "together_initiatives": initiatives_fixture, "meetings_list": meetings_fixture,
           "forecast": lambda **kw: {"month": "2026-11", "items": [], "demo": True},
           "provider": None, "clock": lambda: NOW, "rate": (1000, 60.0)}
    cfg.update(extra)
    return cfg


class StubProvider:
    """Модель-заглушка без сети: отдаёт заданный ответ, записывает запросы."""

    name = "stub"
    model = "stub-model"

    def __init__(self, reply, delay_s: float = 0.0):
        self.reply = reply
        self.delay_s = delay_s
        self.requests = []

    def complete(self, messages, *, timeout_s):
        import json
        import time
        self.requests.append(messages)
        if self.delay_s:
            time.sleep(self.delay_s)
        if isinstance(self.reply, BaseException):
            raise self.reply
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply, ensure_ascii=False)


# ---------------------------------------------------------------- форматы функций соседей «для R03» (их ветки, 15 окт)

def r17_board_snapshot(days=30, district=None):
    """ui.civic_agencies.board_snapshot: все 20 служб (с нулями), итоги по обращениям (совместное — одно)."""
    rows = [{"service": s, "open": 0, "overdue": 0, "median_answer_days": None, "verified_share": None}
            for s in ("road", "street_cleaning", "utilities", "water", "lighting")]
    rows[2].update(open=5, overdue=4, median_answer_days=4.0, verified_share=0.5)    # ЖКХ
    rows[3].update(open=6, overdue=3, median_answer_days=2.5)                        # Водоканал
    rows[0].update(open=7, overdue=2, median_answer_days=1.5, verified_share=0.75)   # дороги
    return {"days": days, "district": district, "services": rows,
            "totals": {"open": 18, "overdue": 8, "joint": 1}, "demo": True, "empty": False, "source": "fixture"}


def r17_active_incidents(district=None):
    """ui.civic_agencies.active_incidents: публичный вид, без задач — прогресс по службам."""
    return [{"id": "inc-demo-blizzard-nura", "kind": "blizzard", "title_ru": "Буран в Нуре", "title_kk": "Нұрадағы боран",
             "zone": {"kind": "district", "district": "nura"}, "zone_label": {"ru": "район Нура", "kk": "Нұра ауданы"},
             "status": "active", "services": ["street_cleaning", "transport"],
             "progress": [{"service": "street_cleaning", "done": 0, "doing": 1, "total": 1},
                          {"service": "transport", "done": 1, "doing": 0, "total": 1}],
             "updates": [{"id": "u-1", "at": NOW.isoformat(), "text_ru": "Дворы расчищают", "text_kk": "Аулалар тазаланып жатыр"}],
             "link": "#agencies/crisis=inc-demo-blizzard-nura", "demo": True}]


def r12_conflicts_summary(district=None):
    return {"conflicts": 5, "high": 2, "source": "fixture", "demo": True,
            "top": [{"id": "cf-1", "kind": "dig_after_surface", "severity": "high", "title_ru": "Копаем дважды",
                     "title_kk": "Екі рет қазамыз", "street_ru": "ул. Сыганак", "street_kk": "Сығанақ көшесі"}]}


def r12_no_works(district=None):
    return {"conflicts": 0, "high": 0, "top": [], "source": "none", "demo": False}


def r16_initiatives_summary(district=None):
    return {"status": "ok", "district": district, "upcoming": 4, "joined_upcoming": 34, "supported": 1, "done": 2,
            "neighbors_done": 26, "on_review": 2, "demo": True,
            "next": [{"id": "i-1", "title": "Субботник во дворе", "starts_at": NOW.isoformat(), "joined": 14,
                      "district": "nura", "target": {"kind": "area", "id": "yard-7"}, "demo": True}]}


def r13_board_block(district=None):
    return {"next": None, "counts": {"total": 9, "todo": 2, "in_progress": 3, "done": 4, "overdue": 1}, "demo": True,
            "orders": [{"id": "o-1", "text_ru": "Нанести разметку", "text_kk": "Таңба салу", "service": "traffic",
                        "due": "2026-10-10", "status": "in_progress", "overdue": True}]}
