"""Предложения акимата и голоса жителей (R06, раунд 14; CONTRACT §7).

Акимат ставит на 3D-карту объект (R05) — появляется предложение со статусом proposal.
Жители голосуют «За» / «Против»: один голос с устройства, повторное нажатие меняет голос,
а не добавляет новый (одна строка civic_votes на пару предложение+устройство — по построению).

Что хранится о жителе: только sha256(соль базы + device_id). Сам device_id (случайная строка
из localStorage браузера) не сохраняется и в ответы не попадает. Это защита от двойного нажатия,
а не от целенаправленной накрутки: очистка браузера даёт новое «устройство» — так и пишем в
known_limits, интерфейс говорит «Один голос с устройства», а не «один голос на человека».
"""

from __future__ import annotations

from collections import deque
import hashlib
import re
import secrets
import threading
import time

from .districts import DISTRICT_NAMES, bbox_intersects, district_of, geometry_bbox
from .objects import BadRequest, Conflict, NotFound, iso, utc_now, _dumps, _loads
from .stages import parse_bbox, parse_district, _single
from .validate import ValidationError, _Errors, clean_geometry, clean_text, is_valid_id


KINDS = ("square", "playground", "sports", "stop", "lighting")
STATUSES = ("proposal", "approved", "rejected", "withdrawn")
VISIBLE_STATUSES = ("proposal", "approved", "rejected")  # withdrawn («Удалить» в R05) не показывается
DECISIONS = {"approve": "approved", "reject": "rejected", "withdraw": "withdrawn"}
# Подписи по умолчанию, если акимат не ввёл название. Совпадают с ключами web/civic/i18n
# proposal.kind.* (R11); kk-формулировки проверяет владелец (KK_REVIEW).
DEFAULT_TITLES = {
    "square": ("Сквер", "Гүлзар"),
    "playground": ("Детская площадка", "Балалар алаңы"),
    "sports": ("Спортплощадка", "Спорт алаңы"),
    "stop": ("Остановка", "Аялдама"),
    "lighting": ("Освещение улицы", "Көше жарығы"),
}
DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}\Z")
MAX_TITLE = 200
MAX_REASON = 500
MAX_PROPOSALS = 500
VOTES_PER_MINUTE = 30  # с одного адреса; защита сервера от залипшей кнопки и скриптов


class VotingClosed(Conflict):
    pass


class RateLimiter:
    """Скользящее окно в памяти процесса. После перезапуска сбрасывается — это нормально."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 10000:  # не копить ключи бесконечно
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] <= self.window}
            return True


class ProposalRepository:
    def __init__(self, database, clock):
        self.db = database
        self.clock = clock
        self.limiter = RateLimiter(VOTES_PER_MINUTE)
        self._salt = None

    # --- служебное -----------------------------------------------------------------------

    def _vote_salt(self, conn) -> str:
        if self._salt is None:
            row = conn.execute("SELECT value FROM civic_v2_settings WHERE name = 'vote_salt'").fetchone()
            self._salt = row["value"]
        return self._salt

    def device_hash(self, conn, device_id):
        if not isinstance(device_id, str) or not DEVICE_RE.match(device_id):
            return None
        return hashlib.sha256((self._vote_salt(conn) + ":" + device_id).encode("ascii")).hexdigest()

    @staticmethod
    def _counts(conn, proposal_id):
        row = conn.execute(
            """SELECT COALESCE(SUM(value = 1), 0) AS up, COALESCE(SUM(value = -1), 0) AS down
               FROM civic_votes WHERE proposal_id = ?""", (proposal_id,)).fetchone()
        return int(row["up"]), int(row["down"])

    def _dto(self, conn, row, device_hash=None) -> dict:
        up, down = self._counts(conn, row["id"])
        my_vote = None
        if device_hash is not None:
            mine = conn.execute("SELECT value FROM civic_votes WHERE proposal_id = ? AND device_hash = ?",
                                (row["id"], device_hash)).fetchone()
            my_vote = mine["value"] if mine else None
        return {
            "id": row["id"], "kind": row["kind"], "geometry": _loads(row["geometry_json"]),
            "rotation_deg": row["rotation_deg"], "title_ru": row["title_ru"], "title_kk": row["title_kk"],
            "status": row["status"], "district": row["district"], "planned_year": row["planned_year"],
            "votes_up": up, "votes_down": down, "my_vote": my_vote,
            "voting_open": row["status"] == "proposal", "demo": bool(row["demo"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"], "decided_at": row["decided_at"],
        }

    @staticmethod
    def _row(conn, proposal_id):
        if not is_valid_id(proposal_id):
            raise BadRequest("Недопустимый ID предложения.", {"id": "Пустой или недопустимый ID."})
        row = conn.execute("SELECT * FROM civic_proposals WHERE id = ?", (proposal_id,)).fetchone()
        if row is None or row["status"] == "withdrawn":
            raise NotFound(proposal_id)
        return row

    # --- чтение --------------------------------------------------------------------------

    def list(self, query: dict, device_id=None) -> dict:
        bbox = parse_bbox(_single(query, "bbox"))
        district = parse_district(query)
        raw = [part for item in query.get("status", []) for part in item.split(",") if part]
        if any(value not in VISIBLE_STATUSES for value in raw):
            raise BadRequest("Недопустимый фильтр.", {"status": "Допустимо: " + ", ".join(VISIBLE_STATUSES)})
        statuses = sorted(set(raw)) or list(VISIBLE_STATUSES)
        with self.db.read() as conn:
            device = self.device_hash(conn, device_id) if device_id else None
            rows = conn.execute(
                f"""SELECT * FROM civic_proposals WHERE status IN ({','.join('?' * len(statuses))})
                    ORDER BY created_at DESC, id DESC LIMIT ?""", (*statuses, MAX_PROPOSALS + 1)).fetchall()
            items = []
            for row in rows[:MAX_PROPOSALS]:
                if district is not None and row["district"] != district:
                    continue
                if bbox is not None:
                    box = geometry_bbox(_loads(row["geometry_json"]))
                    if box is None or not bbox_intersects(box, bbox):
                        continue
                items.append(self._dto(conn, row, device))
        return {"items": items, "truncated": len(rows) > MAX_PROPOSALS}

    def get(self, proposal_id, device_id=None) -> dict:
        with self.db.read() as conn:
            row = self._row(conn, proposal_id)
            return {"item": self._dto(conn, row, self.device_hash(conn, device_id) if device_id else None)}

    def summary(self, since=None) -> dict:
        """Для «Картины дня» (R08): сколько предложений, новые с даты since, голоса."""
        with self.db.read() as conn:
            rows = conn.execute("SELECT * FROM civic_proposals WHERE status != 'withdrawn' "
                                "ORDER BY created_at DESC, id DESC").fetchall()
            items = [self._dto(conn, row) for row in rows]
        new = [i for i in items if since is None or i["created_at"] >= since]
        by_status = {status: sum(1 for i in items if i["status"] == status) for status in VISIBLE_STATUSES}
        top = sorted((i for i in items if i["status"] == "proposal"),
                     key=lambda i: (-(i["votes_up"] + i["votes_down"]), i["id"]))[:5]
        return {"since": since, "total": len(items), "new": len(new), "by_status": by_status,
                "votes_up": sum(i["votes_up"] for i in items), "votes_down": sum(i["votes_down"] for i in items),
                "top": [{k: i[k] for k in ("id", "kind", "title_ru", "title_kk", "district", "votes_up",
                                           "votes_down", "demo")} for i in top]}

    # --- запись --------------------------------------------------------------------------

    def create(self, actor, payload: dict) -> dict:
        errors = _Errors()
        allowed = {"kind", "geometry", "title_ru", "title_kk", "rotation_deg", "planned_year", "demo"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            errors.add(unknown[0] if isinstance(unknown[0], str) and len(unknown[0]) <= 64 else "body",
                       "Неизвестное поле.")
        kind = payload.get("kind")
        if kind not in KINDS:
            errors.add("kind", "Выберите объект: " + ", ".join(KINDS) + ".")
        geometry = clean_geometry(payload.get("geometry"), "geometry", errors)
        if geometry is None and "geometry" not in errors.fields:
            errors.add("geometry", "Укажите место на карте.")
        elif geometry is not None and kind in KINDS:
            # Освещение ставится вдоль участка улицы (форма от R12), остальное — точкой или площадью.
            if kind == "lighting" and geometry["type"] != "LineString":
                errors.add("geometry", "Освещение — линия вдоль участка улицы (LineString).")
            if kind != "lighting" and geometry["type"] == "LineString":
                errors.add("geometry", "Этот объект ставится точкой или площадью.")
        default_ru, default_kk = DEFAULT_TITLES.get(kind, (None, None))
        title_ru = clean_text(payload.get("title_ru"), "title_ru", errors, max_len=MAX_TITLE, nullable=True)
        title_kk = clean_text(payload.get("title_kk"), "title_kk", errors, max_len=MAX_TITLE, nullable=True)
        rotation = payload.get("rotation_deg", 0)
        if isinstance(rotation, bool) or not isinstance(rotation, (int, float)) or rotation != rotation \
                or not -360 <= rotation <= 360:
            errors.add("rotation_deg", "Число от −360 до 360.")
        year = payload.get("planned_year")
        if year is not None and (isinstance(year, bool) or not isinstance(year, int) or not 2025 <= year <= 2040):
            errors.add("planned_year", "Год 2025–2040 или пусто.")
        demo = payload.get("demo", False)
        if not isinstance(demo, bool):
            errors.add("demo", "true или false.")
        if errors.fields:
            raise ValidationError(errors.fields)
        now = iso(utc_now(self.clock))
        proposal_id = "p-" + secrets.token_hex(6)
        with self.db.write() as conn:
            conn.execute(
                """INSERT INTO civic_proposals(id, kind, geometry_json, rotation_deg, title_ru, title_kk, status,
                       district, planned_year, demo, created_at, updated_at, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, 'proposal', ?, ?, ?, ?, ?, ?)""",
                (proposal_id, kind, _dumps(geometry), float(rotation) % 360, title_ru or default_ru,
                 title_kk if title_kk else (default_kk if not title_ru else None), district_of(geometry), year,
                 int(demo), now, now, actor.user_id))
            conn.execute(
                """INSERT INTO civic_proposal_history(proposal_id, at, action, status, reason, actor_user_id,
                       actor_label) VALUES (?, ?, 'create', 'proposal', '', ?, ?)""",
                (proposal_id, now, actor.user_id, actor.label))
            return {"item": self._dto(conn, self._row(conn, proposal_id))}

    def vote(self, proposal_id, payload: dict, *, client_key: str) -> dict:
        """Голос жителя. value 1 | -1. Тот же голос ещё раз — без изменений (changed=false)."""
        errors = _Errors()
        value = payload.get("value")
        if isinstance(value, bool) or value not in (1, -1):
            errors.add("value", "1 (за) или -1 (против).")
        device_id = payload.get("device_id")
        if not isinstance(device_id, str) or not DEVICE_RE.match(device_id):
            errors.add("device_id", "Случайный идентификатор устройства: 16–128 символов [A-Za-z0-9_-].")
        unknown = sorted(set(payload) - {"value", "device_id"})
        if unknown:
            errors.add(unknown[0] if isinstance(unknown[0], str) and len(unknown[0]) <= 64 else "body",
                       "Неизвестное поле.")
        if errors.fields:
            raise ValidationError(errors.fields)
        if not self.limiter.allow(client_key):
            raise _VoteRateLimited()
        now = iso(utc_now(self.clock))
        with self.db.write() as conn:
            row = self._row(conn, proposal_id)
            if row["status"] != "proposal":
                raise VotingClosed("Голосование по этому предложению закрыто.", None, code="voting_closed")
            device = self.device_hash(conn, device_id)
            current = conn.execute("SELECT value FROM civic_votes WHERE proposal_id = ? AND device_hash = ?",
                                   (proposal_id, device)).fetchone()
            changed = current is None or current["value"] != value
            if current is None:
                conn.execute("""INSERT INTO civic_votes(proposal_id, device_hash, value, created_at, updated_at)
                                VALUES (?, ?, ?, ?, ?)""", (proposal_id, device, value, now, now))
            elif changed:
                conn.execute("UPDATE civic_votes SET value = ?, updated_at = ? WHERE proposal_id = ? AND device_hash = ?",
                             (value, now, proposal_id, device))
            item = self._dto(conn, row, device)
        return {"item": item, "changed": changed, "previous": current["value"] if current else None}

    def decide(self, actor, proposal_id, action, payload: dict) -> dict:
        """Одобрить / отклонить / снять (R05 «Удалить»). Только из статуса proposal."""
        if action not in DECISIONS:
            raise BadRequest("Недопустимое действие.")
        errors = _Errors()
        reason = clean_text(payload.get("reason"), "reason", errors, max_len=MAX_REASON)
        unknown = sorted(set(payload) - {"reason"})
        if unknown:
            errors.add(unknown[0] if isinstance(unknown[0], str) and len(unknown[0]) <= 64 else "body",
                       "Неизвестное поле.")
        if errors.fields:
            raise ValidationError(errors.fields)
        status = DECISIONS[action]
        now = iso(utc_now(self.clock))
        with self.db.write() as conn:
            row = self._row(conn, proposal_id)
            if row["status"] != "proposal":
                raise Conflict("Решение по предложению уже принято: обновите карточку.", None,
                               code="already_decided")
            conn.execute("""UPDATE civic_proposals SET status = ?, updated_at = ?, decided_at = ?, decided_by = ?,
                                decision_reason = ? WHERE id = ? AND status = 'proposal'""",
                         (status, now, now, actor.user_id, reason or "", proposal_id))
            conn.execute(
                """INSERT INTO civic_proposal_history(proposal_id, at, action, status, reason, actor_user_id,
                       actor_label) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (proposal_id, now, action, status, reason or "", actor.user_id, actor.label))
            if status == "withdrawn":
                return {"item": None, "withdrawn": proposal_id}
            return {"item": self._dto(conn, self._row(conn, proposal_id))}


class _VoteRateLimited(Exception):
    retry_after = 60


__all__ = ["DECISIONS", "DEFAULT_TITLES", "DISTRICT_NAMES", "KINDS", "ProposalRepository", "STATUSES",
           "VotingClosed"]
