"""«Нужно решение акима» (волна 2 п. 5): 1–3 просрочки, которые служба не может сдвинуть сама.

КРИТЕРИЙ (одним местом):
  обращение не исправлено, срок категории истёк (deadlines.due — рабочие дни),
  И в паспорте решения (R09, волна 2 п. 2) причина задержки — «нужно решение руководителя»:
  delay.reason_code ∈ NEEDS_DECISION или delay.needs_decision = true.
Почему так: аким не должен разбирать каждую просрочку. Обычные задержки — погода, подрядчик, материалы —
видны в «Просрочено» и решаются службой. Сюда попадает только то, где нужен выбор руководителя:
деньги вне плана, «чей это объект», согласование между ведомствами. Без двух вариантов действия пункт
всё равно показывается, но с пометкой «варианты не предложены» — это сигнал службе, а не акиму.

Где лежит причина: паспорт решения R09 (lifecycle.py, claude/modest-shannon-0ki93p) — record["passport"]["delay"] =
  {reason (текст «что мешает»), temp_measure, next_update_at}. Чтобы задержка попала сюда, R09 добавляет в форму
  отметку «Нужно решение руководителя» и два варианта: delay.needs_decision = true, delay.options = [{ru, kk}, {ru, kk}],
  delay.decision = «что нужно от акима» (INTEGRATION.txt §8). Читаем и расширенную форму: record["delay"] /
  passport.delay = {reason_code, problem_ru/kk, blocker_ru/kk, options, decision_ru/kk, temp_measure_ru/kk}.
Пока R09 не даёт причин, а жалобы — демо (R07), блок показывает пример из fixtures/decisions_demo.json
(помечен «Пример»): эти записи проходят тот же критерий, что и настоящие.

ВЫБОР АКИМА («Выбрать» у варианта, R11 IA_WAVE2 §5): choose() пишет {option, at, by} в
.runtime/civic_akim/decisions.json (в Git не попадает; путь — BIRGE_AKIM_DECISIONS). Служба видит выбор
через choice_for(id) — R09 показывает его в паспорте решения («Решение акима: вариант 1»).
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import deadlines, routing

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "decisions_demo.json"
STORE_PATH = Path(os.environ.get("BIRGE_AKIM_DECISIONS") or deadlines.ROOT / ".runtime" / "civic_akim" / "decisions.json")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
_lock = threading.Lock()


class DecisionError(ValueError):
    def __init__(self, field: str, message: str, status: int = 400):
        super().__init__(message)
        self.field, self.status = field, status
NEEDS_DECISION = {"needs_decision", "leader_decision", "akim_decision", "needs_akim_decision", "management_decision"}
MAX_ITEMS = 3


def delay_of(record: dict) -> dict | None:
    d = record.get("delay")
    if not isinstance(d, dict):
        passport = record.get("passport")
        d = passport.get("delay") if isinstance(passport, dict) else None
    return d if isinstance(d, dict) else None


def needs_decision(record: dict) -> bool:
    d = delay_of(record)
    if not d:
        return False
    return d.get("needs_decision") is True or str(d.get("reason_code") or d.get("reason") or "").lower() in NEEDS_DECISION


def _txt(d: dict, key: str, lang: str):
    v = d.get(f"{key}_{lang}")
    if v is None and isinstance(d.get(key), dict):
        v = d[key].get(lang)
    if v is None and lang == "ru" and isinstance(d.get(key), str):
        v = d[key]
    return v.strip() if isinstance(v, str) and v.strip() else None


def _free_reason(d: dict) -> str | None:
    r = d.get("reason")
    if isinstance(r, str) and r.strip() and r.strip().lower() not in NEEDS_DECISION and " " in r.strip():
        return r.strip()
    return None


def own_label(target: dict | None) -> dict | None:
    """Подпись места из самой жалобы (цель R09: {kind, id, label_ru?, label_kk?, approximate?}).

    Нужна, когда места нет на карте за 7 дней (давняя просрочка): иначе в «Нужно решение акима» нет адреса.
    «Примерное место» (approximate) адресом не считаем — лучше район, чем «Шамамен орны».
    """
    if not isinstance(target, dict) or target.get("approximate") or not target.get("label_ru"):
        return None
    return {"ru": target["label_ru"], "kk": target.get("label_kk") or target["label_ru"]}


def _subtopic(category: str | None, subtopic: str | None) -> dict | None:
    if not subtopic:
        return None
    for c in deadlines.load_categories()["categories"]:
        if c["id"] == category:
            for s in c.get("subtopics") or []:
                if s["id"] == subtopic:
                    return {"id": subtopic, "ru": s["ru"], "kk": s["kk"]}
    return None


def build(records: list[dict], as_of: datetime, *, status_at, parse_time, labels: dict | None = None) -> list[dict]:
    """Пункты блока по записям (уже отфильтрованным по району), самые давние просрочки первыми."""
    labels = labels or {}
    cats = {c["id"]: c for c in deadlines.load_categories()["categories"]}
    out = []
    for r in records:
        st = status_at(r, as_of)
        if st not in ("new", "accepted", "in_progress") or not needs_decision(r):
            continue
        created = parse_time(r.get("created_at"))
        timer = deadlines.timer(r.get("category"), created, as_of)
        if timer["state"] != "overdue":
            continue
        d = delay_of(r)
        options = [{"ru": (o.get("ru") or o.get("kk")).strip(), "kk": (o.get("kk") or o.get("ru")).strip(),
                    "kk_missing": not o.get("kk")}
                   for o in (d.get("options") or []) if isinstance(o, dict) and (o.get("ru") or o.get("kk"))][:2]
        target = r.get("target") if isinstance(r.get("target"), dict) else None
        on_map = labels.get(target.get("id")) if target else None
        label = on_map or own_label(target)
        cat = cats.get(r.get("category")) or cats["other"]
        sub = _subtopic(r.get("category"), r.get("subtopic"))
        service = routing.service_for(r.get("category"), r.get("subtopic"))
        item = {
            "id": r.get("id"),
            "category": cat["id"], "category_ru": cat["ru"], "category_kk": cat["kk"],
            "subtopic": sub,
            "district": r.get("district"),
            "place_ru": (label or {}).get("ru") or r.get("place_ru"),
            "place_kk": (label or {}).get("kk") or r.get("place_kk"),
            # Ссылка «на карту» — только если место есть на карте (подпись пришла с тепловой карты R07).
            "target": {"kind": target.get("kind"), "id": target.get("id")} if target and on_map else None,
            "people": 1 + int(r.get("metoo") or 0),
            "timer": timer,
            "service": {k: service[k] for k in ("id", "ru", "kk", "name_edited")},
            "problem_ru": _txt(d, "problem", "ru") or (sub or cat)["ru"],
            "problem_kk": _txt(d, "problem", "kk"),
            # «Что мешает»: blocker_*; у R09 — свободный текст delay.reason (если это не код причины)
            "blocker_ru": _txt(d, "blocker", "ru") or _free_reason(d), "blocker_kk": _txt(d, "blocker", "kk"),
            "options": options,
            "options_missing": len(options) < 2,
            "decision_ru": _txt(d, "decision", "ru"), "decision_kk": _txt(d, "decision", "kk"),
            "temp_measure_ru": _txt(d, "temp_measure", "ru"), "temp_measure_kk": _txt(d, "temp_measure", "kk"),
            "demo": bool(r.get("demo")),
            "chosen": choice_for(str(r.get("id"))),
        }
        # kk нет — интерфейс покажет русский текст с пометкой (как у объектов без kk), а не пустое место.
        for key in ("problem", "blocker", "decision", "temp_measure"):
            item[f"{key}_kk_missing"] = item[f"{key}_ru"] is not None and item[f"{key}_kk"] is None
            if item[f"{key}_kk"] is None:
                item[f"{key}_kk"] = item[f"{key}_ru"]
        out.append(item)
    out.sort(key=lambda x: (-x["timer"]["overdue_by"], -x["people"], str(x["id"])))
    return out


def fixture_records(today: date) -> list[dict]:
    """Пример из fixtures/decisions_demo.json со сдвигом дат на (today − anchor)."""
    from .sources import _shift, _shift_days  # те же правила сдвига, что у фикстур объектов
    raw = json.loads(FIXTURE.read_text("utf-8"))
    days = _shift_days(raw.get("_meta", {}), today)
    out = []
    for r in raw.get("records", []):
        r = json.loads(json.dumps(r))
        r["created_at"] = _shift(r.get("created_at"), days)
        for h in r.get("status_history") or []:
            h["at"] = _shift(h.get("at"), days)
        out.append(r)
    return out


# ---------------------------------------------------------------- выбор акима

def _load(path: Path | None = None) -> dict:
    try:
        data = json.loads(Path(path or STORE_PATH).read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def choice_for(item_id: str, path: Path | None = None) -> dict | None:
    """Выбор акима по обращению: {option, at} или None. Для R09 (паспорт решения) и для «Картины дня».

    R15-S28: оба вывода публичные (GET /akim/summary, паспорт R09) — кто выбрал (by, логин сотрудника) остаётся
    только в файле выборов и в ответе самому сотруднику (choose)."""
    c = _load(path).get(str(item_id))
    return {"option": c["option"], "at": c.get("at")} if isinstance(c, dict) and c.get("option") in (1, 2) else None


def choose(item_id: str, option, *, items: list[dict], actor: str | None = None, path: Path | None = None,
           now: datetime | None = None) -> dict:
    """Записать выбор варианта. items — текущие пункты блока: выбирать можно только из них и только из 2 вариантов."""
    if not isinstance(item_id, str) or not ID_RE.match(item_id):
        raise DecisionError("id", "неверный номер обращения")
    item = next((i for i in items if i.get("id") == item_id), None)
    if item is None:
        raise DecisionError("id", "этого вопроса нет среди «Нужно решение акима»", 404)
    if isinstance(option, bool) or option not in (1, 2):
        raise DecisionError("option", "вариант — 1 или 2")
    if len(item.get("options") or []) < option:
        raise DecisionError("option", "у вопроса нет такого варианта")
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=5))).isoformat(timespec="seconds")
    record = {"option": option, "at": stamp, "by": (str(actor)[:80] if actor else None)}
    p = Path(path or STORE_PATH)
    with _lock:
        data = _load(p)
        data[item_id] = record
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, p)
    return record
