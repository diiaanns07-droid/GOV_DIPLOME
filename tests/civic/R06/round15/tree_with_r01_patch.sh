#!/usr/bin/env bash
# Дерево для проверки R06 раунда 15 «как в сборке»: HEAD этой ветки (отдельный git worktree) + незакоммиченные пути R06
# + патч для R01 research/round-15-results/R06/r01_round15_r06.patch (маршруты API v2 и теги notify в index.html).
#   bash tests/civic/R06/round15/tree_with_r01_patch.sh /путь/к/дереву      (папки быть не должно)
#   NODE_PATH="$(npm root -g)" PYTHON=python3 node tests/civic/R06/round15/browser_r15.cjs /путь/к/дереву кадры --only notify
# Удалить: git worktree remove --force /путь/к/дереву
set -euo pipefail
OUT="$1"
SRC="$(git rev-parse --show-toplevel)"
git -C "$SRC" worktree add --detach "$OUT" HEAD >/dev/null
for p in ui/civic_store web/civic/proposals web/civic/ideas web/civic/notify tests/civic/R06 research/round-15-results/R06; do
  if [ -d "$SRC/$p" ]; then rm -rf "$OUT/$p"; mkdir -p "$(dirname "$OUT/$p")"; cp -r "$SRC/$p" "$OUT/$p"; fi
done
(cd "$OUT" && git apply -p1 "$SRC/research/round-15-results/R06/r01_round15_r06.patch")
echo "$OUT"
