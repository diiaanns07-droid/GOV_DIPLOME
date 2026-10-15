"""Ожидаемые числа экранов для демо-мира (R02, раунд 15) — считает КОД МОДУЛЕЙ, а не R02.

    python3 -m ml.datasets.demo_world_expected                    # EXPECTED.json на опорный момент (REFERENCE_NOW)
    python3 -m ml.datasets.demo_world_expected --now 2026-10-17T18:00:00+05:00 --print   # на свой момент, без записи

Зачем: CONTRACT §11 — «числа Нуры на карте, в „Обращениях“, в „Картине дня“ и на табло служб совпадают». Мир
материализуется на момент now (как при засеве R01), к жалобам добавляется срок ответа R09 (рабочие дни РК), и
дальше те же функции, что работают на стенде:
  - карта — R07 ui.civic_heat.service.HeatService (источник = записи мира, как R01 подключает хранилище R09);
  - «Картина дня» — R08 ui.civic_akim.summary.AkimService поверх той же карты;
  - «Обращения» — R09 ui.civic_feedback.v2.lifecycle.inbox.
Табло служб (R17) и «Мой двор» (R16) пока считаем простыми правилами (их модулей ещё нет) — для сверки ролей.
Если модуля нет в сборке, его блок — {"available": false, "reason": …}, остальные блоки считаются.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from ml.datasets import demo_world_io as wio

REFERENCE_NOW = "2026-10-16T12:00:00+05:00"
HEAT_DAYS = (7, 14, 30)
# Чей код считает блок EXPECTED.json. В сборке R01 у соседей код новее, чем в ветке R02 (например, R09 раунда 15
# «Ждут проверки» = 14 дней): блок с другим отпечатком кода тест R02 не сравнивает с файлом — его сверяет
# tests/civic/R02/round15/stand_numbers.py на живом стенде (тот же код, что у экрана).
MODULE_DIRS = {"R07": "ui/civic_heat", "R08": "ui/civic_akim", "R09": "ui/civic_feedback/v2"}
SECTION_CODE = {"heat": ("R07", "R09"), "akim": ("R07", "R08", "R09"), "inbox": ("R09",), "services": ("R09",),
                "nura_check": ("R07", "R08", "R09")}


def _with_r09_fields(complaints: list[dict]) -> list[dict]:
    """То, что R09 добавляет при засеве: срок ответа (рабочие дни РК) и номер для жителя."""
    from ui.civic_feedback.v2 import record as rec
    out = []
    for n, c in enumerate(sorted(complaints, key=lambda x: x["created_at"]), start=1):
        c = dict(c)
        c["due_at"] = rec.due_at(c["created_at"], c["category"])
        c.setdefault("code", f"B-{n:04d}")
        out.append(c)
    return out


def code_fingerprints() -> dict:
    """Отпечаток кода модулей, которыми посчитаны блоки: sha256 файлов .py пакета (16 знаков); пакета нет — None."""
    out = {}
    for role, rel in MODULE_DIRS.items():
        files = sorted((wio.ROOT / rel).rglob("*.py")) if (wio.ROOT / rel).is_dir() else []
        digest = hashlib.sha256()
        for f in files:
            digest.update(f.relative_to(wio.ROOT).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
        out[role] = digest.hexdigest()[:16] if files else None
    return out


def _safe(block):
    try:
        return block()
    except Exception as exc:  # noqa: BLE001 — нет модуля или он упал: остальные числа всё равно нужны
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}


def heat_numbers(records: list[dict], now: datetime) -> dict:
    from ui.civic_heat.service import HeatService
    heat = HeatService(source=lambda since: records, clock=lambda: now)
    out = {"available": True}
    for days in HEAT_DAYS:
        items = heat.districts(days=days, now=now)
        out[f"districts_{days}d"] = {it["district"]: {"people": it["count"], "targets": it["targets"],
                                                      "level": it["level"], "state": it["state"],
                                                      "fixed_targets": it["fixed_targets"],
                                                      "verified_targets": it["verified_targets"]}
                                     for it in items}
    data = heat.heat(days=14, now=now)
    out["stats_14d"] = data["stats"]
    top = [it for it in data["items"] if it["state"] == "active"][:5]
    out["top5_14d"] = [{"target": it["target"]["id"], "label_ru": it["target"].get("label_ru"),
                        "people": it["count"], "district": it.get("district")} for it in top]
    return out, heat


def akim_numbers(heat, now: datetime) -> dict:
    from ui.civic_akim.summary import AkimService
    akim = AkimService(heat=heat, objects=None, proposals=None, clock=lambda: now, demo_build=True)
    out = {"available": True}
    for district in (None, "nura"):
        s = akim.summary(district=district, now=now)
        kpi = s["kpi"]
        block = {name: kpi[name]["value"] for name in ("new_day", "new_week", "in_progress", "overdue", "fixed_week")}
        block["fixed_week_verified"] = kpi["fixed_week"].get("verified")
        block["decisions"] = [i["id"] for i in s["decisions"]["items"]]
        block["decisions_source"] = s["decisions"].get("source")
        block["overdue_items"] = s["overdue"]["count"]
        block["pulse"] = [{"kind": a["kind"], "category": a.get("category"), "district": a.get("district"),
                           "value": a.get("value"), "base": a.get("base"), "ratio": a.get("ratio"),
                           "text_ru": (a.get("text") or {}).get("ru")} for a in s["pulse"]["items"]]
        out["city" if district is None else district] = block
    return out


def inbox_numbers(records: list[dict], now: datetime) -> dict:
    from ui.civic_feedback.v2 import lifecycle
    out = {"available": True, "city": lifecycle.inbox(records, now)["counts"]}
    for district in ("nura",):
        part = [r for r in records if r.get("district") == district]
        res = lifecycle.inbox(part, now)
        out[district] = dict(res["counts"])
        out[district + "_groups"] = len(res["items"])
    out["complaints_total"] = len(records)
    out["complaints_by_district"] = dict(Counter(r["district"] for r in records))
    return out


def services_numbers(records: list[dict], now: datetime) -> dict:
    """Простое табло служб для сверки с R17: обращения (вся жалоба — ведущей службе; совместная — обеим), открытые
    (у совместной — по части службы, как R17), просроченные (новое и срок ответа прошёл, как у R09), исправлено,
    проверено жителями, вернули жители."""
    from ui.civic_feedback.v2 import record as rec
    board = defaultdict(lambda: Counter())
    for r in records:
        parts = r.get("services") or [{"service": r["service"], "status": None}]
        for part in parts:
            sid = part["service"]
            b = board[sid]
            b["complaints"] += 1
            b["people"] += 1 + int(r.get("metoo") or 0)
            # «Открыто у службы»: у совместной — по её части (сделала свою часть — не открыто), как табло R17.
            if part.get("status") is None:
                b["open"] += r["status"] in rec.OPEN_STATUSES
            else:
                b["open"] += r["status"] in rec.OPEN_STATUSES and part["status"] not in ("done", "rejected")
            b["overdue"] += rec.is_overdue(r, now)
            b["fixed"] += r["status"] == "fixed"
            state = (r.get("resolution") or {}).get("state")
            b["verified"] += state == "verified"
            b["reopened"] += any(h.get("reopened_by_residents") for h in r.get("status_history") or [])
            b["joint"] += bool(r.get("services"))
            b["handoffs_in"] += sum(1 for h in r.get("handoffs") or [] if h.get("to") == sid)
    return {"available": True, "rule": services_numbers.__doc__.split("\n")[0],
            "by_service": {sid: dict(sorted(c.items())) for sid, c in sorted(board.items())}}


def yards_numbers(world_m: dict, records: list[dict], now: datetime) -> dict:
    """«Мой двор» (R16): жалобы с целью-двором (14 и 60 дней), люди, открытые; инициативы и идеи двора."""
    by_yard = defaultdict(list)
    for r in records:
        by_yard[r["target"]["id"]].append(r)
    edge14 = now - timedelta(days=14)
    out = {}
    for y in world_m["yards"]:
        rs = by_yard.get(y["id"], [])
        recent = [r for r in rs if datetime.fromisoformat(r["created_at"]) >= edge14]
        out[y["id"]] = {"complaints_60d": len(rs), "complaints_14d": len(recent),
                        "people_14d": sum(1 + int(r.get("metoo") or 0) for r in recent),
                        "open": sum(1 for r in rs if r["status"] in ("new", "accepted", "in_progress")),
                        "initiatives": [i["id"] for i in world_m["initiatives"] if i["target"]["id"] == y["id"]],
                        "ideas": [i["id"] for i in world_m["ideas"] if (i.get("target") or {}).get("id") == y["id"]],
                        "members": y["members"]}
    return {"available": True, "by_yard": out}


def scenes_numbers(world_m: dict, records: list[dict], now: datetime) -> dict:
    scenes = world_m["scenes"]
    edge14 = now - timedelta(days=14)
    step2 = scenes["step2"]
    at_stop = [r for r in records if r["target"]["id"] == step2["target"]]
    lighting14 = [r for r in at_stop if r["category"] == "lighting" and datetime.fromisoformat(r["created_at"]) >= edge14]
    out = {"step2": {"lighting_people_14d": sum(1 + r["metoo"] for r in lighting14),
                     "stop_people_14d": sum(1 + r["metoo"] for r in at_stop
                                            if datetime.fromisoformat(r["created_at"]) >= edge14)}}
    s9 = [r for r in records if r.get("event") == "ev-w15-buran"]
    out["scene9"] = {"buran_complaints": len(s9), "buran_complaints_nura": sum(1 for r in s9 if r["district"] == "nura"),
                     "buran_people_nura": sum(1 + r["metoo"] for r in s9 if r["district"] == "nura")}
    s7 = scenes["scene7"]
    out["scene7"] = {"yard": s7["yard"], "complaints": len([r for r in records if r["target"]["id"] == s7["yard"]])}
    return out


def expected(world: dict, now: datetime | None = None) -> dict:
    now = wio.astana_now(now)
    world_m = wio.materialize(world, now)
    records = _with_r09_fields(world_m["complaints"])
    result = {"schema": "birge-demo-world-expected-v1", "world_schema": world.get("schema"),
              "world_version": world.get("schema_version"), "now": wio.iso(now),
              "note_ru": "Числа посчитаны кодом модулей (R07 карта, R08 «Картина дня», R09 «Обращения») на записях мира. "
                         "Табло служб и «Мой двор» — простые правила R02 для сверки, пока модулей R16/R17 нет.",
              "code": code_fingerprints()}
    heat_pack = _safe(lambda: heat_numbers(records, now))
    if isinstance(heat_pack, tuple):
        result["heat"], heat = heat_pack
        result["akim"] = _safe(lambda: akim_numbers(heat, now))
    else:
        result["heat"], result["akim"] = heat_pack, {"available": False, "reason": "нет карты R07"}
    result["inbox"] = _safe(lambda: inbox_numbers(records, now))
    result["services"] = _safe(lambda: services_numbers(records, now))
    result["yards"] = _safe(lambda: yards_numbers(world_m, records, now))
    result["scenes"] = _safe(lambda: scenes_numbers(world_m, records, now))
    result["nura_check"] = nura_check(result)
    return result


def nura_check(result: dict) -> dict:
    """Одна строка сверки «Нура» по экранам (для DELIVERY и R10)."""
    heat = (result.get("heat") or {}).get("districts_14d", {}).get("nura", {})
    akim = (result.get("akim") or {}).get("nura", {})
    inbox = (result.get("inbox") or {}).get("nura", {})
    return {"map_people_14d": heat.get("people"), "map_targets_14d": heat.get("targets"),
            "day_new_week": akim.get("new_week"), "day_in_progress": akim.get("in_progress"),
            "day_overdue": akim.get("overdue"), "inbox_counts": inbox,
            "complaints_total": (result.get("inbox") or {}).get("complaints_by_district", {}).get("nura")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--world", default=None, help="путь к миру (по умолчанию world_v1.json)")
    ap.add_argument("--now", default=REFERENCE_NOW, help="момент засева, ISO (по умолчанию опорный)")
    ap.add_argument("--print", action="store_true", help="напечатать, не записывать EXPECTED.json")
    args = ap.parse_args(argv)
    world = wio.load_world(args.world)
    now = datetime.fromisoformat(args.now)
    result = expected(world, now)
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    if args.print:
        sys.stdout.write(text)
    else:
        path = wio.WORLD_DIR / "EXPECTED.json"
        path.write_text(text, encoding="utf-8")
        print(json.dumps(result["nura_check"], ensure_ascii=False))
        print(f"записано: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
