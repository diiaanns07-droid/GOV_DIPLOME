"""Реестр подготовленных графов: сервер загружает граф только по graph_id из graphs/MANIFEST.json.

Клиент не может передать путь, URL или содержимое графа. Файл сверяется с file_sha256 манифеста
и с digest внутри графа; подготовленный индекс кэшируется в памяти процесса.
"""
import hashlib
import json
import threading
from pathlib import Path

from .errors import ScenarioError
from .graph import prepare_graph

GRAPHS = Path(__file__).resolve().parent / "graphs"
CASES = Path(__file__).resolve().parent / "cases"
_lock = threading.Lock()
_cache = {}


def manifest():
    return json.loads((GRAPHS / "MANIFEST.json").read_text("utf-8"))


def _entry(graph_id):
    if not isinstance(graph_id, str):
        raise ScenarioError("unknown_graph", "graph_id — строка")
    for g in manifest()["graphs"]:
        if g["id"] == graph_id:
            return g
    raise ScenarioError("unknown_graph", "graph_id не входит в список подготовленных графов")


def load_graph_dict(graph_id):
    e = _entry(graph_id)
    raw = (GRAPHS / e["file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != e["file_sha256"]:
        raise ScenarioError("graph_digest_mismatch", "файл графа изменён относительно MANIFEST.json")
    g = json.loads(raw.decode("utf-8"))
    if g.get("id") != graph_id or g.get("digest") != e["digest"]:
        raise ScenarioError("graph_digest_mismatch", "граф не совпадает с MANIFEST.json")
    return g


def load_graph(graph_id):
    """PreparedGraph из кэша (проверка digest — при первой загрузке)."""
    with _lock:
        pg = _cache.get(graph_id)
        if pg is None:
            pg = prepare_graph(load_graph_dict(graph_id))
            _cache[graph_id] = pg
        return pg


def list_cases():
    out = []
    for p in sorted(CASES.glob("*.case.json")):
        c = json.loads(p.read_text("utf-8"))
        out.append(c)
    return out
