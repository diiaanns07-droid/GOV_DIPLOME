"""Совместное исполнение и передачи в хранилище жалоб (раунд 15, CONTRACT §5.1, §7) — миксин ComplaintStore.

Действия сотрудника (сессия + CSRF проверяет api.py):
  handoff(id, to, reason)        «Передать в другую службу»: ведущая служба меняется, запись в handoffs[];
  set_services(id, services)     «Совместное исполнение»: 1–3 службы, ровно одна ведущая (подсказка R04 — одним нажатием);
  set_part(id, service, status)  статус части службы прямо из строки «Обращений»; все части done → «исправлено».
Чтение для соседей (без текстов жителей, точек и устройств): service_parts / handoffs_log (R17), yard_complaints (R16).

Срок ответа жителю (due_at) эти действия не трогают никогда — он считается от подачи (правило 2 joint.py).
Передача не двигает статус жалобы назад: житель не видит шага «в работе → принято» из-за того, что службы
договорились между собой; новая ведущая начинает со своей части «ждёт» (todo), а если она уже работала участником —
жалоба идёт вперёд по её части.
"""

from __future__ import annotations

from datetime import timedelta

from . import joint
from . import lifecycle
from . import record as rec

# Кто сделал — роль, а не имя (CONTRACT §10: журнал передач — «кто — роль»). Роли R02: editor, admin.
BY_ROLES = {"editor": "operator", "admin": "admin"}


def by_role(principal_role) -> str:
    return BY_ROLES.get(principal_role, "operator")


class JointMixin:
    """Нужны от ComplaintStore: _tx, _load, _save, _event, _emit, _now, _subscribers, _apply_status, assignee_lookup."""

    # ------------------------------------------------------------ служебное
    def _editable(self, db, complaint_id: str) -> dict:
        from .store import Conflict, NotFound
        record = self._load(db, complaint_id)
        if record is None:
            raise NotFound("Обращение не найдено.", {"id": complaint_id})
        if record.get("duplicate_of"):
            raise Conflict("Обращение объединено с другим — работайте с исходным.",
                           {"duplicate_of": record["duplicate_of"]})
        return record

    def _materialize(self, record: dict) -> list[dict]:
        """Части для изменения: сохранённые или одна часть ведущей службы — как её сейчас показывает паспорт."""
        items = joint.parts(record, self.assignee_lookup)
        for part in items:
            part.pop("implicit", None)
        return items

    @staticmethod
    def _write_parts(record: dict, items: list[dict], source: str) -> None:
        """Сохранить части; ведущая — в service и в паспорте (старые экраны и форма паспорта видят ту же службу)."""
        record["services"] = items
        lead = items[0]["service"]
        record["service"] = lead
        record["service_source"] = source
        passport = dict(record.get("passport") or {})
        passport["assignee_id"] = lead
        passport.pop("assignee", None)
        record["passport"] = passport

    @staticmethod
    def _part_update(record: dict, at: str, kind: str, **fields) -> None:
        """Строка ленты обновлений (видят автор и «Я тоже»): handoff | services | part — без причин и ролей."""
        record.setdefault("updates", []).append({"at": at, "kind": kind, "text": fields.pop("text", None), **fields})

    def _settle(self, db, record: dict, items: list[dict], now: str, *, actor=None, extra=None,
                forward_only: bool = False) -> bool:
        """Статус жалобы по частям (правило 1 joint.py). forward_only — только вперёд (передача: житель не видит
        шага назад «в работе → принято»). -> True, если статус изменился."""
        target = joint.status_after_parts(record["status"], items)
        if target == record["status"]:
            return False
        if forward_only and joint.STATUS_ORDER.get(target, 0) <= joint.STATUS_ORDER.get(record["status"], 0):
            return False
        what_done = joint.combined_note(items) if target == "fixed" else None
        self._apply_status(db, record, target, now, actor=actor, what_done=what_done, photos=None, extra=extra)
        return True

    # ------------------------------------------------------------ вызывает set_status / verify (store.py)
    def _lead_follows_status(self, record: dict, status: str, now: str, what_done):
        """Сотрудник сменил статус всей жалобы: у совместной — ведущая часть следует за ним.
        «Исправлено» при несделанных частях других служб — отказ с их списком (сначала их части)."""
        from .store import Conflict
        if not record.get("services") or status == "rejected":
            return what_done
        items = joint.parts(record, self.assignee_lookup)
        lead = items[0]
        if status == "fixed":
            pending = [p["service"] for p in items[1:] if p["status"] != "done"]
            if pending:
                names = ", ".join(lifecycle.SERVICES[s]["ru"] for s in pending if s in lifecycle.SERVICES)
                raise Conflict(f"Не все службы закончили: {names}. Отметьте их части или дождитесь.",
                               {"waiting": pending})
            lead["status"] = "done"
            what_done = what_done or joint.combined_note(items)
        else:
            lead["status"] = joint.part_status_from_complaint(status)
        lead["updated_at"] = now
        record["services"] = items
        return what_done

    def _lead_reopened(self, record: dict, now: str) -> None:
        """Жители вернули ремонт: у совместной жалобы ведущая служба снова «в работе» (остальные части как были)."""
        if not record.get("services"):
            return
        items = joint.parts(record, self.assignee_lookup)
        items[0]["status"] = "in_progress"
        items[0]["updated_at"] = now
        record["services"] = items

    def _passport_service(self, record: dict, service: str | None, lead_before: str, now: str, role) -> bool:
        """Выбор службы в форме паспорта (FINAL-4) = передача: ведущая в частях и запись в журнале передач.
        service пусто — снова «по таблице», как у новой жалобы. -> True, если ведущая служба сменилась."""
        if service:
            new, source = service, "staff"
        else:
            new = joint.lead_service({"category": record.get("category"), "subtopic": record.get("subtopic")},
                                     self.assignee_lookup)
            source = "table"
        if record.get("services"):
            items = joint.parts(record, self.assignee_lookup)
            if items[0]["service"] != new:
                existing = next((p for p in items[1:] if p["service"] == new), None)
                lead = {**existing, "role": "lead", "updated_at": now} if existing else \
                    {"service": new, "role": "lead", "status": "todo", "updated_at": now}
                record["services"] = [lead] + [p for p in items[1:] if p["service"] != new]
        record["service"] = new
        record["service_source"] = source
        if new == lead_before:
            return False
        reason = joint.SYSTEM_REASONS["passport"]["ru"]
        record.setdefault("handoffs", []).append({"at": now, "from": lead_before, "to": new, "reason": reason,
                                                  "reason_code": "passport", "by_role": by_role(role)})
        self._part_update(record, now, "handoff", service=new)
        return True

    # ------------------------------------------------------------ передача
    def handoff(self, complaint_id: str, to: str, reason=None, *, reason_code=None, keep: bool = False,
                expected_lead: str | None = None, actor: str | None = None, role: str | None = None) -> tuple[dict, int]:
        """«Передать в другую службу». -> (запись, сколько человек увидят «Передано: …»).
        to — id службы; reason — строка или чип reason_code; keep — прежняя ведущая остаётся участником.
        Если to уже участвует — она становится ведущей со своим статусом части."""
        from .store import Conflict
        if to not in lifecycle.SERVICES:
            raise joint.JointError("Неизвестная служба.", {"to": ", ".join(lifecycle.SERVICES)})
        text, code = joint.clean_reason(reason, reason_code)
        now = rec.iso(self._now())
        with self._tx() as db:
            record = self._editable(db, complaint_id)
            if record["status"] in ("fixed", "rejected"):
                raise Conflict("Обращение закрыто — сначала верните его в работу.", {"status": record["status"]})
            items = self._materialize(record)
            lead = items[0]
            if expected_lead is not None and lead["service"] != expected_lead:
                raise Conflict("Обращение уже передали. Обновите карточку.", {"lead": lead["service"]})
            if lead["service"] == to:
                raise joint.JointError("Обращение уже у этой службы.", {"to": to})
            existing = next((p for p in items if p["service"] == to), None)
            new_lead = {**existing, "role": "lead", "updated_at": now} if existing else \
                {"service": to, "role": "lead", "status": "todo", "updated_at": now}
            others = [p for p in items[1:] if p["service"] != to]
            if keep:
                others.append({**lead, "role": "partner", "updated_at": now})
            new_items = [new_lead] + others
            if len(new_items) > joint.MAX_SERVICES:
                raise joint.JointError(f"Не больше {joint.MAX_SERVICES} служб на одно обращение.",
                                       {"services": f"до {joint.MAX_SERVICES}"})
            entry = {"at": now, "from": lead["service"], "to": to, "reason": text, "by_role": by_role(role)}
            if code:
                entry["reason_code"] = code
            record.setdefault("handoffs", []).append(entry)
            self._write_parts(record, new_items, "handoff")
            self._part_update(record, now, "handoff", service=to)
            # Новая ведущая уже работала участником — жалоба идёт вперёд по её части; назад передача не двигает.
            changed = self._settle(db, record, new_items, now, actor=actor, extra={"via": "handoff"}, forward_only=True)
            self._save(db, record)
            events = [self._event(db, "update", record, now)]
            if changed:
                events.append(self._event(db, "status", record, now))
            notified = self._subscribers(db, record)
        self._emit(events)
        return record, notified

    # ------------------------------------------------------------ совместное исполнение
    def set_services(self, complaint_id: str, services, *, reason=None, expected_lead: str | None = None,
                     actor: str | None = None, role: str | None = None) -> tuple[dict, int]:
        """«Совместное исполнение»: полный список служб [{service, role}] (1–3, одна lead). Части, которые остаются,
        сохраняют статус и заметку; новые — «ждёт». Смена ведущей — тоже передача (handoffs[], причина «Совместное
        исполнение», если не указана). Подсказка R04 принята — route_hint.accepted_at (для оценки качества R04)."""
        from .store import Conflict
        wanted = joint.parse_services(services)
        now = rec.iso(self._now())
        with self._tx() as db:
            record = self._editable(db, complaint_id)
            if record["status"] in ("fixed", "rejected"):
                raise Conflict("Обращение закрыто — сначала верните его в работу.", {"status": record["status"]})
            items = self._materialize(record)
            if expected_lead is not None and items[0]["service"] != expected_lead:
                raise Conflict("Обращение уже передали. Обновите карточку.", {"lead": items[0]["service"]})
            current = {p["service"]: p for p in items}
            new_items = []
            for want in wanted:
                base = current.get(want["service"])
                part = {**base, "role": want["role"]} if base else \
                    {"service": want["service"], "role": want["role"], "status": "todo"}
                if not base or base["role"] != want["role"]:
                    part["updated_at"] = now
                new_items.append(part)
            old_ids = [p["service"] for p in items]
            new_ids = [p["service"] for p in new_items]
            if old_ids == new_ids and [p["role"] for p in items] == [p["role"] for p in new_items]:
                return record, self._subscribers(db, record)              # ничего не изменилось
            if new_ids[0] != old_ids[0]:
                text, code = joint.clean_reason(reason, None if reason else "joint")
                entry = {"at": now, "from": old_ids[0], "to": new_ids[0], "reason": text, "by_role": by_role(role)}
                if code:
                    entry["reason_code"] = code
                record.setdefault("handoffs", []).append(entry)
            hint = record.get("route_hint")
            if isinstance(hint, dict) and set(hint.get("services") or []) == set(new_ids):
                hint["accepted_at"] = now
            self._write_parts(record, new_items, "joint" if len(new_items) > 1 else "staff")
            self._part_update(record, now, "services", services=new_ids,
                              added=[s for s in new_ids if s not in old_ids],
                              removed=[s for s in old_ids if s not in new_ids])
            changed = self._settle(db, record, new_items, now, actor=actor, extra={"via": "services"})
            self._save(db, record)
            events = [self._event(db, "update", record, now)]
            if changed:
                events.append(self._event(db, "status", record, now))
            notified = self._subscribers(db, record)
        self._emit(events)
        return record, notified

    def set_part(self, complaint_id: str, service: str, status, note=None, *, expected=None,
                 actor: str | None = None, role: str | None = None) -> tuple[dict, int]:
        """Статус части одной службы (todo | in_progress | done) и короткая заметка для жителей («Трубу заменили»).
        Все части done → жалоба «исправлено» («служба сообщила»), жители проверяют ремонт как обычно."""
        from .store import Conflict
        target = joint.part_status(status)
        if target is None:
            raise joint.JointError("Статус части: ждёт, в работе или сделано.", {"status": "todo | in_progress | done"})
        note = joint.clean_note(note)
        now = rec.iso(self._now())
        with self._tx() as db:
            record = self._editable(db, complaint_id)
            if record["status"] == "rejected":
                raise Conflict("Обращение отклонено — части служб не меняются.", {"status": "rejected"})
            items = self._materialize(record)
            part = next((p for p in items if p["service"] == service), None)
            if part is None:
                raise joint.JointError("Эта служба не участвует в обращении.",
                                       {"service": ", ".join(p["service"] for p in items)})
            if expected is not None and part["status"] != joint.part_status(expected):
                raise Conflict("Статус части уже изменили. Обновите карточку.", {"status": part["status"]})
            if part["status"] == target and (note is None or note == part.get("note")):
                return record, self._subscribers(db, record)              # повтор того же нажатия
            part["status"] = target
            part["updated_at"] = now
            if note is not None:
                part["note"] = note
            part["by_role"] = by_role(role)
            source = record.get("service_source") if record.get("services") else "staff"
            self._write_parts(record, items, source if source in joint.SERVICE_SOURCES else "staff")
            self._part_update(record, now, "part", service=service, status=target, text=note)
            changed = self._settle(db, record, items, now, actor=actor, extra={"part": service})
            self._save(db, record)
            events = [self._event(db, "update", record, now)]
            if changed:
                events.append(self._event(db, "status", record, now))
            notified = self._subscribers(db, record)
        self._emit(events)
        return record, notified

    # ------------------------------------------------------------ чтение для R17 и R16 (без персональных данных)
    def _period(self, since=None, until=None, days=None):
        now = self._now()
        start = rec.parse_iso(since) if isinstance(since, str) else since
        end = rec.parse_iso(until) if isinstance(until, str) else until
        if start is None and days:
            start = now - timedelta(days=int(days))
        return start, end

    def service_parts(self, since=None, until=None, *, days=None, district=None, include_duplicates=False) -> list[dict]:
        """Части служб по жалобам периода (подача в [since, until]) — для табло R17 «Штаб ведомств».
        Без текста, точки и устройства: категория, район, статус, срок, когда ответили, службы и их статусы."""
        start, end = self._period(since, until, days)
        now = self._now()
        out = []
        for record in self.list(since=start, include_duplicates=include_duplicates):
            created = rec.parse_iso(record.get("created_at"))
            if end is not None and created is not None and created > end:
                continue
            if district and record.get("district") != district:
                continue
            items = joint.parts(record, self.assignee_lookup)
            resolution = record.get("resolution") or {}
            info = lifecycle.deadline(record, now) or {}
            out.append({
                "complaint_id": record["id"], "code": record.get("code"), "created_at": record.get("created_at"),
                "category": record.get("category"), "subtopic": record.get("subtopic"),
                "district": record.get("district"), "status": record.get("status"),
                "due_at": record.get("due_at"), "answered_at": joint.answer_at(record),
                "deadline_state": info.get("state"), "overdue": info.get("state") == "overdue",
                "lead": items[0]["service"] if items else None, "joint": len(items) > 1,
                "services": [{"service": p["service"], "role": p["role"], "status": p["status"],
                              "updated_at": p.get("updated_at")} for p in items],
                "handoffs": len(record.get("handoffs") or []),
                "resolution": resolution.get("state"), "reopen_count": int(resolution.get("reopen_count") or 0),
                "reporters": rec.reporters(record), "demo": bool(record.get("demo")),
            })
        return out

    def handoffs_log(self, since=None, until=None, *, days=None, district=None) -> list[dict]:
        """Журнал передач (новые сверху) — для R17 «Передачи»: кто (служба) кому, когда, причина, роль сотрудника."""
        start, end = self._period(since, until, days)
        out = []
        for record in self.list(include_duplicates=True):
            if district and record.get("district") != district:
                continue
            for entry in record.get("handoffs") or []:
                moment = rec.parse_iso(entry.get("at"))
                if moment is None or (start is not None and moment < start) or (end is not None and moment > end):
                    continue
                out.append({"complaint_id": record["id"], "code": record.get("code"), "at": entry.get("at"),
                            "from": entry.get("from"), "to": entry.get("to"), "reason": entry.get("reason"),
                            "reason_code": entry.get("reason_code"), "by_role": entry.get("by_role"),
                            "category": record.get("category"), "district": record.get("district"),
                            "status": record.get("status"), "demo": bool(record.get("demo"))})
        out.sort(key=lambda e: e["at"] or "", reverse=True)
        return out

    def yard_complaints(self, yard_id: str, *, days: int = 60, targets=None, polygon=None) -> dict:
        """Жалобы двора для «Мой двор» R16: цель — сам двор (area yard-<id>), объекты двора (targets — id целей R12)
        или точка внутри контура двора (polygon — кольца GeoJSON Polygon). Публично: без текстов, фото и устройств.
        -> {"yard", "items": [...], "counts": {"open", "fixed", "verified", "total", "people"}}"""
        since = self._now() - timedelta(days=max(1, min(int(days or 60), 365)))
        wanted = {yard_id} | {t for t in (targets or []) if isinstance(t, str)}
        rings = polygon.get("coordinates") if isinstance(polygon, dict) else polygon
        if not isinstance(rings, (list, tuple)) or not rings:
            rings = None
        items = []
        for record in self.list(since=since):
            target_id = (record.get("target") or {}).get("id")
            hit = target_id in wanted
            if not hit and rings and record.get("point"):
                try:
                    hit = rec.distance_to_geometry_m(record["point"], {"type": "Polygon", "coordinates": rings}) == 0
                except (TypeError, ValueError, IndexError, KeyError):
                    hit = False
            if not hit:
                continue
            resolution = record.get("resolution") or {}
            items.append({"id": record["id"], "category": record.get("category"), "subtopic": record.get("subtopic"),
                          "status": record.get("status"), "created_at": record.get("created_at"),
                          "target": {k: v for k, v in (record.get("target") or {}).items()
                                     if k in ("kind", "id", "label_ru", "label_kk", "approximate", "object_kind")},
                          "reporters": rec.reporters(record), "resolution": resolution.get("state"),
                          "heat_state": lifecycle.heat_state(record, self._now()),
                          "services": [p["service"] for p in joint.parts(record, self.assignee_lookup)],
                          "demo": bool(record.get("demo"))})
        counts = {"open": sum(1 for i in items if i["status"] in rec.OPEN_STATUSES),
                  "fixed": sum(1 for i in items if i["status"] == "fixed"),
                  "verified": sum(1 for i in items if i["resolution"] == "verified"),
                  "total": len(items), "people": sum(i["reporters"] for i in items)}
        return {"yard": yard_id, "days": days, "items": items, "counts": counts}
