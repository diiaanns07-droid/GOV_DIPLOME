#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Минимальное воспроизведение несовместимости K12 patch (v1.1) и k05r4_contract (v1.2 @ 42051600).

  python repro_incompat.py --k05-root <app>/inputs/k05_root [--k05r4 FILE]

k05-root — каталог с round-3-results/K05 и next-round/K05 (например, сборка после K12 patch).
Печатает результат двух вызовов v1.2 на синтетических записях (два непересекающихся квадрата одного города).
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k05r5_compat as T  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k05-root", type=Path, required=True)
    ap.add_argument("--k05r4", type=Path, default=T.DEFAULT_K05R4)
    a = ap.parse_args()
    C, sha = T.load_contract(a.k05_root)
    V12 = T.load_v12(a.k05r4)
    print("контракт v1.1:", T.VARIANTS.get(sha, sha[:12]), "| v1.2:", a.k05r4)
    sq_a = T.v12_square("kz.shymkent.sq_a", [69.59, 42.30, 69.61, 42.32], value=2)
    sq_b = T.v12_square("kz.shymkent.sq_b", [69.70, 42.40, 69.72, 42.42], value=3)
    for title, call in [
        ("1) сумма двух непересекающихся квадратов", lambda: V12.aggregate_sum([sq_a, sq_b])),
        ("2) та же сумма с expected_units", lambda: V12.aggregate_sum(
            [sq_a, sq_b], expected_units=["kz.shymkent.sq_a", "kz.shymkent.sq_b", "kz.shymkent.sq_c"])),
    ]:
        try:
            print(title, "→", call())
        except Exception as e:  # noqa: BLE001
            print(title, "→", type(e).__name__, e)


if __name__ == "__main__":
    main()
