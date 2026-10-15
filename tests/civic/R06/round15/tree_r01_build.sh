#!/usr/bin/env bash
# Дерево «как сборка B1»: последняя ветка R01 раунда 15 (B0: маршруты R06 уже есть) + пути R06 из этой рабочей копии
# + то, чего в B0 ещё нет: файлы ленты в CIVIC_ASSETS и теги notify.css / notify.js в web/index.html (INTEGRATION §B).
#   bash tests/civic/R06/round15/tree_r01_build.sh /путь/к/дереву      (папки быть не должно; ветку R01 можно задать: R01=…)
#   NODE_PATH="$(npm root -g)" PYTHON=python3 node tests/civic/R06/round15/browser_r15.cjs /путь/к/дереву кадры
# Удалить: git worktree remove --force /путь/к/дереву
set -euo pipefail
OUT="$1"
SRC="$(git rev-parse --show-toplevel)"
git -C "$SRC" fetch -q origin '+refs/heads/claude/*:refs/remotes/origin/claude/*' || true
R01="${R01:-$(python3 "$SRC/research/round-15/tools/find_branches.py" --no-fetch --json --role R01 \
  | python3 -c 'import json,sys; rows=list(json.load(sys.stdin).values())[0]; print(rows[0]["branch"] if rows else "")')}"
[ -n "$R01" ] || { echo "нет ветки R01"; exit 1; }
git -C "$SRC" worktree add --detach "$OUT" "origin/$R01" >/dev/null
echo "R01 ← $R01 @ $(git -C "$OUT" rev-parse --short HEAD)"
for p in ui/civic_store web/civic/proposals web/civic/ideas web/civic/notify tests/civic/R06; do
  rm -rf "$OUT/$p"; mkdir -p "$(dirname "$OUT/$p")"; cp -r "$SRC/$p" "$OUT/$p"
done
cd "$OUT"
# 1) файлы ленты — в белый список статики /civic/* (рядом с ideas/works R06)
if ! grep -q '"notify/notify.js"' ui/web_server.py; then
  python3 - <<'EOF'
from pathlib import Path
p = Path("ui/web_server.py")
s = p.read_text(encoding="utf-8")
anchor = '"ideas/ideas.js", "ideas/ideas.css", "proposals/works.js",'
assert anchor in s, "нет строки ideas/works в CIVIC_ASSETS"
s = s.replace(anchor, anchor + ' "notify/notify.js", "notify/notify.css",', 1)
p.write_text(s, encoding="utf-8")
EOF
fi
# 2) теги: стиль после ideas.css, скрипт после works.js (defer — по порядку, после birge.js и ui-kit)
if ! grep -q 'civic/notify/notify.js' web/index.html; then
  python3 - <<'EOF'
from pathlib import Path
p = Path("web/index.html")
s = p.read_text(encoding="utf-8")
css = '<link rel="stylesheet" href="/civic/ideas/ideas.css" />'
js = '<script defer src="/civic/proposals/works.js"></script>'
assert css in s and js in s, "нет тегов ideas.css / works.js"
s = s.replace(css, css + '\n    <link rel="stylesheet" href="/civic/notify/notify.css" />', 1)
s = s.replace(js, js + '\n    <script defer src="/civic/notify/notify.js"></script>', 1)
p.write_text(s, encoding="utf-8")
EOF
fi
git -C "$OUT" status --short | head -20
echo "$OUT"
