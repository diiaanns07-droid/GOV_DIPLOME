"""Разрыв greedy против exact без деления на 0/null (определения — config/experiment_config.json)."""
from .metric import OBJECTIVES


def gap(objective, g, e):
    """g, e — метрики планов greedy и exact. Возвращает dict; relative = None, если знаменатель не положителен или не определён."""
    keyf = OBJECTIVES[objective]
    out = {"hit": keyf(g) == keyf(e), "unknown_worse": g["unknown_count"] > e["unknown_count"],
           "abs": None, "rel": None, "greedy_better_than_exact": keyf(g) < keyf(e)}
    if out["unknown_worse"]:
        return out
    if objective == "mean":
        if g["unknown_count"] == e["unknown_count"]:
            out["abs"] = g["weighted_sum_mm"] - e["weighted_sum_mm"]
            if e["weighted_sum_mm"] > 0:
                out["rel"] = out["abs"] / e["weighted_sum_mm"]
    elif objective == "minimax":
        if g["max_mm"] is not None and e["max_mm"] is not None:
            out["abs"] = g["max_mm"] - e["max_mm"]
            if e["max_mm"] > 0:
                out["rel"] = out["abs"] / e["max_mm"]
    else:
        out["abs"] = e["covered_weight"] - g["covered_weight"]
        if e["covered_weight"] > 0:
            out["rel"] = out["abs"] / e["covered_weight"]
    return out
