"""R10 · раунд 15 · согласованность чисел (IDEA §2 D, CONTRACT §11): одни и те же числа во всех разделах.

    python3 tests/civic/R10/consistency.py --root <папка сборки> [--district nura] [--no-world] [--out <папка>]

Стенд сборки с CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1 (единый демо-мир R02). Числа берутся из API разделов — ровно то,
что рисует интерфейс, — и сравниваются попарно при ОДНОМ определении (окно и статусы указаны в каждой строке):
  A. «Жалобы района» — карта R07 (/heat, подпись «Нура · N»: люди = жалобы + «Я тоже» открытых целей за 30 дней)
     = «Обращения» R09 (открытые жалобы района за 30 дней, люди) = «Картина дня» R08 (районы за 7 дней = карта за 7 дней);
  B. «Я тоже» района — R09 (сумма) = демо-мир R02 (если файл мира есть в сборке);
  C. «Просрочено» района — два срока (R02 INTEGRATION §3): C1 исправление — «Картина дня» R08 = табло R17 (overdue_fix);
     C2 первый ответ — «Обращения» R09 = табло R17; C3 Ситуационный центр = «Картина дня»; C4 если числа R08 и R09
     разные — подписи на экранах разные (ключи R11 akim.kpi.overdue и inbox.tab.overdue, ru и kk);
  D. «Открытые у службы» — табло R17 по каждой службе = R09 (ведущая служба открытых жалоб района);
  E. «Мой двор» R16 — люди у двора сцены 7 на странице двора = карточка цели «двор» на карте R07;
  F. «Спросить Birge» R03 — F1/F2 «сколько жалоб за 30 дней / неделю» = карта (люди), F3 «сколько просрочено» = «Картина
     дня», F4 тот же вопрос на ҚАЗ; число и метка из numbers ответа (числа считает код, не модель).
Раздела нет (503) — NOT_RUN с причиной. Расхождение — FAIL с владельцами обеих сторон.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stand import Stand  # noqa: E402

V2 = "/api/civic/v2"
HERE = Path(__file__).resolve().parent
OPEN = ("new", "accepted", "in_progress")  # открытые, как у карты R07 (OPEN_STATUSES) и R08
WORLD_FILE = Path("data/civic/astana/demo-world/world_v1.json")


def unwrap(body):
    if isinstance(body, dict) and "ok" in body and "data" in body:
        return body["data"]
    return body


def parse_time(value):
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def people(rec):
    """Сколько человек сообщили: сама жалоба + «Я тоже» (как «вес и число людей у цели» R02/R07)."""
    for key in ("reporters", "people"):
        if isinstance(rec.get(key), int):
            return rec[key]
    metoo = rec.get("metoo")
    return 1 + (metoo if isinstance(metoo, int) else len(metoo) if isinstance(metoo, list) else 0)


def lead_service(rec):
    """Ведущая служба жалобы: поле service (v2.1, CONTRACT §5.1) или исполнитель паспорта R09/R08."""
    if isinstance(rec.get("service"), str):
        return rec["service"]
    for part in rec.get("services") or []:
        if isinstance(part, dict) and part.get("role") == "lead":
            return part.get("service")
    passport = rec.get("passport_view") or {}
    return passport.get("assignee_id")


def _dig(d, dotted):
    """Ключ словаря R11: плоский «a.b.c» (как web/civic/i18n/*.json) или вложенный."""
    if isinstance(d, dict) and dotted in d:
        return d[dotted]
    for part in dotted.split("."):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


def is_overdue(rec):
    deadline = rec.get("deadline") or (rec.get("passport_view") or {}).get("deadline") or {}
    return rec.get("status") in OPEN and deadline.get("state") == "overdue"


class Consistency:
    def __init__(self, stand: Stand, district: str, world: bool):
        self.s, self.d, self.world = stand, district, world
        self.anon = stand.client()
        self.staff = stand.client()
        self.staff_ok = bool(stand.staff) and self.staff.login(*stand.staff)
        self.values = []   # {metric, source, owner, value, definition}
        self.checks = []   # {name, status, values, owners, note}
        self.now = datetime.now(timezone.utc)

    # --- журнал
    def value(self, metric, source, owner, value, definition):
        self.values.append({"metric": metric, "source": source, "owner": owner, "value": value,
                            "definition": definition})
        shown = "нет раздела" if value is None else value
        print(f"  {metric:<28} {source:<34} {str(shown):<10} {definition}")
        return value

    def compare(self, name, pairs, note="", optional=False):
        """pairs: [(источник, владелец, значение)]. None — раздела нет: NOT_RUN, если сравнивать не с чем.
        optional — число показывается не везде по замыслу (overdue_fix у табло R17 — только если R17 его выводит):
        NOT_RUN такой сверки не держит FINAL-5 (summary_r15.py), противоречие подписей ловит C4."""
        present = [(src, owner, v) for src, owner, v in pairs if v is not None]
        owners = sorted({owner for _, owner, _ in present})
        values = {src: v for src, _, v in pairs}
        if len(present) < 2:
            missing = [src for src, _, v in pairs if v is None]
            status = "NOT_RUN"
            note = (note + "; " if note else "") + f"нет раздела: {', '.join(missing)}"
        else:
            status = "PASS" if len({json.dumps(v, sort_keys=True) for _, _, v in present}) == 1 else "FAIL"
        rec = {"name": name, "status": status, "values": values, "owners": owners, "note": note}
        if optional and status == "NOT_RUN":
            rec["optional"] = True
        self.checks.append(rec)
        print(f"{status:<7} {name} — {json.dumps(values, ensure_ascii=False)}" + (f" ({note})" if note else ""))

    # --- источники
    def get(self, client, path):
        r = client.get(V2 + path)
        return r if r.status != 503 else None

    def heat_count(self, days):
        r = self.get(self.anon, f"/heat?zoom=10&days={days}")
        if r is None or r.status != 200:
            return None
        for item in (r.body or {}).get("items", []):
            if (item.get("target") or {}).get("id") == self.d or item.get("district") == self.d:
                return item.get("count", 0) if item.get("state", "active") == "active" else 0
        return 0

    def r09_items(self, days):
        if not self.staff_ok:
            return None
        r = self.get(self.staff, f"/complaints?days={days}")
        if r is None or r.status != 200:
            return None
        items = (unwrap(r.body) or {}).get("items")
        if not isinstance(items, list):
            return None
        since = self.now - timedelta(days=days)
        return [x for x in items if x.get("district") == self.d
                and (parse_time(x.get("created_at")) or self.now) >= since]

    def akim_summary(self):
        r = self.get(self.anon, f"/akim/summary?district={self.d}")
        return r.body if r is not None and r.status == 200 and isinstance(r.body, dict) else None

    def akim_summary_city(self):
        r = self.get(self.anon, "/akim/summary")
        return r.body if r is not None and r.status == 200 and isinstance(r.body, dict) else None

    def agencies_board(self, days):
        """(строки служб, итоги) табло R17: {"services": [{service, open, overdue, …}], "totals": {open, overdue, …}}."""
        if not self.staff_ok:
            return None, None
        r = self.get(self.staff, f"/agencies/board?days={days}&district={self.d}")
        if r is None or r.status != 200:
            return None, None
        body = unwrap(r.body)
        rows = body if isinstance(body, list) else next(
            (body.get(k) for k in ("services", "rows", "items", "board") if isinstance(body.get(k), list)), None)
        totals = body.get("totals") if isinstance(body, dict) and isinstance(body.get("totals"), dict) else None
        return rows, totals

    # --- проверки
    def run(self):
        d = self.d
        print(f"район: {d}; демо-мир: {'да' if self.world else 'нет'}; стенд: {self.s.base}")
        r09_30, r09_7 = self.r09_items(30), self.r09_items(7)
        open_30 = [x for x in r09_30 or [] if x.get("status") in OPEN] if r09_30 is not None else None

        # A. «Жалобы района»
        map30 = self.value("жалобы района, 30 дн.", "карта R07 /heat", "R07", self.heat_count(30),
                           "люди (жалобы + «Я тоже») открытых целей за 30 дней — подпись «Нура · N»")
        list30 = self.value("жалобы района, 30 дн.", "«Обращения» R09 /complaints", "R09",
                            sum(people(x) for x in open_30) if open_30 is not None else None,
                            "люди открытых жалоб района за 30 дней")
        self.value("жалобы района, 30 дн. (записей)", "«Обращения» R09 /complaints", "R09",
                   len(open_30) if open_30 is not None else None, "записи открытых жалоб (без «Я тоже»)")
        self.compare("A1. карта «Нура · N» = «Обращения» (люди, 30 дней)",
                     [("карта R07", "R07", map30), ("«Обращения» R09", "R09", list30)])
        map7 = self.value("жалобы района, 7 дн.", "карта R07 /heat?days=7", "R07", self.heat_count(7),
                          "люди открытых целей за 7 дней")
        city = self.akim_summary_city()
        dist7 = None
        if city is not None:
            rows = ((city.get("districts") or {}).get("items")) or []
            dist7 = next((row.get("value") for row in rows if row.get("district") == d), 0)
        self.value("жалобы района, 7 дн.", "«Картина дня» R08 районы", "R08", dist7, "районы за 7 дней")
        open_7 = [x for x in r09_7 or [] if x.get("status") in OPEN] if r09_7 is not None else None
        list7 = self.value("жалобы района, 7 дн.", "«Обращения» R09", "R09",
                           sum(people(x) for x in open_7) if open_7 is not None else None, "люди открытых жалоб за 7 дней")
        # «Обращения» за 7 дней — справкой: R09 не отдаёт время каждого «Я тоже», а карта считает «Я тоже» по его времени
        # (жалоба 8 дней назад + «Я тоже» вчера = 1 человек в окне 7 дней). Строго: «Картина дня» = карта (одна формула R07).
        self.compare("A2. «Картина дня» районы (7 дней) = карта за 7 дней",
                     [("«Картина дня» R08", "R08", dist7), ("карта R07", "R07", map7)],
                     note="" if list7 is None or list7 == map7 else f"справка: «Обращения» по дате подачи — {list7}")
        # A3. Карта районов Ситуационного центра (R08 akim/board, тот же расчёт «за 7 дней») = карта R07 за 7 дней.
        board = self.get(self.staff, "/akim/board") if self.staff_ok else None
        bdata = board.data() if board is not None and board.status == 200 and isinstance(board.body, dict) else None
        board7 = None
        if isinstance(bdata, dict):
            rows = ((bdata.get("districts") or {}).get("items")) or []
            board7 = next((row.get("value") for row in rows if row.get("district") == d), 0) if rows else None
        self.value("жалобы района, 7 дн.", "Ситуационный центр R08 карта районов", "R08", board7, "районы за 7 дней на большом экране")
        if board7 is not None:
            self.compare("A3. Ситуационный центр: район за 7 дней = карта за 7 дней",
                         [("Ситуационный центр R08", "R08", board7), ("карта R07", "R07", map7)])

        # B. «Я тоже» района
        metoo = self.value("«Я тоже» района, 30 дн.", "«Обращения» R09", "R09",
                           sum(people(x) - 1 for x in r09_30) if r09_30 is not None else None,
                           "сумма «Я тоже» жалоб района за 30 дней (все статусы)")
        world = self.world_numbers()
        self.compare("B. «Я тоже» района: «Обращения» = демо-мир R02",
                     [("«Обращения» R09", "R09", metoo), ("демо-мир R02", "R02", world.get("metoo_30"))],
                     note="" if world else "файла мира нет в сборке")
        if world:
            self.compare("B2. жалобы района за 30 дней: «Обращения» = демо-мир R02 (записей, все статусы)",
                         [("«Обращения» R09", "R09", len(r09_30) if r09_30 is not None else None),
                          ("демо-мир R02", "R02", world.get("complaints_30"))])

        # C. «Просрочено» района. Два разных срока (R02 INTEGRATION §3): R08 — срок ИСПРАВЛЕНИЯ прошёл у открытой жалобы,
        # R09 «Обращения» — срок ПЕРВОГО ОТВЕТА прошёл у новой. Сравниваем подобное с подобным, а если числа разные —
        # подписи на экранах тоже должны быть разными (иначе жюри видит «Просрочено 7» и «Просрочено 1»).
        summary = self.akim_summary()
        overdue_r08 = ((summary or {}).get("kpi") or {}).get("overdue", {}).get("value") if summary else None
        self.value("просрочено (исправление)", "«Картина дня» R08 kpi", "R08", overdue_r08,
                   "открытые жалобы района, срок исправления прошёл")
        r09_all = self.r09_items(365)
        if r09_all is not None and any("inbox_tab" in x for x in r09_all):
            overdue_r09 = sum(1 for x in r09_all if x.get("inbox_tab") == "overdue")
        else:
            overdue_r09 = sum(1 for x in r09_all if is_overdue(x)) if r09_all is not None else None
        self.value("просрочено (ответ)", "«Обращения» R09 вкладка", "R09", overdue_r09,
                   "жалобы района во вкладке «Просрочено» (срок первого ответа)")
        board, totals = self.agencies_board(30)
        overdue_r17 = overdue_fix_r17 = None
        open_r17 = None
        if board is not None:
            # Совместная жалоба открыта у каждой своей службы: по строкам — части, по итогам — обращения.
            overdue_r17 = (int(totals["overdue"]) if totals and isinstance(totals.get("overdue"), int)
                           else sum(int(row.get("overdue") or 0) for row in board if isinstance(row, dict)))
            if totals:
                for key in ("overdue_answer", "answer_overdue"):
                    if isinstance(totals.get(key), int):
                        overdue_r17 = int(totals[key])
                for key in ("overdue_fix", "fix_overdue"):
                    if isinstance(totals.get(key), int):
                        overdue_fix_r17 = int(totals[key])
            open_r17 = {row.get("service") or row.get("id"): int(row.get("open") or row.get("open_count") or 0)
                        for row in board if isinstance(row, dict)}
        self.value("просрочено (ответ)", "табло служб R17", "R17", overdue_r17, "итог «просрочено» табло района (обращения)")
        self.value("просрочено (исправление)", "табло служб R17", "R17", overdue_fix_r17, "итог overdue_fix табло (если есть)")
        sit = self.get(self.staff, "/akim/board") if self.staff_ok else None
        overdue_sit = None
        if sit is not None and sit.status == 200 and isinstance(sit.body, dict):
            # R08 akim/board: kpi.items — плитки [{id: "overdue", value}]; запасной вид — kpi.overdue.value, как у summary.
            data = sit.data() if hasattr(sit, "data") else sit.body
            kpi = data.get("kpi") if isinstance(data, dict) else None
            if isinstance(kpi, dict) and isinstance(kpi.get("items"), list):
                tile = next((t for t in kpi["items"] if isinstance(t, dict) and t.get("id") == "overdue"), None)
                overdue_sit = tile.get("value") if tile and isinstance(tile.get("value"), int) else None
            elif isinstance(kpi, dict) and isinstance(kpi.get("overdue"), dict):
                overdue_sit = kpi["overdue"].get("value") if isinstance(kpi["overdue"].get("value"), int) else None
            else:
                found = re.search(r'"overdue"\s*:\s*\{[^{}]*"value"\s*:\s*(\d+)', json.dumps(sit.body))
                overdue_sit = int(found.group(1)) if found else None
        self.value("просрочено (город)", "Ситуационный центр R08", "R08", overdue_sit, "kpi overdue большого экрана")
        self.compare("C1. «Просрочено» (срок исправления): «Картина дня» R08 = табло R17 (overdue_fix)",
                     [("«Картина дня» R08", "R08", overdue_r08), ("табло R17", "R17", overdue_fix_r17)],
                     note="табло R17 выводит только «нет ответа в срок» — сверять нечего" if overdue_fix_r17 is None and overdue_r08 is not None else "",
                     optional=True)
        self.compare("C2. «Просрочено» (срок ответа): «Обращения» R09 = табло R17",
                     [("«Обращения» R09", "R09", overdue_r09), ("табло R17", "R17", overdue_r17)])
        self.labels_check(overdue_r08, overdue_r09)
        if overdue_sit is not None and city is not None:
            self.compare("C3. просрочено по городу: Ситуационный центр = «Картина дня»",
                         [("Ситуационный центр R08", "R08", overdue_sit),
                          ("«Картина дня» R08", "R08", ((city.get("kpi") or {}).get("overdue") or {}).get("value"))])

        # D. «Открытые у службы»
        if open_30 is not None:
            by_service = Counter()
            for x in r09_all or []:
                if x.get("status") not in OPEN:
                    continue
                parts = [p for p in (x.get("services") or []) if isinstance(p, dict) and p.get("service")]
                if parts:  # совместное исполнение (§5.1): у каждой службы своя часть; закрытая часть не открыта
                    for part in parts:
                        if part.get("status") != "done":
                            by_service[part["service"]] += 1
                else:
                    by_service[lead_service(x)] += 1
            r09_services = {k: v for k, v in sorted(by_service.items()) if k}
        else:
            r09_services = None
        self.value("открытые по службам", "«Обращения» R09", "R09", r09_services,
                   "открытые жалобы района по службам (у совместных — каждая незакрытая часть)")
        self.value("открытые по службам", "табло служб R17", "R17",
                   {k: v for k, v in sorted(open_r17.items()) if v} if open_r17 else open_r17, "open по строкам табло")
        self.compare("D. открытые у каждой службы: табло R17 = «Обращения» R09",
                     [("табло R17", "R17", {k: v for k, v in sorted((open_r17 or {}).items()) if v} if open_r17 is not None else None),
                      ("«Обращения» R09", "R09", r09_services)])

        # E. «Мой двор»
        self.yard_check(r09_all)

        # F. «Спросить Birge»
        self.ask_check(map30, map7, overdue_r08, overdue_r09)
        return self

    def labels_check(self, fix_value, answer_value):
        """Разные числа «просрочено» — разные подписи (ключи R11: akim.kpi.overdue и inbox.tab.overdue, ru и kk)."""
        if not (isinstance(fix_value, int) and isinstance(answer_value, int)) or fix_value == answer_value:
            self.checks.append({"name": "C4. подписи «просрочено» различаются, если числа разные", "status": "NOT_RUN",
                                "values": {"R08": fix_value, "R09": answer_value}, "owners": ["R08", "R09", "R11"],
                                "note": "числа совпадают или одного нет — различать нечего"})
            return
        same = []
        for lang in ("ru", "kk"):
            path = self.s.root / "web" / "civic" / "i18n" / f"{lang}.json"
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            pick = lambda dotted: _dig(d, dotted)  # noqa: E731
            a, b = pick("akim.kpi.overdue"), pick("inbox.tab.overdue")
            if isinstance(a, str) and isinstance(b, str) and a.strip().lower() == b.strip().lower():
                same.append(f"{lang}: «{a}»")
        status = "FAIL" if same else "PASS"
        self.checks.append({"name": "C4. подписи «просрочено» различаются, если числа разные (R08 ≠ R09)", "status": status,
                            "values": {"«Картина дня» R08": fix_value, "«Обращения» R09": answer_value, "одинаковые подписи": same},
                            "owners": ["R08", "R09", "R11"],
                            "note": "жюри видит «Просрочено N» в двух местах с разными числами" if same else ""})
        print(f"{status:<7} C4. подписи «просрочено»: {same or 'разные'}")

    def world_numbers(self):
        """Числа района из файла мира R02 (истина для засева): записи и «Я тоже» за 30 дней."""
        path = self.s.root / WORLD_FILE
        if not self.world or not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return {}
        complaints = [c for c in data.get("complaints", []) if isinstance(c, dict) and c.get("district") == self.d]

        def age_days(c):
            # Время мира R02 (SCHEMA §1) — объект {"ago_hours": 30.5} / {"ago_days": 3.25}; абсолютная строка — как есть.
            v = c.get("created_at")
            if isinstance(v, dict):
                if isinstance(v.get("ago_days"), (int, float)):
                    return float(v["ago_days"])
                if isinstance(v.get("ago_hours"), (int, float)):
                    return float(v["ago_hours"]) / 24
                return None
            t = parse_time(v)
            return (self.now - t).total_seconds() / 86400 if t else None

        recent = [c for c in complaints if (age_days(c) if age_days(c) is not None else 999) <= 30]
        return {"complaints_30": len(recent), "metoo_30": sum(people(c) - 1 for c in recent)}

    def yard_check(self, r09_all):
        yard = None
        path = self.s.root / WORLD_FILE
        if path.exists():
            try:
                scenes = json.loads(path.read_text(encoding="utf-8")).get("scenes") or {}
                yard = json.dumps(scenes, ensure_ascii=False)
                found = re.search(r'"(yard-[A-Za-z0-9_-]+)"', yard)
                yard = found.group(1) if found else None
            except ValueError:
                yard = None
        if yard is None:
            self.compare("E. «Мой двор»: проблемы двора = открытые жалобы на двор", [("«Мой двор» R16", "R16", None)],
                         note="нет двора сцены 7 (scenes в файле мира R02)")
            return
        # «Проблемы двора» у R16 — МЕСТА с жалобами (цели тепловой карты в дворе и до 60 м), у каждого — люди, как на карте.
        # Сверяем людей у самого двора: страница «Мой двор» = карточка цели «двор» на карте R07 (/heat/target).
        r = self.get(self.anon, f"/together/yards/{yard}")
        r16_people = r16_places = None
        if r is not None and r.status == 200:
            body = unwrap(r.body) or {}
            problems = body.get("problems") if isinstance(body.get("problems"), dict) else {}
            r16_places = (body.get("counts") or {}).get("problems", problems.get("count"))
            own = [it for it in problems.get("items") or [] if ((it.get("target") or {}).get("id")) == yard]
            r16_people = own[0].get("count") if own else (0 if problems.get("status") == "ok" else None)
        h = self.get(self.anon, f"/heat/target?kind=area&id={yard}")
        r07_people = None
        if h is not None and h.status in (200, 404):
            item = (h.body or {}).get("item") if isinstance(h.body, dict) else None
            r07_people = (item or {}).get("count", 0) if h.status == 200 else 0
        r09_yard = (sum(1 for x in r09_all if (x.get("target") or {}).get("id") == yard and x.get("status") in OPEN)
                    if r09_all is not None else None)
        self.value(f"двор {yard}: люди у двора", "«Мой двор» R16", "R16", r16_people, f"проблемных мест рядом: {r16_places}")
        self.value(f"двор {yard}: люди у двора", "карта R07 /heat/target", "R07", r07_people, "карточка цели «двор» на карте")
        self.value(f"двор {yard}: открытые жалобы", "«Обращения» R09", "R09", r09_yard, "справка: записи с целью-двором")
        self.compare("E. «Мой двор»: люди у двора = карточка двора на карте",
                     [("«Мой двор» R16", "R16", r16_people), ("карта R07", "R07", r07_people)])

    def ask_check(self, map30, map7, overdue_r08, overdue_r09):
        """«Спросить Birge» (R03): три отдельных вопроса — в ответе то же число, что на экране, и понятная метка.

        Ответ R03: {"headline", "lead", "numbers": [{"value", "label": {"ru", "kk"}, "fact"}], "blocks"} — сверяем numbers;
        нет numbers — числа из текста ответа (слабее: только «есть ли число»)."""
        if not self.staff_ok:
            self.compare("F. «Спросить Birge»", [("R03", "R03", None)], note="нет входа сотрудника")
            return
        names = {"nura": ("Нуре", "Нұрада")}.get(self.d, (self.d, self.d))
        cases = [
            ("F1", f"Сколько жалоб в {names[0]} за 30 дней?", "ru", map30, r"человек", "карта 30 дней (люди)"),
            ("F2", f"Сколько жалоб в {names[0]} за неделю?", "ru", map7, r"человек", "карта 7 дней (люди)"),
            ("F3", f"Сколько обращений просрочено в {names[0]}?", "ru", overdue_r08, r"просроч", "«Картина дня» (исправление)"),
            ("F4", f"{names[1]} 30 күнде қанша шағым түсті?", "kk", map30, r"адам", "карта 30 дней (люди), вопрос на ҚАЗ"),
        ]
        for tag, question, lang, expected, label_re, what in cases:
            r = self.staff.post(V2 + "/assistant/ask", {"question": question, "lang": lang})
            if r.status in (404, 503) or r.status == 0:
                self.compare(f"{tag}. «Спросить Birge»: «{question}»", [("«Спросить Birge» R03", "R03", None)],
                             note=f"маршрут ответил {r.status}")
                continue
            data = unwrap(r.body) if isinstance(r.body, dict) else {}
            nums = data.get("numbers") if isinstance(data, dict) else None
            if isinstance(nums, list) and nums:
                got = [(n.get("value"), ((n.get("label") or {}).get(lang) or (n.get("label") or {}).get("ru") or ""))
                       for n in nums if isinstance(n, dict)]
                hit = [v for v, lab in got if v == expected and re.search(label_re, lab, re.I)]
                shown = [f"{v} {lab}" for v, lab in got][:4]
            else:
                text = json.dumps(data, ensure_ascii=False)
                got = sorted({int(n) for n in re.findall(r"(?<![\w.])(\d{1,5})(?![\w.])", text)})
                hit = [v for v in got if v == expected]
                shown = got[:12]
            ok = r.status == 200 and isinstance(expected, int) and bool(hit)
            status = "NOT_RUN" if not isinstance(expected, int) else ("PASS" if ok else "FAIL")
            self.value(f"«Спросить Birge» {tag}", "R03 /assistant/ask", "R03", shown, f"{question} — за {round(r.ms)} мс")
            self.checks.append({"name": f"{tag}. «Спросить Birge»: «{question}» = {what}", "status": status,
                                "values": {"ответ": shown, "ожидалось": expected, "ms": round(r.ms)}, "owners": ["R03"],
                                "note": "" if ok or status == "NOT_RUN" else "в ответе нет числа экрана с понятной меткой"})
            print(f"{status:<7} {tag}. {question} → {shown} (ожидалось {expected})")

def run(root, district="nura", world=True):
    with Stand(root, world=world) as stand:
        c = Consistency(stand, district, world).run()
        counts = Counter(x["status"] for x in c.checks)
        return {"root": str(root), "district": district, "world": world, "values": c.values, "checks": c.checks,
                "counts": {s: counts.get(s, 0) for s in ("PASS", "FAIL", "NOT_RUN")}}


def to_markdown(result, label=""):
    lines = [f"# R10 · согласованность чисел {label}".rstrip(), "",
             f"Сборка: `{result['root']}` · район: {result['district']} · демо-мир: {'да' if result['world'] else 'нет'} · "
             f"PASS {result['counts']['PASS']} · FAIL {result['counts']['FAIL']} · NOT_RUN {result['counts']['NOT_RUN']}", "",
             "## Сверки", "", "| Статус | Сверка | Значения | Владельцы | Примечание |", "|---|---|---|---|---|"]
    for c in result["checks"]:
        vals = json.dumps(c["values"], ensure_ascii=False).replace("|", "/")
        lines.append(f"| {c['status']} | {c['name']} | {vals[:220]} | {', '.join(c['owners'])} | {c['note']} |")
    lines += ["", "## Числа по разделам", "", "| Число | Раздел | Значение | Определение |", "|---|---|---|---|"]
    grouped = defaultdict(list)
    for v in result["values"]:
        grouped[v["metric"]].append(v)
    for metric, rows in grouped.items():
        for v in rows:
            shown = "нет раздела" if v["value"] is None else json.dumps(v["value"], ensure_ascii=False)
            lines.append(f"| {metric} | {v['source']} | {shown[:120]} | {v['definition']} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(HERE.parents[2]))
    parser.add_argument("--district", default="nura")
    parser.add_argument("--no-world", action="store_true")
    parser.add_argument("--out")
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    result = run(args.root, args.district, world=not args.no_world)
    print(json.dumps(result["counts"], ensure_ascii=False))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "CONSISTENCY.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "CONSISTENCY.md").write_text(to_markdown(result, args.label), encoding="utf-8")
    return 1 if result["counts"]["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
