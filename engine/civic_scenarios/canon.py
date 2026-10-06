"""Канонический JSON и дайджесты (sha256, hex).

canonical_json: json.dumps(sort_keys, без пробелов, UTF-8 без экранирования, NaN/Infinity запрещены).
graph digest = sha256(canonical_json(graph без ключа "digest")).
Дайджест — воспроизводимость и защита от подмены, не криптографическая подпись источника.
"""
import hashlib
import json


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_hex(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def graph_digest(graph):
    body = {k: v for k, v in graph.items() if k != "digest"}
    return sha256_hex(body)


def length_mm(length_m):
    """Метры -> целые миллиметры, округление половины вверх (для длин >= 0)."""
    x = length_m * 1000.0
    f = int(x)
    return f + 1 if x - f >= 0.5 else f
