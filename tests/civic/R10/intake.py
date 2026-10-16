"""R10 · раунд 15+ (поправка П3) · приёмка сцены 0 «ИИ-разбор пачки обращений» (R04) через шлюз R01.

    python3 tests/civic/R10/intake.py --root <папка сборки> [--out <папка отчёта>] [--label "<подпись>"] [--no-world]

Маршруты П3 (research/round-15/AMENDMENTS.md): POST intake/analyze {texts | sample: "night"} · GET intake/sample ·
POST intake/commit {batch_id, task_ids} — только сотрудник (сессия + CSRF); записи жалоб создаёт R09.
Строка отчёта — PASS / FAIL / NOT_RUN; blocking — ломает ли это показ сцены 0 (иначе — «смотреть» с владельцем).
  I0. маршруты есть в шлюзе (DELETE → 405 с Allow); модуля нет — 503 module_not_ready → остальное NOT_RUN с причиной;
  I1. доступ: без входа 401/403, житель — 401/403, сотрудник без CSRF — 403 на POST; ошибки понятные (код + текст по-русски);
  I2. пример «обращения за ночь» (GET intake/sample): сотни текстов, пометка demo;
  I3. разбор примера: ответ по П3 (summary {total, tasks, services, urgent, merged, no_address, ms}, tasks, method, demo,
      batch_id); числа итога сходятся с задачами; у каждого текста не больше одной задачи; ≤ 10 с на 300 текстов;
  I4. задачи: заголовки ru / kk, категория из 12, службы из справочника §3, место — цель в Астане или «адрес уточнить»,
      у срочной — причина, «почему так» ru / kk; нет телефонов / ИИН / e-mail (R15 смотрит глубже);
  I5. свои тексты (как вставил сотрудник): точный повтор одного места — одна задача, «люк у школы, дети» — срочно, текст без
      места — без цели и с «адрес уточнить»; тот же пример вставкой (сотни текстов) проходит предел шлюза R01;
  I6. пределы: 501 текст и тело > 300 КБ — понятная ошибка 4xx, не 500 и не обрыв;
  I7. «Создать задачи»: записей в «Обращениях» R09 стало больше ровно на число задач, commit называет то же число;
      повтор того же batch_id — без дублей; у созданных — источник «разбор пачки», у примера — пометка demo.
Код возврата 1 при FAIL с blocking.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_v2 import ASTANA, CYR, SERVICES, privacy_issues, understandable, unwrap  # noqa: E402
from stand import Stand  # noqa: E402

V2 = "/api/civic/v2"
HERE = Path(__file__).resolve().parent
ROUTES = (("POST", "intake/analyze"), ("GET", "intake/sample"), ("POST", "intake/commit"))
LIMIT_MS = 10_000          # П3: живой счётчик ≤ 10 с на 300 обращений
SAMPLE_MIN = 200           # П3: «~300 синтетических текстов» R02 (до 17 окт 02:00 у R04 своя фикстура 30–50)
SOURCE = re.compile(r"intake|batch|разбор|пачк|талда", re.I)

# Свои тексты I5: что сотрудник мог бы вставить. Остановка «Хан Шатыр» есть в данных карты (osm-node-4109037548).
OWN = [
    ("dup1", "Остановка «Хан Шатыр»: не горит фонарь, вечером совсем темно"),
    ("dup2", "Остановка «Хан Шатыр»: не горит фонарь, вечером совсем темно"),
    ("urgent", "Открытый люк возле школы, дети ходят рядом — очень опасно"),
    ("noaddr", "Во дворе неделю не вывозят мусор, контейнеры переполнены"),
    ("mixed", "Хан Шатыр аялдамасында жарық жоқ, кешке қараңғы"),
]


def categories(root: Path) -> set[str]:
    for rel in ("research/round-14/categories_v2.json", "ml/civic_classifier_v2/categories_v2.json"):
        p = root / rel
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                items = data.get("categories") if isinstance(data, dict) else data
                return {c["id"] for c in items if isinstance(c, dict) and c.get("id")}
            except (OSError, ValueError, KeyError, TypeError):
                pass
    return set()


def sample_texts(body) -> tuple[list[dict], object]:
    """Тексты примера: список строк или словарей {id, text}. → ([{id, text}], пометка demo)."""
    data = unwrap(body)
    demo = data.get("demo") if isinstance(data, dict) else None
    items = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("texts", "items", "sample", "complaints", "lines"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
            if isinstance(data.get(key), dict):  # {"sample": {"texts": [...], "demo": true}}
                inner = data[key]
                demo = inner.get("demo", demo)
                for k2 in ("texts", "items"):
                    if isinstance(inner.get(k2), list):
                        items = inner[k2]
                        break
    out = []
    for i, x in enumerate(items or []):
        if isinstance(x, str):
            out.append({"id": i, "text": x})
        elif isinstance(x, dict):
            text = x.get("text") or x.get("text_ru") or x.get("body") or ""
            out.append({"id": x.get("id", i), "text": text, "demo": x.get("demo")})
    return out, demo


def task_services(task) -> list[tuple[str, str]]:
    out = []
    for s in task.get("services") or []:
        if isinstance(s, dict):
            out.append((str(s.get("id")), str(s.get("role") or "")))
        elif isinstance(s, str):
            out.append((s, ""))
    return out


def is_lead(role: str) -> bool:
    return role.lower() in ("lead", "main", "primary", "owner", "ведущая", "")


def summary_consistency(analysis: dict, total_in: int | None) -> list[tuple[str, bool, dict, bool]]:
    """Числа итога против задач. → [(проверка, верно ли, подробно, blocking)].
    Определения П3 там, где они однозначны (tasks, urgent); для services / no_address / merged — два прочтения
    (все службы или только ведущие; задачи или тексты без места; лишние тексты или группы повторов) — верно любое,
    в подробностях — какое совпало."""
    s = analysis.get("summary") or {}
    tasks = analysis.get("tasks") or []
    rows = []
    rows.append(("итог: задач = число задач в списке", s.get("tasks") == len(tasks),
                 {"summary.tasks": s.get("tasks"), "задач в списке": len(tasks)}, True))
    urgent = sum(1 for t in tasks if t.get("urgent"))
    rows.append(("итог: срочных = задач с пометкой «срочно»", s.get("urgent") == urgent,
                 {"summary.urgent": s.get("urgent"), "срочных задач": urgent}, True))
    every = {sid for t in tasks for sid, _ in task_services(t)}
    lead = {sid for t in tasks for sid, role in task_services(t) if is_lead(role)} or every
    hit = "все службы задач" if s.get("services") == len(every) else "ведущие службы" if s.get("services") == len(lead) else None
    rows.append(("итог: служб = разных служб в задачах", hit is not None,
                 {"summary.services": s.get("services"), "все службы": len(every), "ведущие": len(lead), "совпало": hit}, True))
    no_t = [t for t in tasks if not t.get("target")]
    no_tasks, no_texts = len(no_t), sum(len(t.get("text_ids") or []) for t in no_t)
    hit = "задачи без места" if s.get("no_address") == no_tasks else "тексты без места" if s.get("no_address") == no_texts else None
    rows.append(("итог: без адреса = задач (текстов) без места", hit is not None,
                 {"summary.no_address": s.get("no_address"), "задач без места": no_tasks, "текстов без места": no_texts,
                  "совпало": hit}, True))
    ids = [i for t in tasks for i in (t.get("text_ids") or [])]
    extra = sum(max(0, len(t.get("text_ids") or []) - 1) for t in tasks)
    groups = sum(1 for t in tasks if len(t.get("text_ids") or []) > 1)
    hit = "лишние тексты в задачах" if s.get("merged") == extra else "группы повторов" if s.get("merged") == groups else None
    rows.append(("итог: повторов склеено = повторы в задачах", hit is not None,
                 {"summary.merged": s.get("merged"), "лишних текстов": extra, "групп повторов": groups, "совпало": hit}, False))
    dup = len(ids) - len(set(map(str, ids)))
    rows.append(("у каждого текста не больше одной задачи (без двойного счёта)", dup == 0,
                 {"текстов в задачах": len(ids), "повторно": dup}, True))
    with_place = sum(1 for t in tasks if t.get("target") or t.get("point"))
    if "ready" in s:
        rows.append(("итог: ready (будет создано записей) = задач с местом", s.get("ready") == with_place,
                     {"summary.ready": s.get("ready"), "задач с местом": with_place}, True))
    groups_list = analysis.get("services")
    if isinstance(groups_list, list):
        rows.append(("итог: служб = групп служб в ответе (services[])", s.get("services") == len(groups_list),
                     {"summary.services": s.get("services"), "групп": len(groups_list)}, False))
    if total_in is not None:
        rows.append(("итог: обращений = число текстов на входе", s.get("total") == total_in,
                     {"summary.total": s.get("total"), "текстов на входе": total_in,
                      "в задачах": len(set(map(str, ids))), "вне задач (модерация?)": total_in - len(set(map(str, ids)))}, True))
    return rows


def task_issues(task, cats: set[str]) -> list[str]:
    bad = []
    for key in ("title_ru", "title_kk", "why_ru", "why_kk"):
        if not isinstance(task.get(key), str) or not CYR.search(task.get(key) or ""):
            bad.append(f"{key} пусто")
    if cats and task.get("category") not in cats:
        bad.append(f"категория {task.get('category')!r} не из 12")
    svc = task_services(task)
    if not svc:
        bad.append("нет служб")
    for sid, _ in svc:
        if sid not in SERVICES:
            bad.append(f"служба {sid!r} не из справочника §3")
    target = task.get("target")
    if target:
        pt = task.get("point") or target.get("point") or target.get("coords") or (
            [target.get("lon"), target.get("lat")] if target.get("lon") is not None else None)
        if isinstance(pt, (list, tuple)) and len(pt) == 2 and all(isinstance(v, (int, float)) for v in pt):
            if not (ASTANA[0] <= pt[0] <= ASTANA[2] and ASTANA[1] <= pt[1] <= ASTANA[3]):
                bad.append(f"место вне Астаны {pt}")
        if not target.get("id"):
            bad.append("у места нет id")
    elif task.get("point"):
        bad.append("точка без цели — место угадано?")
    if task.get("urgent") and not (task.get("urgent_why") or task.get("urgent_why_ru") or "").strip():
        bad.append("срочно без причины (urgent_why)")
    if not task.get("text_ids"):
        bad.append("нет text_ids")
    return bad


class IntakeCheck:
    def __init__(self, stand: Stand, world: bool):
        self.s, self.world = stand, world
        token = secrets.token_hex(4)
        self.anon = stand.client()
        self.res = stand.client(device=f"r10-intake-res-{token}")
        self.staff = stand.client()
        self.staff_ok = bool(stand.staff) and self.staff.login(*stand.staff)
        self.nocsrf = stand.client()
        if stand.staff and self.nocsrf.login(*stand.staff):
            self.nocsrf.csrf = None
        self.cats = categories(stand.root)
        self.rows = []
        self.facts = {}

    def add(self, area, name, status, detail=None, owner="R04", blocking=True):
        row = {"area": area, "name": name, "status": status, "detail": detail, "owner": owner,
               "blocking": bool(blocking) and status == "FAIL"}
        self.rows.append(row)
        mark = {"PASS": "PASS   ", "FAIL": "FAIL   ", "NOT_RUN": "NOT_RUN"}[status]
        print(f"{mark} {area} {name}" + (f" — {json.dumps(detail, ensure_ascii=False)[:260]}" if detail else ""))

    def ok(self, area, name, cond, detail=None, owner="R04", blocking=True):
        self.add(area, name, "PASS" if cond else "FAIL", detail, owner, blocking)
        return cond

    def registered(self):
        out = {}
        for method, path in ROUTES:
            r = self.anon.request("DELETE", f"{V2}/{path}")
            allow = {m.strip() for m in (r.headers.get("Allow") or r.headers.get("allow") or "").split(",") if m.strip()}
            out[f"{method} {path}"] = r.status == 405 and method in allow
        return out

    def run(self):
        reg = self.registered()
        self.facts["routes"] = reg
        if not any(reg.values()):
            for key in reg:
                self.add("I0", f"маршрут {key}", "NOT_RUN", "маршрутов intake нет в шлюзе этой сборки (R01 подключает по П3)",
                         "R01")
            return self
        for key, present in reg.items():
            self.ok("I0", f"маршрут {key} есть в шлюзе", present, None, "R01")
        if not self.staff_ok:
            self.add("I0", "вход сотрудника", "FAIL", "сотрудник r10-operator не вошёл — проверки сотрудника не выполнить", "R01")
            return self
        r = self.staff.get(f"{V2}/intake/sample")
        if r.status == 503:
            code = (r.body or {}).get("error") if isinstance(r.body, dict) else None
            status = "NOT_RUN" if code == "module_not_ready" else "FAIL"
            self.add("I0", "модуль R04 intake отвечает", status,
                     {"status": 503, "error": code, "почему": "модуля intake нет в сборке" if status == "NOT_RUN" else "модуль упал"})
            if status == "NOT_RUN":
                return self
        self.access()
        sample = self.sample(r)
        analysis = self.analyze_sample(sample)
        self.own_texts()
        if sample:
            self.paste(sample, analysis)
        self.limits()
        if analysis:
            self.commit(analysis, sample)
        tb = self.s.tracebacks()
        self.ok("журнал", "в журнале сервера нет Traceback модулей", not tb, {"ошибки": tb[:3]} if tb else None)
        return self

    # --- I1 доступ
    def access(self):
        body = {"sample": "night"}
        for who, client in (("без входа", self.anon), ("житель с устройством", self.res)):
            r = client.get(f"{V2}/intake/sample")
            self.ok("I1", f"GET intake/sample {who} → 401/403", r.status in (401, 403), {"status": r.status}, "R01")
            r = client.post(f"{V2}/intake/analyze", body)
            self.ok("I1", f"POST intake/analyze {who} → 401/403", r.status in (401, 403), {"status": r.status}, "R01")
            r = client.post(f"{V2}/intake/commit", {"batch_id": "r10-probe", "task_ids": []})
            self.ok("I1", f"POST intake/commit {who} → 401/403", r.status in (401, 403), {"status": r.status}, "R01")
        for path, payload in (("intake/analyze", body), ("intake/commit", {"batch_id": "r10-probe", "task_ids": []})):
            r = self.nocsrf.post(f"{V2}/{path}", payload)
            self.ok("I1", f"POST {path}: сотрудник без CSRF → 403", r.status == 403, {"status": r.status}, "R01")
        r = self.anon.post(f"{V2}/intake/analyze", body)
        good, why = understandable(r)
        self.ok("I1", "отказ без входа — понятная ошибка (код + текст по-русски)", good, why, "R01", blocking=False)

    # --- I2 пример
    def sample(self, reply):
        if reply.status != 200:
            self.add("I2", "GET intake/sample (сотрудник) → 200", "FAIL", {"status": reply.status, "body": reply.text or reply.body})
            return []
        texts, demo = sample_texts(reply.body)
        self.facts["sample_n"] = len(texts)
        self.ok("I2", "пример «обращения за ночь» — тексты есть", len(texts) > 0, {"текстов": len(texts)})
        self.ok("I2", f"пример — сотни текстов (≥ {SAMPLE_MIN}; П3: ~300 набора R02)", len(texts) >= SAMPLE_MIN,
                {"текстов": len(texts)}, "R04 + R02", blocking=False)
        marked = demo is True or (texts and all(t.get("demo") is True for t in texts))
        self.ok("I2", "пример помечен demo (синтетика)", marked, {"demo": demo}, "R04", blocking=False)
        langs = {"kk": sum(1 for t in texts if re.search(r"[ӘәҒғҚқҢңӨөҰұҮүҺһІі]", t["text"])),
                 "lat": sum(1 for t in texts if re.search(r"[A-Za-z]{4,}", t["text"]) and not CYR.search(t["text"]))}
        self.facts["sample_langs"] = langs
        return texts

    # --- I3 разбор примера
    def analyze(self, payload, timeout=120):
        t0 = time.perf_counter()
        r = self.staff.post(f"{V2}/intake/analyze", payload, timeout=timeout)
        wall = round((time.perf_counter() - t0) * 1000)
        data = unwrap(r.body) if isinstance(r.body, (dict, list)) else None
        return r, (data if isinstance(data, dict) else None), wall

    def analyze_sample(self, sample):
        r, data, wall = self.analyze({"sample": "night"})
        if r.status != 200 or data is None:
            self.add("I3", "POST intake/analyze {sample: night} → 200", "FAIL",
                     {"status": r.status, "body": r.text or r.body, "ms": wall})
            return None
        self.add("I3", "POST intake/analyze {sample: night} → 200", "PASS", {"ms": wall})
        s = data.get("summary") or {}
        need = ("total", "tasks", "services", "urgent", "merged", "no_address", "ms")
        miss = [k for k in need if not isinstance(s.get(k), (int, float))]
        self.ok("I3", "summary по П3 {total, tasks, services, urgent, merged, no_address, ms}", not miss, {"нет": miss})
        self.ok("I3", "есть tasks (список) и batch_id для «Создать задачи»",
                isinstance(data.get("tasks"), list) and bool(data.get("batch_id")),
                {"tasks": type(data.get("tasks")).__name__, "batch_id": data.get("batch_id")})
        self.ok("I3", "method и demo в ответе (откуда подсказки; пример — синтетика)",
                bool(data.get("method")) and data.get("demo") is True, {"method": data.get("method"), "demo": data.get("demo")},
                blocking=False)
        n_in = len(sample) if sample else None
        for name, cond, detail, blocking in summary_consistency(data, n_in):
            self.ok("I3", name, cond, detail, blocking=blocking)
        ids_in = {str(t["id"]) for t in sample} if sample else None
        if ids_in:
            ids = {str(i) for t in data.get("tasks") or [] for i in (t.get("text_ids") or [])}
            # text_ids — id примера или номер строки (0- или 1-based): годится любое, лишь бы все были из входа
            numeric = {str(i) for i in range(len(sample) + 1)}
            alien = sorted(ids - ids_in - numeric)[:5]
            self.ok("I3", "text_ids — тексты входа", not alien, {"чужие": alien})
        ms = s.get("ms")
        self.facts["analyze_sample"] = {"wall_ms": wall, "summary": s, "tasks": len(data.get("tasks") or [])}
        n = s.get("total") or n_in or 0
        self.ok("I3", f"разбор ≤ 10 с ({n} текстов, облако)", wall <= LIMIT_MS and (not isinstance(ms, (int, float)) or ms <= LIMIT_MS),
                {"запрос_ms": wall, "summary.ms": ms, "текстов": n}, blocking=False)
        bad = {}
        for t in data.get("tasks") or []:
            issues = task_issues(t, self.cats)
            if issues:
                bad[str(t.get("id"))] = issues
        self.ok("I4", "задачи по П3: заголовки и «почему» ru / kk, категория из 12, службы §3, место или «адрес уточнить»",
                not bad, {"задач с замечаниями": len(bad), "пример": dict(list(bad.items())[:3])}, blocking=False)
        tasks = data.get("tasks") or []
        order = [bool(t.get("urgent")) for t in tasks]
        self.ok("I4", "срочные — наверху списка", order == sorted(order, reverse=True),
                {"первые": order[:8]}, blocking=False)
        kk_same = sum(1 for t in tasks if t.get("title_kk") and t.get("title_kk") == t.get("title_ru"))
        self.ok("I4", "заголовки ҚАЗ не копия РУС", kk_same <= max(1, len(tasks) // 10),
                {"одинаковых": kk_same, "задач": len(tasks)}, "R04 + R11", blocking=False)
        leak = privacy_issues({"tasks": tasks})
        self.ok("I4", "в итоге нет телефонов, ИИН, e-mail, устройств", not leak, {"нашлось": leak[:4]}, "R04 + R15", blocking=False)
        return data

    # --- I5 свои тексты и вставка
    def own_texts(self):
        payload = {"texts": [t for _, t in OWN]}
        r, data, wall = self.analyze(payload)
        if r.status != 200 or data is None:
            self.add("I5", "свои 5 текстов (texts) → 200", "FAIL", {"status": r.status, "body": r.text or r.body})
            return
        self.add("I5", "свои 5 текстов (texts) → 200", "PASS", {"ms": wall})
        for name, cond, detail, blocking in summary_consistency(data, len(OWN)):
            if not cond:
                self.add("I5", "свои тексты: " + name, "FAIL", detail, blocking=blocking)
        tasks = data.get("tasks") or []
        # text_ids своих текстов (строки без id): R04 нумерует «t1…tN» с 1; годится и номер строки с 0 или с 1.
        ids_all = [str(x) for t in tasks for x in (t.get("text_ids") or [])]
        one_based = str(len(OWN)) in ids_all or f"t{len(OWN)}" in ids_all

        def find(key):
            i = [n for n, (k, _) in enumerate(OWN) if k == key][0]
            want = {f"t{i + 1}", str(i + 1)} if one_based else {str(i), f"t{i}"}
            return next((t for t in tasks if want & {str(x) for x in (t.get("text_ids") or [])}), None)

        d1, d2 = find("dup1"), find("dup2")
        if d1 and d1.get("target"):
            self.ok("I5", "точный повтор у остановки «Хан Шатыр» — одна задача (склеено)", d1 is d2,
                    {"задача 1": d1.get("id"), "задача 2": (d2 or {}).get("id"), "место": d1.get("target")}, blocking=False)
        else:
            self.add("I5", "место «Остановка «Хан Шатыр»» найдено по названию из данных карты", "FAIL",
                     {"задача": d1, "почему важно": "без места повторы не склеиваются (П3: одна цель + категория + текст)"},
                     blocking=False)
        u = find("urgent")
        self.ok("I5", "«открытый люк возле школы, дети» — срочно (явные правила П3)", bool(u and u.get("urgent")),
                {"urgent": (u or {}).get("urgent"), "почему": (u or {}).get("urgent_why")}, blocking=False)
        na = find("noaddr")
        self.ok("I5", "текст без места — без цели и без точки (не угадывать; на экране — «адрес уточнить»)",
                bool(na) and not na.get("target") and not na.get("point"),
                {"target": (na or {}).get("target"), "point": (na or {}).get("point"), "address_text": (na or {}).get("address_text")},
                blocking=False)
        mx = find("mixed")
        self.ok("I5", "текст по-казахски про ту же остановку — разобран (категория, служба)",
                bool(mx) and bool(task_services(mx)),
                {"задача": (mx or {}).get("title_ru"), "категория": (mx or {}).get("category"),
                 "вместе с русским повтором": bool(mx and d1 and mx is d1)}, blocking=False)

    def paste(self, sample, analysis_sample):
        texts = [t["text"] for t in sample]
        size = len(json.dumps({"texts": texts}, ensure_ascii=False).encode("utf-8"))
        r, data, wall = self.analyze({"texts": texts})
        detail = {"текстов": len(texts), "КБ": round(size / 1024), "status": r.status, "ms": wall}
        if r.status == 413:
            detail["почему"] = "предел тела шлюза R01 (CIVIC_MAX_BODY 64 КБ в FINAL-5.1) меньше 300 КБ П3"
        self.ok("I5", "пример вставкой (texts — как вставил сотрудник) → 200", r.status == 200 and data is not None,
                detail, "R01 + R04", blocking=False)
        if data and analysis_sample:
            a, b = analysis_sample.get("summary") or {}, data.get("summary") or {}
            keys = ("total", "tasks", "services", "urgent", "merged", "no_address")
            same = {k: (a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)}
            self.ok("I5", "вставка и кнопка «Пример» дают одни числа", not same, {"различия": same}, blocking=False)

    # --- I6 пределы
    def limits(self):
        r, _, wall = self.analyze({"texts": [f"Тест R10 {i}: не горит фонарь" for i in range(501)]})
        good, why = understandable(r)
        self.ok("I6", "501 текст → понятная ошибка 4xx (предел 500)", 400 <= r.status < 500 and good,
                {"status": r.status, "ошибка": why, "ms": wall}, blocking=False)
        big = "Длинное обращение R10 " + "я" * 16000
        r, _, wall = self.analyze({"texts": [big] * 10})
        self.ok("I6", "тело > 300 КБ → 4xx (413), не 500 и не обрыв", 400 <= r.status < 500,
                {"status": r.status, "ms": wall, "ошибка": understandable(r)[1]}, blocking=False)

    # --- I7 «Создать задачи»
    def count_records(self):
        r = self.staff.get(f"{V2}/complaints?duplicates=1")
        data = unwrap(r.body) if r.status == 200 else None
        if not isinstance(data, dict):
            return None, {}
        items = data.get("items") if isinstance(data.get("items"), list) else []
        return data.get("count", len(items)), {str(x.get("id")): x for x in items if isinstance(x, dict)}

    def commit(self, analysis, sample):
        tasks = analysis.get("tasks") or []
        ids = [t.get("id") for t in tasks if t.get("id") is not None]
        before, before_items = self.count_records()
        if before is None:
            self.add("I7", "«Обращения» R09 отдают список сотруднику (GET complaints)", "FAIL", None, "R09")
            return
        r = self.staff.post(f"{V2}/intake/commit", {"batch_id": analysis.get("batch_id"), "task_ids": ids}, timeout=120)
        data = unwrap(r.body) if isinstance(r.body, (dict, list)) else None
        if r.status not in (200, 201):
            self.add("I7", "POST intake/commit (все задачи) → 200", "FAIL", {"status": r.status, "body": r.text or r.body})
            return
        self.add("I7", "POST intake/commit (все задачи) → 200", "PASS", {"задач": len(ids)})
        after, after_items = self.count_records()
        made = after - before if after is not None else None
        said = None
        if isinstance(data, dict):
            v = data.get("created", data.get("count", data.get("records")))
            said = len(v) if isinstance(v, list) else v
            if isinstance(said, bool) or said is None:  # created — флаг у записей: считаем новые
                recs = data.get("records") if isinstance(data.get("records"), list) else []
                said = sum(1 for x in recs if isinstance(x, dict) and x.get("created"))
        self.facts["commit"] = {"tasks": len(ids), "records_before": before, "records_after": after, "said": said}
        placed = sum(1 for t in tasks if t.get("target") or t.get("point"))
        ready = (analysis.get("summary") or {}).get("ready", placed)
        self.ok("I7", "записей в «Обращениях» стало больше ровно на число задач с местом (ready)", made == ready == placed,
                {"задач": len(ids), "с местом": placed, "summary.ready": ready, "новых записей": made}, "R04 + R09")
        self.ok("I7", "commit называет то же число, что создано (его покажет тост «Создано N задач»)", said == made,
                {"в ответе": said, "новых записей": made})
        r2 = self.staff.post(f"{V2}/intake/commit", {"batch_id": analysis.get("batch_id"), "task_ids": ids}, timeout=120)
        again, _ = self.count_records()
        self.ok("I7", "повтор commit того же batch_id — без дублей", again == after and r2.status < 500,
                {"status": r2.status, "записей было": after, "стало": again}, "R04 + R09")
        new = [after_items[k] for k in after_items if k not in before_items]
        if new:
            src = sum(1 for x in new if SOURCE.search(json.dumps({k: v for k, v in x.items() if "source" in k or "origin" in k
                                                                    or "channel" in k}, ensure_ascii=False)))
            self.ok("I7", "у созданных записей — источник «разбор пачки» (поле source)", src == len(new),
                    {"новых": len(new), "с источником": src, "пример полей": sorted(new[0].keys())[:30]}, "R09", blocking=False)
            demo = sum(1 for x in new if x.get("demo") is True or x.get("synthetic") is True)
            self.ok("I7", "у созданных из примера — пометка demo", demo == len(new), {"новых": len(new), "demo": demo},
                    "R04 + R09", blocking=False)
            placed_tasks = [t for t in tasks if t.get("target") or t.get("point")]
            people_tasks = sum(int(t.get("people") or len(t.get("text_ids") or []) or 1) for t in placed_tasks)
            people_new = sum(int(x.get("reporters") or x.get("people") or 1 + int(x.get("metoo") or 0)) for x in new)
            self.facts["commit"]["people"] = {"в задачах с местом": people_tasks, "в новых записях": people_new}
            self.ok("I7", "людей в новых записях = людей в задачах (1 + «Я тоже» с текстами)", people_new == people_tasks,
                    {"в задачах": people_tasks, "в записях": people_new}, "R04 + R09", blocking=False)

    def summary(self):
        counts = {s: sum(1 for r in self.rows if r["status"] == s) for s in ("PASS", "FAIL", "NOT_RUN")}
        counts["blocking"] = sum(1 for r in self.rows if r["blocking"])
        return {"counts": counts, "facts": self.facts}


def run(root, world=True):
    with Stand(root, world=world) as stand:
        check = IntakeCheck(stand, world).run()
        return {"root": str(root), "world": world, "seeds": stand.seeds, "rows": check.rows, **check.summary()}


def to_markdown(result, label=""):
    c = result["counts"]
    lines = [f"# R10 · сцена 0 «ИИ-разбор пачки обращений» (П3) {label}".rstrip(), "",
             f"Сборка: `{result['root']}` · демо-мир: {'да' if result['world'] else 'нет'} · PASS {c['PASS']} · "
             f"FAIL {c['FAIL']} (ломают показ: {c['blocking']}) · NOT_RUN {c['NOT_RUN']}", ""]
    f = result.get("facts") or {}
    if f.get("analyze_sample"):
        a = f["analyze_sample"]
        s = a.get("summary") or {}
        lines += [f"Итог разбора примера: {s.get('total')} обращений → {s.get('tasks')} задач · {s.get('services')} служб · "
                  f"{s.get('urgent')} срочных · {s.get('merged')} повторов склеено · без адреса {s.get('no_address')} · "
                  f"{a.get('wall_ms')} мс (summary.ms {s.get('ms')})", ""]
    if f.get("commit"):
        lines += [f"«Создать задачи»: {json.dumps(f['commit'], ensure_ascii=False)}", ""]
    lines += ["| Статус | Раздел | Проверка | Подробно | Владелец | Ломает показ |", "|---|---|---|---|---|---|"]
    for r in result["rows"]:
        detail = json.dumps(r["detail"], ensure_ascii=False)[:180] if r["detail"] else ""
        lines.append(f"| {r['status']} | {r['area']} | {r['name']} | {detail.replace('|', '/')} | {r['owner'] or ''} | "
                     f"{'да' if r['blocking'] else ''} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(HERE.parents[2]))
    parser.add_argument("--out", help="папка отчёта: INTAKE.json и INTAKE.md")
    parser.add_argument("--label", default="")
    parser.add_argument("--no-world", action="store_true", help="без CIVIC_DEMO_WORLD=1")
    args = parser.parse_args()
    result = run(args.root, world=not args.no_world)
    print(json.dumps(result["counts"], ensure_ascii=False))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "INTAKE.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "INTAKE.md").write_text(to_markdown(result, args.label), encoding="utf-8")
    return 1 if result["counts"]["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main())
