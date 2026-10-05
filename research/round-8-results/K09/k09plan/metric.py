"""haversine-mm-v1 и метрики плана по CORE_SPEC (раздел «РАСЧЁТ»).

Расстояние: гаверсинус, R = 6371008.8 м, вход [lon, lat], промежуточное a зажато в [0, 1];
каждое расстояние ОДИН раз округляется до целых миллиметров floor(d_m*1000 + 0.5) (все значения неотрицательны).
"""
import math

R_EARTH = 6371008.8
INF = float("inf")


def haversine_m(lon1, lat1, lon2, lat2):
    r = math.pi / 180.0
    a = math.sin((lat2 - lat1) * r / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def dist_mm(lon1, lat1, lon2, lat2):
    return int(math.floor(haversine_m(lon1, lat1, lon2, lat2) * 1000 + 0.5))


class Problem:
    """Предвычисленная задача: расстояния точка→источник (минимум) и точка→кандидат в мм.

    sources: [{id, lon, lat}] — исходные записи категории в срезе (kind=source);
    candidates: [{id, lon, lat, cost}] — гипотетические кандидаты (kind=hypothetical);
    points: [{id, lon, lat, weight}].
    Порядок входных массивов не влияет на результат: всё сортируется по id.
    """

    def __init__(self, points, sources, candidates, radius_m):
        self.points = sorted(points, key=lambda p: p["id"])
        self.sources = sorted(sources, key=lambda s: s["id"])
        self.candidates = sorted(candidates, key=lambda c: c["id"])
        self.radius_mm = int(radius_m) * 1000
        self.weights = [int(p["weight"]) for p in self.points]
        self.total_weight = sum(self.weights)
        self.cand_ids = [c["id"] for c in self.candidates]
        self.cand_index = {cid: i for i, cid in enumerate(self.cand_ids)}
        self.cost = [int(c["cost"]) for c in self.candidates]
        # baseline: ближайшая исходная запись (мм, id) или None
        self.base = []
        for p in self.points:
            best = None
            for s in self.sources:
                d = dist_mm(p["lon"], p["lat"], s["lon"], s["lat"])
                if best is None or (d, s["id"]) < best:
                    best = (d, s["id"])
            self.base.append(best)
        # кандидаты: матрица [c][p] мм
        self.cand_mm = [[dist_mm(p["lon"], p["lat"], c["lon"], c["lat"]) for p in self.points] for c in self.candidates]

    def after_vector(self, selected_idx):
        """after_mm по точкам для набора индексов кандидатов (None — нет ни одного объекта)."""
        out = []
        for j in range(len(self.points)):
            b = self.base[j]
            v = b[0] if b is not None else None
            for i in selected_idx:
                d = self.cand_mm[i][j]
                if v is None or d < v:
                    v = d
            out.append(v)
        return out

    def metrics_from_after(self, after, selected_idx):
        unknown = sum(1 for v in after if v is None)
        wsum = sum(w * v for w, v in zip(self.weights, after) if v is not None)
        covered = sum(w for w, v in zip(self.weights, after) if v is not None and v <= self.radius_mm)
        return {
            "unknown_count": unknown,
            "weighted_sum_mm": wsum,
            "weighted_mean_mm": (wsum / self.total_weight) if unknown == 0 and self.total_weight > 0 else None,
            "max_mm": max(after) if unknown == 0 and after else None,
            "covered_weight": covered,
            "coverage_fraction": (covered / self.total_weight) if self.total_weight > 0 else None,
            "cost": sum(self.cost[i] for i in selected_idx),
            "selected_ids": sorted(self.cand_ids[i] for i in selected_idx),
        }

    def evaluate(self, selected_idx):
        after = self.after_vector(selected_idx)
        return self.metrics_from_after(after, selected_idx)

    def rows(self, selected_idx):
        """Таблица по точкам: before/after/delta в мм с источником ближайшего (source|hypothetical)."""
        rows = []
        for j, p in enumerate(self.points):
            b = self.base[j]
            best = (b[0], 0, b[1]) if b is not None else None        # (мм, kind_rank 0=source, id)
            for i in selected_idx:
                cand = (self.cand_mm[i][j], 1, self.cand_ids[i])
                if best is None or cand < best:
                    best = cand
            before = b[0] if b is not None else None
            after = best[0] if best is not None else None
            rows.append({"point_id": p["id"], "weight": p["weight"], "before_mm": before, "after_mm": after,
                         "delta_mm": (before - after) if before is not None and after is not None else None,
                         "nearest_after": None if best is None else {"kind": "source" if best[1] == 0 else "hypothetical", "id": best[2]}})
        return rows


def key_mean(m):
    return (m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"], m["cost"], m["selected_ids"])


def key_minimax(m):
    return (m["unknown_count"], INF if m["max_mm"] is None else m["max_mm"], m["weighted_sum_mm"], m["cost"], m["selected_ids"])


def key_coverage(m):
    return (-m["covered_weight"], m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"], m["cost"], m["selected_ids"])


OBJECTIVES = {"mean": key_mean, "minimax": key_minimax, "coverage": key_coverage}
