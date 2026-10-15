#!/bin/bash
# Стенд R16 на чистой базе (по COMMON.txt «КАК ПОДНЯТЬ СТЕНД»): база демо, сотрудник operator, сервер на порту.
#   bash tests/civic/R16/stand_reset.sh [папка=/tmp/birge] [порт=8655]
# Пароль сотрудника стенда — R16_STAFF_PASS (по умолчанию тестовый «demo-stand-pass-2026», только для облачного стенда).
set -e
DIR="${1:-/tmp/birge}"
PORT="${2:-8655}"
PASS="${R16_STAFF_PASS:-demo-stand-pass-2026}"
cd "$(dirname "$0")/../../.."
mkdir -p "$DIR"
if [ -f "$DIR/server.pid" ]; then kill "$(cat "$DIR/server.pid")" 2>/dev/null || true; sleep 1; fi
rm -f "$DIR"/demo.sqlite3*
python3 -B -m ui.civic_store --db "$DIR/demo.sqlite3" init > /dev/null
python3 -B -m ui.civic_store --db "$DIR/demo.sqlite3" seed-demo --package data/civic/astana/demo_synthetic.json > /dev/null
python3 -B -m ui.civic_store --db "$DIR/demo.sqlite3" seed-r14-demo > /dev/null
printf '%s\n%s\n' "$PASS" "$PASS" | python3 -B -m ui.civic_store --db "$DIR/demo.sqlite3" create-editor operator --password-stdin > /dev/null
CIVIC_DB_PATH="$DIR/demo.sqlite3" CIVIC_DEMO=1 nohup python3 -B tests/civic/R16/stand.py --port "$PORT" > "$DIR/server.log" 2>&1 &
echo $! > "$DIR/server.pid"
for i in $(seq 1 40); do curl -s -o /dev/null "http://127.0.0.1:$PORT/api/health" && break; sleep 0.5; done
echo "стенд R16: http://127.0.0.1:$PORT (база $DIR/demo.sqlite3, pid $(cat "$DIR/server.pid"))"
