"""R08 · «Картина дня» после сцены 0 «ИИ-разбор» (поправка П3): числа растут ровно на созданные записи и сходятся.

    CIVIC_DEMO=1 CIVIC_DEMO_WORLD=1 python3 app.py --port 8660         # сборка R01 с модулем R04 intake
    CIVIC_STAND_PASSWORD=… python3 tests/civic/R08/scene0_check.py --base http://127.0.0.1:8660 [--out <файл.json>]

ВНИМАНИЕ: проверка ПИШЕТ в базу стенда — «Создать задачи» по примеру «обращения за ночь» (R02, demo: true), как ведущий
в сцене 0. Запускать на одноразовой базе стенда (init + seed + create-editor), не на базе показа.
Пароль — только из переменной окружения. Нет модуля R04 (503 module_not_ready) — NOT_RUN, а не FAIL.
Что проверяет:
  S0  вход сотрудника и CSRF-токен сессии;
  I1  intake/analyze {sample: "night"} отвечает итогом и задачами; I2 intake/commit создаёт записи;
  D1  «Картина дня» (город): новые сегодня и за неделю выросли ровно на число созданных записей, в работе / не исправлено
      в срок / исправлено за 7 дней не изменились; сводка текстом называет новое число;
  D2  Ситуационный центр после разбора = «Картина дня» (те же пять чисел);
  D3  повторное «Создать задачи» того же разбора — 0 новых записей, числа те же;
  D4  идущий кризисный штаб R17 остаётся в «Пульсе»: среди трёх видимых тревог есть тревога со ссылкой на идущий штаб
      (кнопку штаба страница ставит ей — ui_check «пульс: …»);
  W   сверка world_check.py после разбора (C1–C11, без EXPECTED.json — числа демо-мира уже другие).
Итог — JSON (по умолчанию research/round-15-results/R08/scene0/scene0_check.json); код выхода 1, если есть FAIL.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_check  # noqa: E402  (соседний скрипт R08: клиент, отчёт, пять чисел)
from world_check import V2, Client, Report, kpi_values  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
GROW = ("new_day", "new_week")
SAME = ("in_progress", "overdue", "fixed_week")


class CsrfClient(Client):
    """Клиент world_check + заголовок X-CSRF-Token у POST (шлюз R01: unsafe-запросы сотрудника — с токеном сессии)."""

    csrf = None

    def call(self, method: str, path: str, body=None):
        if method == "GET" or not self.csrf:
            return super().call(method, path, body)
        req = urllib.request.Request(self.base + path, data=json.dumps(body or {}).encode(), method=method)
        req.add_header("Origin", self.base)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except ValueError:
                return e.code, None

    def post(self, path: str, body: dict):
        status, data = self.call("POST", path, body)
        if isinstance(data, dict) and data.get("ok") is True and "data" in data:
            data = data["data"]
        return status, data


def text_number(body: dict) -> str:
    return re.sub(r"\s", "", ((body or {}).get("text") or {}).get("ru") or "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default="http://127.0.0.1:8660")
    ap.add_argument("--user", default="operator")
    ap.add_argument("--password-env", default="CIVIC_STAND_PASSWORD")
    ap.add_argument("--out", default=str(ROOT / "research/round-15-results/R08/scene0/scene0_check.json"))
    a = ap.parse_args(argv)
    c, rep = CsrfClient(a.base), Report()

    password = os.environ.get(a.password_env)
    if not password:
        rep.skip("S0", "вход сотрудника", f"нет {a.password_env}")
        return world_check.finish(rep, a)
    status, _ = c.call("POST", "/api/civic/v1/session/login", {"username": a.user, "password": password})
    _, sess = c.get("/api/civic/v1/session")
    c.csrf = (sess or {}).get("csrf_token")
    rep.check("S0", "вход сотрудника и CSRF-токен", status == 200 and bool(c.csrf), {"status": status})
    if status != 200 or not c.csrf:
        return world_check.finish(rep, a)

    _, day0 = c.get(V2 + "/akim/summary")
    before = kpi_values(day0)

    status, an = c.post(V2 + "/intake/analyze", {"sample": "night"})
    if status in (404, 501, 503):
        rep.skip("I1", "ИИ-разбор примера «за ночь»", f"в сборке нет модуля R04 intake (HTTP {status})")
        return world_check.finish(rep, a)
    tasks = (an or {}).get("tasks") or []
    rep.check("I1", "ИИ-разбор примера «за ночь»: итог и задачи", status == 200 and bool(tasks) and isinstance((an or {}).get("summary"), dict),
              {"status": status, "summary": (an or {}).get("summary")})
    if status != 200 or not tasks:
        return world_check.finish(rep, a)
    body = {"batch_id": an.get("batch_id"), "task_ids": [t["id"] for t in tasks]}
    status, cm = c.post(V2 + "/intake/commit", body)
    created = int((cm or {}).get("created") or 0)
    rep.check("I2", "«Создать задачи»: записи созданы", status == 200 and created > 0,
              {"status": status, **{k: (cm or {}).get(k) for k in ("created", "joined_existing", "joined", "skipped_no_address", "failed")}})

    _, day1 = c.get(V2 + "/akim/summary")
    after = kpi_values(day1)
    grow = {k: (before.get(k), after.get(k)) for k in GROW}
    same = {k: (before.get(k), after.get(k)) for k in SAME}
    rep.check("D1", f"«Картина дня»: новые сегодня и за неделю + {created}, остальные числа те же",
              all(isinstance(v[0], int) and v[1] == v[0] + created for v in grow.values()) and all(v[0] == v[1] for v in same.values()),
              {"grow": grow, "same": same, "created": created})
    rep.check("D1", "сводка текстом называет новое число обращений",
              str(after.get("new_day")) in text_number(day1), ((day1 or {}).get("text") or {}).get("ru", "")[:160])

    _, board1 = c.get(V2 + "/akim/board")
    rep.check("D2", "Ситуационный центр после разбора = «Картина дня»", kpi_values(board1) == after,
              {"board": kpi_values(board1), "day": after})

    status, cm2 = c.post(V2 + "/intake/commit", body)
    _, day2 = c.get(V2 + "/akim/summary")
    rep.check("D3", "повторное «Создать задачи» — 0 новых, числа те же",
              status == 200 and int((cm2 or {}).get("created") or 0) == 0 and kpi_values(day2) == after,
              {"status": status, "created": (cm2 or {}).get("created"), "day": kpi_values(day2)})

    crisis = (day1 or {}).get("crisis") or {}
    items = ((day1 or {}).get("pulse") or {}).get("items") or []
    if crisis.get("available") and crisis.get("active"):
        visible = [((it.get("crisis") or {}).get("incident"), it.get("category")) for it in items[:3]]
        rep.check("D4", "идущий штаб в «Пульсе»: тревога со ссылкой на него — среди трёх видимых",
                  any(inc for inc, _ in visible), {"visible": visible, "active": [x.get("id") for x in crisis["active"]]})
    else:
        rep.skip("D4", "идущий штаб в «Пульсе»", "в демо-мире нет идущего кризиса")

    w_out = str(Path(a.out).with_name("world_check_after_scene0.json"))
    w_code = world_check.main(["--base", a.base, "--user", a.user, "--password-env", a.password_env, "--out", w_out])
    rep.check("W", "сверка world_check после разбора (C1–C11)", w_code == 0, w_out)
    return world_check.finish(rep, a)


if __name__ == "__main__":
    sys.exit(main())
