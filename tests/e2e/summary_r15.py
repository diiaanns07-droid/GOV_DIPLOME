#!/usr/bin/env python3
"""R10 · раунд 15 · сводка приёмки сборки: ACCEPTANCE.md + VERDICT.json («можно показывать: да / нет» с причинами).

    python3 tests/e2e/summary_r15.py <папка отчёта acceptance_r15.sh> [--base research/round-15-results/R10/final4-a4937462/e2e]

Читает то, что положили шаги acceptance_r15.sh (api/API_V2.json, numbers/CONSISTENCY.json, e2e/RESULT.json, v2/RESULT.json,
map/…, ref/TOTALS.json, video/MANIFEST.json), и сравнивает часть 1 с базой FINAL-4 (172 / 0 / 0, время шагов).
Правила вердикта (CONTRACT §0, R10.txt «Готово, когда»):
  - часть 1 без регресса: demo_flow FAIL = 0; время варианта не больше базы FINAL-4 более чем на 25 % (иначе «смотреть»);
  - сцены 7–9: FAIL = 0 (на FINAL-5 ещё и NOT_RUN = 0: всё должно быть в сборке);
  - числа: FAIL = 0 в сверках A, B, C, D, E, F;
  - API v2: жёсткие правила (нет 500, сотрудник закрыт, приватность) — FAIL = 0;
  - pytest tests/civic/R10 зелёный; ролик (если записывали) — все сцены сняты.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HARD_API_AREAS = ("доступ", "журнал")


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def chain(out: Path) -> dict:
    steps = {}
    for line in (out / "chain.log").read_text(encoding="utf-8").splitlines() if (out / "chain.log").exists() else []:
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("label", "root", "sha"):
            steps[parts[0]] = " ".join(parts[1:])
        elif len(parts) >= 2 and parts[1].lstrip("-").isdigit():
            steps[parts[0]] = {"rc": int(parts[1]), "time": parts[2] if len(parts) > 2 else ""}
    return steps


def e2e_timing(result) -> dict:
    out = {}
    for layer, t in (result or {}).get("timing", {}).items():
        if layer.startswith("UI "):
            out[layer] = round(t.get("total_ms", 0) / 1000, 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--base", default="research/round-15-results/R10/final4-a4937462/e2e")
    ap.add_argument("--final", action="store_true", help="сборка FINAL-5: сцены 7–9 без NOT_RUN")
    a = ap.parse_args()
    out = Path(a.out)
    ch = chain(out)
    label = ch.get("label", out.name)
    final = a.final or bool(re.search(r"FINAL-5", label))
    reasons, watch, lines = [], [], []

    # pytest
    pt = (out / "pytest.log").read_text(encoding="utf-8") if (out / "pytest.log").exists() else ""
    m = re.search(r"(\d+) passed(?:, (\d+) failed)?", pt)
    failed_pt = int(re.search(r"(\d+) failed", pt).group(1)) if re.search(r"(\d+) failed", pt) else 0
    lines.append(f"| pytest tests/civic/R10 | {m.group(0) if m else 'нет данных'} |")
    if failed_pt:
        reasons.append(f"pytest R10: {failed_pt} FAIL")

    # API v2
    api = load(out / "api" / "API_V2.json")
    if api:
        hard = [r for r in api["rows"] if r["status"] == "FAIL" and (r["area"] in HARD_API_AREAS or "→ 5" in r["name"])]
        other = [r for r in api["rows"] if r["status"] == "FAIL" and r not in hard]
        lines.append(f"| API v2 (CONTRACT §7) | PASS {api['counts']['PASS']} · FAIL {api['counts']['FAIL']} · NOT_RUN "
                     f"{api['counts']['NOT_RUN']} (жёстких FAIL {len(hard)}) |")
        if hard:
            reasons.append("API v2: " + "; ".join(r["name"] for r in hard[:4]))
        if other:
            watch.append("API v2 (формат/примеры): " + "; ".join(r["name"] for r in other[:4]))
    else:
        reasons.append("API v2: нет отчёта")

    # Числа
    num = load(out / "numbers" / "CONSISTENCY.json")
    if num:
        fails = [c for c in num["checks"] if c["status"] == "FAIL"]
        lines.append(f"| Согласованность чисел | PASS {num['counts']['PASS']} · FAIL {num['counts']['FAIL']} · NOT_RUN "
                     f"{num['counts']['NOT_RUN']} |")
        for c in fails:
            reasons.append(f"числа: {c['name']} — {json.dumps(c['values'], ensure_ascii=False)[:120]}")
        if final:
            nr = [c["name"] for c in num["checks"] if c["status"] == "NOT_RUN"]
            if nr:
                reasons.append("числа на FINAL-5 не проверены: " + "; ".join(nr[:4]))
    else:
        reasons.append("числа: нет отчёта")

    # Часть 1
    e2e = load(out / "e2e" / "RESULT.json")
    base = load(Path(a.base) / "RESULT.json")
    if e2e:
        c = e2e["counts"]
        lines.append(f"| Часть 1 (шаги 1–7 FINAL-4) | PASS {c['PASS']} · FAIL {c['FAIL']} · NOT_RUN {c['NOT_RUN']} "
                     f"(база FINAL-4: 172 / 0 / 0) |")
        if c["FAIL"]:
            bad = [r for r in e2e["results"] if r["status"] == "FAIL"]
            reasons.append("часть 1: " + "; ".join(f"{r['layer']} {r['step']} {r['name'][:60]}" for r in bad[:4]))
        now_t, base_t = e2e_timing(e2e), e2e_timing(base)
        for layer, t in now_t.items():
            b = base_t.get(layer)
            if b and t > b * 1.25:
                watch.append(f"часть 1 медленнее FINAL-4: {layer} {t} с против {b} с (+{round((t / b - 1) * 100)} %)")
        if now_t:
            lines.append("| Время части 1, с | " + ", ".join(f"{k.replace('UI ', '')} {v}" + (f" (FINAL-4 {base_t[k]})" if k in base_t else "")
                                                    for k, v in now_t.items()) + " |")
    else:
        reasons.append("часть 1: нет отчёта")

    # Сцены 7–9
    v2 = load(out / "v2" / "RESULT.json")
    if v2:
        c = v2["counts"]
        lines.append(f"| Сцены 7–9 «Бірге» | PASS {c['PASS']} · FAIL {c['FAIL']} · NOT_RUN {c['NOT_RUN']} |")
        bad = [r for r in v2["results"] if r["status"] == "FAIL"]
        if bad:
            reasons.append("сцены 7–9: " + "; ".join(f"{r['layer']} {r['step']} {r['name'][:60]}" for r in bad[:4]))
        if final and c["NOT_RUN"]:
            nr = [r for r in v2["results"] if r["status"] == "NOT_RUN"]
            reasons.append("сцены 7–9 на FINAL-5 не проверены: " + "; ".join(f"{r['step']} {r['name'][:50]}" for r in nr[:4]))
        elif c["NOT_RUN"]:
            watch.append(f"сцены 7–9: NOT_RUN {c['NOT_RUN']} (модулей/экранов нет в сборке)")
    else:
        reasons.append("сцены 7–9: нет отчёта")

    # Карта: первый значок
    mp = load(out / "map" / "BASELINE.json")
    if mp:
        badge = []
        for k, v in (mp.get("cases") or {}).items():
            med = (v or {}).get("median") or {}
            if isinstance(med.get("first_badge"), (int, float)):
                badge.append((k, round(med["first_badge"])))
        if badge:
            worst = max(b for _, b in badge)
            lines.append(f"| Первый значок карты, мс | {', '.join(f'{k} {v}' for k, v in badge[:8])} |")
            if worst > 3000:
                watch.append(f"первый значок карты {worst} мс > 3 с")

    # Эталон
    ref = load(out / "ref" / "TOTALS.json")
    if ref:
        lines.append(f"| Эталон A (47 элементов) | {json.dumps(ref, ensure_ascii=False)[:160]} |")

    # Ролик
    vid = load(out / "video" / "MANIFEST.json")
    if vid:
        for r in vid.get("runs", []):
            bad = [s["id"] for s in r.get("scenes", []) if not s.get("ok")]
            lines.append(f"| Ролик {r['lang']} | {r.get('duration_s')} с, {r.get('mp4') or r.get('webm')}, "
                         f"сцены {len(r.get('scenes', []))}{', пропущено: ' + ', '.join(x['scene'] for x in r.get('skipped', [])) if r.get('skipped') else ''} |")
            if bad:
                watch.append(f"ролик {r['lang']}: не снято {bad}")

    verdict = "да" if not reasons else "нет"
    md = [f"# R10 · приёмка сборки {label}", "", f"Код: `{ch.get('sha', '?')}` · отчёт: `{out}`", "",
          f"## Можно показывать: **{verdict}**", ""]
    md += [f"- ❌ {r}" for r in reasons] or ["- блокеров нет"]
    if watch:
        md += ["", "Смотреть (не блокирует):"] + [f"- {w}" for w in watch]
    md += ["", "| Проверка | Итог |", "|---|---|", *lines, "", "Шаги (код возврата, время):", "",
           "```", *[f"{k} {v}" for k, v in ch.items()], "```"]
    (out / "ACCEPTANCE.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out / "VERDICT.json").write_text(json.dumps({"label": label, "sha": ch.get("sha"), "show": verdict,
                                                  "reasons": reasons, "watch": watch}, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
