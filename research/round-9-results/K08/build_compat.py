"""K08 R9: совместимость моего r8 Python-оракула (research/round-8-results/K08/planlib.py @ 7fb81b9) с BUILD d865dd4.

Единственное отличие в определении: BUILD (web/plan.js sourceSnapshot) берёт последним элементом METRIC "haversine-mm-v1",
а мой r8 предлагал FORMULA "haversine:R=6371008.8". Здесь — snapshot по формуле BUILD; остальной r8-код не меняется.
"""
import sys
from pathlib import Path

R8 = Path(__file__).resolve().parents[2] / "round-8-results" / "K08"
sys.path.insert(0, str(R8))
import planlib as P  # noqa: E402


def build_snapshot(ctx, city):
    c = ctx.city(city)
    fsha = ((c.get("files") or {}).get("places_social") or {}).get("sha256")
    return "sha256:" + P.sha256hex(P.js_json([P.SCHEMA, city, c["release"], fsha, P.places_digest(ctx, city), P.METRIC_VERSION]))


def use_build_snapshot():
    """Переключить r8-оракул на snapshot BUILD (для проверки фикстур, построенных под BUILD)."""
    P.source_snapshot = lambda ctx, city, schema=P.SCHEMA: build_snapshot(ctx, city)
    return P
