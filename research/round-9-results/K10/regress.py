"""K10 round 9: one-command regression of a BUILD commit against the frozen K10 r8 packs (stdlib + node + git).

    python3 research/round-9-results/K10/regress.py --sha <BUILD sha> [--out DIR] [--workdir DIR]

Expectations are never recomputed from the BUILD: the r8 packs must be byte-identical to frozen/r8_packs.json
(their expected values come from the independent K10 oracle), and source files/records are compared with
frozen/sources.json (read from the K10 package in git, commit 602f0c0).

Steps -> DIR/summary.json (default research/round-9-results/K10/results/<sha7>/):
  EXTRACT         prototypes/city-evidence copied byte-exact from git (blob ids re-hashed), manifest kept
  FROZEN_PACKS    research/round-8-results/K10/packs == frozen/r8_packs.json (161 files)
  SOURCE_HASHES   inputs/k10 places_social.geojson x2 + package_manifest.json == K10 package; data.js points to the same sha256
  SOURCE_IDS      data.js places per city: same ids and groups as the K10 package; lon/lat = package values rounded to 6 dp
  R8_SUITE        research/round-8-results/K10/tests/run_build_suite.py (packs vs data, oracle recompute, JS geometry,
                  unit tests, verify-inputs, packs through web/plan.js, export round trip, plan.js mutants)
  R9_ENVELOPES    tests/check_envelopes.py: the 19 city-resilience-v1 packs vs this build's data + K10 oracle checks
  R9_PROPOSAL_ON_PLAN_JS  tests/run_res_adapter.cjs: K10 proposals/resilience.js over this build's plan.js (SKIP if absent)
  BUILD_RESILIENCE  the build's own web/resilience.js against the 19 packs (tests/run_build_resilience.cjs: math, rows per
                  case, order, import/export, refusals), its exports re-checked by the K10 oracle, and the packs' power to
                  catch injected rule errors (tests/run_build_res_mutants.py); NOT_RUN when the build has no resilience.js
Exit 0 only if every step is PASS, SKIP or NOT_RUN (NOT_RUN is reported, never counted as PASS).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
R8 = REPO / "research/round-8-results/K10"
PREFIX = "prototypes/city-evidence"


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO)


def extract(sha, dest):
    """Byte-exact copy of prototypes/city-evidence at sha; every blob id is recomputed and compared."""
    entries = []
    for row in git("ls-tree", "-r", sha, PREFIX + "/").decode().splitlines():
        meta, path = row.split("\t", 1)
        _mode, kind, oid = meta.split()
        if kind != "blob":
            continue
        data = git("cat-file", "blob", oid)
        if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() != oid:
            raise SystemExit(f"blob mismatch: {path}")
        p = dest / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        entries.append({"path": path, "git_blob": oid, "sha256": sha256(data), "bytes": len(data)})
    return entries


def parse_js(raw):
    t = raw.decode("utf-8")
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")])


def check_frozen_packs():
    fz = json.loads((HERE / "frozen/r8_packs.json").read_text(encoding="utf-8"))
    now = {str(p.relative_to(R8 / "packs")): sha256(p.read_bytes()) for p in sorted((R8 / "packs").rglob("*")) if p.is_file()}
    diff = sorted(set(now) ^ set(fz["sha256"])) + sorted(k for k in now if k in fz["sha256"] and now[k] != fz["sha256"][k])
    return {"status": "PASS" if not diff else "FAIL", "files": len(now), "frozen_commit": fz["commit"], "differences": diff[:20]}


def check_sources(app):
    fz = json.loads((HERE / "frozen/sources.json").read_text(encoding="utf-8"))
    hashes, ids = {"package_commit": fz["commit"], "files": {}}, {}
    ok_h = True
    pairs = {"inputs/k10/package_manifest.json": "package_manifest.json"}
    pairs.update({f"inputs/k10/data/{c}/places_social.geojson": f"data/{c}/places_social.geojson" for c in ("shymkent", "astana")})
    for app_rel, pkg_rel in pairs.items():
        got = sha256((app / app_rel).read_bytes()) if (app / app_rel).exists() else None
        hashes["files"][app_rel] = {"sha256": got, "frozen": fz["files"][pkg_rel], "ok": got == fz["files"][pkg_rel]}
        ok_h &= got == fz["files"][pkg_rel]
    data = parse_js((app / "web/data.js").read_bytes())
    ok_i = True
    for city, recs in fz["records"].items():
        c = data["cities"][city]
        declared = c["files"]["places_social"]["sha256"]
        dh = declared == fz["files"][f"data/{city}/places_social.geojson"]
        hashes["files"][f"web/data.js:{city}.files.places_social.sha256"] = {"sha256": declared, "ok": dh}
        ok_h &= dh
        want = {r[0]: (r[1], round(r[2], 6), round(r[3], 6)) for r in recs}
        got = {p["id"]: (p["group"], p["lon"], p["lat"]) for p in c["places"]}
        missing, extra = sorted(set(want) - set(got)), sorted(set(got) - set(want))
        bad = sorted(k for k in set(want) & set(got)
                     if got[k][0] != want[k][0] or abs(got[k][1] - want[k][1]) > 5.1e-7 or abs(got[k][2] - want[k][2]) > 5.1e-7)
        by_group = {}
        for g, *_ in got.values():
            by_group[g] = by_group.get(g, 0) + 1
        ids[city] = {"records": len(got), "frozen": len(want), "missing": missing, "extra": extra, "changed": bad,
                     "school": by_group.get("school", 0), "outpatient_clinic": by_group.get("outpatient_clinic", 0)}
        ok_i &= not (missing or extra or bad)
    return ({"status": "PASS" if ok_h else "FAIL", **hashes}, {"status": "PASS" if ok_i else "FAIL", "cities": ids})


def check_build_exports(d):
    """The BUILD's own exports (exportResilience) must be accepted by the K10 oracle and give the same optimum."""
    sys.path.insert(0, str(HERE))
    from k10res import edgecases as XE  # noqa: E402
    from k10res import oracle_res as RO  # noqa: E402
    files, differ = sorted(d.glob("*.json")), []
    for f in files:
        pack = json.loads((HERE / "envelopes" / f.name).read_text(encoding="utf-8"))
        try:
            ctx = XE.context_of(pack)
            got = RO.optimize_resilience(ctx, RO.validate_resilience(RO.O.parse_strict(f.read_bytes()), ctx))
            if json.dumps(got, sort_keys=True) != json.dumps(pack["expected"]["optimize"], sort_keys=True):
                differ.append(f.stem)
        except (RO.ResError, RO.O.PlanError) as e:
            differ.append(f"{f.stem}: {e.code}")
    return {"files": len(files), "differ": differ}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out")
    ap.add_argument("--workdir", help="where to extract (default: a temporary directory, removed afterwards)")
    a = ap.parse_args()
    full = git("rev-parse", a.sha).decode().strip()
    out = Path(a.out) if a.out else HERE / "results" / full[:7]
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    tmp = None
    work = Path(a.workdir) if a.workdir else Path(tmp := tempfile.mkdtemp(prefix=f"k10r9_{full[:7]}_"))
    s = {"sha": full, "steps": {}}
    try:
        entries = extract(full, work)
        app = work / PREFIX
        (out / "extract_manifest.json").write_text(json.dumps({"commit": full, "prefix": PREFIX, "files": len(entries),
                                                               "entries": entries}, indent=1) + "\n", encoding="utf-8")
        s["steps"]["EXTRACT"] = {"status": "PASS", "files": len(entries)}
        s["steps"]["FROZEN_PACKS"] = check_frozen_packs()
        s["steps"]["SOURCE_HASHES"], s["steps"]["SOURCE_IDS"] = check_sources(app)
        r = subprocess.run([sys.executable, str(R8 / "tests/run_build_suite.py"), "--app-root", str(app), "--commit", full,
                            "--out", str(out / "r8_suite")], capture_output=True, text=True)
        suite = json.loads((out / "r8_suite/summary.json").read_text(encoding="utf-8")) if (out / "r8_suite/summary.json").exists() else {}
        s["steps"]["R8_SUITE"] = {"status": "PASS" if r.returncode == 0 else "FAIL", "steps": suite.get("steps"),
                                  "build_exports": suite.get("build_exports"), "build_mutants": suite.get("build_mutants"),
                                  "stderr_tail": r.stderr[-400:] if r.returncode else ""}
        # round 9: resilience envelopes (K10 oracle) and the K10 proposal module on top of this build's plan.js
        r = subprocess.run([sys.executable, str(HERE / "tests/check_envelopes.py"), "--app-root", str(app),
                            "--json", str(out / "check_envelopes.json")], capture_output=True, text=True, cwd=HERE)
        s["steps"]["R9_ENVELOPES"] = {"status": "PASS" if r.returncode == 0 else "FAIL", "summary": r.stdout.strip()[-600:]}
        packs9 = sorted(str(q) for q in (HERE / "envelopes").glob("*.json") if q.name != "INDEX.json")
        if (app / "web/plan.js").exists():
            r = subprocess.run(["node", str(HERE / "tests/run_res_adapter.cjs"), str(app), *packs9], capture_output=True, text=True)
            (out / "res_adapter.json").write_text(r.stdout, encoding="utf-8")
            s["steps"]["R9_PROPOSAL_ON_PLAN_JS"] = {"status": "PASS" if r.returncode == 0 else "FAIL",
                                                    "note": "K10 proposals/resilience.js on this build's plan.js; not a BUILD feature"}
        else:
            s["steps"]["R9_PROPOSAL_ON_PLAN_JS"] = {"status": "SKIP", "note": "no web/plan.js in this build"}
        # the BUILD's own city-resilience-v1 module, if this build has one
        if (app / "web/resilience.js").exists():
            with tempfile.TemporaryDirectory() as exp_dir:
                r = subprocess.run(["node", str(HERE / "tests/run_build_resilience.cjs"), str(app), *packs9], capture_output=True,
                                   text=True, env={**os.environ, "K10_EXPORT_DIR": exp_dir})
                (out / "build_resilience.json").write_text(r.stdout, encoding="utf-8")
                exports = check_build_exports(Path(exp_dir))
            m = subprocess.run([sys.executable, str(HERE / "tests/run_build_res_mutants.py"), "--app-root", str(app),
                                "--json", str(out / "build_res_mutants.json")], capture_output=True, text=True)
            mut = json.loads((out / "build_res_mutants.json").read_text(encoding="utf-8"))
            ok = r.returncode == 0 and exports["differ"] == [] and exports["files"] > 0 and m.returncode == 0
            s["steps"]["BUILD_RESILIENCE"] = {"status": "PASS" if ok else "FAIL", "packs_exit": r.returncode, "exports": exports,
                                              "mutants": {k: mut[k] for k in ("mutants", "killed", "survived", "not_applicable")},
                                              "resilience_js_sha256": sha256((app / "web/resilience.js").read_bytes())}
        else:
            s["steps"]["BUILD_RESILIENCE"] = {"status": "NOT_RUN", "note": "this build has no web/resilience.js"}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    s["seconds"] = round(time.time() - t0, 1)
    s["ok"] = all(v["status"] in ("PASS", "SKIP", "NOT_RUN") for v in s["steps"].values())
    txt = json.dumps(s, ensure_ascii=False, indent=1)
    if tmp:  # keep local temporary paths out of the stored results
        txt = txt.replace(tmp, "<workdir>")
        for f in out.rglob("*"):
            if f.is_file() and f.suffix in (".json", ".txt"):
                t = f.read_text(encoding="utf-8")
                if tmp in t:
                    f.write_text(t.replace(tmp, "<workdir>"), encoding="utf-8")
    (out / "summary.json").write_text(txt + "\n", encoding="utf-8")
    print(json.dumps({"sha": full, "ok": s["ok"], "seconds": s["seconds"],
                      "steps": {k: v["status"] for k, v in s["steps"].items()},
                      "r8_suite": s["steps"].get("R8_SUITE", {}).get("steps")}, ensure_ascii=False))
    sys.exit(0 if s["ok"] else 1)


if __name__ == "__main__":
    main()
