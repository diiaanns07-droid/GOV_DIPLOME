"""Поиск похожих обращений: Deduper.find(text, records, point=…, target=…, days=…).

Правило (prompts/R04.txt п. 2):
    похожее = сходство текста ≥ порога
              И (та же цель target ИЛИ расстояние между точками ≤ radius_m, по умолчанию 200 м)
              И создано за последние N дней (по умолчанию 14)
              И обращение открыто (new / accepted / in_progress) и не помечено дублем другого.
Без точки и без цели совпадений нет: «где» — обязательная часть дубля (иначе «яма на дороге»
в Нуре совпала бы с ямой в Сарыарке).

Записи — словари CONTRACT §5 (ui/civic_feedback/v2 у R09). Текст записи нужен только здесь,
на сервере; наружу (в ответ API) текст не попадает.

Признаки текстов кэшируются по (id, sha1 текста): на 5 000 обращений повторный поиск не
пересчитывает n-граммы/эмбеддинги. Кэш потокобезопасен.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ml.civic_dedup.geo import distance_m, parse_point
from ml.civic_dedup.normalize import letters

ASTANA_TZ = timezone(timedelta(hours=5))
OPEN_STATUSES = ("new", "accepted", "in_progress")
DEFAULT_DAYS = 14
MAX_DAYS = 365
DEFAULT_RADIUS_M = 200.0
MIN_LETTERS = 3


def target_id(target) -> str | None:
    """{"kind", "id", …} или строка id -> id; иначе None."""
    if isinstance(target, dict):
        target = target.get("id")
    if isinstance(target, str) and target.strip():
        return target.strip()
    return None


def parse_time(value) -> datetime | None:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA_TZ)


def clamp_days(days) -> int:
    if days is None:
        return DEFAULT_DAYS
    if isinstance(days, bool) or not isinstance(days, (int, float)):
        raise ValueError("days: целое число дней от 1 до 365.")
    return max(1, min(MAX_DAYS, int(days)))


@dataclass
class Match:
    complaint_id: str
    score: float
    target: dict | None
    metoo: int
    category: str | None
    created_at: str | None
    status: str | None
    distance_m: float | None
    same_target: bool

    def as_dict(self) -> dict:
        return {
            "complaint_id": self.complaint_id,
            "score": round(self.score, 4),
            "target": self.target,
            "metoo": self.metoo,
            # Сверх контракта (CONTRACT §7), для карточки «Об этом уже сообщили»: без текста жалобы.
            "people": 1 + self.metoo,
            "category": self.category,
            "created_at": self.created_at,
            "status": self.status,
            "distance_m": None if self.distance_m is None else round(self.distance_m, 1),
            "same_target": self.same_target,
        }


class FeatureCache:
    """LRU-кэш признаков текста: ключ (id записи, sha1 текста) -> признаки оценщика."""

    def __init__(self, max_items: int = 50_000):
        self.max_items = max_items
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def key(record_id: str, text: str) -> tuple[str, str]:
        return record_id, hashlib.sha1(text.encode("utf-8")).hexdigest()

    def get_many(self, scorer, items: list[tuple[str, str]]) -> list:
        """items = [(id, text)] -> признаки в том же порядке; недостающие считаются одним пакетом."""
        keys = [self.key(i, t) for i, t in items]
        out: list = [None] * len(items)
        missing = []
        with self._lock:
            for n, k in enumerate(keys):
                feats = self._data.get(k)
                if feats is not None:
                    self._data.move_to_end(k)
                    out[n] = feats
                else:
                    missing.append(n)
        if missing:
            # Вне блокировки: эмбеддинги e5 считаются десятки миллисекунд, другие запросы не ждут.
            computed = scorer.encode_many([items[n][1] for n in missing])
            with self._lock:
                for n, feats in zip(missing, computed):
                    out[n] = feats
                    self._data[keys[n]] = feats
                    self._data.move_to_end(keys[n])
                while len(self._data) > self.max_items:
                    self._data.popitem(last=False)
        return out

    def __len__(self) -> int:
        return len(self._data)


class Deduper:
    def __init__(self, scorer, threshold: float, *, radius_m: float = DEFAULT_RADIUS_M, cache_items: int = 50_000):
        self.scorer = scorer
        self.threshold = float(threshold)
        self.radius_m = float(radius_m)
        self.cache = FeatureCache(cache_items)

    @property
    def version(self) -> str:
        return f"{self.scorer.version}-t{self.threshold:g}"

    def eligible(self, records, *, point=None, target=None, days=None, now: datetime | None = None):
        """Записи, прошедшие фильтры места, времени и статуса: [(record, distance_m | None, same_target)]."""
        days = clamp_days(days)
        now = now or datetime.now(ASTANA_TZ)
        since = now - timedelta(days=days)
        here = parse_point(point) if point is not None else None
        tid = target_id(target)
        out = []
        seen = set()
        for rec in records or ():
            if not isinstance(rec, dict):
                continue
            rid = rec.get("id")
            if not isinstance(rid, str) or rid in seen:
                continue
            if rec.get("duplicate_of") or rec.get("status", "new") not in OPEN_STATUSES:
                continue
            created = parse_time(rec.get("created_at"))
            if created is None or created < since or created > now + timedelta(minutes=5):
                continue
            text = rec.get("text")
            if not isinstance(text, str) or letters(text) < MIN_LETTERS:
                continue
            same = tid is not None and target_id(rec.get("target")) == tid
            dist = None
            other = parse_point(rec.get("point")) if rec.get("point") is not None else None
            if here is not None and other is not None:
                dist = distance_m(here, other)
            if not (same or (dist is not None and dist <= self.radius_m)):
                continue
            seen.add(rid)
            out.append((rec, dist, same))
        return out

    def find(self, text: str, records, *, point=None, target=None, days=None, now: datetime | None = None,
             limit: int = 5) -> list[Match]:
        if not isinstance(text, str) or letters(text) < MIN_LETTERS:
            return []
        if point is None and target_id(target) is None:
            return []  # без места дубль не определяем (см. docstring модуля)
        cands = self.eligible(records, point=point, target=target, days=days, now=now)
        if not cands:
            return []
        query = self.scorer.encode_many([text])[0]
        feats = self.cache.get_many(self.scorer, [(rec["id"], rec["text"]) for rec, _d, _s in cands])
        threshold_for = getattr(self.scorer, "threshold_for", None)
        matches = []
        for (rec, dist, same), f in zip(cands, feats):
            s = self.scorer.score(query, f)
            thr = threshold_for(query, f, self.threshold) if threshold_for else self.threshold
            if s >= thr:
                tgt = rec.get("target")
                matches.append(Match(
                    complaint_id=rec["id"], score=s,
                    target=dict(tgt) if isinstance(tgt, dict) else None,
                    metoo=max(0, int(rec.get("metoo") or 0)),
                    category=rec.get("category"), created_at=rec.get("created_at"), status=rec.get("status"),
                    distance_m=dist, same_target=same))
        # Сначала самое похожее; при равенстве — та же цель, затем ближе, затем больше людей.
        matches.sort(key=lambda m: (-round(m.score, 4), not m.same_target,
                                    m.distance_m if m.distance_m is not None else 1e9, -m.metoo, m.complaint_id))
        return matches[:max(1, int(limit))]
