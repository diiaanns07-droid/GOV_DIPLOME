"""«Это разные проблемы»: акимат разъединяет ошибочно объединённое одним действием (волна мелочей п. 9, R04 + R09).

Объединение бывает двух видов, и оба отменяются без потерь:

1) Дубль. Сотрудник отметил жалобу A дублем B (store.mark_duplicate): люди A — автор и его «Я тоже» — перенесены
   в «Я тоже» B с ВРЕМЕНЕМ ОБЪЕДИНЕНИЯ (оно же стоит в status_history A). Отмена: A снова отдельная открытая жалоба;
   из B (и дальше по цепочке, если B потом тоже объединили с C) удаляются ровно те «Я тоже», которые добавило
   объединение, — по совпадению устройства И времени. Собственные нажатия людей на B остаются: у них своё время.
   Дубли, которые при объединении перепривязали с A на B, снова ссылаются на A (по их status_history).

2) «Я тоже» из формы жалобы. Житель написал текст и выбрал место, R04 /similar нашёл похожую, житель нажал «Я тоже».
   Его текст, место, цель и категория сохраняются в complaint_metoo_notes_v2 (видит только акимат). Отмена:
   «Я тоже» снимается, из сохранённого создаётся отдельная жалоба этого жителя со временем, когда он сообщил
   (срок ответа считается от него), и в «Моих обращениях» она становится его собственной.
   «Я тоже» без текста (кнопка на карточке места R07) разделять нечем: житель согласился с проблемой места.

После отмены — события «separated» + «metoo»/«created»: тепловая карта R07 пересчитывает обе цели (шлюз R01
сбрасывает её кэш на любое событие хранилища), R04 записывает пару как «разные» в журнал решений
(ml/civic_dedup/feedback.py) — по нему видно, как часто подсказка «Похоже на» ошибается.
"""

from __future__ import annotations

import json
import secrets

from . import categories
from . import record as rec
from .record import RecordError

NOTE_PREFIX = "mt-"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS complaint_metoo_notes_v2 (
  id TEXT PRIMARY KEY,
  complaint_id TEXT NOT NULL,
  device_hash TEXT NOT NULL,
  at TEXT NOT NULL,
  note_json TEXT NOT NULL,
  separated_into TEXT,
  separated_at TEXT,
  separated_by TEXT
);
CREATE INDEX IF NOT EXISTS complaint_metoo_notes_v2_complaint ON complaint_metoo_notes_v2 (complaint_id);
"""

MERGED_LIMIT = 50


def _last_merge(record: dict) -> dict | None:
    """Последняя запись истории «отмечено дублем» (в ней время объединения и исходная)."""
    for entry in reversed(record.get("status_history") or []):
        if isinstance(entry, dict) and entry.get("duplicate_of"):
            return entry
    return None


class SeparateMixin:
    """Методы ComplaintStore для п. 9. Пользуются _tx/_load/_save/_event/_emit/_next_code/_recount_metoo хранилища."""

    # ------------------------------------------------------------ текст «Я тоже» из формы
    def parse_metoo_note(self, note) -> dict | None:
        """То же, что проверяет create(): текст, точка, цель (с проверкой по карте R12), категория.
        Неверная заметка не мешает «Я тоже»: оно засчитывается, просто разделить его потом будет нечем."""
        if not isinstance(note, dict):
            return None
        try:
            text = rec.parse_text(note.get("text"))
            point = rec.parse_point(note.get("point"))
            target = (rec.checked_target(rec.parse_target(note["target"]), point, self.target_lookup)
                      if note.get("target") is not None else rec.cell_target(*point))
        except (RecordError, KeyError, TypeError, ValueError):
            return None
        category = note.get("category") if categories.is_category(note.get("category")) else None
        lang = note.get("lang") if note.get("lang") in ("ru", "kk", "mixed") else rec.detect_lang(text)
        return {"text": text, "lang": lang, "point": point, "target": target, "category": category}

    def _add_metoo_note(self, db, complaint_id: str, device: str, at: str, note: dict) -> str:
        note_id = NOTE_PREFIX + secrets.token_hex(8)
        db.execute("INSERT INTO complaint_metoo_notes_v2 (id, complaint_id, device_hash, at, note_json) "
                   "VALUES (?,?,?,?,?)", (note_id, complaint_id, device, at, json.dumps(note, ensure_ascii=False)))
        return note_id

    # ------------------------------------------------------------ что объединено (карточка акимата)
    def merged(self, target_id: str, *, limit: int = MERGED_LIMIT) -> list[dict]:
        """Что присоединено к жалобам этой цели: дубли и «Я тоже» с текстом. Только для сотрудника (тексты жителей)."""
        with self._lock:
            roots = {row[0]: json.loads(row[1]) for row in self._db.execute(
                "SELECT id, record_json FROM complaints_v2 WHERE target_id = ? AND duplicate_of IS NULL", (target_id,))}
            if not roots:
                return []
            ids = list(roots)
            marks = ",".join("?" * len(ids))
            dups = [json.loads(row[0]) for row in self._db.execute(
                f"SELECT record_json FROM complaints_v2 WHERE duplicate_of IN ({marks})", ids)]
            joined = ids + [d["id"] for d in dups]
            notes = self._db.execute(
                f"SELECT * FROM complaint_metoo_notes_v2 WHERE separated_into IS NULL "
                f"AND complaint_id IN ({','.join('?' * len(joined))})", joined).fetchall()
            codes = {d["id"]: d.get("code") for d in dups}
        codes.update({rid: r.get("code") for rid, r in roots.items()})
        items = []
        for dup in dups:
            merge = _last_merge(dup) or {}
            items.append({"id": dup["id"], "kind": "duplicate", "code": dup.get("code"), "into": dup["duplicate_of"],
                          "into_code": codes.get(dup["duplicate_of"]), "text": dup.get("text"), "lang": dup.get("lang"),
                          "at": dup.get("created_at"), "merged_at": merge.get("at"), "category": dup.get("category"),
                          "target": dup.get("target"), "people": rec.reporters(dup)})
        for row in notes:
            note = json.loads(row["note_json"])
            into = row["complaint_id"]
            items.append({"id": row["id"], "kind": "metoo", "into": into, "into_code": codes.get(into),
                          "text": note.get("text"), "lang": note.get("lang"), "at": row["at"], "merged_at": row["at"],
                          "category": note.get("category"), "target": note.get("target"), "people": 1})
        flag_of = getattr(rec, "moderation", None)   # пометка «Содержит грубые слова» (п. 8), если фильтр есть
        for item in items:
            flag = flag_of(item.get("text")) if flag_of else None
            if flag:
                item["moderation"] = flag
        items.sort(key=lambda item: item.get("merged_at") or "", reverse=True)
        return items[:max(1, int(limit))]

    # ------------------------------------------------------------ «Это разные проблемы»
    def separate(self, item_id: str, *, actor: str | None = None) -> tuple[dict, dict | None]:
        """item_id — id жалобы-дубля (c-…) или записи «Я тоже» с текстом (mt-…).
        -> (отдельная теперь жалоба, исходная после пересчёта людей)."""
        if isinstance(item_id, str) and item_id.startswith(NOTE_PREFIX):
            return self._separate_metoo(item_id, actor)
        return self._separate_duplicate(item_id, actor)

    def _chain(self, db, start_id):
        """Исходные по цепочке duplicate_of: [start, …, корень] (защита от петли) и времена их объединений."""
        chain, times, seen, current = [], set(), set(), start_id
        while current and current not in seen:
            record = self._load(db, current)
            if record is None:
                break
            chain.append(record)
            seen.add(current)
            merge = _last_merge(record) if record.get("duplicate_of") else None
            if merge:
                times.add(merge["at"])
            current = record.get("duplicate_of")
        return chain, times

    @staticmethod
    def _drop_metoo(db, chain, devices, times) -> None:
        """Удалить «Я тоже» этих устройств, поставленные объединением (время совпадает), у всех исходных цепочки."""
        if not devices or not times:
            return
        tmarks = ",".join("?" * len(times))
        for record in chain:
            for device in devices:
                db.execute(f"DELETE FROM complaint_metoo_v2 WHERE complaint_id = ? AND device_hash = ? AND at IN ({tmarks})",
                           (record["id"], device, *sorted(times)))

    def _separate_duplicate(self, dup_id, actor):
        from .store import Conflict, NotFound
        now = rec.iso(self._now())
        with self._tx() as db:
            dup = self._load(db, dup_id)
            if dup is None:
                raise NotFound("Обращение не найдено.", {"id": dup_id})
            if not dup.get("duplicate_of"):
                raise Conflict("Это обращение не объединено с другим.")
            merge = _last_merge(dup)
            first = merge["duplicate_of"] if merge else dup["duplicate_of"]
            chain, times = self._chain(db, first)
            if merge:
                times.add(merge["at"])
            author = db.execute("SELECT device_hash FROM complaints_v2 WHERE id = ?", (dup["id"],)).fetchone()[0]
            devices = ([author] if author else []) + [row[0] for row in db.execute(
                "SELECT device_hash FROM complaint_metoo_v2 WHERE complaint_id = ?", (dup["id"],))]
            self._drop_metoo(db, chain, devices, times)
            # Дубли, перепривязанные при объединении с этой жалобы на корень, снова ссылаются на неё.
            root_id = chain[-1]["id"] if chain else dup["duplicate_of"]
            for (child_id,) in db.execute("SELECT id FROM complaints_v2 WHERE duplicate_of = ? AND id != ?",
                                          (root_id, dup["id"])).fetchall():
                child = self._load(db, child_id)
                child_merge = _last_merge(child)
                if child_merge and child_merge.get("duplicate_of") == dup["id"]:
                    child["duplicate_of"] = dup["id"]
                    self._save(db, child)
            dup["duplicate_of"] = None
            entry = {"at": now, "status": dup["status"], "separated_from": first}
            if actor:
                entry["by"] = str(actor)[:80]
            dup["status_history"].append(entry)
            self._recount_metoo(db, dup)
            self._save(db, dup)
            events = [self._event(db, "separated", dup, now)]
            events[0]["original_id"] = first
            for record in chain:
                self._recount_metoo(db, record)
                self._save(db, record)
                events.append(self._event(db, "metoo", record, now))
        self._emit(events)
        return dup, (chain[0] if chain else None)

    def _separate_metoo(self, note_id, actor):
        from .store import Conflict, NotFound
        now = rec.iso(self._now())
        with self._tx() as db:
            row = db.execute("SELECT * FROM complaint_metoo_notes_v2 WHERE id = ?", (note_id,)).fetchone()
            if row is None:
                raise NotFound("Отметка «Я тоже» не найдена.", {"id": note_id})
            if row["separated_into"]:
                raise Conflict("Уже разделено.", {"complaint": row["separated_into"]})
            note = json.loads(row["note_json"])
            chain, times = self._chain(db, row["complaint_id"])
            if not chain:
                raise NotFound("Обращение не найдено.", {"id": row["complaint_id"]})
            times.add(row["at"])
            self._drop_metoo(db, chain, [row["device_hash"]], times)
            base = chain[0]
            category = note.get("category") if categories.is_category(note.get("category")) else base["category"]
            history = [{"at": row["at"], "status": "new"}, {"at": now, "status": "new", "separated_from": base["id"]}]
            if actor:
                history[1]["by"] = str(actor)[:80]
            record = {
                "id": "c-" + secrets.token_hex(8),
                "code": self._next_code(db),
                "created_at": row["at"],            # житель сообщил тогда, когда нажал «Я тоже»
                "text": note["text"], "lang": note.get("lang") or rec.detect_lang(note["text"]),
                "category": category, "category_source": "resident", "model": None,
                "point": note["point"], "target": note["target"], "district": base.get("district"),
                "status": "new", "status_history": history,
                "metoo": 0, "duplicate_of": None, "demo": False, "separated_from": base["id"],
                "due_at": rec.due_at(row["at"], category),
                "schema": rec.SCHEMA,
            }
            flag = rec.moderation(record["text"]) if hasattr(rec, "moderation") else None   # п. 8
            if flag:
                record["moderation"] = flag
            self._save(db, record, device_hash=row["device_hash"])
            db.execute("UPDATE complaint_metoo_notes_v2 SET separated_into = ?, separated_at = ?, separated_by = ? "
                       "WHERE id = ?", (record["id"], now, str(actor)[:80] if actor else None, note_id))
            events = [self._event(db, "created", record, now), self._event(db, "separated", record, now)]
            events[1]["original_id"] = base["id"]
            for other in chain:
                self._recount_metoo(db, other)
                self._save(db, other)
                events.append(self._event(db, "metoo", other, now))
        self._emit(events)
        return record, base
