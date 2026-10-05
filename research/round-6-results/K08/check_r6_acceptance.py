"""K08 R6: приёмка атрибуции и модифицированных копий демо prototypes/city-evidence.

Usage: python check_r6_acceptance.py --app-root <prototypes/city-evidence> --repo <git с объектами входов>
       [--checker <check_demo_attribution.py раунда 5>] [--json OUT]

Инварианты:
  I1  архивные копии source_manifest.json побайтно = manifest и = upstream `git show sha:path`
  I2  архивные копии inputs/r4/MANIFEST.json побайтно = manifest и = upstream
  I3  K03 v2 (inputs/k03v2_root): original_sha256 = архивной копии, patched_sha256 = используемому файлу,
      patch-файл = архивной копии из r4 MANIFEST, остальные файлы = inputs/k03_root, повторный setup даёт тот же hash
  I4  контракт (inputs/contract): original_sha256 = файлу-источнику, used_sha256 = используемому файлу,
      флаг modified согласован, повторный setup даёт тот же hash
  I5  K02 v4 (inputs/k02v4): original = архивной копии r4, adapted = используемому файлу, повторный setup — тот же hash
  I6  используемые модули — модифицированные копии, не архивные (по путям импорта в tools/)
  I7  routes: в data.js нет ключа routes; пробел задокументирован (README/web)
  I8  атрибуция web: checker раунда 5 (A2–A9)
Модифицированный файл НЕ сравнивается с upstream: для него требуются честное происхождение и отдельные hash.
Только stdlib (повторный setup использует `patch` и python, как в BUILD). Входная папка не меняется: setup идёт в копии.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def h(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def upstream(repo, sha, path):
    try:
        return hashlib.sha256(subprocess.check_output(["git", "show", f"{sha}:{path}"], cwd=repo, stderr=subprocess.DEVNULL)).hexdigest()
    except subprocess.CalledProcessError:
        return None


def check_manifest(app, repo, rel):
    m = json.loads((app / rel).read_text(encoding="utf-8"))
    bad = []
    for e in m["files"]:
        p = app / e["copied_to"]
        local = h(p) if p.is_file() else None
        up = upstream(repo, e["sha"], e["path"])
        if not (local == e["sha256"] == up):
            bad.append({"copied_to": e["copied_to"], "manifest": e["sha256"], "local": local, "upstream": up})
    return len(m["files"]), bad, m


def rerun_setup(app, script, out_rel, files):
    """Запустить tools/<script> в копии app и вернуть hash указанных файлов."""
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "app"
        shutil.copytree(app, cp, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
        shutil.rmtree(cp / out_rel, ignore_errors=True)
        r = subprocess.run([sys.executable, str(cp / "tools" / script)], cwd=cp, capture_output=True, text=True)
        if r.returncode:
            return None, r.stderr[-400:]
        return {f: h(cp / f) for f in files}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--checker", default=str(Path(__file__).resolve().parents[2] / "round-5-results/K08/check_demo_attribution.py"))
    ap.add_argument("--json")
    a = ap.parse_args()
    app = Path(a.app_root).resolve()
    res = []

    def add(i, ok, text, **kw):
        res.append({"invariant": i, "verdict": "PASS" if ok else "FAIL", "text": text, **kw})

    n, bad, src_man = check_manifest(app, a.repo, "source_manifest.json")
    add("I1", not bad, f"source_manifest.json: {n - len(bad)}/{n} = manifest = upstream", mismatches=bad)
    n, bad, r4_man = check_manifest(app, a.repo, "inputs/r4/MANIFEST.json")
    add("I2", not bad, f"inputs/r4/MANIFEST.json: {n - len(bad)}/{n} = manifest = upstream", mismatches=bad)
    r4_hash = {e["copied_to"]: e["sha256"] for e in r4_man["files"]}

    # I3 K03 v2
    k3 = json.loads((app / "inputs/k03v2_root/MANIFEST_K03V2.json").read_text(encoding="utf-8"))
    probs = []
    for m in k3["modified"]:
        if h(app / "inputs/k03_root" / m["path"]) != m["original_sha256"]:
            probs.append(f"original_sha256 != inputs/k03_root/{m['path']}")
        if h(app / "inputs/k03v2_root" / m["path"]) != m["patched_sha256"]:
            probs.append(f"patched_sha256 != inputs/k03v2_root/{m['path']}")
        if m["original_sha256"] == m["patched_sha256"]:
            probs.append("patched == original (патч не применён)")
    if h(app / k3["patch"]["path"]) != k3["patch"]["sha256"] or r4_hash.get(k3["patch"]["path"]) != k3["patch"]["sha256"]:
        probs.append("patch-файл не совпадает с архивной копией r4")
    mod = {m["path"] for m in k3["modified"]} | {"MANIFEST_K03V2.json"}
    for f in sorted((app / "inputs/k03v2_root").rglob("*")):
        r = f.relative_to(app / "inputs/k03v2_root").as_posix()
        if f.is_file() and r not in mod and "__pycache__" not in r:
            o = app / "inputs/k03_root" / r
            if not o.is_file() or h(o) != h(f):
                probs.append(f"немодифицированный файл отличается от k03_root: {r}")
    tgt = "inputs/k03v2_root/" + k3["modified"][0]["path"]
    rh, err = rerun_setup(app, "setup_k03_v2.py", "inputs/k03v2_root", [tgt])
    if err or rh[tgt] != k3["modified"][0]["patched_sha256"]:
        probs.append(f"повторный setup_k03_v2.py не воспроизводит hash: {err or rh}")
    add("I3", not probs, "K03 v2: отдельные hash исходного и модифицированного файла, патч из архива, воспроизводимо", problems=probs,
        original_sha256=k3["modified"][0]["original_sha256"], patched_sha256=k3["modified"][0]["patched_sha256"])

    # I4 contract
    cm = json.loads((app / "inputs/contract/CONTRACT_MANIFEST.json").read_text(encoding="utf-8"))
    probs = []
    for r in cm["files"]:
        if h(app / r["from"]) != r["original_sha256"]:
            probs.append(f"original_sha256 != {r['from']}")
        if h(app / "inputs/contract" / r["path"]) != r["used_sha256"]:
            probs.append(f"used_sha256 != inputs/contract/{r['path']}")
        if r["modified"] != (r["used_sha256"] != r["original_sha256"]):
            probs.append(f"флаг modified несогласован: {r['path']}")
        src_ok = any(e["copied_to"] == r["from"] and e["sha256"] == r["original_sha256"] for e in src_man["files"] + r4_man["files"])
        if not src_ok:
            probs.append(f"источник {r['from']} не найден в manifest с тем же hash")
    if h(app / cm["patch"]["path"]) != cm["patch"]["sha256"] or r4_hash.get(cm["patch"]["path"]) != cm["patch"]["sha256"]:
        probs.append("patch-файл контракта не совпадает с архивной копией r4")
    used = ["inputs/contract/" + r["path"] for r in cm["files"]]
    rh, err = rerun_setup(app, "setup_contract.py", "inputs/contract", used)
    if err or any(rh[u] != r["used_sha256"] for u, r in zip(used, cm["files"])):
        probs.append(f"повторный setup_contract.py не воспроизводит hash: {err or rh}")
    add("I4", not probs, f"контракт {cm.get('contract_id')}: модифицировано {sum(r['modified'] for r in cm['files'])} из {len(cm['files'])}, hash раздельны, воспроизводимо",
        problems=probs, modified=[{k: r[k] for k in ("path", "original_sha256", "used_sha256")} for r in cm["files"] if r["modified"]])

    # I5 K02 v4
    k2 = json.loads((app / "inputs/k02v4/MANIFEST.json").read_text(encoding="utf-8"))
    probs = []
    if h(app / k2["original"]["path"]) != k2["original"]["sha256"] or r4_hash.get(k2["original"]["path"]) != k2["original"]["sha256"]:
        probs.append("original != архивной копии r4")
    if h(app / k2["adapted"]["path"]) != k2["adapted"]["sha256"]:
        probs.append("adapted_sha256 != используемому файлу")
    rh, err = rerun_setup(app, "setup_k02.py", "inputs/k02v4", [k2["adapted"]["path"]])
    if err or rh[k2["adapted"]["path"]] != k2["adapted"]["sha256"]:
        probs.append(f"повторный setup_k02.py не воспроизводит hash: {err or rh}")
    add("I5", not probs, "K02 v4: original/adapted hash раздельны, воспроизводимо", problems=probs,
        original_sha256=k2["original"]["sha256"], adapted_sha256=k2["adapted"]["sha256"])

    # I6 используемые модули
    txt = {p.name: p.read_text(encoding="utf-8") for p in (app / "tools").glob("*.py")}
    probs = []
    if '"k03v2_root"' not in txt.get("build_evidence.py", ""):
        probs.append("build_evidence.py не импортирует k03v2_root")
    if 'inputs" / "contract"' not in txt.get("contract.py", ""):
        probs.append("contract.py не импортирует inputs/contract")
    if '"k02v4"' not in txt.get("explain_ref.py", ""):
        probs.append("explain_ref.py не импортирует k02v4")
    for name, t in txt.items():
        if name.startswith("setup_") or name == "copy_inputs.py":
            continue
        for arch in ('"k03_root" / "research"', "inputs/k05_root/round-3-results/K05/k05r3_contract", 'r4" / "K02" / "fixed'):
            if arch in t:
                probs.append(f"{name} импортирует архивную копию: {arch}")
    add("I6", not probs, "используемые модули — модифицированные копии; архивные копии не импортируются", problems=probs)

    # I7 routes deferred
    data = (app / "web/data.js").read_text(encoding="utf-8")
    docs = (app / "README.md").read_text(encoding="utf-8") + (app / "web/app.js").read_text(encoding="utf-8")
    add("I7", '"routes"' not in data and "routes" in docs,
        "routes: значений в data.js нет, пробел задокументирован" if '"routes"' not in data else "в data.js есть routes")

    # I8 атрибуция web через checker раунда 5
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out = tf.name
    r = subprocess.run([sys.executable, a.checker, "--app-root", str(app), "--repo", a.repo, "--json", out], capture_output=True, text=True)
    rep = json.loads(Path(out).read_text(encoding="utf-8"))
    Path(out).unlink()
    fails = [x for x in rep["results"] if x["status"] == "FAIL"]
    add("I8", not fails, f"checker R5 ({h(a.checker)[:12]}): {rep['summary']}", failed=[{"id": x["id"], "text": x["text"]} for x in fails])

    rep_all = {"checker": "K08 R6 check_r6_acceptance", "app_root": str(app), "results": res,
               "summary": {v: sum(1 for x in res if x["verdict"] == v) for v in ("PASS", "FAIL")}}
    if a.json:
        Path(a.json).write_text(json.dumps(rep_all, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for x in res:
        print(f"[{x['verdict']}] {x['invariant']} {x['text']}" + (f" — {x.get('problems') or x.get('failed') or ''}" if x["verdict"] == "FAIL" else ""))
    print(json.dumps(rep_all["summary"]))
    sys.exit(1 if rep_all["summary"]["FAIL"] else 0)


if __name__ == "__main__":
    main()
