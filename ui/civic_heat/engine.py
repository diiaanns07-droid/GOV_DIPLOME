"""Расчёт тепловой карты: вес, уровень, «исправлено», районы (CONTRACT §6).

Правила (одним местом, чтобы следующий разработчик не искал по коду):
- Человек = одна жалоба + каждое «Я тоже» к ней. Вклад каждого человека: 0.5 ** (возраст_в_днях / 14).
  Возраст «Я тоже» — по его собственному времени из поля metoo_times (R09: ComplaintStore.metoo_times);
  если времени нет (старые записи, демо), «Я тоже» стареет вместе со своей жалобой.
- Дубли (duplicate_of задан) не считаются: их люди уже перенесены в «Я тоже» исходной записи (R09).
- В расчёт идут жалобы за выбранный период (7/30/90 дней), кроме статусов fixed и rejected.
- Если цель отмечена исправленной (статус fixed в истории), всё, что пришло ДО этого момента, считается
  закрытым. Новых жалоб нет → цель 7 дней зелёная «исправлено», вес 0. Пришли новые → снова краснеет.
- count — сколько человек сообщили за период (без затухания): это число на значке и в карточке.
  level — по весу (с затуханием): так цель «остывает», если новых жалоб нет.
- Проверка жителями (волна 2, п. 1; categories_v2.json → heat_states). Ответы жителей после ремонта читаются терпимо
  (resident_answers): «Да, исправлено» → цель «проверено жителями» (зелёный, 7 дней от ответа); ответов нет →
  «служба сообщила об устранении» (светло-зелёный пунктир, 7 дней от ремонта); последний ответ «Проблема осталась» →
  жалоба снова открыта («вернули жители»): цвет по весу, отметка на значке, люди этой жалобы снова в счёте, а их
  вес считается от момента возврата (житель подтвердил, что проблема есть сейчас). «Не могу проверить» — без влияния.
- Ремонт закрывает цель, только пока он «стоит»: исправленная жалоба, которую жители вернули, — не ремонт.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import deadline, geo
from .config import DAILY_WINDOW_DAYS, DISTRICT_LEVEL_SCALE, HeatConfig

ASTANA_TZ = timezone(timedelta(hours=5))
OPEN_STATUSES = ("new", "accepted", "in_progress")
STATUS_RANK = {"new": 0, "accepted": 1, "in_progress": 2}
MAX_OPEN_IDS = 50


def parse_time(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ASTANA_TZ)
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ASTANA_TZ)


def iso(dt: datetime) -> str:
    return dt.astimezone(ASTANA_TZ).isoformat(timespec="seconds")


def people(c: dict) -> int:
    try:
        metoo = int(c.get("metoo") or 0)
    except (TypeError, ValueError):
        metoo = 0
    return 1 + max(0, metoo)


def fixed_at(c: dict) -> datetime | None:
    """Когда жалоба получила статус fixed (последний раз). Нет истории — время создания."""
    last = None
    for h in c.get("status_history") or []:
        if isinstance(h, dict) and h.get("status") == "fixed":
            t = parse_time(h.get("at"))
            if t and (last is None or t > last):
                last = t
    if last is None and c.get("status") == "fixed":
        last = parse_time(c.get("updated_at")) or parse_time(c.get("created_at"))
    return last


# Ответ жителя после ремонта (волна 2, п. 1). Слова — с запасом: поле R09 ещё не утверждено (INTEGRATION R07 §2е).
_YES = {"yes", "confirmed", "fixed", "verified", "resolved", "ok", "да", "иә"}
_NO = {"no", "not_fixed", "still", "remains", "reopened", "problem_remains", "нет", "жоқ"}
_CANT = {"cant_check", "cant", "cannot_check", "unknown", "skip", "not_sure"}
_ANSWER_KEYS = ("answer", "state", "result", "value")


def _answer(value) -> str | None:
    if value is True:
        return "yes"
    s = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in _YES:
        return "yes"
    if s in _NO:
        return "no"
    if s in _CANT:
        return "cant"
    return None


def _answer_of(d: dict):
    for k in _ANSWER_KEYS:
        if k in d:
            return d[k]
    return None


def resident_answers(c: dict) -> list[tuple[str, datetime | None]]:
    """Ответы жителей «исправлено?» из записи: [(yes|no|cant, когда)], без повторов.

    Читается любое из (что даст R09): resident_checks / checks — список {answer|state|result, at};
    resident_check / verification — один такой объект или строка; verified / verified_by_residents /
    resident_confirmed = true (только true: false по умолчанию у непроверенных не значит «осталось»);
    записи status_history с полем resident_check / check / answer или со статусом verified / confirmed (да),
    reopened / resident_not_fixed (осталось)."""
    out: list = []
    seen = set()

    def add(value, at):
        a = _answer(value)
        if not a:
            return
        t = parse_time(at)
        k = (a, t.isoformat() if t else None)
        if k not in seen:
            seen.add(k)
            out.append((a, t))

    fallback_at = c.get("verified_at") or c.get("checked_at") or c.get("updated_at")
    for key in ("resident_checks", "checks"):
        val = c.get(key)
        if isinstance(val, list):
            for x in val:
                if isinstance(x, dict):
                    add(_answer_of(x), x.get("at"))
                else:
                    add(x, fallback_at)
    for key in ("resident_check", "verification"):
        val = c.get(key)
        if isinstance(val, dict):
            add(_answer_of(val), val.get("at") or fallback_at)
        elif isinstance(val, str):
            add(val, fallback_at)
    for key in ("verified", "verified_by_residents", "resident_confirmed"):
        if c.get(key) is True:
            add(True, fallback_at)
    for h in c.get("status_history") or []:
        if not isinstance(h, dict):
            continue
        for k in ("resident_check", "check", "answer"):
            if k in h:
                v = h[k]
                add(_answer_of(v) if isinstance(v, dict) else v, h.get("at"))
                break
        else:
            st = str(h.get("status") or h.get("event") or "")
            if st in ("verified", "confirmed", "resident_confirmed"):
                add("yes", h.get("at"))
            elif st in ("reopened", "resident_not_fixed"):
                add("no", h.get("at"))
    return out


def repair_state(c: dict) -> tuple[str, datetime, dict] | None:
    """Что с последним ремонтом жалобы: ("reported" | "verified" | "reopened", когда, {yes, no, cant}).
    None — ремонта не было. Решает последний ответ после ремонта; «не могу проверить» не решает ничего."""
    f = fixed_at(c)
    if f is None:
        return None
    after = [(a, t or f) for a, t in resident_answers(c) if t is None or t >= f - timedelta(minutes=1)]
    counts = {"yes": 0, "no": 0, "cant": 0}
    for a, _ in after:
        counts[a] += 1
    decisive = sorted([(t, a) for a, t in after if a != "cant"])
    if decisive and decisive[-1][1] == "no":
        return "reopened", decisive[-1][0], counts
    yes = [t for a, t in after if a == "yes"]
    if yes:
        return "verified", max(yes), counts
    return "reported", f, counts


def subtopic_of(c: dict) -> str | None:
    """Уточнение, выбранное жителем (волна 1, п. 2, R09: поле subtopic — id из categories_v2.json)."""
    st = c.get("subtopic")
    if isinstance(st, dict):
        st = st.get("id")
    return str(st) if st else None


def reports(c: dict, created: datetime) -> list[datetime]:
    """Моменты, когда люди сообщили о проблеме: сама жалоба + каждое «Я тоже» (по его времени, если оно есть)."""
    out = [created]
    times = [t for t in (parse_time(x) for x in (c.get("metoo_times") or [])) if t is not None]
    out.extend(times)
    out.extend([created] * max(0, people(c) - 1 - len(times)))
    return out


def decay(age_days: float, half_life: float) -> float:
    return 0.5 ** (max(0.0, age_days) / half_life)


def target_key(c: dict) -> tuple[dict, bool] | None:
    """Цель жалобы. Без цели — ячейка ~150 м вокруг точки, помеченная как примерное место."""
    t = c.get("target")
    if isinstance(t, dict) and t.get("id"):
        return t, False
    p = c.get("point")
    if isinstance(p, (list, tuple)) and len(p) == 2:
        return {"kind": "area", "id": geo.cell_id_for(p)}, True
    return None


def complaint_district(c: dict) -> str | None:
    d = c.get("district")
    if d:
        return str(d)
    p = c.get("point")
    if isinstance(p, (list, tuple)) and len(p) == 2:
        return geo.district_of(p)
    return None


def _astana_day(dt: datetime):
    return dt.astimezone(ASTANA_TZ).date()


def is_r07_example(c: dict) -> bool:
    """Синтетическая жалоба демо-набора R07 (demo_seed: id c-demo-…). В общей сборке её нет в хранилище R09 —
    поменять ей статус или нажать «Я тоже» нельзя (R10 B-037). Демо-жалобы самого R09 (demo: true, другие id) — можно."""
    return bool(c.get("demo")) and str(c.get("id") or "").startswith("c-demo-")


def compute(complaints, *, now: datetime, days: int, config: HeatConfig, resolver, category: str | None = None,
            district: str | None = None, bbox=None, actionable=None) -> dict:
    """Все цели с жалобами → {items, stats}. Порядок items: сначала самые горячие.
    actionable(запись) → можно ли менять её статус / жать «Я тоже» (None — все): в open_ids только такие,
    остальные открытые — числом examples_open (карточка покажет «Пример: статус не меняется»)."""
    period_start = now - timedelta(days=days)
    fixed_span = timedelta(days=config.fixed_days)
    today = _astana_day(now)
    groups: dict = defaultdict(list)
    meta: dict = {}
    stats = {"complaints": 0, "skipped_invalid": 0, "duplicates_skipped": 0, "unresolved_targets": 0, "approximate_targets": 0}

    for c in complaints:
        if not isinstance(c, dict):
            stats["skipped_invalid"] += 1
            continue
        created = parse_time(c.get("created_at"))
        tk = target_key(c)
        if created is None or tk is None:
            stats["skipped_invalid"] += 1
            continue
        if c.get("duplicate_of"):
            stats["duplicates_skipped"] += 1
            continue
        if category and c.get("category") != category:
            continue
        cd = complaint_district(c)
        if district and cd != district:
            continue
        stats["complaints"] += 1
        target, missing = tk
        key = (target.get("kind") or "area", str(target["id"]))
        groups[key].append((c, created))
        m = meta.setdefault(key, {"target": target, "missing": missing, "district": cd, "point": None, "last": None})
        if m["last"] is None or created > m["last"]:
            m["last"] = created
            m["point"] = c.get("point")
            m["district"] = cd or m["district"]

    items = []
    totals = {"fixed_reported": 0, "fixed_verified": 0, "reopened": 0}
    for key, rows in groups.items():
        m = meta[key]
        repairs = {id(c): repair_state(c) for c, _ in rows}
        reopened = {i: r[1] for i, r in repairs.items() if r and r[0] == "reopened"}
        # Ремонт закрывает цель, только пока он стоит: жалоба в статусе fixed, которую жители не вернули.
        t_fixed = None
        for c, _ in rows:
            if c.get("status") == "fixed" and id(c) not in reopened:
                f = fixed_at(c)
                if f and (t_fixed is None or f > t_fixed):
                    t_fixed = f
        # Открыта жалоба со статусом new / accepted / in_progress (R10 B-036, R09: статус каждой жалобы честный —
        # «исправлено» у одной не закрывает остальные). Только примеры R07, статус которых не поменять (общая сборка),
        # закрывает более поздний ремонт места — иначе цель с примерами никогда не стала бы зелёной.
        # Возвращённая жителями жалоба открыта всегда, даже если R09 ещё не сменил ей статус.
        active = [(c, cr) for c, cr in rows
                  if c.get("status") != "rejected"
                  and (id(c) in reopened
                       or (c.get("status", "new") in OPEN_STATUSES
                           and (actionable is None or actionable(c) or t_fixed is None or cr > t_fixed)))]
        latest = now + timedelta(minutes=5)   # небольшой запас на расхождение часов
        weight = 0.0
        count = 0
        by_cat: dict = defaultdict(int)
        by_sub: dict = defaultdict(int)
        status_rank = 0
        in_period = []
        events_in_period = []                # (жалоба, момент) — для графика по дням
        reopened_at = None
        due = None
        for c, cr in active:
            back = reopened.get(id(c))
            moments = reports(c, cr)
            if back is not None:
                moments = [max(t, back) for t in moments]   # житель подтвердил: проблема есть сейчас
            moments = [t for t in moments if period_start <= t <= latest]
            if not moments:
                continue
            in_period.append((c, max(moments)))
            for t in moments:
                weight += decay((now - t).total_seconds() / 86400.0, config.half_life_days)
                events_in_period.append(t)
            count += len(moments)
            by_cat[c.get("category") or "other"] += len(moments)
            sub = subtopic_of(c)
            if sub:
                by_sub[sub] += len(moments)
            if back is not None:
                status_rank = max(status_rank, STATUS_RANK["in_progress"])
                reopened_at = back if reopened_at is None or back > reopened_at else reopened_at
            else:
                status_rank = max(status_rank, STATUS_RANK.get(c.get("status", "new"), 0))
            # Срок ответа (R09 due_at) — только у новых: «просрочено» по R09 = никто не ответил, а срок прошёл.
            if c.get("status", "new") == "new" and back is None:
                d = parse_time(c.get("due_at"))
                if d is not None and (due is None or d < due):
                    due = d

        state = "active"
        fixed_until = None
        fixed_kind = None
        checks = None
        if count == 0:
            if t_fixed is None:
                continue
            # Тот же ремонт — все исправленные за сутки до последнего (сотрудник закрывает жалобы места по одной).
            round_ = [repairs[id(c)] for c, _ in rows if c.get("status") == "fixed" and id(c) not in reopened
                      and repairs[id(c)] and repairs[id(c)][1] >= t_fixed - timedelta(days=1)]
            verified = [r[1] for r in round_ if r[0] == "verified"]
            if verified:
                fixed_kind = "verified"
                fixed_until = max(verified) + timedelta(days=config.verified_days())
            else:
                fixed_kind = "reported"
                fixed_until = t_fixed + fixed_span
            if now >= fixed_until:
                continue
            state = "fixed"
            tally = {"yes": 0, "no": 0, "cant": 0}
            for r in round_:
                for k in tally:
                    tally[k] += r[2][k]
            checks = tally if any(tally.values()) else None
            closed = [(c, cr) for c, cr in rows if c.get("status") != "rejected" and id(c) not in reopened
                      and cr <= t_fixed and cr >= t_fixed - timedelta(days=days)]
            count = sum(people(c) for c, _ in closed)
            for c, _ in closed:
                by_cat[c.get("category") or "other"] += people(c)
                sub = subtopic_of(c)
                if sub:
                    by_sub[sub] += people(c)
        elif reopened_at is not None:
            tally = {"yes": 0, "no": 0, "cant": 0}
            for c, _ in active:
                r = repairs[id(c)]
                if r and r[0] == "reopened":
                    for k in tally:
                        tally[k] += r[2][k]
            checks = tally

        resolved = resolver.resolve(m["target"], m["point"])
        if not resolved:
            stats["unresolved_targets"] += 1
            continue
        approximate = bool(resolved.get("approximate") or m["missing"] or m["target"].get("approximate"))
        if approximate:
            stats["approximate_targets"] += 1
        if bbox is not None:
            gb = geo.bbox_of(resolved["geometry"])
            if gb is None or not geo.bbox_intersects(gb, bbox):
                continue

        daily = [0] * DAILY_WINDOW_DAYS
        for t in (events_in_period if state == "active" else []):
            idx = DAILY_WINDOW_DAYS - 1 - (today - _astana_day(t)).days
            if 0 <= idx < DAILY_WINDOW_DAYS:
                daily[idx] += 1

        level = config.level_for(weight) if state == "active" else "fixed"
        if state == "active":
            color = config.color_for(level)
        else:
            color = config.state_color("verified_fixed" if fixed_kind == "verified" else "reported_fixed")
        status = "fixed" if state == "fixed" else ("new", "accepted", "in_progress")[status_rank]
        open_sorted = sorted(in_period, key=lambda x: x[1], reverse=True)
        label_ru = "Примерное место" if m["missing"] else resolved["label_ru"]
        label_kk = "Шамамен көрсетілген орын" if m["missing"] else resolved["label_kk"]
        target_out = {"kind": key[0], "id": key[1], "label_ru": label_ru, "label_kk": label_kk}
        if resolved.get("subtype"):
            target_out["subtype"] = resolved["subtype"]   # например bus_stop → в карточке «Остановка»
        subs = dict(sorted(by_sub.items(), key=lambda kv: -kv[1]))
        top_sub = next(((sid, n) for sid, n in subs.items() if sid in (config.subtopics or {})), None)
        if fixed_kind:
            totals["fixed_" + fixed_kind] += 1
        if state == "active" and reopened_at is not None:
            totals["reopened"] += 1
        items.append({
            "target": target_out,
            "geometry": resolved["geometry"],
            "anchor": [round(v, 6) for v in resolved["anchor"]] if resolved.get("anchor") else None,
            "weight": round(weight, 3),
            "level": level,
            "color": color,
            "count": count,
            "fixed_until": iso(fixed_until) if fixed_until else None,
            "state": state,
            "fixed_kind": fixed_kind,              # reported | verified | None (волна 2, п. 1)
            "reopened": state == "active" and reopened_at is not None,
            "reopened_at": iso(reopened_at) if state == "active" and reopened_at is not None else None,
            "checks": checks,                      # {yes, no, cant} — ответы жителей о последнем ремонте
            "status": status,
            "due": deadline.response_due(due, now, ASTANA_TZ) if due is not None and state == "active" else None,
            "approximate": approximate,
            "district": m["district"],
            "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
            "subtopics": subs,                     # id уточнения → людей (R09 subtopic)
            "top_subtopic": ({"id": top_sub[0], "ru": config.subtopics[top_sub[0]]["ru"], "kk": config.subtopics[top_sub[0]]["kk"],
                              "count": top_sub[1]} if top_sub else None),
            "daily": daily,
            "last_at": iso(m["last"]),
            "open_ids": [c.get("id") for c, _ in open_sorted if c.get("id") and (actionable is None or actionable(c))][:MAX_OPEN_IDS],
            "examples_open": 0 if actionable is None else sum(1 for c, _ in open_sorted if not actionable(c)),
            "demo": all(bool(c.get("demo")) for c, _ in rows),
        })

    stats.update(totals)
    items.sort(key=lambda it: (it["state"] == "active", it["level"] if it["state"] == "active" else 0, it["weight"], it["count"]), reverse=True)
    return {"items": items, "stats": stats}


_NORM_RE = re.compile(r"[^\w\s]+", re.U)
TEXT_MAX = 140


def _norm_text(text: str) -> str:
    return " ".join(_NORM_RE.sub(" ", text.lower()).split())[:80]


def text_groups(complaints, *, kind: str, target_id: str, now: datetime, days: int, include_real: bool, limit: int = 3) -> dict:
    """«Что пишут жители»: 1–3 группы похожих текстов по цели с числом людей.

    Тексты демо-записей (synthetic) показываются всегда — в них нет людей и личных данных.
    Тексты НАСТОЯЩИХ жалоб — только сотруднику (include_real=True ставит шлюз R01 после проверки входа);
    жителю и публичной карте — никогда (CONTRACT, промпт R07: «только цель и число»).
    Группа = одинаковый текст без регистра и знаков; показывается самый свежий вариант формулировки.
    """
    period_start = now - timedelta(days=days)
    rows = []
    t_fixed = None
    for c in complaints:
        t = c.get("target") if isinstance(c, dict) else None
        if not isinstance(t, dict) or str(t.get("id")) != target_id or (t.get("kind") or "area") != kind or c.get("duplicate_of"):
            continue
        cr = parse_time(c.get("created_at"))
        if cr is None:
            continue
        rows.append((c, cr))
        f = fixed_at(c)
        if f and (t_fixed is None or f > t_fixed):
            t_fixed = f
    groups: dict = {}
    hidden = 0
    for c, cr in rows:
        if c.get("status", "new") not in OPEN_STATUSES or (t_fixed is not None and cr <= t_fixed) or cr < period_start:
            continue
        text = str(c.get("text") or "").strip()
        if not text:
            continue
        if not c.get("demo") and not include_real:
            hidden += people(c)
            continue
        g = groups.setdefault(_norm_text(text), {"text": text, "people": 0, "demo": True, "lang": c.get("lang"), "_last": cr})
        g["people"] += people(c)
        g["demo"] = g["demo"] and bool(c.get("demo"))
        if cr >= g["_last"]:
            g["_last"], g["text"], g["lang"] = cr, text, c.get("lang")
    ordered = sorted(groups.values(), key=lambda g: (-g["people"], -g["_last"].timestamp()))[: max(0, limit)]
    out = []
    for g in ordered:
        text = g["text"] if len(g["text"]) <= TEXT_MAX else g["text"][: TEXT_MAX - 1].rstrip() + "…"
        out.append({"text": text, "people": g["people"], "demo": g["demo"], "lang": g["lang"]})
    return {"groups": out, "hidden_people": hidden}


def districts_summary(target_items: list, config: HeatConfig, *, district: str | None = None) -> list:
    """Мелкий масштаб: сумма по району. Пороги уровней умножены на DISTRICT_LEVEL_SCALE.
    Район без единой жалобы за период — «нет свежих данных» (серый, волна 2): отсутствие жалоб не значит «всё хорошо».
    Серый — только у районов (на крупном масштабе тысячи серых объектов перегрузили бы карту) и только у тех, что
    проходят фильтр района."""
    acc: dict = {}
    for it in target_items:
        d = it.get("district")
        if not d:
            continue
        a = acc.setdefault(d, {"weight": 0.0, "count": 0, "targets": 0, "fixed": 0, "verified": 0, "reopened": 0, "top": None})
        if it["state"] == "fixed":
            a["fixed"] += 1
            a["verified"] += 1 if it.get("fixed_kind") == "verified" else 0
            continue
        a["weight"] += it["weight"]
        a["count"] += it["count"]
        a["targets"] += 1
        a["reopened"] += 1 if it.get("reopened") else 0
        if a["top"] is None or it["weight"] > a["top"]["weight"]:
            a["top"] = {"target": it["target"], "weight": it["weight"], "count": it["count"]}
    out = []
    all_d = geo.districts()
    no_data_color = config.state("no_data").get("color")
    for d_id, d in all_d.items():
        if district and d_id != district:
            continue
        a = acc.get(d_id)
        if a is None and not no_data_color:
            continue
        a = a or {"weight": 0.0, "count": 0, "targets": 0, "fixed": 0, "verified": 0, "reopened": 0, "top": None, "none": True}
        level = config.level_for(a["weight"], DISTRICT_LEVEL_SCALE) if a["count"] else 0
        state = "no_data" if a.get("none") else ("active" if a["count"] else "calm")
        out.append({
            "target": {"kind": "district", "id": d_id, "label_ru": d["name_ru"], "label_kk": d["name_kk"]},
            "geometry": d["geometry"],
            "anchor": [round(v, 6) for v in geo.anchor_of(d["geometry"])],
            "weight": round(a["weight"], 3),
            "level": level,
            "color": no_data_color if state == "no_data" else config.color_for(level),
            "count": a["count"],
            "fixed_until": None,
            "state": state,
            "targets": a["targets"],
            "fixed_targets": a["fixed"],
            "verified_targets": a["verified"],
            "reopened_targets": a["reopened"],
            "top": a["top"],
            "district": d_id,
        })
    out.sort(key=lambda it: (it["weight"], it["count"]), reverse=True)
    return out


def round_geometry(geometry: dict, digits: int = 6) -> dict:
    def r(c):
        if c and isinstance(c[0], (int, float)):
            return [round(c[0], digits), round(c[1], digits)]
        return [r(x) for x in c]
    return {"type": geometry["type"], "coordinates": r(geometry["coordinates"])}


def is_finite_number(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)
