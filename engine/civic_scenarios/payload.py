"""Проверка payload civic-scenario-v1 и семантика времени.

Время: analysis_at, start_at, end_at — ISO 8601 с явным смещением (Z или ±HH:MM).
Сравнение — по абсолютному моменту (UTC), поэтому 12:00+05:00 и 07:00Z — один момент.
Перекрытие активно, если start_at <= analysis_at < end_at (start включительно, end исключительно).
Пустой или обратный интервал (start_at >= end_at) — ошибка, а не «никогда не активно».
Лишние ключи payload отклоняются: клиент не передаёт метрики, пути к файлам или URL.
"""
import re
from datetime import datetime, timezone

from .errors import ScenarioError

SCHEMA = "civic-scenario-v1"
PLAN_IDS = ("A", "B")
MAX_ORIGINS = 25
MAX_DESTINATIONS = 100
MAX_PAIRS = 1000
MAX_CLOSURES_PER_PLAN = 100
MAX_EDGE_IDS_PER_PLAN = 2000

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$")
TOP_KEYS = {"schema_version", "city", "graph_id", "graph_digest", "mode", "analysis_at",
            "origin_node_ids", "destination_node_ids", "plans"}
PLAN_KEYS = {"id", "closures"}
CLOSURE_KEYS = {"edge_ids", "start_at", "end_at"}


def _bad(msg, code="invalid_payload", **fields):
    raise ScenarioError(code, msg, fields or None)


def parse_ts(value, field):
    if not isinstance(value, str) or not _TS.match(value):
        _bad(f"{field}: ISO 8601 с явным смещением, например 2026-10-07T09:00:00+05:00", field=field)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _bad(f"{field}: недопустимая дата/время", field=field)
    if dt.tzinfo is None or dt.utcoffset() is None:
        _bad(f"{field}: нужно смещение UTC", field=field)
    return dt.astimezone(timezone.utc)


def utc_iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _id_list(value, field, limit):
    if not isinstance(value, list) or not value:
        _bad(f"{field}: непустой массив строк", field=field)
    if len(value) > limit:
        raise ScenarioError("too_large", f"{field}: не больше {limit}", {"field": field, "limit": limit})
    if not all(isinstance(x, str) and x for x in value):
        _bad(f"{field}: элементы — непустые строки", field=field)
    if len(set(value)) != len(value):
        _bad(f"{field}: повторяющиеся ID", field=field)
    return list(value)


def validate_payload(payload, pg):
    """Проверяет payload против подготовленного графа. Возвращает нормализованное описание."""
    if not isinstance(payload, dict):
        _bad("payload — объект")
    extra = sorted(set(payload) - TOP_KEYS)
    if extra:
        _bad("неизвестные поля payload: " + ", ".join(extra[:10]), fields=extra[:10])
    missing = sorted(TOP_KEYS - set(payload))
    if missing:
        _bad("нет полей: " + ", ".join(missing), fields=missing)
    if payload["schema_version"] != SCHEMA:
        _bad(f"schema_version должна быть {SCHEMA}", field="schema_version")
    if payload["city"] != "astana":
        _bad("в раунде 11 поддерживается только city=astana", code="city_mismatch", field="city")
    if pg.city != payload["city"]:
        _bad(f"граф относится к городу {pg.city!r}, payload — к {payload['city']!r}", code="city_mismatch", field="city")
    if payload["graph_id"] != pg.id:
        _bad("graph_id не совпадает с загруженным графом", code="graph_mismatch", field="graph_id")
    if payload["graph_digest"] != pg.digest:
        raise ScenarioError("graph_digest_mismatch", "graph_digest не совпадает с текущей версией графа",
                            {"expected": pg.digest, "got": payload["graph_digest"]})
    if payload["mode"] not in ("walking", "driving"):
        _bad("mode — walking|driving", field="mode")
    if payload["mode"] != pg.mode:
        _bad(f"граф построен для mode={pg.mode}; подмена режима запрещена", code="mode_mismatch", field="mode")
    at = parse_ts(payload["analysis_at"], "analysis_at")

    origins = _id_list(payload["origin_node_ids"], "origin_node_ids", MAX_ORIGINS)
    dests = _id_list(payload["destination_node_ids"], "destination_node_ids", MAX_DESTINATIONS)
    if len(origins) * len(dests) > MAX_PAIRS:
        raise ScenarioError("too_large", f"пар OD больше {MAX_PAIRS}", {"limit": MAX_PAIRS})
    unknown_nodes = sorted({n for n in origins + dests if n not in pg.node_ids})
    if unknown_nodes:
        _bad("неизвестные узлы: " + ", ".join(x[:60] for x in unknown_nodes[:10]), code="unknown_node",
             node_ids=unknown_nodes[:50])

    plans = payload["plans"]
    if not isinstance(plans, list) or not 1 <= len(plans) <= 2:
        _bad("plans: 1–2 плана с id A/B", field="plans")
    seen, norm_plans, unknown_edges = set(), [], set()
    for p in plans:
        if not isinstance(p, dict) or set(p) != PLAN_KEYS:
            _bad("план: ровно поля id, closures", field="plans")
        if p["id"] not in PLAN_IDS or p["id"] in seen:
            _bad("id плана — уникальные A или B", field="plans.id")
        seen.add(p["id"])
        cl = p["closures"]
        if not isinstance(cl, list):
            _bad(f"план {p['id']}: closures — массив", field="closures")
        if len(cl) > MAX_CLOSURES_PER_PLAN:
            raise ScenarioError("too_large", f"план {p['id']}: не больше {MAX_CLOSURES_PER_PLAN} перекрытий")
        n_ids, norm_cl = 0, []
        for j, c in enumerate(cl):
            if not isinstance(c, dict) or set(c) != CLOSURE_KEYS:
                _bad(f"план {p['id']}, перекрытие #{j}: ровно поля edge_ids, start_at, end_at", field="closures")
            ids = c["edge_ids"]
            if not isinstance(ids, list) or not ids or not all(isinstance(x, str) and x for x in ids):
                _bad(f"план {p['id']}, перекрытие #{j}: edge_ids — непустой массив строк", field="edge_ids")
            n_ids += len(ids)
            if n_ids > MAX_EDGE_IDS_PER_PLAN:
                raise ScenarioError("too_large", f"план {p['id']}: не больше {MAX_EDGE_IDS_PER_PLAN} edge_ids")
            unknown_edges.update(x for x in ids if x not in pg.edges)
            s = parse_ts(c["start_at"], "start_at")
            e = parse_ts(c["end_at"], "end_at")
            if s >= e:
                _bad(f"план {p['id']}, перекрытие #{j}: start_at должен быть раньше end_at", field="start_at")
            norm_cl.append({"edge_ids": sorted(set(ids)), "start": s, "end": e,
                            "start_at": c["start_at"], "end_at": c["end_at"]})
        norm_plans.append({"id": p["id"], "closures": norm_cl})
    if unknown_edges:
        u = sorted(unknown_edges)
        _bad("неизвестные рёбра: " + ", ".join(x[:60] for x in u[:10]), code="unknown_edge", edge_ids=u[:50])
    norm_plans.sort(key=lambda p: p["id"])
    return {"at": at, "origins": origins, "destinations": dests, "plans": norm_plans}


def active_closed(plan, at):
    """Множество рёбер, закрытых в момент at, и разбор неактивных перекрытий."""
    closed, inactive = set(), []
    for c in plan["closures"]:
        if c["start"] <= at < c["end"]:
            closed.update(c["edge_ids"])
        else:
            inactive.append({"edge_ids": c["edge_ids"], "start_at": c["start_at"], "end_at": c["end_at"],
                             "reason": "not_started" if at < c["start"] else "ended"})
    return closed, inactive
