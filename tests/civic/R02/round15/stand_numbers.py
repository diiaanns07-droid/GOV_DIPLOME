"""R02 · раунд 15 · сверка чисел живого стенда с демо-миром (CIVIC_DEMO=1, CIVIC_DEMO_WORLD=1).

    python3 tests/civic/R02/round15/stand_numbers.py --base http://127.0.0.1:8656 --user operator --password-file p.txt

Берёт числа из API (то, что рисует интерфейс) и сравнивает с ml.datasets.demo_world_expected на тот же момент:
карта R07 (/heat, «Нура · N»), «Картина дня» R08 (/akim/summary), «Обращения» R09 (/complaints/inbox, /complaints).
Печатает таблицу и пишет JSON (--out). Код выхода 1 — есть расхождение. Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from ml.datasets import demo_world_expected as exp  # noqa: E402
from ml.datasets import demo_world_io as wio  # noqa: E402

OPEN = ("new", "accepted", "in_progress")


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Origin", self.base)
        if self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"null")

    def login(self, user: str, password: str) -> bool:
        status, body = self.call("POST", "/api/civic/v1/session/login", {"username": user, "password": password})
        if status == 200 and (body or {}).get("ok"):
            self.csrf = body["data"].get("csrf_token")
            return True
        return False


def unwrap(body):
    return body["data"] if isinstance(body, dict) and "ok" in body and "data" in body else body


def stand_numbers(c: Client, district: str = "nura") -> dict:
    v2 = "/api/civic/v2"
    out = {}
    for days in (7, 14, 30):
        status, body = c.call("GET", f"{v2}/heat?zoom=10&days={days}")
        row = next((it for it in (body or {}).get("items", []) if (it.get("target") or {}).get("id") == district), {})
        out[f"map_people_{days}d"] = row.get("count") if row.get("state", "active") == "active" else 0
    status, body = c.call("GET", f"{v2}/akim/summary?district={district}")
    kpi = (body or {}).get("kpi") or {}
    for name in ("new_day", "new_week", "in_progress", "overdue", "fixed_week"):
        out[f"day_{name}"] = (kpi.get(name) or {}).get("value")
    out["day_decisions"] = [i.get("id") for i in ((body or {}).get("decisions") or {}).get("items", [])]
    out["day_pulse"] = [(p.get("kind"), p.get("category"), p.get("value"), p.get("ratio"))
                        for p in ((body or {}).get("pulse") or {}).get("items", [])]
    status, body = c.call("GET", f"{v2}/akim/summary")
    rows = (((body or {}).get("districts") or {}).get("items")) or []
    out["day_districts_7d"] = next((r.get("value") for r in rows if r.get("district") == district), None)
    status, body = c.call("GET", f"{v2}/complaints/inbox")
    out["inbox_city"] = (unwrap(body) or {}).get("counts")
    status, body = c.call("GET", f"{v2}/complaints?days=60")
    items = (unwrap(body) or {}).get("items") or []
    now = datetime.now(timezone.utc)
    mine = [x for x in items if x.get("district") == district]
    out["r09_complaints"] = len(items)
    out["r09_complaints_" + district] = len(mine)
    for days in (7, 30):
        since = now - timedelta(days=days)
        recent = [x for x in mine if datetime.fromisoformat(x["created_at"]) >= since]
        out[f"r09_people_open_{days}d"] = sum(x.get("reporters", 1 + int(x.get("metoo") or 0))
                                              for x in recent if x.get("status") in OPEN)
    return out


def expected_numbers(now: datetime, district: str = "nura") -> dict:
    world = wio.load_world()
    e = exp.expected(world, now)
    m = wio.materialize(world, now)
    out = {f"map_people_{d}d": e["heat"][f"districts_{d}d"].get(district, {}).get("people") for d in (7, 14, 30)}
    akim = e["akim"][district]
    for name in ("new_day", "new_week", "in_progress", "overdue", "fixed_week"):
        out[f"day_{name}"] = akim[name]
    out["day_decisions"] = akim["decisions"]
    out["inbox_city"] = e["inbox"]["city"]
    cs = m["complaints"]
    out["r09_complaints"] = len(cs)
    out["r09_complaints_" + district] = sum(1 for x in cs if x["district"] == district)
    for days in (7, 30):
        since = now - timedelta(days=days)
        out[f"r09_people_open_{days}d"] = sum(1 + x["metoo"] for x in cs if x["district"] == district
                                              and x["status"] in OPEN and datetime.fromisoformat(x["created_at"]) >= since)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Сверка стенда с демо-миром R02")
    ap.add_argument("--base", default="http://127.0.0.1:8656")
    ap.add_argument("--user", default="operator")
    ap.add_argument("--password-file", required=True, help="файл с паролем сотрудника (пароль не в командной строке)")
    ap.add_argument("--district", default="nura")
    ap.add_argument("--seeded-at", default=None, help="момент засева ISO (по умолчанию — сейчас)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    c = Client(args.base)
    if not c.login(args.user, Path(args.password_file).read_text(encoding="utf-8").strip()):
        print("вход сотрудника не удался")
        return 2
    got = stand_numbers(c, args.district)
    now = datetime.fromisoformat(args.seeded_at) if args.seeded_at else datetime.now(timezone.utc)
    want = expected_numbers(now, args.district)
    rows, bad = [], 0
    for key in want:
        same = got.get(key) == want[key]
        bad += not same
        rows.append({"metric": key, "stand": got.get(key), "expected": want[key], "same": same})
        print(f"{'OK ' if same else 'НЕТ'} {key:<26} стенд {json.dumps(got.get(key), ensure_ascii=False):<40} "
              f"мир {json.dumps(want[key], ensure_ascii=False)}")
    extra = {k: v for k, v in got.items() if k not in want}
    for key, value in extra.items():
        print(f"    {key:<26} стенд {json.dumps(value, ensure_ascii=False)}")
    if args.out:
        Path(args.out).write_text(json.dumps({"base": args.base, "now": wio.iso(now), "rows": rows, "extra": extra},
                                             ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
