"""Общие заготовки тестов R08: синтетические записи жалоб v2 (CONTRACT §5) с заданным возрастом и историей."""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=5))
# Понедельник 12 октября 2026, 10:00 по Астане — «сейчас» во всех тестах.
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=TZ)
# Точка в районе Нура (район в записи указан явно, поэтому точка нужна только для формата).
NURA_POINT = [71.415, 51.1]


def rec(i, *, at=None, age_days=None, category="roads", status="new", history=None, district="nura",
        metoo=0, duplicate_of=None, target=None, point=None, demo=True):
    """Запись v2. at — время подачи; или age_days — сколько дней назад от NOW.

    history — список (смещение_в_днях_от_подачи, статус); «new» в момент подачи добавляется сам.
    """
    created = at if at is not None else NOW - timedelta(days=age_days or 0)
    hist = [{"at": created.isoformat(), "status": "new"}]
    for shift, st in history or []:
        hist.append({"at": (created + timedelta(days=shift)).isoformat(), "status": st})
    if history and status == "new":
        status = hist[-1]["status"]
    return {
        "id": f"c-r08-{i}", "created_at": created.isoformat(), "text": f"секретный текст жителя {i}", "lang": "ru",
        "category": category, "category_source": "resident", "model": None,
        "point": point or NURA_POINT, "target": target or {"kind": "area", "id": f"cell-r08-{i}"},
        "district": district, "status": status, "status_history": hist, "metoo": metoo,
        "duplicate_of": duplicate_of, "demo": demo,
    }
