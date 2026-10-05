# A07 — изолированный эксперимент (SYNTHETIC). Не использует реальные данные Шымкента.
# Проверяемое предположение: валидатор маршрута (1) никогда не считает неизвестные часы "открыто",
# (2) помечает устаревшие источники, (3) считает метрики исполнимости и неизвестности.
import json, datetime as dt

TODAY = dt.date(2026, 10, 4)
STALE_DAYS = 90

# Синтетические POI: часы в простом формате {weekday: [open, close]} или None (неизвестно)
POIS = {
  "P1": {"name": "SYNTH Музей A", "hours": {6: ["10:00", "18:00"]}, "hours_src": "SYN-S1", "verified": "2026-09-20",
         "price_kzt": 1000, "price_src": "SYN-S1", "wheelchair": "limited"},
  "P2": {"name": "SYNTH Парк B", "hours": {6: ["00:00", "23:59"]}, "hours_src": "SYN-S2", "verified": "2026-03-01",
         "price_kzt": 0, "price_src": "SYN-S2", "wheelchair": "yes"},
  "P3": {"name": "SYNTH Зоопарк C", "hours": None, "hours_src": None, "verified": None,
         "price_kzt": None, "price_src": None, "wheelchair": "unknown"},
  "P4": {"name": "SYNTH Мечеть D", "hours": {6: ["09:00", "12:00"]}, "hours_src": "SYN-S3", "verified": "2026-09-30",
         "price_kzt": 0, "price_src": "SYN-S3", "wheelchair": "no"},
}
# Синтетический маршрут на субботу (weekday()==5 -> используем ключ 6 как "суббота" условно)
ITIN = [
  {"poi": "P1", "arrive": "10:30", "stay_min": 60, "travel_min_from_prev": 0,  "travel_src": "SYN-matrix"},
  {"poi": "P4", "arrive": "11:50", "stay_min": 30, "travel_min_from_prev": 20, "travel_src": "SYN-matrix"},
  {"poi": "P2", "arrive": "12:40", "stay_min": 90, "travel_min_from_prev": 25, "travel_src": None},
  {"poi": "P3", "arrive": "14:30", "stay_min": 90, "travel_min_from_prev": 15, "travel_src": "SYN-matrix"},
]
DAY_KEY = 6
BUDGET = 3000

def t(s): h, m = map(int, s.split(":")); return h*60+m

def check_stop(stop):
    p = POIS[stop["poi"]]; flags = []
    a, d = t(stop["arrive"]), t(stop["arrive"]) + stop["stay_min"]
    if p["hours"] is None or DAY_KEY not in p["hours"]:
        hours_status = "unknown"; flags.append("HOURS_UNKNOWN")
    else:
        o, c = map(t, p["hours"][DAY_KEY])
        hours_status = "open" if (o <= a and d <= c) else "closed_or_partial"
        if hours_status != "open": flags.append("CLOSED_DURING_VISIT")
    if p["verified"] is None: flags.append("NO_SOURCE")
    else:
        age = (TODAY - dt.date.fromisoformat(p["verified"])).days
        if age > STALE_DAYS: flags.append(f"STALE_SOURCE_{age}d")
    if p["price_kzt"] is None: flags.append("PRICE_UNKNOWN")
    if stop["travel_src"] is None: flags.append("TRAVEL_TIME_UNSOURCED")
    if p["wheelchair"] == "unknown": flags.append("ACCESS_UNKNOWN")
    return {"poi": stop["poi"], "name": p["name"], "hours_status": hours_status,
            "hours_source_id": p["hours_src"], "verified_at": p["verified"], "flags": flags}

def sequence_ok(itin):
    issues = []
    for prev, cur in zip(itin, itin[1:]):
        earliest = t(prev["arrive"]) + prev["stay_min"] + cur["travel_min_from_prev"]
        if earliest > t(cur["arrive"]):
            issues.append(f"{cur['poi']}: earliest {earliest//60:02d}:{earliest%60:02d} > planned {cur['arrive']}")
    return issues

res = [check_stop(s) for s in ITIN]
seq = sequence_ok(ITIN)
known_cost = [POIS[s["poi"]]["price_kzt"] for s in ITIN if POIS[s["poi"]]["price_kzt"] is not None]
n = len(res)
metrics = {
  "stops": n,
  "verified_executable_stops": sum(1 for r in res if r["hours_status"] == "open" and not any(f.startswith(("STALE","NO_SOURCE")) for f in r["flags"])),
  "unknown_hours_share": round(sum(r["hours_status"] == "unknown" for r in res)/n, 2),
  "stale_or_unsourced_share": round(sum(any(f.startswith(("STALE","NO_SOURCE")) for f in r["flags"]) for r in res)/n, 2),
  "sequence_violations": seq,
  "known_cost_kzt": sum(known_cost),
  "cost_status": "partial" if len(known_cost) < n else "complete",
  "within_budget_if_known": sum(known_cost) <= BUDGET,
  "itinerary_status": None,
}
metrics["itinerary_status"] = ("NOT_EXECUTABLE" if any(r["hours_status"]=="closed_or_partial" for r in res) or seq
                               else "UNVERIFIED" if any(r["flags"] for r in res) else "VERIFIED")
# Ключевая проверка предположения
assert all(r["hours_status"] != "open" for r in res if POIS[r["poi"]]["hours"] is None), "unknown treated as open!"
print(json.dumps({"stops": res, "metrics": metrics}, ensure_ascii=False, indent=1))
