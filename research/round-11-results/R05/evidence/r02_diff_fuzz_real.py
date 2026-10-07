import copy, datetime, json, random, sys
R05_TOOLS, R02_ROOT = sys.argv[1], sys.argv[2]
sys.path.insert(0, R05_TOOLS); sys.path.insert(0, R02_ROOT)
import civic_v1 as cv
from ui.civic_store import validate as r02
fence = cv.load_geofence()
base = {"schema_version": "civic-v1", "id": "ast-r05-x", "city": "astana", "kind": "roadworks", "title": "Ремонт улицы",
        "description": "Описание.", "status": "unknown", "publication": "draft", "geometry": {"type": "Point", "coordinates": [71.43, 51.17]},
        "geometry_precision": "approximate", "schedule": {"planned_start": "2026-10-01", "original_planned_end": "2026-11-01",
        "current_planned_end": "2026-11-01", "actual_end": None}, "budget": {"amount_kzt": 250000000, "basis": "planned", "source_id": "src-a"},
        "responsible": {"organization": "ГУ «Управление»", "public_contact": None}, "evidence_type": "observed",
        "source_refs": [{"id": "src-a", "url": "https://www.gov.kz/memleket/entities/astana/press/news/details/1?lang=ru", "publisher": "gov.kz",
                         "published_on": "2026-09-30", "retrieved_at": "2026-10-06T09:00:00Z", "access_status": "fetched", "license": None,
                         "fields": ["schedule.planned_start", "schedule.original_planned_end", "schedule.current_planned_end",
                                    "budget.amount_kzt", "budget.basis", "responsible.organization"]}],
        "evidence_notes": "Источник сообщает плановые сроки.", "updated_at": "2026-10-06T09:30:00Z", "revision": 1}
rnd = random.Random(11)
TXT = ["­", "​", " ", "ㅤ", "&laquo;", "Ernst&Young;", "<i", "\n", "\t", " ", "👷", "+7 701 123 45 67", "'", "x" * 2100]
def mutate(o):
    o = copy.deepcopy(o); r = o["source_refs"][0]
    for _ in range(rnd.randint(1, 3)):
        k = rnd.choice(["title", "description", "evidence_notes", "org", "contact", "publisher", "license", "url", "amount", "dates", "fields", "geometry"])
        if k in ("title", "description", "evidence_notes"): o[k] = o[k] + rnd.choice(TXT)
        elif k == "org": o["responsible"]["organization"] = rnd.choice(["ТОО «A&B»", "Org\nX", "x" * 301, "ㅤ"])
        elif k == "contact": o["responsible"]["public_contact"] = rnd.choice(["109", "x" * 201, "call\tcenter"]); r["fields"].append("responsible.public_contact")
        elif k == "publisher": r["publisher"] = rnd.choice(["Акимат", "A\nB", "x" * 301, "​A"])
        elif k == "license": r["license"] = rnd.choice(["CC BY 4.0", "x" * 201, "L\n"])
        elif k == "url": r["url"] = rnd.choice(["https://www.gov.kz/a b", "https://www.gov.kz/⁠x", "https://www.gov.kz/People's", "https://x.kz:0/", "https://www.gov.kz/" + "a" * 2000])
        elif k == "amount": o["budget"]["amount_kzt"] = rnd.choice([1e13, 1e13 + 1, 0.5e6, 2**53])
        elif k == "dates": o["schedule"]["current_planned_end"] = rnd.choice(["2026-09-01", "2101-01-01", "2026-12-01"])
        elif k == "fields": r["fields"].append(rnd.choice(["schedule", "budget.source_id", "evidence_type"]))
        elif k == "geometry": o["geometry"] = rnd.choice([{"type": "LineString", "coordinates": [[71.43, 51.17]] * 2}, {"type": "Point", "coordinates": [71.43, 51.17, 5]}])
    return o
acc = mism = 0; ex = []
for i in range(6000):
    o = mutate(base)
    if [x for x in cv.validate_object(o, profile="real", as_of="2026-10-06", fence=fence) if x["severity"] == "error"]:
        continue
    acc += 1
    try:
        r02.validate_content({k: o[k] for k in r02.CONTENT_FIELDS if k in o}, today=datetime.date(2026, 10, 6))
    except r02.ValidationError as exc:
        mism += 1; ex.append(exc.fields)
print("accepted by R05 real", acc, "rejected by R02", mism); [print(e) for e in ex[:5]]
