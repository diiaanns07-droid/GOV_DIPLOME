"""HTTP-адаптер для R01: маршруты /api/civic/v1/scenarios/* в форме ответа CONTRACT.txt.

    handle(method, path, query=None, body=None) -> None | {status, headers, body}

None — путь не относится к сценариям (R01 передаёт дальше). Тело POST уже разобрано R01 из JSON
с лимитом размера (рекомендуется 64 КБ -> 413). Ответ — {ok:true,data} или {ok:false,error}.
Endpoint'ы только читают подготовленные данные и считают; авторизация не требуется, CSRF не нужен,
потому что состояние не изменяется (R01 может всё равно требовать same-origin).

  GET  /api/civic/v1/scenarios/graphs           список графов (без геометрии) + NOT_READY
  GET  /api/civic/v1/scenarios/graphs/{id}      граф для карты (узлы, рёбра, геометрия, digest)
  GET  /api/civic/v1/scenarios/cases            подготовленные кейсы (payload-шаблоны)
  POST /api/civic/v1/scenarios/compare          compare(payload, load_graph(payload.graph_id))
"""
import time

from .compare import compare
from .errors import ScenarioError
from .registry import list_cases, load_graph, load_graph_dict, manifest

PREFIX = "/api/civic/v1/scenarios"
MAX_BODY_BYTES = 64 * 1024
HEADERS = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}


def _ok(data, status=200):
    return {"status": status, "headers": dict(HEADERS), "body": {"ok": True, "data": data}}


def _err(status, code, message, fields=None):
    e = {"code": code, "message": message}
    if fields:
        e["fields"] = fields
    return {"status": status, "headers": dict(HEADERS), "body": {"ok": False, "error": e}}


def handle(method, path, query=None, body=None):
    if path != PREFIX and not path.startswith(PREFIX + "/"):
        return None
    sub = path[len(PREFIX):].rstrip("/")
    try:
        if sub == "/graphs" and method == "GET":
            m = manifest()
            return _ok({"items": [{k: v for k, v in g.items() if k != "file"} for g in m["graphs"]],
                        "not_ready": m.get("not_ready", [])})
        if sub.startswith("/graphs/") and method == "GET":
            g = load_graph_dict(sub[len("/graphs/"):])
            return _ok({"graph": g})
        if sub == "/cases" and method == "GET":
            return _ok({"items": list_cases()})
        if sub == "/compare" and method == "POST":
            if not isinstance(body, dict):
                return _err(400, "invalid_payload", "ожидается JSON-объект")
            t0 = time.perf_counter()
            res = compare(body, load_graph(body.get("graph_id")))
            res = dict(res, timing_ms=round((time.perf_counter() - t0) * 1000, 1))
            return _ok(res)
        if sub in ("/graphs", "/cases", "/compare") or sub.startswith("/graphs/"):
            return _err(405, "method_not_allowed", "метод не поддерживается")
        return _err(404, "not_found", "неизвестный путь")
    except ScenarioError as e:
        return _err(e.http_status, e.code, e.message, e.fields or None)
