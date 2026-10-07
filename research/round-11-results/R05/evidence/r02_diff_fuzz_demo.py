"""Differential check: every object R05 accepts (demo/real profile) must pass R02 validate_content."""
import copy, datetime, json, random, sys
R05_TOOLS, R02_ROOT = sys.argv[1], sys.argv[2]
sys.path.insert(0, R05_TOOLS); sys.path.insert(0, R02_ROOT)
import civic_v1 as cv
from ui.civic_store import validate as r02
fence = cv.load_geofence()
demo = json.load(open(R05_TOOLS + "/../demo_synthetic.json", encoding="utf-8"))["items"]
rnd = random.Random(7)
CHARS = ["­", "​", "‍", " ", "ㅤ", "", "͸", "&amp;", "&laquo;", "Ernst&Young;", "<b", "\t", "\n",
         " ", "№", "«», —", "👷‍♂️", "'", "﻿", " "]
URLS = ["https://www.gov.kz/x?a=1&b=2", "https://www.gov.kz/x y", "https://www.gov.kz/​x", "https://www.gov.kz/x ",
        "https://www.gov.kz/People's", "http://[::1]/x", "https://u:p@www.gov.kz/", "https://www.gov.kz:99999/"]
def mutate(o):
    o = copy.deepcopy(o)
    k = rnd.choice(["title", "description", "evidence_notes", "url", "fields", "amount", "dates", "ref_id"])
    if k in ("title", "description", "evidence_notes"):
        o[k] = (o[k] or "Демо") + rnd.choice(CHARS) + rnd.choice(CHARS)
    elif k == "url":
        o["source_refs"] = [{"id": "src-a", "url": rnd.choice(URLS), "publisher": "P", "published_on": None,
                             "retrieved_at": None, "access_status": "not_fetched", "license": None, "fields": []}]
    elif k == "fields":
        o["source_refs"] = [{"id": "src-a", "url": "https://www.gov.kz/x", "publisher": "P", "published_on": None,
                             "retrieved_at": None, "access_status": "not_fetched", "license": None,
                             "fields": [rnd.choice(["schedule", "schedule.foo", "budget.source_id", "evidence_type", "status"])]}]
    elif k == "amount":
        o["budget"] = {"amount_kzt": rnd.choice([0, 1e13, 1e13 + 1, 5e9]), "basis": rnd.choice(["planned", "unknown"]), "source_id": None}
    elif k == "dates":
        o["schedule"] = dict(o["schedule"], planned_start=rnd.choice(["2026-10-01", "2026-12-01", None]),
                             current_planned_end=rnd.choice(["2026-11-01", "2026-09-01", None]))
    elif k == "ref_id":
        o["source_refs"] = [{"id": rnd.choice(["src-a", "src:a/b", "a" * 65]), "url": "https://www.gov.kz/x", "publisher": None,
                             "published_on": None, "retrieved_at": None, "access_status": "not_fetched", "license": None, "fields": []}]
    return o
mismatch, accepted, total = [], 0, 0
for i in range(6000):
    o = mutate(rnd.choice(demo))
    for profile in ("contract", "demo"):
        errs = [x for x in cv.validate_object(o, profile=profile, as_of="2026-10-06", fence=fence) if x["severity"] == "error"]
        if profile == "contract":
            continue
        total += 1
        if errs:
            continue
        accepted += 1
        content = {k: o[k] for k in r02.CONTENT_FIELDS if k in o}
        try:
            r02.validate_content(content, today=datetime.date(2026, 10, 6))
        except r02.ValidationError as exc:
            mismatch.append((exc.fields, {k: o[k] for k in ("title", "description", "evidence_notes", "source_refs", "budget", "schedule")}))
print("checked", total, "accepted by R05 demo profile", accepted, "rejected by R02 among those", len(mismatch))
for m in mismatch[:5]:
    print(json.dumps(m, ensure_ascii=False)[:400])
