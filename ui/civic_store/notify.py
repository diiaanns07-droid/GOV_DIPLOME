"""Лента «Что нового для меня» (R06, раунд 15; CONTRACT §5.8, §7): одна лента жителя вместо пяти мест.

Что в ней:
  - события соседей — их функцией updates(device, since) (вызов в процессе, только чтение): двор и инициативы (R16),
    кризис в районе или дворе жителя (R17), встречи и поручения (R13), ответы и статусы его обращений (R09);
    модуля нет в сборке — блок пропускается (sources[роль] = "absent"), ошибка соседа ленту не роняет ("error");
  - свои события R06 — из своих таблиц: идея жителя опубликована / акимат проверяет / стала проектом / отклонена /
    «сделайте вместе» (инициатива R16); проект, за который житель голосовал, одобрен или отклонён; работы и
    отключения рядом с его двором (R16 «Я живу здесь») и в районе, на который он подписан в «Рядом» (R08).
В чужие таблицы ничего не пишем: прочитанное хранится у себя (civic_notify_reads, хэш устройства с солью базы).

Житель — устройство: заголовок X-Birge-Device (тот же id, что у R09, R08, R13, R17: localStorage "birge.device").
Идеи и голоса R06 исторически привязаны к другому id браузера (localStorage "birge.device_id") — клиент шлёт его
заголовком X-Birge-Ideas-Device; без него свои события R06 ищутся по основному id.

Приватность: только события этого устройства; из событий соседей берутся лишь поля §5.8 (id, at, module, kind,
target, title_ru, title_kk, link, demo); ссылка — только внутренний адрес приложения (#раздел/…), иначе её нет;
id устройств, тексты чужих жалоб и время визитов наружу не уходят.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import inspect
import logging
import re
import threading
import time

from .objects import BadRequest, iso, utc_now, _dumps, _loads
from .validate import ValidationError


LOGGER = logging.getLogger("ui.civic_store.notify")
DEVICE_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}\Z")      # как V2_DEVICE_ID шлюза R01
LINK_RE = re.compile(r"^#[a-z][a-z0-9-]{0,30}(?:[/=][A-Za-z0-9._:=&/+-]{1,200})?\Z")
KIND_RE = re.compile(r"^[a-z]{2,20}\.[a-z_]{2,30}\Z")
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}\Z")      # id соседа; в ленте — event_id()
# id события в ленте — по правилу CIVIC_ID шлюза R01 (POST notifications/read проверяет им каждый id): до 96 знаков.
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
# путь адреса оболочки (IA_ROUND15 §7.3, PATH_RE R01) для частей ссылки «#раздел/путь»
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
KINDS = ("yard.news", "initiative.update", "incident.update", "meeting.result", "complaint.update", "work.near",
         "idea.update", "project.update")
# Соседи: роль, модули-кандидаты (первый найденный), функция. Имена — из INTEGRATION соседей раунда 15.
NEIGHBORS = (
    ("R09", ("ui.civic_feedback.v2.integration",), "updates"),
    ("R16", ("ui.civic_together",), "updates"),
    ("R17", ("ui.civic_agencies",), "updates"),
    ("R13", ("ui.civic_meetings",), "updates"),
)
MAX_ITEMS = 60               # лента — последние 60 событий (новые сверху)
MAX_PER_MODULE = 40
TITLE_MAX = 240
READ_IDS_MAX = 300
CACHE_SECONDS = 5.0          # колокольчик опрашивает раз в минуту, вкладок может быть несколько
CACHE_DEVICES = 2000
WORK_NEAR_DAYS = 30          # работа у двора попадает в ленту, если её добавили или изменили за последние 30 дней
DISTRICT_DAYS = 7            # по подписке на район — только свежее за неделю (район большой: иначе лента — поток работ)
DISTRICT_MAX = 5             # и не больше 5 на район (самые свежие); у двора — все ближе YARD_RADIUS_M
# «рядом с двором» — как вкладка «Работы» двора R16 (ui.civic_together.neighbors.WORK_RADIUS_M = 800): уведомление
# «Рядом с вашим двором» ведёт в эту вкладку (#yard/<двор>) — там должна быть эта работа. Меряем от точки двора.
YARD_RADIUS_M = 800


class _ModuleAbsent(Exception):
    pass


def _parse_time(value):
    """ISO 8601 → aware datetime (UTC) или None. Без пояса — время Астаны (UTC+5), как у остальных модулей."""
    if not isinstance(value, str) or not 10 <= len(value) <= 40:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "+"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone(timedelta(hours=5)))
    if not 2000 <= moment.year <= 2100:
        return None
    return moment.astimezone(timezone.utc)


def _text(value, limit=TITLE_MAX):
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:limit] if text else None


def event_id(module: str, raw_id: str) -> str:
    """«<роль>:<id соседа>»; длиннее 96 знаков — начало id + 16 знаков его sha256 (тот же id при каждом запросе)."""
    full = f"{module}:{raw_id}"
    if EVENT_ID_RE.match(full):
        return full
    digest = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]
    return f"{module}:{raw_id[:96 - len(module) - 18]}.{digest}"


def normalize(event, module: str):
    """Событие соседа → строго поля §5.8 (или None, если оно неполное). Лишнее (устройства, тексты) отбрасывается."""
    if not isinstance(event, dict):
        return None
    at = _parse_time(event.get("at"))
    raw_id = event.get("id")
    raw_id = str(raw_id) if isinstance(raw_id, (str, int)) and not isinstance(raw_id, bool) else None
    title_ru, title_kk = _text(event.get("title_ru")), _text(event.get("title_kk"))
    kind = event.get("kind")
    if at is None or not raw_id or not ID_RE.match(raw_id) or not (title_ru or title_kk) \
            or not isinstance(kind, str) or not KIND_RE.match(kind):
        return None
    link = event.get("link")
    target = event.get("target")
    if isinstance(target, dict) and isinstance(target.get("kind"), str) and isinstance(target.get("id"), str) \
            and len(target["kind"]) <= 20 and len(target["id"]) <= 120:
        target = {"kind": target["kind"], "id": target["id"]}
    else:
        target = None
    return {"id": event_id(module, raw_id), "at": iso(at), "module": module, "kind": kind, "target": target,
            "title_ru": title_ru or title_kk, "title_kk": title_kk or title_ru,
            "link": link if isinstance(link, str) and LINK_RE.match(link) else None,
            "demo": bool(event.get("demo"))}


def _call(fn, device, since, db_path):
    """updates() соседа с теми именованными параметрами, которые он объявил (db_path / db, limit)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    kwargs = {}
    if "db_path" in params:
        kwargs["db_path"] = db_path
    elif "db" in params:
        kwargs["db"] = db_path
    if "limit" in params:
        kwargs["limit"] = MAX_PER_MODULE
    result = fn(device, since, **kwargs)
    items = result.get("items") if isinstance(result, dict) else result
    return list(items or [])[:MAX_PER_MODULE]


def _work_link(yard, item) -> str:
    """Куда ведёт «работа рядом» (IA_ROUND15 §2: работы рядом — вкладка «Работы» двора R16).

    Рядом с двором — «#yard/<id двора>» (R16 открывает двор, его «Работы» — по nearby_items R06); по подписке «Рядом» R08 —
    «#nearby/<район>/<id записи>» (R08 по пути открывает район и эту запись; без поддержки пути — ленту района).
    """
    if yard and isinstance(yard, str) and SAFE_PATH_RE.match(yard):
        return "#yard/" + yard
    district = item.get("district")
    if isinstance(district, str) and re.match(r"^[a-z]{2,20}\Z", district) and SAFE_PATH_RE.match(item["id"]):
        return f"#nearby/{district}/{item['id']}"
    return "#nearby"


class NotificationCenter:
    """Лента одного хранилища R06 (CivicV2): соседи + свои события + прочитанное."""

    def __init__(self, v2, *, neighbors=NEIGHBORS, importer=None):
        self.v2 = v2
        self.db = v2.service.db
        self.clock = v2.service.clock
        self.neighbors = neighbors
        self._import = importer or importlib.import_module
        self._cache: dict = {}
        self._lock = threading.Lock()

    # --- чтение -------------------------------------------------------------------------------------------------

    def collect(self, device_id, since=None, ideas_device=None) -> dict:
        device = self._device(device_id)
        ideas_device = ideas_device if isinstance(ideas_device, str) and DEVICE_RE.match(ideas_device) else None
        since_dt = None
        if since not in (None, ""):
            since_dt = _parse_time(since)
            if since_dt is None:
                raise BadRequest("since: время ISO 8601.", {"since": "Например 2026-10-15T10:00:00+05:00."})
        events, sources = self._events(device, ideas_device)
        read_until, read_ids = self._read_state(device)
        unread = 0
        items = []
        for event in events:
            read = (read_until is not None and event["at"] <= read_until) or event["id"] in read_ids
            unread += 0 if read else 1
            if since_dt is not None and _parse_time(event["at"]) <= since_dt:
                continue
            items.append(dict(event, read=read))
        return {"items": items[:MAX_ITEMS], "unread": unread, "read_until": read_until, "now": iso(utc_now(self.clock)),
                "sources": sources, "truncated": len(items) > MAX_ITEMS}

    def _events(self, device, ideas_device):
        key = (device, ideas_device)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < CACHE_SECONDS:
                return cached[1], cached[2]
        sources = {"R06": "ok"}
        events = []
        try:
            for event in self.own_events(device, ideas_device or device):
                # свои id — по тому же правилу, что у соседей (CIVIC_ID шлюза, до 96 знаков)
                event["id"] = event["id"] if EVENT_ID_RE.match(event["id"]) else event_id("R06", event["id"][4:])
                events.append(event)
        except Exception:  # noqa: BLE001 — своя часть тоже не роняет ленту соседей
            LOGGER.exception("notify: события R06 не собраны")
            sources["R06"] = "error"
        db_path = str(self.db.path)
        for role, modules, name in self.neighbors:
            try:
                fn = self._neighbor(modules, name)
                raw = _call(fn, device, None, db_path)
            except _ModuleAbsent:
                sources[role] = "absent"
                continue
            except Exception:  # noqa: BLE001 — сосед упал: его блок пропускаем, остальное показываем
                LOGGER.exception("notify: updates() %s упал", role)
                sources[role] = "error"
                continue
            sources[role] = "ok"
            events.extend(e for e in (normalize(item, role) for item in raw) if e is not None)
        seen, merged = set(), []
        for event in sorted(events, key=lambda e: (e["at"], e["id"]), reverse=True):
            if event["id"] in seen:
                continue
            seen.add(event["id"])
            merged.append(event)
        merged = merged[:MAX_ITEMS * 2]
        with self._lock:
            if len(self._cache) >= CACHE_DEVICES:
                self._cache.clear()
            self._cache[key] = (now, merged, sources)
        return merged, dict(sources)

    def _neighbor(self, modules, name):
        for module_name in modules:
            try:
                module = self._import(module_name)
            except ModuleNotFoundError as exc:
                missing = getattr(exc, "name", None) or ""
                if module_name == missing or module_name.startswith(missing + "."):
                    continue
                raise
            fn = getattr(module, name, None) if module is not None else None
            if callable(fn):
                return fn
        raise _ModuleAbsent(name)

    @staticmethod
    def _device(device_id):
        if not isinstance(device_id, str) or not DEVICE_RE.match(device_id):
            raise ValidationError({"device_id": "Нужен id устройства (заголовок X-Birge-Device): 8–128 символов "
                                                "[A-Za-z0-9._:-]."})
        return device_id

    # --- свои события R06 ---------------------------------------------------------------------------------------

    def own_events(self, device, ideas_device) -> list[dict]:
        out = []
        with self.db.read() as conn:
            dev = self.v2.proposals.device_hash(conn, ideas_device)
            if dev is not None:
                out.extend(self._idea_events(conn, dev))
                out.extend(self._project_events(conn, dev))
        out.extend(self._work_events(device))
        return out

    @staticmethod
    def _title(texts, lang, fallback):
        return (texts or {}).get("title_" + lang) or (texts or {}).get("title_ru") or (texts or {}).get("title_kk") \
            or fallback

    def _idea_events(self, conn, dev) -> list[dict]:
        rows = conn.execute(
            """SELECT h.id AS hid, h.idea_id, h.at, h.action, i.texts_json, i.demo, i.status,
                      (i.author_hash = ?) AS mine
                 FROM civic_idea_history h JOIN civic_ideas i ON i.id = h.idea_id
                WHERE h.action IN ('publish', 'check', 'project', 'reject', 'hide', 'reopen')
                  AND (i.author_hash = ? OR EXISTS (SELECT 1 FROM civic_idea_votes v
                                                     WHERE v.idea_id = i.id AND v.device_hash = ?))
                ORDER BY h.at DESC, h.id DESC LIMIT 100""", (dev, dev, dev)).fetchall()
        out = []
        for row in rows:
            mine = bool(row["mine"])
            if not mine and row["action"] in ("publish", "check", "hide"):
                continue  # поддержавшим — только итог: проект, отказ, снова на голосовании
            texts = _loads(row["texts_json"]) or {}
            ru, kk = self._title(texts, "ru", "идея"), self._title(texts, "kk", "идея")
            phrases = IDEA_PHRASES[row["action"]]
            who = 0 if mine else 1
            out.append({"id": f"R06:idea.{row['hid']}", "at": row["at"], "module": "R06", "kind": "idea.update",
                        "target": {"kind": "idea", "id": row["idea_id"]},
                        "title_ru": _text(phrases["ru"][who].format(t=ru)), "title_kk": _text(phrases["kk"][who].format(t=kk)),
                        "link": "#ideas/" + row["idea_id"], "demo": bool(row["demo"])})
        # «Сделайте вместе»: идея стала инициативой R16 (миграция 10: initiative_id/at у идеи).
        for row in conn.execute(
                """SELECT i.id, i.initiative_id, i.initiative_at, i.texts_json, i.demo FROM civic_ideas i
                    WHERE i.initiative_id IS NOT NULL AND i.initiative_at IS NOT NULL
                      AND (i.author_hash = ? OR EXISTS (SELECT 1 FROM civic_idea_votes v
                                                         WHERE v.idea_id = i.id AND v.device_hash = ?))
                    ORDER BY i.initiative_at DESC LIMIT 30""", (dev, dev)):
            texts = _loads(row["texts_json"]) or {}
            out.append({"id": f"R06:idea.{row['id']}.together", "at": row["initiative_at"], "module": "R06",
                        "kind": "idea.update", "target": {"kind": "idea", "id": row["id"]},
                        "title_ru": _text(f"«{self._title(texts, 'ru', 'идея')}» — сделаем вместе: акимат поддержит "
                                          "инвентарём"),
                        "title_kk": _text(f"«{self._title(texts, 'kk', 'идея')}» — бірге жасайық: әкімдік құрал-жабдықпен "
                                          "қолдайды"),
                        "link": "#together/" + row["initiative_id"], "demo": bool(row["demo"])})
        return out

    def _project_events(self, conn, dev) -> list[dict]:
        out = []
        for row in conn.execute(
                """SELECT h.id AS hid, h.proposal_id, h.at, h.action, p.title_ru, p.title_kk, p.demo
                     FROM civic_proposal_history h JOIN civic_proposals p ON p.id = h.proposal_id
                     JOIN civic_votes v ON v.proposal_id = p.id AND v.device_hash = ?
                    WHERE h.action IN ('approve', 'reject')
                    ORDER BY h.at DESC, h.id DESC LIMIT 50""", (dev,)):
            ok = row["action"] == "approve"
            ru = f"Проект «{row['title_ru']}», за который вы голосовали, {'одобрен' if ok else 'отклонён'}"
            kk_title = row["title_kk"] or row["title_ru"]
            kk = f"Сіз дауыс берген «{kk_title}» жобасы {'мақұлданды' if ok else 'қабылданбады'}"
            out.append({"id": f"R06:project.{row['hid']}", "at": row["at"], "module": "R06", "kind": "project.update",
                        "target": {"kind": "project", "id": row["proposal_id"]}, "title_ru": _text(ru),
                        "title_kk": _text(kk), "link": "#ideas/" + row["proposal_id"], "demo": bool(row["demo"])})
        return out

    def _places(self, device):
        """(районы подписки R08, работы подписки R08, [(id двора, точка)] R16) этого устройства; соседа нет — пусто."""
        districts, items, points = set(), set(), []
        try:
            nearby = self._import("ui.civic_akim.nearby")
            for sub in nearby.subscriptions(device) or []:
                if sub.get("scope") == "district" and isinstance(sub.get("id"), str):
                    districts.add(sub["id"])
                elif sub.get("scope") == "item" and isinstance(sub.get("id"), str):
                    items.add(sub["id"])
        except Exception:  # noqa: BLE001 — R08 нет или устройство без подписок «Рядом»
            pass
        for yard in self._yards(device):
            point = _yard_point(self._import, yard)
            if point is not None:
                points.append((yard, point))
        return districts, items, points

    def _yards(self, device) -> list[str]:
        """Дворы «Я живу здесь» R16 этого устройства (функция модуля или хранилище его сервиса)."""
        try:
            together = self._import("ui.civic_together")
        except Exception:  # noqa: BLE001
            return []
        for name in ("yards_of_device", "device_yards", "my_yards", "yards_for_device"):
            fn = getattr(together, name, None)
            if callable(fn):
                try:
                    found = fn(device) or []
                except Exception:  # noqa: BLE001
                    return []
                return [y.get("id") if isinstance(y, dict) else y for y in found if y][:3]
        factory = getattr(together, "default_service", None)
        try:
            service = factory(str(self.db.path)) if callable(factory) else None
            return list(service.store.my_yards(device))[:3] if service is not None else []
        except Exception:  # noqa: BLE001
            return []

    def _work_events(self, device) -> list[dict]:
        districts, subscribed, points = self._places(device)
        if not districts and not subscribed and not points:
            return []
        now = utc_now(self.clock)
        fresh = now - timedelta(days=WORK_NEAR_DAYS)
        fresh_district = now - timedelta(days=DISTRICT_DAYS)
        out = []
        per_district: dict = {}
        from . import works_v2
        items = sorted(self.v2.nearby.items(None), key=lambda i: str(i.get("updated_at") or ""), reverse=True)
        for item in items:
            updated = _parse_time(item.get("updated_at"))
            if updated is None or updated < fresh:
                continue
            if item["type"] == "work" and item.get("status") == "done":
                continue
            if item["type"] == "outage" and (_parse_time(item.get("end")) or now) < now:
                continue
            near_yard = next((yard for yard, p in points
                              if (works_v2.distance_to_geometry_m(p, item.get("geometry")) or 1e9) <= YARD_RADIUS_M), None)
            by_district = item.get("district") in districts and updated >= fresh_district \
                and per_district.get(item.get("district"), 0) < DISTRICT_MAX
            if not (near_yard or item["id"] in subscribed or by_district):
                continue
            if by_district and not near_yard and item["id"] not in subscribed:
                per_district[item.get("district")] = per_district.get(item.get("district"), 0) + 1
            ru, kk = item.get("title_ru") or "", item.get("title_kk") or item.get("title_ru") or ""
            where_ru = "Рядом с вашим двором" if near_yard else "В вашем районе"
            where_kk = "Аулаңыздың жанында" if near_yard else "Сіздің ауданыңызда"
            digest = hashlib.sha256(str(item.get("updated_at")).encode("utf-8")).hexdigest()[:8]
            out.append({"id": f"R06:work.{item['id']}.{digest}", "at": iso(updated), "module": "R06",
                        "kind": "work.near", "target": {"kind": "work", "id": item["id"]},
                        "title_ru": _text(f"{where_ru}: {ru}"), "title_kk": _text(f"{where_kk}: {kk}"),
                        "link": _work_link(near_yard, item), "demo": bool(item.get("demo"))})
        return out

    # --- прочитано ----------------------------------------------------------------------------------------------

    def _hash(self, conn, device):
        return self.v2.proposals.device_hash(conn, device)

    def _read_state(self, device):
        with self.db.read() as conn:
            row = conn.execute("SELECT read_until, read_ids_json FROM civic_notify_reads WHERE device_hash = ?",
                               (self._hash(conn, device),)).fetchone()
        if row is None:
            return None, set()
        return row["read_until"], set(_loads(row["read_ids_json"]) or [])

    def mark_read(self, device_id, payload, ideas_device=None) -> dict:
        """{all: true} — прочитано всё, что сейчас в ленте; {ids: [...]} — отдельные события; {until: ISO} — до момента.

        «Всё» — граница «прочитано до» = сейчас, а события ленты со временем впереди часов сервера (демо «через час»,
        расхождение часов модулей) отмечаются по id: иначе «Прочитать все» оставляло бы счётчик, а граница в будущем
        молча «прочитала» бы новые события, пришедшие до этого времени."""
        device = self._device(device_id)
        ideas_device = ideas_device if isinstance(ideas_device, str) and DEVICE_RE.match(ideas_device) else None
        payload = payload if isinstance(payload, dict) else {}
        unknown = sorted(set(payload) - {"ids", "all", "until", "device_id"})
        if unknown:
            raise ValidationError({str(unknown[0])[:64]: "Неизвестное поле."})
        ids = payload.get("ids") or []
        if not isinstance(ids, list) or len(ids) > 200 or not all(isinstance(i, str) and 0 < len(i) <= 160 for i in ids):
            raise ValidationError({"ids": "Список id событий (до 200)."})
        everything = payload.get("all", False)
        if not isinstance(everything, bool):
            raise ValidationError({"all": "true или false."})
        until = payload.get("until")
        until_dt = _parse_time(until) if until is not None else None
        if until is not None and until_dt is None:
            raise ValidationError({"until": "Время ISO 8601."})
        if not ids and not everything and until_dt is None:
            if isinstance(payload.get("ids"), list):
                # {"ids": []} — отмечать нечего: ответ — то, что уже прочитано, без записи в базу
                read_until, read_ids = self._read_state(device)
                return {"read_until": read_until, "read_ids": len(read_ids)}
            raise ValidationError({"ids": "Что отметить: ids, all или until."})
        now = utc_now(self.clock)
        future = []
        if everything:
            events, _sources = self._events(device, ideas_device)
            future = [e["id"] for e in events if e["at"] > iso(now)]
        with self.db.write() as conn:
            dev = self._hash(conn, device)
            row = conn.execute("SELECT read_until, read_ids_json FROM civic_notify_reads WHERE device_hash = ?",
                               (dev,)).fetchone()
            read_until = row["read_until"] if row else None
            read_ids = list(_loads(row["read_ids_json"]) or []) if row else []
            if everything or until_dt is not None:
                mark = iso(now if everything else min(until_dt, now))
                if read_until is None or mark > read_until:
                    read_until = mark
            # прежние отметки по id не сбрасываем: событие «впереди часов», прочитанное нажатием, остаётся прочитанным
            for event_id in list(future) + list(ids):
                if event_id not in read_ids:
                    read_ids.append(event_id)
            read_ids = read_ids[-READ_IDS_MAX:]
            conn.execute("""INSERT INTO civic_notify_reads(device_hash, read_until, read_ids_json, updated_at)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(device_hash) DO UPDATE SET read_until = excluded.read_until,
                                read_ids_json = excluded.read_ids_json, updated_at = excluded.updated_at""",
                         (dev, read_until, _dumps(read_ids), iso(now)))
        with self._lock:
            for key in [k for k in self._cache if k[0] == device]:
                self._cache.pop(key, None)
        return {"read_until": read_until, "read_ids": len(read_ids)}


# Тексты своих событий: [автору, поддержавшему]. {t} — название идеи на языке ленты (как написал житель).
IDEA_PHRASES = {
    "publish": {"ru": ("Ваша идея «{t}» опубликована — соседи могут её поддержать", ""),
                "kk": ("«{t}» идеяңыз жарияланды — көршілер қолдай алады", "")},
    "check": {"ru": ("Акимат проверяет вашу идею «{t}»", ""),
              "kk": ("Әкімдік «{t}» идеяңызды тексеруде", "")},
    "project": {"ru": ("Ваша идея «{t}» стала проектом акимата", "Идея «{t}», которую вы поддержали, стала проектом"),
                "kk": ("«{t}» идеяңыз әкімдік жобасына айналды", "Сіз қолдаған «{t}» идеясы жобаға айналды")},
    "reject": {"ru": ("Идея «{t}» отклонена — причина в карточке идеи", "Идея «{t}», которую вы поддержали, отклонена"),
               "kk": ("«{t}» идеясы қабылданбады — себебі идея карточкасында", "Сіз қолдаған «{t}» идеясы қабылданбады")},
    "hide": {"ru": ("Идея «{t}» не опубликована: в ней личные данные или грубые слова", ""),
             "kk": ("«{t}» идеясы жарияланбады: онда жеке деректер немесе дөрекі сөздер бар", "")},
    "reopen": {"ru": ("Идея «{t}» снова на голосовании", "Идея «{t}», которую вы поддержали, снова на голосовании"),
               "kk": ("«{t}» идеясы қайтадан дауыс беруде", "Сіз қолдаған «{t}» идеясы қайтадан дауыс беруде")},
}


def _yard_point(importer, yard_id):
    """Точка двора R12 (середина его границы) — для «работ рядом». Нет R12 или двора — None."""
    if not isinstance(yard_id, str) or not yard_id:
        return None
    try:
        geo = importer("engine.civic_geo")
        got = geo.target_geometry({"kind": "area", "id": yard_id})
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(got, dict):
        return None
    point = got.get("point")
    if isinstance(point, (list, tuple)) and len(point) == 2:
        return [float(point[0]), float(point[1])]
    geometry = got.get("geometry") or {}
    coords = geometry.get("coordinates")
    if geometry.get("type") == "Polygon" and coords and coords[0]:
        ring = coords[0]
        return [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]
    if geometry.get("type") == "Point" and coords:
        return [float(coords[0]), float(coords[1])]
    return None


__all__ = ["DEVICE_RE", "EVENT_ID_RE", "KINDS", "LINK_RE", "NEIGHBORS", "NotificationCenter", "event_id", "normalize"]
