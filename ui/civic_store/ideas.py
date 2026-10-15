"""Идеи жителей → голоса → проект (R06, раунд 14, волна 2 п. 7; схема экранов — R11 IA_WAVE2 §8).

Путь идеи:
    review   — житель прислал; видна только автору («Идею опубликуют после проверки») и сотруднику;
    voting   — сотрудник опубликовал; соседи поддерживают («Поддержать», одна поддержка с устройства);
    checking — акимат проверяет реализуемость (чек-лист сохранён): голосование закрыто, идея — во вкладке «Голосование»;
    project  — по всем 4 пунктам чек-листа «да», акимат сделал проект (civic_proposals, «По идее жителей · N голосов»);
    rejected — отказ с причиной (видна всем) и, по желанию, «Можно доработать: …»;
    hidden   — не опубликована при модерации (личные данные, грубые слова, реклама); автор видит, что идея не прошла.

Честно (POLISH_WAVE_2 п. 7): поддержка — это опрос для выбора концепции, решение принимает акимат. Голос не
юридически значим, «один голос с устройства» — защита от двойного нажатия, а не от накрутки (R15 S08): поэтому
ещё лимиты по адресу клиента, как у голосов за проекты.

Что хранится о жителе: только sha256(соль базы + device_id) — для «Вы поддержали», «моя идея» и лимитов.
Имени, телефона и адреса нет; текст идеи проверяет сотрудник до публикации.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time

from .districts import DISTRICT_NAMES, district_of
from .districts import _load as _geofence
from .objects import BadRequest, Conflict, NotFound, iso, utc_now, _dumps, _loads
from .proposals import DEVICE_RE, KINDS, MAX_PROPOSAL_POSITIONS, RateLimiter, _VoteRateLimited, _positions
from .stages import parse_district
from .validate import ValidationError, _Errors, clean_geometry, clean_text, is_valid_id


STATUSES = ("review", "voting", "checking", "project", "rejected", "hidden")
PUBLIC_STATUSES = ("voting", "checking", "project", "rejected")
ACTIONS = ("publish", "hide", "check", "project", "reject")
CHECK_KEYS = ("land", "networks", "access", "maintenance")  # чек-лист R11: idea.check.*
CHECK_ANSWERS = ("yes", "no", "unknown")
LANGS = ("ru", "kk")
TITLE_MIN, TITLE_MAX = 3, 60       # IA_WAVE2 §8: название ≤ 60
DESCRIPTION_MAX = 300              # описание ≤ 300
REASON_MAX = 300
MAX_LIST = 300
# Город с запасом — если в сборке нет границы районов (geofence.json), проверяем хотя бы прямоугольник.
CITY_BOX = (70.9, 50.9, 71.9, 51.4)
# Новые идеи: с одного адреса не больше 5 в час; на проверке у одного устройства — не больше 3; очередь проверки
# на весь город — не больше 300 (иначе скрипт завалит сотрудника, R15).
IDEAS_PER_HOUR = 5
REVIEW_PER_DEVICE = 3
REVIEW_QUEUE_MAX = 300
# R15-S32: очередь полна — новые идеи принимаются только с адресов, которые за сутки идей не подавали (один скрипт
# с десятков адресов не закрывает приём для всего города), и не больше этого потолка.
REVIEW_QUEUE_HARD_MAX = 2 * REVIEW_QUEUE_MAX
CREATOR_MEMORY = 24 * 3600.0
# R15-S31: идею увидят все — телефон, почта и ИИН в ней не нужны (шаблоны как в ui/civic_feedback/text.py).
_PERSONAL = (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE), re.compile(r"(?<!\d)\d{12}(?!\d)"),
             re.compile(r"(?<![\w+])(?:\+?7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"))
PERSONAL_HINT = "Не пишите телефон, e-mail или ИИН: идею увидят все жители."
SUPPORTS_PER_MINUTE = 30
SUPPORTS_PER_IDEA_PER_DAY = 20      # как VOTES_PER_TARGET_PER_DAY у проектов (R15 S08)
# Раунд 15 (VISUAL_BRIEF §3): тема идеи — для линейной иллюстрации вместо серой лампочки и для ленты/двора R16.
# Объект из каталога 3D — сам вид; без объекта — по словам названия и описания (ru и kk), иначе «другое».
# Это только картинка: тема не меняет ни статус, ни решение акимата.
TOPICS = ("square", "playground", "sports", "stop", "lighting", "benches", "greening", "other")
_TOPIC_WORDS = (  # порядок важен: «спортплощадка» — спорт, а не детская площадка
    ("stop", ("остановк", "павильон", "аялдама")),
    ("lighting", ("освещ", "фонар", "темно", "жарық", "шам", "қараңғы")),
    ("sports", ("спорт", "футбол", "баскетбол", "тренаж", "воркаут", "волейбол")),
    ("playground", ("детск", "площадк", "качел", "балалар", "әткеншек")),
    ("benches", ("скамейк", "лавочк", "беседк", "орындық", "отыратын")),
    ("greening", ("дерев", "озелен", "газон", "клумб", "сажен", "ағаш", "көгал", "гүл")),
    ("square", ("сквер", "парк", "аллея", "фонтан", "гүлзар", "саябақ", "субұрқақ")),
)


def topic_of(texts: dict, obj) -> str:
    """Тема идеи: вид объекта 3D, иначе тема по словам названия, затем описания («Фонтан во дворе… детям» — сквер)."""
    if isinstance(obj, dict) and obj.get("kind") in TOPICS:
        return obj["kind"]
    for prefix in ("title_", "description_"):
        words = " ".join(str(v) for k, v in (texts or {}).items()
                         if isinstance(v, str) and k.startswith(prefix)).casefold()
        for topic, stems in _TOPIC_WORDS:
            if any(stem in words for stem in stems):
                return topic
    return "other"


class IdeaClosed(Conflict):
    pass


class IdeaRepository:
    def __init__(self, database, clock, proposals):
        self.db = database
        self.clock = clock
        self.proposals = proposals  # ProposalRepository: та же соль устройства и создание проекта из идеи
        self.create_limiter = RateLimiter(IDEAS_PER_HOUR, window=3600.0)
        self.support_limiter = RateLimiter(SUPPORTS_PER_MINUTE)
        self.target_limiter = RateLimiter(SUPPORTS_PER_IDEA_PER_DAY, window=24 * 3600.0)
        self._creators: dict[str, float] = {}   # R15-S32: адрес → когда подал последнюю идею (память процесса)
        self._creators_lock = threading.Lock()

    def _recent_creator(self, client_key: str) -> bool:
        with self._creators_lock:
            at = self._creators.get(client_key)
            return at is not None and time.monotonic() - at < CREATOR_MEMORY

    def _remember_creator(self, client_key: str) -> None:
        with self._creators_lock:
            now = time.monotonic()
            if len(self._creators) > 10000:
                self._creators = {k: v for k, v in self._creators.items() if now - v < CREATOR_MEMORY}
            self._creators[client_key] = now

    # --- служебное -----------------------------------------------------------------------

    def _device(self, conn, device_id):
        return self.proposals.device_hash(conn, device_id) if device_id else None

    @staticmethod
    def _votes(conn, idea_id):
        return int(conn.execute("SELECT COUNT(*) FROM civic_idea_votes WHERE idea_id = ?", (idea_id,)).fetchone()[0])

    @staticmethod
    def _row(conn, idea_id):
        if not is_valid_id(idea_id):
            raise BadRequest("Недопустимый ID идеи.", {"id": "Пустой или недопустимый ID."})
        row = conn.execute("SELECT * FROM civic_ideas WHERE id = ?", (idea_id,)).fetchone()
        if row is None:
            raise NotFound(idea_id)
        return row

    def _dto(self, conn, row, device=None, *, staff=False) -> dict:
        texts = _loads(row["texts_json"]) or {}
        lang = row["lang"]
        other = "kk" if lang == "ru" else "ru"
        votes = self._votes(conn, row["id"])
        project = None
        if row["project_id"]:
            p = conn.execute("SELECT id, kind, status, title_ru, title_kk, planned_year FROM civic_proposals WHERE id = ?",
                             (row["project_id"],)).fetchone()
            if p is not None and p["status"] != "withdrawn":
                # planned_year — «срок» в карточке идеи (эталон 13 окт: три цифры «поддержали · срок · …»)
                project = {"id": p["id"], "kind": p["kind"], "status": p["status"], "title_ru": p["title_ru"],
                           "title_kk": p["title_kk"], "planned_year": p["planned_year"]}
        mine = device is not None and row["author_hash"] == device
        supported = None
        if device is not None:
            supported = conn.execute("SELECT 1 FROM civic_idea_votes WHERE idea_id = ? AND device_hash = ?",
                                     (row["id"], device)).fetchone() is not None
        decided = row["status"] in ("project", "rejected")
        public_reason = row["status"] == "rejected" or staff  # причина скрытия (hidden) — служебная
        reason = row["reason"] if public_reason else ""
        can_improve = row["can_improve"] if public_reason else ""
        item = {
            "id": row["id"], "status": row["status"], "lang": lang,
            # Текст жителя — как написан; перевод есть только у демо-идей (оба языка). title — для R05 (метка, карточка).
            "title": texts.get("title_" + lang) or texts.get("title_" + other) or "",
            "title_ru": texts.get("title_ru") or texts.get("title_" + lang) or "",
            "title_kk": texts.get("title_kk") or texts.get("title_" + lang) or "",
            "description": texts.get("description_" + lang) or texts.get("description_" + other) or "",
            "description_ru": texts.get("description_ru") or texts.get("description_" + lang) or "",
            "description_kk": texts.get("description_kk") or texts.get("description_" + lang) or "",
            "geometry": _loads(row["geometry_json"]), "district": row["district"],
            "object": _loads(row["object_json"]) if row["object_json"] else None,
            "topic": topic_of(texts, _loads(row["object_json"]) if row["object_json"] else None),
            "votes": votes, "votes_up": votes,  # votes_up — имя поля у R05 (метка «Идея · 47»)
            "my_support": supported, "mine": mine, "voting_open": row["status"] == "voting",
            # Чек-лист реализуемости публичен после решения (IA_WAVE2 §8: «чек-лист после проверки»).
            "check": _loads(row["check_json"]) if row["check_json"] and (decided or staff) else None,
            "reason": reason, "can_improve": can_improve,
            # Причина и «Можно доработать» — на языке сотрудника; у демо-идей — оба языка (texts_json).
            "reason_ru": (texts.get("reason_ru") or reason) if reason else "",
            "reason_kk": (texts.get("reason_kk") or reason) if reason else "",
            "can_improve_ru": (texts.get("can_improve_ru") or can_improve) if can_improve else "",
            "can_improve_kk": (texts.get("can_improve_kk") or can_improve) if can_improve else "",
            "project": project, "votes_at_decision": row["votes_at_decision"],
            # Раунд 15: идея стала инициативой жителей R16 («Сделайте вместе — поддержим инвентарём»).
            "initiative": {"id": row["initiative_id"], "at": row["initiative_at"]} if row["initiative_id"] else None,
            "demo": bool(row["demo"]), "created_at": row["created_at"], "published_at": row["published_at"],
            "decided_at": row["decided_at"],
        }
        return item  # причина скрытия (hidden) — служебная: автору — только что идея не прошла проверку

    # --- чтение --------------------------------------------------------------------------

    def list(self, query: dict, device_id=None, *, staff=False) -> dict:
        """Публично: voting | project | rejected (+ свои идеи на проверке и скрытые — только автору).
        Сотруднику (staff=True): все статусы, по умолчанию review и voting («Идеи на проверке»)."""
        district = parse_district(query)
        raw = [part for item in query.get("status", []) for part in item.split(",") if part]
        allowed = STATUSES if staff else PUBLIC_STATUSES
        if any(value not in allowed for value in raw):
            raise BadRequest("Недопустимый фильтр.", {"status": "Допустимо: " + ", ".join(allowed)})
        statuses = sorted(set(raw)) or (["review", "voting", "checking"] if staff else list(PUBLIC_STATUSES))
        with self.db.read() as conn:
            device = self._device(conn, device_id)
            rows = conn.execute(
                f"""SELECT * FROM civic_ideas WHERE (status IN ({','.join('?' * len(statuses))})
                           AND (? OR published_at IS NOT NULL))
                       OR (? IS NOT NULL AND author_hash = ? AND status IN ('review', 'hidden', 'rejected'))
                    ORDER BY created_at DESC, id DESC LIMIT ?""",
                (*statuses, int(staff), device, device, MAX_LIST + 1)).fetchall()
            items = []
            for row in rows[:MAX_LIST]:
                if district is not None and row["district"] != district:
                    continue
                items.append(self._dto(conn, row, device, staff=staff))
        # Порядок (R11 SCHEMES §2.1): свои на проверке сверху, затем больше голосов — выше, при равенстве — новее.
        rank = {"review": 0, "hidden": 0, "voting": 1, "checking": 1, "project": 2, "rejected": 3}
        items.sort(key=lambda i: i["created_at"], reverse=True)
        items.sort(key=lambda i: (rank[i["status"]], -i["votes"]))
        counts = {s: sum(1 for i in items if i["status"] == s) for s in statuses}
        return {"items": items, "counts": counts, "truncated": len(rows) > MAX_LIST}

    def get(self, idea_id, device_id=None, *, staff=False) -> dict:
        with self.db.read() as conn:
            row = self._row(conn, idea_id)
            device = self._device(conn, device_id)
            if not staff and (row["status"] not in PUBLIC_STATUSES or row["published_at"] is None) \
                    and row["author_hash"] != device:
                raise NotFound(idea_id)  # чужая идея на проверке не видна
            return {"item": self._dto(conn, row, device, staff=staff)}

    def summary(self) -> dict:
        """Для «Картины дня» R08 (по желанию): сколько идей ждут проверки и топ по голосам."""
        with self.db.read() as conn:
            counts = {s: 0 for s in STATUSES}
            for row in conn.execute("SELECT status, COUNT(*) AS n FROM civic_ideas GROUP BY status"):
                counts[row["status"]] = int(row["n"])
            top = conn.execute("""SELECT i.*, (SELECT COUNT(*) FROM civic_idea_votes v WHERE v.idea_id = i.id) AS n
                                  FROM civic_ideas i WHERE status = 'voting' ORDER BY n DESC, created_at LIMIT 3""").fetchall()
            return {"counts": counts, "top": [self._dto(conn, row) for row in top]}

    # --- запись: житель ------------------------------------------------------------------

    @staticmethod
    def _clean_point(value, path, errors):
        geometry = clean_geometry(value, path, errors)
        if geometry is None:
            if path not in errors.fields:
                errors.add(path, "Укажите место на карте.")
            return None
        if geometry["type"] != "Point":
            errors.add(path, "Место идеи — точка на карте.")
            return None
        if not _inside_city(geometry):
            errors.add(path, "Место должно быть внутри границы Астаны.")
            return None
        return geometry

    @staticmethod
    def _clean_object(value, errors):
        """Объект из каталога 3D R05 (по желанию): {kind} или эскиз {kind, geometry, rotation_deg}."""
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) - {"kind", "geometry", "rotation_deg", "near_street",
                                                         "near_street_kk", "target"}:
            errors.add("object", "Объект: {kind, geometry?, rotation_deg?} или null.")
            return None
        kind = value.get("kind")
        if kind not in KINDS:
            errors.add("object.kind", "Выберите объект: " + ", ".join(KINDS) + ".")
            return None
        out = {"kind": kind}
        if value.get("geometry") is not None:
            geometry = clean_geometry(value["geometry"], "object.geometry", errors)
            if geometry is None:
                return None
            if geometry["type"] == "LineString" and kind != "lighting":
                errors.add("object.geometry", "Этот объект ставится точкой или площадью.")
                return None
            points = _positions(geometry)
            if len(points) > MAX_PROPOSAL_POSITIONS or not _inside_city(geometry):
                errors.add("object.geometry", "Эскиз — внутри границы Астаны, не более 500 точек.")
                return None
            out["geometry"] = geometry
        rotation = value.get("rotation_deg", 0)
        if isinstance(rotation, bool) or not isinstance(rotation, (int, float)) or rotation != rotation \
                or not -360 <= rotation <= 360:
            errors.add("object.rotation_deg", "Число от −360 до 360.")
            return None
        if rotation:
            out["rotation_deg"] = float(rotation) % 360
        return out

    def create(self, payload: dict, *, client_key: str) -> dict:
        """Новая идея жителя: {title, description?, geometry: Point, object?, device_id, lang?} → status review."""
        errors = _Errors()
        unknown = sorted(set(payload) - {"title", "description", "geometry", "object", "device_id", "lang"})
        if unknown:
            errors.add(unknown[0] if isinstance(unknown[0], str) and len(unknown[0]) <= 64 else "body",
                       "Неизвестное поле.")
        lang = payload.get("lang", "ru")
        if lang not in LANGS:
            errors.add("lang", "ru или kk.")
        title = clean_text(payload.get("title"), "title", errors, max_len=TITLE_MAX, required=True)
        if title is not None and len(title) < TITLE_MIN and "title" not in errors.fields:
            errors.add("title", f"Название — от {TITLE_MIN} символов.")
        description = clean_text(payload.get("description"), "description", errors, max_len=DESCRIPTION_MAX,
                                 multiline=True)
        for name, value in (("title", title), ("description", description)):
            if isinstance(value, str) and name not in errors.fields and any(rx.search(value) for rx in _PERSONAL):
                errors.add(name, PERSONAL_HINT)
        geometry = self._clean_point(payload.get("geometry"), "geometry", errors)
        obj = self._clean_object(payload.get("object"), errors)
        device_id = payload.get("device_id")
        if not isinstance(device_id, str) or not DEVICE_RE.match(device_id):
            errors.add("device_id", "Случайный идентификатор устройства: 8–128 символов [A-Za-z0-9._:-].")
        if errors.fields:
            raise ValidationError(errors.fields)
        now = iso(utc_now(self.clock))
        texts = {"title_" + lang: title}
        if description:
            texts["description_" + lang] = description
        with self.db.write() as conn:
            device = self._device(conn, device_id)
            pending = conn.execute("SELECT COUNT(*) FROM civic_ideas WHERE status = 'review' AND author_hash = ?",
                                   (device,)).fetchone()[0]
            if pending >= REVIEW_PER_DEVICE:
                raise Conflict(f"У вас уже {REVIEW_PER_DEVICE} идеи на проверке. Дождитесь ответа.", None,
                               code="limit")
            queue = conn.execute("SELECT COUNT(*) FROM civic_ideas WHERE status = 'review'").fetchone()[0]
            if queue >= REVIEW_QUEUE_HARD_MAX or (queue >= REVIEW_QUEUE_MAX and self._recent_creator(client_key)):
                raise Conflict("Сейчас на проверке много идей. Попробуйте завтра.", None, code="limit")
            # Лимит по адресу — последним: отказ по другим причинам не тратит попытку жителя.
            if not self.create_limiter.allow(client_key):
                raise _VoteRateLimited("С этого устройства или сети уже много новых идей. Попробуйте через час.",
                                       self.create_limiter.retry_after(client_key))
            self._remember_creator(client_key)
            idea_id = "i-" + secrets.token_hex(6)
            conn.execute(
                """INSERT INTO civic_ideas(id, lang, texts_json, geometry_json, district, object_json, status,
                       author_hash, demo, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'review', ?, 0, ?, ?)""",
                (idea_id, lang, _dumps(texts), _dumps(geometry), district_of(geometry),
                 _dumps(obj) if obj else None, device, now, now))
            self._history(conn, idea_id, now, "create", "review", "", None, "resident")
            return {"item": self._dto(conn, self._row(conn, idea_id), device)}

    def support(self, idea_id, payload: dict, *, client_key: str) -> dict:
        """«Поддержать» / снять поддержку: {device_id, on: true|false}. Повтор того же — без изменений."""
        errors = _Errors()
        device_id = payload.get("device_id")
        if not isinstance(device_id, str) or not DEVICE_RE.match(device_id):
            errors.add("device_id", "Случайный идентификатор устройства: 8–128 символов [A-Za-z0-9._:-].")
        on = payload.get("on", True)
        if not isinstance(on, bool):
            errors.add("on", "true (поддержать) или false (снять поддержку).")
        unknown = sorted(set(payload) - {"device_id", "on"})
        if unknown:
            errors.add(unknown[0] if isinstance(unknown[0], str) and len(unknown[0]) <= 64 else "body",
                       "Неизвестное поле.")
        if errors.fields:
            raise ValidationError(errors.fields)
        if not self.support_limiter.allow(client_key):
            raise _VoteRateLimited()
        now = iso(utc_now(self.clock))
        with self.db.write() as conn:
            row = self._row(conn, idea_id)
            if row["status"] != "voting":
                raise IdeaClosed("Голосование по этой идее закрыто.", None, code="voting_closed")
            device = self._device(conn, device_id)
            had = conn.execute("SELECT 1 FROM civic_idea_votes WHERE idea_id = ? AND device_hash = ?",
                               (idea_id, device)).fetchone() is not None
            if on and not had:
                key = f"{client_key}|idea|{idea_id}"
                if not self.target_limiter.allow(key):
                    raise _VoteRateLimited(
                        "С этого устройства или сети уже много голосов за эту идею. Попробуйте завтра.",
                        self.target_limiter.retry_after(key))
                conn.execute("INSERT INTO civic_idea_votes(idea_id, device_hash, created_at) VALUES (?, ?, ?)",
                             (idea_id, device, now))
            elif not on and had:
                conn.execute("DELETE FROM civic_idea_votes WHERE idea_id = ? AND device_hash = ?", (idea_id, device))
            return {"item": self._dto(conn, row, device), "changed": on != had}

    # --- запись: сотрудник ---------------------------------------------------------------

    @staticmethod
    def _clean_check(value, errors):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) - set(CHECK_KEYS):
            errors.add("check", "Чек-лист: " + ", ".join(CHECK_KEYS) + " — yes | no | unknown.")
            return None
        out = {}
        for key in CHECK_KEYS:
            answer = value.get(key, "unknown")
            if answer not in CHECK_ANSWERS:
                errors.add("check." + key, "yes, no или unknown.")
                return None
            out[key] = answer
        return out

    def decide(self, actor, idea_id, payload: dict) -> dict:
        """Действие сотрудника: {action, …}.
            publish                        review → voting (идея видна всем)
            hide    {reason}               review | voting | checking → hidden (служебная причина)
            check   {check}                чек-лист реализуемости: voting | checking → checking (голосование закрыто)
            project {check?, kind?, geometry?, rotation_deg?, near_street?, near_street_kk?, planned_year?}
                                           voting | checking → project, только при 4 «да»: проект «По идее жителей»
            reject  {reason, can_improve?, check?}   review | voting | checking → rejected (причина видна всем)
        """
        errors = _Errors()
        action = payload.get("action")
        if action not in ACTIONS:
            raise ValidationError({"action": "Допустимо: " + ", ".join(ACTIONS) + "."})
        allowed = {"action"} | {
            "publish": set(), "hide": {"reason"}, "check": {"check"},
            "project": {"check", "kind", "geometry", "rotation_deg", "near_street", "near_street_kk", "planned_year"},
            "reject": {"reason", "can_improve", "check"}}[action]
        unknown = sorted(set(payload) - allowed)
        if unknown:
            errors.add(unknown[0] if isinstance(unknown[0], str) and len(unknown[0]) <= 64 else "body",
                       "Неизвестное поле.")
        check = self._clean_check(payload.get("check"), errors)
        reason = clean_text(payload.get("reason"), "reason", errors, max_len=REASON_MAX,
                            required=action in ("reject", "hide"), multiline=True)
        can_improve = clean_text(payload.get("can_improve"), "can_improve", errors, max_len=REASON_MAX,
                                 multiline=True)
        if action == "check" and check is None and "check" not in errors.fields:
            errors.add("check", "Заполните чек-лист.")
        if errors.fields:
            raise ValidationError(errors.fields)
        now = iso(utc_now(self.clock))
        with self.db.write() as conn:
            row = self._row(conn, idea_id)
            status = row["status"]
            # R15: скрыть можно и после решения (личные данные заметили позже, просьба автора).
            sources = {"publish": ("review",), "hide": ("review", "voting", "checking", "rejected", "project"),
                       "check": ("voting", "checking"), "project": ("voting", "checking"),
                       "reject": ("review", "voting", "checking")}[action]
            if status not in sources:
                raise Conflict("Решение по идее уже принято: обновите карточку.", None, code="already_decided")
            check_json = _dumps(check) if check is not None else row["check_json"]
            if action == "publish":
                conn.execute("""UPDATE civic_ideas SET status = 'voting', published_at = ?, updated_at = ?
                                WHERE id = ? AND status = 'review'""", (now, now, idea_id))
                self._history(conn, idea_id, now, "publish", "voting", "", actor.user_id, actor.label)
            elif action == "hide":
                conn.execute("""UPDATE civic_ideas SET status = 'hidden', reason = ?, updated_at = ?, decided_at = ?,
                                    decided_by = ? WHERE id = ?""", (reason, now, now, actor.user_id, idea_id))
                self._history(conn, idea_id, now, "hide", "hidden", reason, actor.user_id, actor.label)
            elif action == "check":
                # Акимат начал проверку — голосование закрыто, число голосов больше не меняется (R11 SCHEMES §2.1).
                conn.execute("UPDATE civic_ideas SET status = 'checking', check_json = ?, updated_at = ? WHERE id = ?",
                             (check_json, now, idea_id))
                self._history(conn, idea_id, now, "check", "checking", "", actor.user_id, actor.label)
            elif action == "reject":
                conn.execute("""UPDATE civic_ideas SET status = 'rejected', reason = ?, can_improve = ?,
                                    check_json = ?, votes_at_decision = ?, updated_at = ?, decided_at = ?,
                                    decided_by = ? WHERE id = ?""",
                             (reason, can_improve or "", check_json, self._votes(conn, idea_id), now, now,
                              actor.user_id, idea_id))
                self._history(conn, idea_id, now, "reject", "rejected", reason, actor.user_id, actor.label)
            else:
                return self._to_project(conn, actor, row, payload, check_json, now)
            return {"item": self._dto(conn, self._row(conn, idea_id), staff=True)}

    def _to_project(self, conn, actor, row, payload, check_json, now) -> dict:
        """Проект из идеи: вид и место — из запроса сотрудника, иначе из эскиза жителя (объект R05), иначе точка идеи.
        Название проекта — «вид + улица рядом» на обоих языках (как у демо-проектов); текст жителя остаётся в идее."""
        check = _loads(check_json) if check_json else None
        if not check or any(check.get(k) != "yes" for k in CHECK_KEYS):
            # R11 SCHEMES §2.3: «Сделать проектом» — только когда по всем четырём пунктам «да».
            raise ValidationError({"check": "Проект — только когда по всем четырём пунктам чек-листа «да»."})
        obj = _loads(row["object_json"]) if row["object_json"] else {}
        kind = payload.get("kind") or obj.get("kind")
        geometry = payload.get("geometry") or obj.get("geometry") or _loads(row["geometry_json"])
        rotation = payload.get("rotation_deg", obj.get("rotation_deg", 0))
        if not isinstance(kind, str):
            raise ValidationError({"kind": "Выберите объект из каталога: " + ", ".join(KINDS) + "."})
        if kind == "lighting" and (not isinstance(geometry, dict) or geometry.get("type") != "LineString"):
            raise ValidationError({"geometry": "Освещение — линия вдоль участка улицы: поставьте его в 3D-каталоге."})
        body = {"kind": kind, "geometry": geometry, "rotation_deg": rotation, "demo": bool(row["demo"])}
        for key in ("near_street", "near_street_kk", "planned_year"):
            if payload.get(key) is not None:
                body[key] = payload[key]
        votes = self._votes(conn, row["id"])
        project = self.proposals.create_in(conn, actor, body, now, idea_id=row["id"])
        conn.execute("""UPDATE civic_ideas SET status = 'project', project_id = ?, check_json = ?,
                            votes_at_decision = ?, updated_at = ?, decided_at = ?, decided_by = ? WHERE id = ?""",
                     (project["id"], check_json, votes, now, now, actor.user_id, row["id"]))
        self._history(conn, row["id"], now, "project", "project", project["id"], actor.user_id, actor.label)
        # Проект перечитываем после записи голосов в идею: в нём «По идее жителей · N голосов».
        project = self.proposals._dto(conn, self.proposals._row(conn, project["id"]))
        return {"item": self._dto(conn, self._row(conn, row["id"]), staff=True), "proposal": project}

    @staticmethod
    def _history(conn, idea_id, at, action, status, reason, user_id, label):
        conn.execute("""INSERT INTO civic_idea_history(idea_id, at, action, status, reason, actor_user_id, actor_label)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""", (idea_id, at, action, status, reason or "", user_id, label))

    # --- демо ----------------------------------------------------------------------------

    def seed_demo(self, idea: dict, *, votes: int, project_id=None) -> dict:
        """Демо-идея (demo=true, тексты ru+kk) с демо-поддержками от случайных устройств. Без лимитов HTTP."""
        now = iso(utc_now(self.clock))
        idea_id = "i-demo-" + secrets.token_hex(4)
        status = idea["status"]
        with self.db.write() as conn:
            conn.execute(
                """INSERT INTO civic_ideas(id, lang, texts_json, geometry_json, district, object_json, status,
                       check_json, reason, can_improve, project_id, votes_at_decision, demo, created_at, updated_at,
                       published_at, decided_at)
                   VALUES (?, 'ru', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
                (idea_id, _dumps(idea["texts"]), _dumps(idea["geometry"]), district_of(idea["geometry"]),
                 _dumps(idea["object"]) if idea.get("object") else None, status,
                 _dumps(idea["check"]) if idea.get("check") else None, idea.get("reason", ""),
                 idea.get("can_improve", ""), project_id, votes if status in ("project", "rejected") else None,
                 now, now, now if status != "review" else None, now if status in ("project", "rejected") else None))
            for _ in range(votes if status != "review" else 0):
                device = hashlib.sha256(secrets.token_bytes(32)).hexdigest()  # случайно: демо-голос не перевернуть
                conn.execute("INSERT INTO civic_idea_votes(idea_id, device_hash, created_at) VALUES (?, ?, ?)",
                             (idea_id, device, now))
            if project_id:
                conn.execute("UPDATE civic_proposals SET idea_id = ? WHERE id = ? AND idea_id IS NULL",
                             (idea_id, project_id))
            self._history(conn, idea_id, now, "create", status, "Демо-данные (синтетика)", None, "seed-r14-demo")
        return {"id": idea_id, "status": status, "votes": votes}


def project_withdrawn(conn, proposal_id, now, actor) -> None:
    """Проект из идеи сняли («Удалить» в 3D R05): идея снова на голосовании, история сохраняется.
    Вызывает ProposalRepository.decide в той же транзакции."""
    row = conn.execute("SELECT id FROM civic_ideas WHERE project_id = ? AND status = 'project'",
                       (proposal_id,)).fetchone()
    if row is not None:
        conn.execute("UPDATE civic_ideas SET status = 'voting', updated_at = ? WHERE id = ?", (now, row["id"]))
        IdeaRepository._history(conn, row["id"], now, "reopen", "voting", "Проект снят", actor.user_id, actor.label)


def project_restored(conn, proposal_id, now, actor) -> None:
    """«Отменить» после «Удалить»: проект вернулся — идея снова «Стала проектом»."""
    row = conn.execute("SELECT id FROM civic_ideas WHERE project_id = ? AND status = 'voting'",
                       (proposal_id,)).fetchone()
    if row is not None:
        conn.execute("UPDATE civic_ideas SET status = 'project', updated_at = ? WHERE id = ?", (now, row["id"]))
        IdeaRepository._history(conn, row["id"], now, "project", "project", proposal_id, actor.user_id, actor.label)


def _inside_city(geometry) -> bool:
    """Все точки — в районах Астаны (geofence.json сборки); нет файла границы — прямоугольник города."""
    points = _positions(geometry)
    if _geofence():
        return all(district_of({"type": "Point", "coordinates": p}) is not None for p in points)
    return all(CITY_BOX[0] <= p[0] <= CITY_BOX[2] and CITY_BOX[1] <= p[1] <= CITY_BOX[3] for p in points)


__all__ = ["ACTIONS", "CHECK_ANSWERS", "CHECK_KEYS", "DISTRICT_NAMES", "IdeaClosed", "IdeaRepository",
           "PUBLIC_STATUSES", "STATUSES", "TOPICS", "topic_of"]
