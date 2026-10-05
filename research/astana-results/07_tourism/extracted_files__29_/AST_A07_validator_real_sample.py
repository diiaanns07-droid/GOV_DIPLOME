# AST-A07 — изолированный эксперимент на МАЛОМ РЕАЛЬНОМ образце (ручная выписка из открытых источников,
# доступ 2026-10-05). Проверяемое предположение: валидатор различает official / aggregator / unknown,
# ловит конфликты источников и внутренние противоречия, не превращает "неизвестно" в "открыто".
import json, datetime as dt, calendar

D = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
def last_weekday(y, m, wd):
    last = calendar.monthrange(y, m)[1]
    d = dt.date(y, m, last)
    while d.weekday() != wd: d -= dt.timedelta(days=1)
    return d

# Реальные записи (значения переписаны вручную; locator указывает место в источнике)
SAMPLE = {
 "AST-POI-001": {"name": "Национальный музей РК", "coords": [51.11840, 71.46700],
   "coords_src": ("AST-A07-S010", "Details → Coordinates"),
   "hours_claims": [
     {"src": "AST-A07-S010", "tier": "official_national_portal", "locator": "Address field (часы внутри строки адреса)",
      "rule": {"days": ["Tue","Wed","Thu","Fri","Sat","Sun"], "open": "10:00", "close": "18:00", "exceptions": []}},
     {"src": "AST-A07-S011", "tier": "aggregator", "locator": "список музеев, Национальный музей РК",
      "rule": {"days": ["Tue","Wed","Thu","Fri","Sat","Sun"], "open": "10:00", "close": "18:00",
               "exceptions": ["last_tuesday_closed"]}}],
   "price_claims": [
     {"src": "AST-A07-S010", "tier": "official_national_portal", "adult_kzt": 1000},
     {"src": "AST-A07-S012", "tier": "aggregator_undated", "adult_kzt": 700}]},
 "AST-POI-002": {"name": "Visit Astana, киоск у Байтерека", "coords": None, "coords_src": None,
   "hours_claims": [
     {"src": "AST-A07-S003", "tier": "official_city_portal", "locator": "Tourist kiosks: Baiterek (часы не указаны)", "rule": None},
     {"src": "AST-A07-S013", "tier": "aggregator", "locator": "карточка 2ГИС",
      "rule": {"days": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"], "open": "10:00", "close": "21:00", "exceptions": []}}],
   "price_claims": []},
 "AST-POI-003": {"name": "Музей энергии будущего Nur Alem", "coords": None, "coords_src": None,
   "hours_claims": [
     {"src": "AST-A07-S011", "tier": "aggregator", "locator": "список музеев, Nur Alem",
      "rule_raw": "Вт-Сб – 10:00-20:00, Сб/Вс – 10:00-21:00",
      "rule": {"by_day": {"Tue":["10:00","20:00"],"Wed":["10:00","20:00"],"Thu":["10:00","20:00"],"Fri":["10:00","20:00"],
                          "Sat":[["10:00","20:00"],["10:00","21:00"]], "Sun":["10:00","21:00"]}}}],
   "price_claims": []},
}
TRANSIT = {"Tarlan Astana LRT": {"src": "AST-A07-S006", "tier": "media_citing_operator", "service": ["06:00","23:00"], "fare_kzt": 200}}

def t(s): h, m = map(int, s.split(":")); return h*60+m

def eval_claim(claim, date, hhmm):
    r = claim.get("rule")
    if r is None: return "unknown"
    day = D[date.weekday()]
    if "by_day" in r:
        v = r["by_day"].get(day)
        if v is None: return "closed"
        if isinstance(v[0], list):  # противоречивые интервалы для одного дня
            outs = {("open" if t(a) <= t(hhmm) < t(b) else "closed") for a, b in v}
            return "internally_inconsistent" if len(outs) > 1 else outs.pop()
        return "open" if t(v[0]) <= t(hhmm) < t(v[1]) else "closed"
    if day not in r["days"]: return "closed"
    if "last_tuesday_closed" in r["exceptions"] and date == last_weekday(date.year, date.month, 1): return "closed"
    return "open" if t(r["open"]) <= t(hhmm) < t(r["close"]) else "closed"

RANK = {"official_city_portal": 3, "official_national_portal": 3, "operator": 4,
        "media_citing_operator": 2, "aggregator": 1, "aggregator_undated": 0}

def resolve(poi_id, date, hhmm):
    p = SAMPLE[poi_id]; res = [(c["src"], c["tier"], eval_claim(c, date, hhmm)) for c in p["hours_claims"]]
    known = [r for r in res if r[2] in ("open", "closed")]
    flags = []
    if any(r[2] == "internally_inconsistent" for r in res): flags.append("INTERNAL_INCONSISTENCY")
    if not known: status = "unknown"
    elif len({r[2] for r in known}) > 1: status = "conflict"; flags.append("SOURCE_CONFLICT")
    else:
        status = known[0][2]
        if max(RANK[r[1]] for r in known) < 3: flags.append("NO_OFFICIAL_CONFIRMATION")
    if any(r[2] == "unknown" and RANK[r[1]] >= 3 for r in res): flags.append("OFFICIAL_SILENT")
    # VERIFIED_OPEN требует official-заявку с verified_at (дата проверки) не старше 90 дней.
    # В образце ни у одной заявки нет verified_at -> максимум LIKELY_OPEN.
    has_fresh_verified = any(c.get("verified_at") for c in p["hours_claims"])
    if status == "open" and not has_fresh_verified: flags.append("NO_VERIFIED_AT")
    verdict = ("NOT_EXECUTABLE" if status == "closed" else
               "VERIFIED_OPEN" if status == "open" and not flags else
               "LIKELY_OPEN" if status == "open" and flags == ["NO_VERIFIED_AT"] else "UNVERIFIED")
    return {"poi": poi_id, "name": p["name"], "when": f"{date} {D[date.weekday()]} {hhmm}",
            "claims": res, "status": status, "flags": flags, "verdict": verdict}

def transit_ok(line, hhmm):
    a, b = TRANSIT[line]["service"]
    return {"line": line, "at": hhmm, "in_service": t(a) <= t(hhmm) < t(b), "src": TRANSIT[line]["src"]}

cases = [
  resolve("AST-POI-001", dt.date(2026,10,5), "11:00"),   # понедельник (дата поиска)
  resolve("AST-POI-001", dt.date(2026,10,27), "11:00"),  # последний вторник октября
  resolve("AST-POI-001", dt.date(2026,10,7), "11:00"),   # среда
  resolve("AST-POI-002", dt.date(2026,10,11), "20:00"),  # воскресенье вечер
  resolve("AST-POI-003", dt.date(2026,10,10), "20:30"),  # суббота 20:30
]
price = SAMPLE["AST-POI-001"]["price_claims"]
price_conflict = len({c["adult_kzt"] for c in price}) > 1
transit = [transit_ok("Tarlan Astana LRT", "23:30"), transit_ok("Tarlan Astana LRT", "09:00")]

all_claims = [c for p in SAMPLE.values() for c in p["hours_claims"]]
summary = {
  "last_tuesday_oct_2026": str(last_weekday(2026,10,1)),
  "hours_claims_total": len(all_claims),
  "hours_claims_official_with_value": sum(1 for c in all_claims if RANK[c["tier"]] >= 3 and c.get("rule")),
  "hours_claims_official_silent": sum(1 for c in all_claims if RANK[c["tier"]] >= 3 and not c.get("rule")),
  "pois_with_coordinates": sum(1 for p in SAMPLE.values() if p["coords"]),
  "price_conflict_AST-POI-001": price_conflict,
  "verdicts": {c["when"]+" "+c["poi"]: c["verdict"] for c in cases},
}
assert all(c["verdict"] not in ("VERIFIED_OPEN","LIKELY_OPEN") for c in cases if c["status"] in ("unknown","conflict"))
print(json.dumps({"cases": cases, "transit": transit, "summary": summary}, ensure_ascii=False, indent=1))
