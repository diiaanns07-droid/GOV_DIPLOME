"""R08 · сверка чисел на демо-мире R02 (раунд 15, задача 5): одни и те же числа на всех экранах.

    CIVIC_DEMO=1 CIVIC_DEMO_WORLD=1 python3 app.py --port 8660         # сборка R01 + модули соседей + R08
    CIVIC_STAND_PASSWORD=… python3 tests/civic/R08/world_check.py --base http://127.0.0.1:8660 \\
        [--user operator] [--expected data/civic/astana/demo-world/EXPECTED.json] [--out <файл.json>]

Пароль — только из переменной окружения (в файлы и вывод не попадает). Без пароля — только публичные проверки.
Что сверяет (R08 ничего не пересчитывает за соседей — сверка ловит расхождения правил и подписей):
  C1  «Картина дня» = Ситуационный центр: новые сегодня / за неделю, в работе, просрочено, исправлено (город и район);
  C2  районы «Картины дня» за 7 дней = карта R07 за 7 дней (люди), C3 — то же в Ситуационном центре;
  C4  табло служб Ситуационного центра = табло R17 (agencies/board, 7 дней) построчно;
  C5  «новые за неделю» R08 = «поступило» R17 за 7 дней;
  C6  кризис: Ситуационный центр = «Картина дня» = R17; кнопка штаба у тревоги про снег ведёт в идущий штаб;
  C7  «Жители вместе» и «Встречи»: Ситуационный центр = «Картина дня»; «двор недели» = страница двора R16;
  C8  демо-мир: фикстуры R08 выключены (источники — соседи), в ответах нет id примеров R08;
  C9  «Картина недели»: сумма по дням = числу за неделю; в работе, просрочено, поступило, исправлено и проверено
      за 7 дней = «Картине дня» (одно окно 7 × 24 ч, R10 C5);
  C10 «Нужно решение акима»: у каждого пункта есть адрес; с --expected — те же жалобы, что в EXPECTED.json R02;
  C11 сцена 7: «Поддержать» в «Картине дня» ведёт к делу сцены (GET demo/scenes R01), если сцена есть.
Итог — JSON (по умолчанию research/round-15-results/R08/world_check.json); код выхода 1, если есть FAIL.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
V2 = "/api/civic/v2"
KPI = ("new_day", "new_week", "in_progress", "overdue", "fixed_week")
FIXTURE_IDS = ("inc-demo-", "i-demo-", "yard-demo-", "m-demo-", "o-demo-")


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Origin", self.base)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except ValueError:
                return e.code, None

    def get(self, path: str):
        status, body = self.call("GET", path)
        if isinstance(body, dict) and body.get("ok") is True and "data" in body:
            body = body["data"]
        return status, body


class Report:
    def __init__(self):
        self.rows = []

    def check(self, code: str, name: str, ok: bool, detail=None):
        self.rows.append({"check": code, "name": name, "status": "PASS" if ok else "FAIL",
                          **({"detail": detail} if detail is not None else {})})
        print(("PASS " if ok else "FAIL ") + f"{code} {name}"
              + ("" if ok or detail is None else " — " + json.dumps(detail, ensure_ascii=False)[:400]))

    def skip(self, code: str, name: str, reason: str):
        self.rows.append({"check": code, "name": name, "status": "NOT_RUN", "detail": reason})
        print(f"NOT_RUN {code} {name} — {reason}")


def kpi_values(body: dict) -> dict:
    k = (body or {}).get("kpi") or {}
    return {name: (k.get(name) or {}).get("value") if isinstance(k.get(name), dict) else k.get(name) for name in KPI}


def districts(body: dict) -> dict:
    return {it.get("district"): it.get("value") for it in ((body or {}).get("districts") or {}).get("items") or []}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default="http://127.0.0.1:8660")
    ap.add_argument("--user", default="operator")
    ap.add_argument("--password-env", default="CIVIC_STAND_PASSWORD")
    ap.add_argument("--district", default="nura")
    ap.add_argument("--expected", default=None, help="EXPECTED.json R02 (необязательно)")
    ap.add_argument("--out", default=str(ROOT / "research/round-15-results/R08/world_check.json"))
    a = ap.parse_args(argv)
    c, rep = Client(a.base), Report()
    d = a.district

    _, day_city = c.get(V2 + "/akim/summary")
    _, day_d = c.get(V2 + f"/akim/summary?district={d}")
    _, heat = c.get(V2 + "/heat?zoom=10&days=7")
    if not isinstance(day_city, dict) or "kpi" not in day_city:
        rep.check("C0", "«Картина дня» отвечает", False, day_city)
        return finish(rep, a)

    # C2: районы «Картины дня» = карта R07 (7 дней, люди по району, только «активные» места)
    heat_d = {(it.get("target") or {}).get("id"): (it.get("count") if it.get("state", "active") == "active" else 0)
              for it in (heat or {}).get("items") or []}
    dd = districts(day_city)
    rep.check("C2", "районы «Картины дня» (7 дн.) = карта R07 (7 дн.)",
              bool(dd) and all(heat_d.get(k) == v for k, v in dd.items()), {"day": dd, "map": heat_d})

    password = os.environ.get(a.password_env)
    staff = False
    if password:
        status, body = c.call("POST", "/api/civic/v1/session/login", {"username": a.user, "password": password})
        staff = status == 200
        rep.check("S0", "вход сотрудника", staff, status)
    if not staff:
        for code in ("C1", "C3", "C4", "C5", "C6", "C7", "C8", "C9"):
            rep.skip(code, "проверки сотрудника", f"нет пароля в {a.password_env} или вход не удался")
    else:
        _, board_city = c.get(V2 + "/akim/board")
        _, board_d = c.get(V2 + f"/akim/board?district={d}")
        _, week = c.get(V2 + "/akim/week")
        _, r17 = c.get(V2 + "/agencies/board?days=7")

        for scope, day, brd in (("город", day_city, board_city), (d, day_d, board_d)):
            rep.check("C1", f"«Картина дня» = Ситуационный центр: числа ({scope})",
                      kpi_values(day) == kpi_values(brd), {"day": kpi_values(day), "board": kpi_values(brd)})
        rep.check("C3", "районы Ситуационного центра = «Картина дня»", districts(board_city) == dd,
                  {"board": districts(board_city), "day": dd})

        # C4–C5: табло служб — числа R17 как есть
        sv = (board_city or {}).get("services") or {}
        rows17 = {r.get("service"): r for r in (r17 or {}).get("services") or (r17 or {}).get("items") or []}
        diff = []
        for it in sv.get("items") or []:
            r = rows17.get(it["service"]) or {}
            for key in ("open", "overdue", "median_answer_days", "verified_share"):
                want = r.get(key)
                got = it.get(key)
                if key == "verified_share" and isinstance(want, (int, float)):
                    want = round(want / 100.0 if want > 1 else want, 3)
                if key == "median_answer_days" and isinstance(want, (int, float)):
                    want = round(want, 1)
                if got != want:
                    diff.append({"service": it["service"], "key": key, "board": got, "r17": want})
        rep.check("C4", "табло служб Ситуационного центра = табло R17 (7 дн.)",
                  bool(sv.get("items")) and not diff and len(sv.get("items")) == len(rows17), diff[:6] or None)
        totals17 = (r17 or {}).get("totals") or {}
        rep.check("C5", "«новые за неделю» R08 = «поступило» R17 (7 дн.)",
                  kpi_values(board_city)["new_week"] == totals17.get("received"),
                  {"r08": kpi_values(board_city)["new_week"], "r17": totals17.get("received")})

        # C6: кризис
        ids = lambda part: sorted(x.get("id") for x in ((part or {}).get("active") or []))  # noqa: E731
        rep.check("C6", "кризис: Ситуационный центр = «Картина дня»",
                  ids(board_city.get("crisis")) == ids(day_city.get("crisis")),
                  {"board": ids(board_city.get("crisis")), "day": ids(day_city.get("crisis"))})
        active = ids(board_city.get("crisis"))
        snow = [p for p in ((day_city.get("pulse") or {}).get("items") or []) if p.get("category") == "snow_ice"]
        if active and snow:
            link = (snow[0].get("crisis") or {}).get("link") or ""
            rep.check("C6", "тревога «снег» → «Открыть кризисный штаб» ведёт в идущий штаб",
                      any(link.endswith(("crisis/" + i, "crisis=" + i)) for i in active), {"link": link, "active": active})
        else:
            rep.skip("C6", "кнопка штаба у тревоги «снег»", "нет идущего кризиса или тревоги про снег")

        # C7: жители и встречи — один и тот же блок соседа на двух экранах
        tg_b, tg_d = board_city.get("together") or {}, day_city.get("together") or {}
        rep.check("C7", "«Жители вместе»: Ситуационный центр = «Картина дня»",
                  tg_b.get("counts") == tg_d.get("counts") and tg_b.get("available") == tg_d.get("available"),
                  {"board": tg_b.get("counts"), "day": tg_d.get("counts")})
        y = tg_b.get("yard_of_week")
        if y:
            _, yard = c.get(V2 + "/together/yards/" + y["id"])
            yard = (yard or {}).get("yard") if isinstance(yard, dict) else None
            rep.check("C7", "«двор недели» = страница двора R16 (подпись, соседи)",
                      bool(yard) and yard.get("label_ru") == y.get("label_ru") and yard.get("members") == y.get("members"),
                      {"board": {k: y.get(k) for k in ("label_ru", "members")},
                       "r16": {k: (yard or {}).get(k) for k in ("label_ru", "members")}})
        mt_b, mt_d = board_city.get("meetings") or {}, day_city.get("meetings") or {}
        rep.check("C7", "«Встречи»: Ситуационный центр = «Картина дня»", mt_b.get("counts") == mt_d.get("counts"),
                  {"board": mt_b.get("counts"), "day": mt_d.get("counts")})

        # C8: фикстуры R08 выключены в демо-мире
        src = (board_city or {}).get("sources") or {}
        neighbour_src = {k: src.get(k) for k in ("crisis", "services", "together", "meetings", "forecast")}
        text = json.dumps([board_city, day_city], ensure_ascii=False)
        rep.check("C8", "демо-мир: источники — соседи, фикстур R08 нет",
                  src.get("demo_world") is True and not any("fixture" in str(v) for v in neighbour_src.values())
                  and not any(p in text for p in FIXTURE_IDS), neighbour_src)

        # C9: «Картина недели»
        wk = week or {}
        k = wk.get("kpi") or {}
        series_new = sum(x for x in ((k.get("new") or {}).get("series") or []) if isinstance(x, int))
        val = lambda name: (k.get(name) or {}).get("value")  # noqa: E731
        rep.check("C9", "«Картина недели»: сумма по дням = поступило за неделю", series_new == val("new"),
                  {"series": series_new, "kpi": val("new")})
        if (wk.get("week") or {}).get("current"):
            day_k = kpi_values(day_city)
            rep.check("C9", "«Картина недели»: в работе и просрочено = «Картина дня»",
                      val("in_progress") == day_k["in_progress"] and val("overdue") == day_k["overdue"],
                      {"week": [val("in_progress"), val("overdue")], "day": [day_k["in_progress"], day_k["overdue"]]})
            # Одно окно «неделя» = 7 × 24 ч (R10 consistency C5 / B-122): поступило, исправлено и проверено жителями.
            day_fw = ((day_city.get("kpi") or {}).get("fixed_week") or {})
            rep.check("C9", "«Картина недели» = «Картина дня»: поступило, исправлено, проверено за 7 дней",
                      val("new") == day_k["new_week"] and val("fixed") == day_k["fixed_week"]
                      and (k.get("fixed") or {}).get("verified") == day_fw.get("verified"),
                      {"week": [val("new"), val("fixed"), (k.get("fixed") or {}).get("verified")],
                       "day": [day_k["new_week"], day_k["fixed_week"], day_fw.get("verified")]})

    # C10: «Нужно решение акима»
    dec = (day_city.get("decisions") or {}).get("items") or []
    rep.check("C10", "«Нужно решение акима»: у каждого пункта есть адрес",
              bool(dec) and all(i.get("place_ru") for i in dec), [i.get("id") for i in dec if not i.get("place_ru")] or None)
    if a.expected:
        exp = json.loads(Path(a.expected).read_text(encoding="utf-8"))
        want = ((exp.get("akim") or {}).get("city") or {}).get("decisions")
        rep.check("C10", "«Нужно решение акима» = EXPECTED.json R02 (город)", [i.get("id") for i in dec] == want,
                  {"day": [i.get("id") for i in dec], "expected": want})

    # C11: сцена 7 — «Поддержать» ведёт к делу сцены (правило карточки «Жители вместе» в akim.js)
    _, scenes = c.get(V2 + "/demo/scenes")
    scene7 = ((scenes or {}).get("scenes") or {}).get("scene7") if isinstance(scenes, dict) else None
    want_id = None
    if isinstance(scene7, dict):
        want_id = scene7.get("initiative") or scene7.get("initiative_id")
    if want_id:
        now = datetime.now(timezone.utc)
        def started(x):
            try:
                return datetime.fromisoformat(str(x.get("starts_at")).replace("Z", "+00:00")) <= now
            except ValueError:
                return False
        top = [x for x in ((day_city.get("together") or {}).get("top") or []) if x.get("status") != "done"]
        ahead = [x for x in top if not started(x)]
        pick = next((x for x in ahead if not x.get("supported")), None) or (ahead or top or [None])[0]
        rep.check("C11", "сцена 7: «Поддержать» в «Картине дня» — дело сцены", bool(pick) and pick.get("id") == want_id
                  and not pick.get("supported"), {"pick": (pick or {}).get("id"), "scene7": want_id})
    else:
        rep.skip("C11", "сцена 7", "нет GET demo/scenes или в нём нет scene7.initiative")
    return finish(rep, a)


def finish(rep: Report, a) -> int:
    fails = sum(1 for r in rep.rows if r["status"] == "FAIL")
    passed = sum(1 for r in rep.rows if r["status"] == "PASS")
    out = {"base": a.base, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "pass": passed, "fail": fails, "not_run": len(rep.rows) - passed - fails, "results": rep.rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nИтог: {passed} PASS, {fails} FAIL, {out['not_run']} NOT_RUN → {a.out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
