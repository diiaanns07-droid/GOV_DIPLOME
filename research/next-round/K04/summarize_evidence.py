"""K04: read-only summary of saved evidence.json files for both cities.

Reads research/{govtech,astana}-results/**/*evidence*.json (skips byte-identical
"(1)" duplicates), counts fact kinds / source access statuses / dataset access
statuses per agent, and lists every opportunity with its user, datasets and the
access status of those datasets. Writes evidence_summary.json next to this file.

Nothing is fetched from the network; numbers are counts of what the agents
*recorded*, not verification of the underlying facts.
"""
import collections
import glob
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CITY_DIRS = {"shymkent": "govtech-results", "astana": "astana-results"}


def files_for(city_dir):
    seen = set()
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, city_dir, "**", "*evidence*.json"), recursive=True)):
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        out.append(path)
    return out


def summarize(path, city):
    d = json.load(open(path, encoding="utf-8"))
    meta = d.get("meta", {})
    facts = d.get("facts", [])
    sources = d.get("sources", [])
    datasets = d.get("datasets", [])
    ds_status = {x.get("dataset_id"): x.get("access_status") for x in datasets}
    fact_kind = {x.get("fact_id"): x.get("kind") for x in facts}
    opps = []
    for o in d.get("opportunities", []):
        req = o.get("required_dataset_ids", []) or []
        ev = o.get("evidence_fact_ids", []) or []
        opps.append({
            "idea_id": o.get("idea_id"),
            "title": o.get("title"),
            "primary_user": o.get("primary_user"),
            "user_task": o.get("user_task"),
            "required_datasets": {r: ds_status.get(r, "not_in_file") for r in req},
            "evidence_fact_kinds": dict(collections.Counter(fact_kind.get(f, "not_in_file") for f in ev)),
            "blockers": o.get("blockers"),
            "feasibility_10_days": o.get("feasibility_10_days"),
            "non_ai_baseline": o.get("non_ai_baseline"),
        })
    return {
        "city": city,
        "agent_id": meta.get("agent_id"),
        "topic": meta.get("topic"),
        "file": os.path.relpath(path, ROOT),
        "access_limitations_count": len(meta.get("access_limitations", []) or []),
        "fact_kinds": dict(collections.Counter(x.get("kind") for x in facts)),
        "source_access": dict(collections.Counter(x.get("access_status") for x in sources)),
        "dataset_access": dict(collections.Counter(x.get("access_status") for x in datasets)),
        "datasets": [{"id": x.get("dataset_id"), "title": x.get("title"), "access_status": x.get("access_status"),
                      "license": x.get("license"), "period": x.get("period")} for x in datasets],
        "opportunities": opps,
    }


def main():
    rows = []
    for city, cdir in CITY_DIRS.items():
        for p in files_for(cdir):
            rows.append(summarize(p, city))
    with open(os.path.join(HERE, "evidence_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    for r in rows:
        print(f"{r['city']:8} {r['agent_id']:8} facts={r['fact_kinds']} ds={r['dataset_access']}")
        for o in r["opportunities"]:
            print(f"    {o['idea_id']}: {o['title']}")
            print(f"       user: {(o['primary_user'] or '')[:110]}")
            print(f"       data: {o['required_datasets']}")


if __name__ == "__main__":
    main()
