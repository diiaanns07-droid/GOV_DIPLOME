"""Засев «Встреч с акимом» из демо-мира R02 (CONTRACT §11): seed_world(db_path, records, now=None).

records — весь мир (dict из data/civic/astana/demo-world/world_v1.json) или только список встреч. Берём свою часть:
  meetings  — встречи по CONTRACT §5.7 (+ поручения внутри, + итог), время — относительно момента засева;
  questions — вопросы: с meeting / meeting_id — к встрече, без — общие вопросы «Вопроса акиму».
Повторный засев ничего не дублирует (постоянные id) и не трогает правки сотрудника.

Время в мире R02 относительное (CONTRACT §11: ago_days, ago_hours, in_days). Понимаем и абсолютное ISO:
  встреча:   at | in_days / in_hours / ago_days / ago_hours [+ time «18:30» по Астане];
  итог:      result {text_ru, text_kk, at | ago_days | ago_hours} или result_ru / result_kk;
  поручение: due «ГГГГ-ММ-ДД» | due_in_days (от сегодня) | due_days_after (от дня встречи); status todo|in_progress|done;
  вопрос:    ago_days / ago_hours (публикация), votes | base_votes, answer_ru / answer_kk (+ answered_ago_days).
Неизвестные поля пропускаем; запись без обязательного поля — skipped (засев не падает).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from .store import iso, parse_iso

ASTANA = timezone(timedelta(hours=5))
DISTRICTS = ("almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka")
SERVICES = ("road", "traffic", "street_cleaning", "transport", "lighting", "landscaping", "greenery", "waste",
            "utilities", "heating", "water", "power", "gas", "housing", "ecology", "emergency", "police", "animals",
            "parking", "akimat")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\Z")


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _moment(rec: dict, now: datetime, *, prefix: str = "") -> datetime | None:
    """Момент из записи: ISO (prefix+at) или относительное время (prefix+in_days/…); time — время суток по Астане."""
    absolute = rec.get(prefix + "at")
    if isinstance(absolute, str):
        moment = parse_iso(absolute)
        if moment is not None:
            return moment
    delta, found = timedelta(0), False
    for key, sign, unit in (("in_days", 1, "days"), ("in_hours", 1, "hours"), ("ago_days", -1, "days"),
                            ("ago_hours", -1, "hours"), ("in_minutes", 1, "minutes"), ("ago_minutes", -1, "minutes")):
        if rec.get(prefix + key) is not None:
            delta += sign * timedelta(**{unit: _num(rec[prefix + key])})
            found = True
    if not found:
        return None
    moment = now + delta
    clock = rec.get(prefix + "time") or rec.get(prefix + "local_time")
    if isinstance(clock, str) and TIME_RE.match(clock.strip()):
        hour, minute = (int(x) for x in TIME_RE.match(clock.strip()).groups())
        local = moment.astimezone(ASTANA).replace(hour=min(hour, 23), minute=min(minute, 59), second=0, microsecond=0)
        moment = local.astimezone(timezone.utc)
    return moment


def _due(order: dict, now: datetime, meeting_at: datetime) -> str | None:
    due = order.get("due")
    if isinstance(due, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
        return due
    if order.get("due_in_days") is not None:
        return (now.astimezone(ASTANA) + timedelta(days=_num(order["due_in_days"]))).date().isoformat()
    if order.get("due_days_after") is not None:
        return (meeting_at.astimezone(ASTANA) + timedelta(days=_num(order["due_days_after"]))).date().isoformat()
    if order.get("due_ago_days") is not None:
        return (now.astimezone(ASTANA) - timedelta(days=_num(order["due_ago_days"]))).date().isoformat()
    return None


def _place(rec: dict) -> tuple[dict | None, list | None]:
    place = rec.get("place") or rec.get("target") or {}
    if not isinstance(place, dict):
        place = {}
    out = None
    if place.get("label_ru") or place.get("id"):
        kind = place.get("kind") if place.get("kind") in ("object", "segment", "area") else None
        pid = place.get("id") if isinstance(place.get("id"), str) and ID_RE.match(place["id"]) else None
        out = {"kind": kind if pid else None, "id": pid if kind else None,
               "label_ru": place.get("label_ru") or place.get("label") or pid,
               "label_kk": place.get("label_kk")}
    point = rec.get("point") or place.get("point")
    if not (isinstance(point, (list, tuple)) and len(point) == 2):
        point = None
    else:
        point = [float(point[0]), float(point[1])]
    return out, point


def meeting_rows(world, now: datetime) -> tuple[list[dict], list[dict], int]:
    """(встречи, поручения, пропущено) в виде для MeetingStore.seed."""
    raw = world.get("meetings") if isinstance(world, dict) else world
    meetings, orders, skipped = [], [], 0
    for rec in raw or []:
        if not isinstance(rec, dict):
            skipped += 1
            continue
        mid = rec.get("id")
        start = _moment(rec, now)
        district = rec.get("district")
        title_ru = rec.get("title_ru") or rec.get("title")
        if not (isinstance(mid, str) and ID_RE.match(mid) and start and district in DISTRICTS and title_ru):
            skipped += 1
            continue
        place, point = _place(rec)
        result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
        result_ru = result.get("text_ru") or rec.get("result_ru")
        result_kk = result.get("text_kk") or rec.get("result_kk")
        result_at = _moment(result, now) if result else None
        duration = int(_num(rec.get("duration_min"), 90)) or 90
        if (result_ru or result_kk) and result_at is None:
            result_at = start + timedelta(minutes=duration)
        meetings.append({
            "id": mid, "district": district, "title_ru": title_ru, "title_kk": rec.get("title_kk"),
            "at": iso(start), "duration_min": max(30, min(480, duration)), "place": place, "point": point,
            "status": "cancelled" if rec.get("status") == "cancelled" else "scheduled",
            "base_registered": int(_num(rec.get("registered") or rec.get("base_registered"), 0)),
            "result_ru": result_ru, "result_kk": result_kk,
            "result_at": iso(result_at) if (result_ru or result_kk) and result_at else None,
            "created_at": iso(min(start, now) - timedelta(days=7)), "demo": rec.get("demo", True) is not False,
        })
        for position, order in enumerate(rec.get("orders") or [], start=1):
            if not isinstance(order, dict):
                skipped += 1
                continue
            oid = order.get("id")
            # Короткие id поручений мира («o-1») уникальны только внутри встречи — делаем уникальными в базе.
            if isinstance(oid, str) and ID_RE.match(oid) and not oid.startswith(mid + "-"):
                oid = f"o-{mid.removeprefix('m-')}-{oid.removeprefix('o-')}"
            due = _due(order, now, start)
            status = order.get("status") if order.get("status") in ("todo", "in_progress", "done") else "todo"
            if not (isinstance(oid, str) and ID_RE.match(oid) and order.get("text_ru") and order.get("service") in SERVICES
                    and due):
                skipped += 1
                continue
            created = start + timedelta(minutes=duration) + timedelta(hours=2)
            created = min(created, now)
            updated = _moment(order, now, prefix="updated_") or (created if status == "todo" else min(now, created + timedelta(days=2)))
            link = order.get("link") if isinstance(order.get("link"), dict) else None
            if link and not (link.get("kind") in ("complaint", "work", "project") and isinstance(link.get("id"), str)
                             and ID_RE.match(link["id"])):
                link = None
            orders.append({
                "id": oid, "meeting_id": mid, "position": position, "text_ru": order["text_ru"],
                "text_kk": order.get("text_kk"), "service": order["service"], "due": due, "status": status,
                "link": link, "created_at": iso(created), "updated_at": iso(updated),
                "done_at": iso(updated) if status == "done" else None, "demo": order.get("demo", True) is not False,
            })
    return meetings, orders, skipped


def question_rows(world, now: datetime, meetings: dict[str, dict]) -> tuple[list[dict], int]:
    """Вопросы мира -> строки QuestionStore.seed. meetings — {id: строка встречи} (для района и закрытия голосов)."""
    raw = world.get("questions") if isinstance(world, dict) else None
    rows, skipped = [], 0
    for rec in raw or []:
        if not isinstance(rec, dict):
            skipped += 1
            continue
        qid = rec.get("id")
        text = rec.get("text") or rec.get("text_ru")
        meeting_id = rec.get("meeting_id") or rec.get("meeting")
        meeting = meetings.get(meeting_id) if isinstance(meeting_id, str) else None
        district = rec.get("district") or (meeting or {}).get("district")
        if not (isinstance(qid, str) and qid.startswith("q-") and ID_RE.match(qid) and isinstance(text, str)
                and 10 <= len(text) <= 300 and district in DISTRICTS):
            skipped += 1
            continue
        published = _moment(rec, now) or now - timedelta(days=1)
        status = rec.get("status") if rec.get("status") in ("pending", "published", "rejected") else "published"
        if status == "rejected":  # отклонённые в демо не нужны: их никто не видит
            skipped += 1
            continue
        if meeting is not None and published > parse_iso(meeting["at"]):
            published = parse_iso(meeting["at"]) - timedelta(hours=6)  # вопрос к встрече — до её начала
        answer_ru, answer_kk = rec.get("answer_ru"), rec.get("answer_kk")
        answered = None
        if answer_ru or answer_kk:
            answered = _moment(rec, now, prefix="answered_") or (
                parse_iso(meeting["at"]) + timedelta(hours=2) if meeting else published + timedelta(days=2))
            answered = min(answered, now)
        rows.append({
            "id": qid, "district": district, "lang": rec.get("lang") if rec.get("lang") in ("ru", "kk") else "ru",
            "text": text.strip(), "status": status,
            "created_at": iso(published - timedelta(hours=2)),
            "published_at": iso(published) if status == "published" else None,
            "base_votes": int(_num(rec.get("votes") if rec.get("votes") is not None else rec.get("base_votes"), 0)),
            "answer_ru": answer_ru if status == "published" else None,
            "answer_kk": answer_kk if status == "published" else None,
            "answered_at": iso(answered) if answered and status == "published" else None,
            "meeting_id": meeting_id if meeting else None,
            "votes_close_at": meeting["at"] if meeting else None,
        })
    return rows, skipped


def seed_world(db_path, records, now=None) -> dict:
    """CONTRACT §11: засеять встречи, поручения и вопросы мира. -> {"inserted", "skipped"} (идемпотентно)."""
    from ui.civic_qa.store import QuestionStore  # noqa: WPS433
    from .store import MeetingStore

    now = now.astimezone(timezone.utc) if isinstance(now, datetime) else datetime.now(timezone.utc)
    store = MeetingStore(db_path)
    meetings, orders, skipped = meeting_rows(records, now)
    inserted, already = store.seed(meetings, orders)
    by_id = {m["id"]: m for m in meetings}
    raw_questions = (records.get("questions") or []) if isinstance(records, dict) else []
    # Вопросы к встречам, уже лежащим в базе (засев раньше или встреча сотрудника), тоже узнаём по id встречи.
    for mid in {(q.get("meeting_id") or q.get("meeting")) for q in raw_questions if isinstance(q, dict)} - set(by_id):
        if isinstance(mid, str):
            try:
                by_id[mid] = store.get_meeting(mid)
            except LookupError:
                pass
    questions, q_skipped = question_rows(records, now, by_id)
    made = QuestionStore(db_path).seed(questions) if questions else 0
    return {"inserted": inserted + made, "skipped": skipped + already + q_skipped + (len(questions) - made)}
