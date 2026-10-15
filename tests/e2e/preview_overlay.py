#!/usr/bin/env python3
"""R10 · превью интеграции: сборка R01 + модули из веток ролей (как R01 соберёт), чтобы проверить работу ролей до сборки.

Для каждой ветки роли берутся файлы, изменённые её коммитами после --since (кроме research/ и tests/), и кладутся поверх
рабочей копии с базой R01. Наложение «чистое», если в базе R01 лежит ровно та версия файла, что была у роли до этих
коммитов (R01 ничего в нём не правил) — иначе файл помечается КОНФЛИКТ и не кладётся (без --force).
Патчи для R01 из папок ролей (--patch ветка:путь) применяются через git apply.

  python3 tests/e2e/preview_overlay.py --worktree ../bpv3 --base origin/claude/sharp-dijkstra-0t87gl \
      --since "2026-10-13 03:00" --branches origin/claude/r14-R11,origin/claude/r14-R07,... \
      [--patch origin/claude/r14-R08:research/round-14-results/R08/r01_today_r08.patch] [--force]

Рабочая копия создаётся (git worktree add --detach), если её нет. Итог — таблица в stdout и <worktree>/PREVIEW.json.
Ничего не коммитит и не пушит; ветки ролей только читаются.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def git(*args, cwd=None, check=True, inp=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, input=inp)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def blob(ref, path, cwd):
    r = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{ref}:{path}"], cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--since", required=True)
    ap.add_argument("--branches", required=True)
    ap.add_argument("--patch", action="append", default=[])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    repo = Path(git("rev-parse", "--show-toplevel"))
    wt = Path(a.worktree).resolve()
    if not wt.exists():
        git("worktree", "add", "--detach", str(wt), a.base, cwd=repo)
    base = git("rev-parse", "--short", a.base, cwd=repo)
    report = {"base": a.base, "base_sha": base, "since": a.since, "branches": [], "patches": []}
    for br in [b for b in a.branches.split(",") if b]:
        commits = git("log", f"--since={a.since}", "--format=%H", br, cwd=repo).split()
        head = git("rev-parse", "--short", br, cwd=repo)
        if not commits:
            report["branches"].append({"branch": br, "head": head, "files": [], "note": "нет коммитов после --since"})
            print(f"{br} {head}: нет коммитов после {a.since}")
            continue
        prev = commits[-1] + "~1"
        files = [f for f in git("diff", "--name-only", "--diff-filter=AM", prev, br, cwd=repo).splitlines()
                 if f and not f.startswith(("research/", "tests/"))]
        rows = []
        for f in files:
            clean = blob(a.base, f, repo) == blob(prev, f, repo)
            take = clean or a.force
            if take:
                git("checkout", br, "--", f, cwd=wt)
            rows.append({"file": f, "clean": clean, "applied": take})
            if not clean:
                print(f"  КОНФЛИКТ {br} {f}: в базе R01 другая версия{' — положено (--force)' if a.force else ' — пропущен'}")
        report["branches"].append({"branch": br, "head": head, "from": git("rev-parse", "--short", prev, cwd=repo), "files": rows})
        print(f"{br} {head}: файлов {len(rows)}, чисто {sum(r['clean'] for r in rows)}")
    for spec in a.patch:
        br, p = spec.split(":", 1)
        # Текст патча — как есть (без strip): последние пустые строки контекста — часть патча.
        text = subprocess.run(["git", "show", f"{br}:{p}"], cwd=repo, capture_output=True, text=True, check=True).stdout
        r = subprocess.run(["git", "apply", "-v"], cwd=wt, capture_output=True, text=True, input=text)
        ok = r.returncode == 0
        report["patches"].append({"patch": spec, "applied": ok, "log": (r.stderr or r.stdout).strip()[-400:]})
        print(f"patch {spec}: {'применён' if ok else 'НЕ применён'}")
    (wt / "PREVIEW.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    bad = sum(1 for b in report["branches"] for r in b["files"] if not r["clean"]) + sum(1 for p in report["patches"] if not p["applied"])
    print("ГОТОВО:", wt, "· конфликтов", bad)
    return 1 if bad and not a.force else 0


if __name__ == "__main__":
    sys.exit(main())
