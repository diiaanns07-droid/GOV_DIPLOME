"""Обслуживание таблиц feedback_* без веб-сервера.

    python -m ui.civic_feedback stats --db .runtime/civic.sqlite3
    python -m ui.civic_feedback purge-antispam --db .runtime/civic.sqlite3 --days 30

stats печатает только счётчики (без текстов и служебных хэшей). purge-antispam
обезличивает хэш отправителя и client_request_id у сообщений старше N дней;
тексты, решения и журнал остаются.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .service import FeedbackService


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ui.civic_feedback", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    stats = sub.add_parser("stats", help="счётчики сообщений по статусам")
    stats.add_argument("--db", required=True)
    purge = sub.add_parser("purge-antispam", help="обезличить служебные антиспам-поля старых сообщений")
    purge.add_argument("--db", required=True)
    purge.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)

    if not Path(args.db).is_file():
        print(f"База не найдена: {args.db}", file=sys.stderr)
        return 2
    if getattr(args, "days", 1) < 1:
        print("--days должен быть >= 1", file=sys.stderr)
        return 2
    service = FeedbackService(args.db, lambda object_id: None)
    try:
        if args.command == "stats":
            print(json.dumps(service.stats(), ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"purged": service.purge_antispam(args.days), "older_than_days": args.days}))
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
