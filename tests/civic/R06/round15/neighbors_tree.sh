#!/usr/bin/env bash
# Дерево для стыка ленты R06 с настоящими соседями: HEAD этой ветки + незакоммиченные пути R06 + модули соседей из их
# веток раунда 15 (ветки — по find_branches.py; можно передать свои: R16=… R13=… R17=… R09=… R02=…).
#   bash tests/civic/R06/round15/neighbors_tree.sh /путь/к/дереву
# Удалить: git worktree remove --force /путь/к/дереву
set -euo pipefail
OUT="$1"
SRC="$(git rev-parse --show-toplevel)"
git -C "$SRC" fetch -q origin '+refs/heads/claude/*:refs/remotes/origin/claude/*' || true
branch() {  # ветка роли по find_branches.py (лучшая первой)
  python3 "$SRC/research/round-15/tools/find_branches.py" --no-fetch --json --role "$1" \
    | python3 -c 'import json,sys; rows=list(json.load(sys.stdin).values())[0]; print(rows[0]["branch"] if rows else "")'
}
git -C "$SRC" worktree add --detach "$OUT" HEAD >/dev/null
for p in ui/civic_store web/civic/proposals web/civic/ideas web/civic/notify tests/civic/R06; do
  rm -rf "$OUT/$p"; cp -r "$SRC/$p" "$OUT/$p"
done
take() {  # роль, пути…
  local role="$1"; shift
  local b="${!role:-$(branch "$role")}"
  [ -n "$b" ] || { echo "нет ветки $role — пропуск"; return; }
  echo "$role ← $b"
  (cd "$OUT" && git checkout "origin/$b" -- "$@" 2>/dev/null) || echo "  (не все пути есть в $b: $*)"
}
take R16 ui/civic_together web/civic/together
take R13 ui/civic_meetings ui/civic_qa
take R17 ui/civic_agencies
take R09 ui/civic_feedback
take R02 ml/datasets/demo_world_io.py data/civic/astana/demo-world
echo "$OUT"
