"""Командная строка жалоб v2.

  python -m ui.civic_feedback.v2 migrate --v1 <civic.sqlite3> [--db <v2.sqlite3>] [--real]
  python -m ui.civic_feedback.v2 stats --db <v2.sqlite3>
  python -m ui.civic_feedback.v2 events --db <v2.sqlite3> [--after N]

По умолчанию перенесённые записи помечаются demo=true (происхождение старых строк неизвестно,
выдавать синтетику за реальные обращения нельзя). --real — только если владелец подтвердил.
"""

import argparse
import json
import sys

from .migrate import migrate
from .store import ComplaintStore


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ui.civic_feedback.v2")
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("migrate", help="перенести сообщения v1 в v2")
    m.add_argument("--v1", required=True)
    m.add_argument("--db", help="база v2 (по умолчанию та же, что v1)")
    m.add_argument("--real", action="store_true", help="не помечать перенесённые записи как demo")
    s = sub.add_parser("stats")
    s.add_argument("--db", required=True)
    e = sub.add_parser("events")
    e.add_argument("--db", required=True)
    e.add_argument("--after", type=int, default=0)
    args = parser.parse_args(argv)

    store = ComplaintStore(args.db or args.v1)
    try:
        if args.cmd == "migrate":
            out = migrate(args.v1, store, demo=not args.real)
        elif args.cmd == "stats":
            items = store.list(include_duplicates=True)
            by_status = {}
            for item in items:
                by_status[item["status"]] = by_status.get(item["status"], 0) + 1
            out = {"total": len(items), "by_status": by_status, "overdue": len(store.overdue()),
                   "demo": sum(1 for i in items if i.get("demo"))}
        else:
            out = store.events_since(args.after)
    finally:
        store.close()
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
