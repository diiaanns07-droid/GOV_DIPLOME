"""K01 round-3: проверка git-объектов из snapshots.json (без научных выводов).
Для каждой ветки: один git fetch, наличие коммита SHA, предок ли он текущей вершины ветки,
список файлов research/next-round/<KXX>/ в этом коммите (+ sha256 блобов)."""
import json, subprocess, hashlib, sys, datetime

SRC = "origin/codex/research-import-2026-10-05"
def git(*a, check=False):
    r = subprocess.run(["git", *a], capture_output=True)
    return r.returncode, r.stdout, r.stderr.decode(errors="replace").strip()

_, snap_raw, _ = git("show", f"{SRC}:research/round-3/snapshots.json")
snap = json.loads(snap_raw)
_, src_sha, _ = git("rev-parse", SRC)

def check(slot, branch, sha, folder, role):
    rec = {"slot": slot, "role": role, "branch": branch, "sha": sha, "folder": folder}
    rc, _, err = git("fetch", "origin", branch)
    rec["fetch"] = "ok" if rc == 0 else f"failed: {err.splitlines()[-1] if err else rc}"
    rc, out, _ = git("rev-parse", f"origin/{branch}")
    rec["branch_tip"] = out.decode().strip() if rc == 0 else None
    rc, out, _ = git("cat-file", "-t", sha)
    rec["commit_present"] = rc == 0 and out.decode().strip() == "commit"
    if not rec["commit_present"]:
        rec["status"] = "commit_unavailable"
        rec["reason"] = "SHA не найден локально после одного fetch ветки" + ("" if rec["fetch"] == "ok" else f"; fetch: {rec['fetch']}")
        rec["files"] = []
        return rec
    if rec["branch_tip"]:
        rc, _, _ = git("merge-base", "--is-ancestor", sha, rec["branch_tip"])
        rec["sha_in_branch_history"] = rc == 0
        rec["tip_equals_sha"] = rec["branch_tip"] == sha
    rc, out, _ = git("ls-tree", "-r", "-l", sha, "--", folder)
    files = []
    for line in out.decode("utf-8", "replace").splitlines():
        meta, path = line.split("\t", 1)
        mode, typ, blob, size = meta.split()
        _, data, _ = git("cat-file", "blob", blob)
        files.append({"path": path, "blob": blob, "size": int(size),
                      "sha256": hashlib.sha256(data).hexdigest()})
    rec["files"] = files
    rec["status"] = "ok" if files else "folder_missing"
    if rec.get("sha_in_branch_history") is False:
        rec["status"] += "_but_sha_not_in_branch_history"
    return rec

results = []
for a in snap["assignments"]:
    slot = a["slot"]
    results.append(check(slot, a["branch"], a["sha"], f"research/next-round/{slot}/", "primary"))
    if slot == "K03":
        k02 = next(x for x in snap["assignments"] if x["slot"] == "K02")
        results.append(check(slot, k02["branch"], k02["sha"], "research/next-round/K03/",
                             "secondary (clever-mccarthy; по заданию K01)"))

manifest = {
    "task": "K01 round-3: контроль сохранности git-объектов прошлого раунда",
    "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "snapshots_source": f"{SRC}:research/round-3/snapshots.json",
    "snapshots_source_commit": src_sha.decode().strip(),
    "snapshots_base": snap.get("base"),
    "scope": "Только наличие коммитов и файлов; содержание и научные выводы не проверялись.",
    "summary": {s: sum(r["status"] == s for r in results) for s in sorted({r["status"] for r in results})},
    "entries": results,
}
json.dump(manifest, sys.stdout, ensure_ascii=False, indent=2)
