"""Картина дня в терминале: python -m ui.civic_akim [--date 2026-10-12] [--district nura] [--lang kk] [--json]"""
from __future__ import annotations

import argparse
import json
import sys

from .summary import AkimError, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="«Картина дня» для акима (R08)")
    ap.add_argument("--date", help="день, например 2026-10-12 (по умолчанию сегодня)")
    ap.add_argument("--district", help="id района: nura, esil, … (по умолчанию весь город)")
    ap.add_argument("--lang", choices=("ru", "kk"), default="ru")
    ap.add_argument("--json", action="store_true", help="весь ответ API")
    args = ap.parse_args(argv)
    try:
        s = summary(date=args.date, district=args.district)
    except AkimError as exc:
        print(f"{exc.field}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    k = s["kpi"]
    print(f"Картина дня · {s['date']} · {(s['district'] or {}).get('ru', 'весь город')}"
          f"{'  [ПРИМЕР: демо-данные]' if s['demo']['any'] else ''}")
    print(f"новые за день {k['new_day']['value']} (неделю назад {k['new_day']['prev']}) · "
          f"за 7 дней {k['new_week']['value']} ({k['new_week']['prev']}) · в работе {k['in_progress']['value']} · "
          f"ждут ответа {k['in_progress']['waiting']} · просрочено {k['overdue']['value']} · "
          f"исправлено за неделю {k['fixed_week']['value']}")
    print(s["text"][args.lang])
    if s["hot"].get("available"):
        for h in s["hot"]["items"]:
            print(f"  {h['rank']:>2}. ({h['count']}) {h['target']['label_' + args.lang]} · уровень {h['level']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
