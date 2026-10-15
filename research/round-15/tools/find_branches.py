"""Где работают роли раунда 15 — без реестра владельца.

Роль считается «живущей» в ветке, если в ветке есть её handoff
research/handoffs/astana/<роль>/round<N>/STATUS.md. Скрипт скачивает список
веток claude/* из origin, ищет в каждой эти файлы и печатает для каждой роли
самую свежую ветку, SHA, время последнего коммита и code_sha из DELIVERY.json.

    python3 research/round-15/tools/find_branches.py              # все роли
    python3 research/round-15/tools/find_branches.py --role R07   # одна роль (все её ветки)
    python3 research/round-15/tools/find_branches.py --build      # последняя сборка R01 (BUILD.json)
    python3 research/round-15/tools/find_branches.py --json       # то же в JSON
    python3 research/round-15/tools/find_branches.py --round 14   # проверка на данных раунда 14

Только чтение: скрипт ничего не коммитит и не пушит. Нужен git и доступ к origin.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import subprocess
import sys

ROLES = [f"R{n:02d}" for n in range(1, 18)]
ALIVE_MINUTES = 90  # моложе — значит, роль сейчас ведёт другая сессия


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def fetch(skip: bool) -> None:
    if skip:
        return
    # Только ветки claude/*: в них работают сессии Claude Code.
    git("fetch", "--quiet", "--prune", "origin", "+refs/heads/claude/*:refs/remotes/origin/claude/*", check=False)


def remote_branches() -> list[str]:
    out = git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/claude/")
    return [line.strip() for line in out.splitlines() if line.strip()]


def scan(round_no: int) -> dict[str, list[dict]]:
    """Для каждой роли — ветки с её handoff, лучшая первой.

    Порядок: 1) ветка, где STATUS роли меняли последним; при равенстве — 2) ветка, которую роль сама
    назвала в STATUS, 3) ветка по соглашению claude/r<N>-<роль>. Ветки, созданные от чужих веток,
    наследуют чужие STATUS — поэтому важен не факт наличия файла, а где его меняли и что в нём написано.
    """
    found: dict[str, list[dict]] = {role: [] for role in ROLES}
    now = datetime.now(timezone.utc)
    for ref in remote_branches():
        names = set(git("ls-tree", "-r", "--name-only", ref, "research/handoffs/astana", check=False).splitlines())
        branch = ref.removeprefix("origin/")
        head_sha, head_stamp = git("log", "-1", "--format=%H %ct", ref).split()
        head_time = datetime.fromtimestamp(int(head_stamp), tz=timezone.utc)
        for role in ROLES:
            status_path = f"research/handoffs/astana/{role}/round{round_no}/STATUS.md"
            if status_path not in names:
                continue
            touched = git("log", "-1", "--format=%ct", ref, "--", status_path).strip()
            touched_time = datetime.fromtimestamp(int(touched), tz=timezone.utc) if touched else head_time
            head_text = "\n".join(git("show", f"{ref}:{status_path}", check=False).splitlines()[:25])
            declared = re.findall(r"claude/[A-Za-z0-9._/-]+", head_text)
            declared_branch = declared[0].rstrip("`*.,;:)") if declared else None
            delivery = git("show", f"{ref}:research/round-{round_no}-results/{role}/DELIVERY.json", check=False)
            code_sha = None
            if delivery.strip():
                try:
                    data = json.loads(delivery)
                    code_sha = data.get("code_sha") if isinstance(data, dict) else None
                    if code_sha is not None:
                        code_sha = str(code_sha)[:40]
                except ValueError:
                    code_sha = "DELIVERY.json не читается"
            found[role].append({
                "branch": branch,
                "head": head_sha[:10],
                "last_commit_utc": head_time.strftime("%Y-%m-%d %H:%M"),
                "minutes_ago": int((now - head_time).total_seconds() // 60),
                "status_updated_utc": touched_time.strftime("%Y-%m-%d %H:%M"),
                "named_by_convention": branch == f"claude/r{round_no}-{role}",
                "declared_in_status": declared_branch == branch,
                "delivery_code_sha": code_sha,
            })
    for role in found:
        # Главное — где STATUS роли меняли последним (брошенная ветка проигрывает живой);
        # копия, унаследованная другой веткой, имеет то же время — тогда решают самоназвание и имя ветки.
        found[role].sort(key=lambda row: (row["status_updated_utc"], row["declared_in_status"],
                                          row["named_by_convention"]), reverse=True)
    return found


def latest_build(found: dict[str, list[dict]], round_no: int) -> dict | None:
    """BUILD.json R01: {"build": "B1", "code_sha": "…", "at": "…"} из самой свежей ветки R01."""
    for row in found.get("R01", []):
        raw = git("show", f"origin/{row['branch']}:research/round-{round_no}-results/R01/BUILD.json", check=False)
        if raw.strip():
            try:
                build = json.loads(raw)
            except ValueError:
                continue
            if isinstance(build, dict):
                return {**build, "branch": row["branch"]}
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument("--build", action="store_true", help="показать последнюю сборку R01")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--round", type=int, default=15)
    parser.add_argument("--no-fetch", action="store_true", help="не обращаться к origin (уже скачано)")
    args = parser.parse_args()

    fetch(args.no_fetch)
    found = scan(args.round)

    if args.build:
        build = latest_build(found, args.round)
        if args.json:
            print(json.dumps(build, ensure_ascii=False, indent=2))
        elif build:
            print(f"Сборка R01: {build.get('build', '?')} · код {build.get('code_sha', '?')} · ветка {build['branch']}"
                  f" · {build.get('at', '')}")
        else:
            print("Сборки R01 раунда ещё нет (нет BUILD.json). База — FINAL-4 a4937462.")
        return 0

    roles = [args.role] if args.role else ROLES
    if args.json:
        print(json.dumps({role: found[role] for role in roles}, ensure_ascii=False, indent=2))
        return 0
    for role in roles:
        rows = found[role]
        if not rows:
            print(f"{role}: ветки нет — роль ещё не начата")
            continue
        shown = rows if args.role else rows[:1]
        for i, row in enumerate(shown):
            alive = " · ЖИВАЯ (идёт работа)" if row["minutes_ago"] < ALIVE_MINUTES else ""
            prefix = role if i == 0 else " " * len(role)
            print(f"{prefix}: {row['branch']} @ {row['head']} · {row['last_commit_utc']} UTC"
                  f" ({row['minutes_ago']} мин назад){alive} · поставка: {row['delivery_code_sha'] or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
