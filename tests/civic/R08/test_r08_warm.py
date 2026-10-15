"""R08 раунд 15: прогрев «Картины дня» (просьба R01 — холодный akim/summary до 1,2 с) и памятки разбора времени и истории.

warm_up() R01 зовёт в фоне при старте (цикл прогрева в ui/web_server.py, как R07 / R16): считает сводку города и Нуры,
ошибку глотает. Памятки (_parse_iso, _history) ускоряют пересчёт сводки и не должны менять ни одного числа.
Запуск: python -m pytest tests/civic/R08 -q
"""
import sys
from datetime import datetime, timedelta, timezone

import pytest

from r08_helpers import NOW, rec
from ui.civic_akim import AkimService, warm_up
from ui.civic_akim.summary import _history, parse_time, status_at

S = sys.modules["ui.civic_akim.summary"]   # модуль (имя summary в пакете — функция)


def fresh_history(record):
    """Та же история без памятки — эталон для сравнения."""
    out = []
    for h in record.get("status_history") or []:
        if isinstance(h, dict):
            t = parse_time(h.get("at"))
            if t is not None and h.get("status"):
                out.append((t, str(h["status"])))
    return sorted(out, key=lambda x: x[0])


def test_parse_time_forms_unchanged():
    assert parse_time("2026-10-12T10:00:00Z") == datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
    assert parse_time("2026-10-12T10:00:00").utcoffset() == timedelta(hours=5)   # без пояса — Астана
    assert parse_time("не время") is None and parse_time("") is None and parse_time(None) is None
    naive = datetime(2026, 10, 12, 10, 0)
    assert parse_time(naive).utcoffset() == timedelta(hours=5)
    assert parse_time("2026-10-12T10:00:00+05:00") is parse_time("2026-10-12T10:00:00+05:00")  # разобрано один раз


def test_history_memo_matches_fresh_parse_and_sees_new_steps():
    r = rec(1, age_days=3, category="roads")
    assert _history(r) == fresh_history(r) and status_at(r, NOW) == "new"
    assert _history(r) is _history(r)                                     # второй вызов — из памятки
    # R09 дописал шаг в конец того же списка — памятка видит его (длина другая)
    r["status_history"].append({"at": (NOW - timedelta(hours=1)).isoformat(), "status": "in_progress"})
    r["status"] = "in_progress"
    assert _history(r) == fresh_history(r) and status_at(r, NOW) == "in_progress"
    # заменил список целиком — тоже
    r["status_history"] = r["status_history"][:1] + [{"at": (NOW - timedelta(hours=2)).isoformat(), "status": "fixed"}]
    r["status"] = "fixed"
    assert _history(r) == fresh_history(r) and status_at(r, NOW) == "fixed"
    # записи без истории
    bare = dict(r, status_history=None)
    assert _history(bare) == [] and _history(bare) == []


def test_summary_numbers_same_with_and_without_memo():
    records = [rec(i, age_days=i % 9 + 0.5, category=("roads", "snow_ice", "lighting")[i % 3],
                   history=[(0.3, "accepted"), (0.6, "in_progress")] + ([(0.9, "fixed")] if i % 4 == 0 else []))
               for i in range(40)]
    svc = AkimService(heat=False, records=lambda since: records, objects=None, proposals=None, clock=lambda: NOW)
    first = svc.summary(now=NOW)
    S._HIST_MEMO.clear()
    S._parse_iso.cache_clear()
    svc.invalidate()
    second = svc.summary(now=NOW)
    for key in ("new_day", "new_week", "in_progress", "overdue", "fixed_week"):
        assert first["kpi"][key] == second["kpi"][key]
    assert first["text"] == second["text"]


@pytest.fixture
def default_svc(monkeypatch):
    records = [rec(i, age_days=1 + i, category="roads", district=("nura", "esil")[i % 2]) for i in range(6)]
    svc = AkimService(heat=False, records=lambda since: records, objects=None, proposals=None, clock=lambda: NOW)
    monkeypatch.setattr(S, "_default", svc)
    return svc


def test_warm_up_fills_cache_for_city_and_nura(default_svc):
    out = warm_up("/tmp/ignored.sqlite3")            # R01 передаёт путь базы — аргументы не нужны
    assert set(out) == {"city", "nura"} and all(isinstance(v, int) and v >= 0 for v in out.values())
    keys = {(k[0], k[1]) for k in default_svc._cache}
    assert (NOW.astimezone(S.ASTANA_TZ).date().isoformat(), None) in keys
    assert (NOW.astimezone(S.ASTANA_TZ).date().isoformat(), "nura") in keys


def test_warm_up_never_raises(default_svc, monkeypatch):
    def broken(**_kw):
        raise RuntimeError("сосед упал")
    monkeypatch.setattr(default_svc, "summary", broken)
    assert warm_up() == {}
