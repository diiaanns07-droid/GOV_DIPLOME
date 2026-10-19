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
  - pytest tests/civic/R10 зелёный; ролик (если записывали) — все сцены сняты;
  - качество вида (шрифт, зоны нажатия, контраст, термины), производительность, аудит экранов, эталон A — «смотреть»
    (показ они не ломают, дефекты — в BUGS); нарушение П1 «Без ИИ-слопа» и «Хроника» не доигрывает — блокируют.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HARD_API_AREAS = ("доступ", "журнал")
# Проверки качества вида (VISUAL_BRIEF §4): шрифт, зоны нажатия, контраст, термины — показ не ломают, идут в «смотреть»
# со ссылкой на BUGS. Функциональные шаги, русские подписи на ҚАЗ, ключи перевода на экране и числа — блокируют.
LIMIT_TAIL = re.compile(r"\s*≤ 1 с$")  # «… → раздел yard ≤ 1 с» → «… → раздел yard» в строке «Смотреть»
QUALITY = re.compile(r"шрифт|зоны нажатия|контраст|мелкого текста|термин словаря|значок «ИИ»", re.I)


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
    ap.add_argument("--ref-before", default="research/round-15-results/R10/final4-a4937462/ref",
                    help="прогон эталона FINAL-4 (TOTALS.json) — база «не хуже»")
    a = ap.parse_args()
    out = Path(a.out)
    ch = chain(out)
    label = ch.get("label", out.name)
    final = a.final or bool(re.search(r"FINAL-[56]", label))
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
        fails = [c for c in num["checks"] if c["status"] == "FAIL" and c.get("blocking", True)]
        for c in num["checks"]:
            if c["status"] == "FAIL" and not c.get("blocking", True):
                watch.append(f"числа (не блокирует): {c['name']} — {json.dumps(c['values'], ensure_ascii=False)[:120]}")
        lines.append(f"| Согласованность чисел | PASS {num['counts']['PASS']} · FAIL {num['counts']['FAIL']} · NOT_RUN "
                     f"{num['counts']['NOT_RUN']} |")
        for c in fails:
            reasons.append(f"числа: {c['name']} — {json.dumps(c['values'], ensure_ascii=False)[:120]}")
        if final:
            nr = [c["name"] for c in num["checks"] if c["status"] == "NOT_RUN" and not c.get("optional")]
            if nr:
                reasons.append("числа на FINAL-5 не проверены: " + "; ".join(nr[:4]))
    else:
        reasons.append("числа: нет отчёта")

    # Сцена 0 «ИИ-разбор» по API (П3, R04): блокеры — доступ, числа итога, созданные записи; остальное — «смотреть».
    ink = load(out / "intake" / "INTAKE.json")
    if ink:
        c = ink["counts"]
        s = ((ink.get("facts") or {}).get("analyze_sample") or {}).get("summary") or {}
        line = (f" — {s.get('total')} обращений → {s.get('tasks')} задач · {s.get('services')} служб · {s.get('urgent')} срочных · "
                f"{s.get('merged')} склеено · ready {s.get('ready')}" if s else "")
        lines.append(f"| Сцена 0 «ИИ-разбор» (API intake) | PASS {c['PASS']} · FAIL {c['FAIL']} (ломают показ {c.get('blocking', 0)}) · "
                     f"NOT_RUN {c['NOT_RUN']}{line} |")
        hard = [r for r in ink["rows"] if r.get("blocking")]
        soft = [r for r in ink["rows"] if r["status"] == "FAIL" and not r.get("blocking")]
        if hard:
            reasons.append("сцена 0 (API): " + "; ".join(f"{r['name'][:70]} ({r['owner']})" for r in hard[:4]))
        if soft:
            watch.append("сцена 0 (API), не блокирует: " + "; ".join(f"{r['name'][:60]} ({r['owner']})" for r in soft[:5]))
        if c["NOT_RUN"] and not c["PASS"]:
            watch.append("сцены 0 «ИИ-разбор» нет в сборке (маршрутов или модуля R04) — показ без неё (П3)")

    # Часть 1
    e2e = load(out / "e2e" / "RESULT.json")
    base = load(Path(a.base) / "RESULT.json")
    if e2e:
        c = e2e["counts"]
        lines.append(f"| Часть 1 (шаги 1–7 FINAL-4) | PASS {c['PASS']} · FAIL {c['FAIL']} · NOT_RUN {c['NOT_RUN']} "
                     f"(база FINAL-4: 172 / 0 / 0) |")
        if c["FAIL"]:
            bad = [r for r in e2e["results"] if r["status"] == "FAIL" and not QUALITY.search(r["name"])]
            soft = [r for r in e2e["results"] if r["status"] == "FAIL" and QUALITY.search(r["name"])]
            if bad:
                reasons.append("часть 1: " + "; ".join(f"{r['layer']} {r['step']} {r['name'][:60]}" for r in bad[:4]))
            if soft:
                watch.append("часть 1, качество вида: " + "; ".join(f"{r['layer']} {r['step']} {r['name'][:50]}" for r in soft[:4]))
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
        lines.append(f"| Сцены 0 и 7–9 «Бірге» | PASS {c['PASS']} · FAIL {c['FAIL']} · NOT_RUN {c['NOT_RUN']}"
                     + (f" · ИНФО {c['INFO']}" if c.get("INFO") else "") + " |")
        info = [r for r in v2["results"] if r["status"] == "INFO"]
        if info:
            watch.append("сцены 7–9, проверить на ноутбуке (облако — программный WebGL): " + "; ".join(
                f"{r['layer']} {r['step']} {LIMIT_TAIL.sub('', r['name'])[:70]}: {((r.get('detail') or {}).get('ms'))} мс, без кадров карты "
                f"{((r.get('detail') or {}).get('ms_without_map_frames'))} мс" for r in info[:4]))
        bad = [r for r in v2["results"] if r["status"] == "FAIL" and not QUALITY.search(r["name"]) and not r.get("soft")]
        soft = [r for r in v2["results"] if r["status"] == "FAIL" and QUALITY.search(r["name"]) and not r.get("soft")]
        # «Смотреть» (soft): сцена 0 — время, «Почему так», Tab, Esc, П1, метки; значок «ИИ» (П3) — показ не ломают.
        marked = [r for r in v2["results"] if r["status"] == "FAIL" and r.get("soft")]
        if marked:
            watch.append("сцены 0 и 7–9, не блокирует: " + "; ".join(f"{r['layer']} {r['step']} {r['name'][:55]} ({r.get('owner')})" for r in marked[:6])
                         + (f" и ещё {len(marked) - 6}" if len(marked) > 6 else ""))
        if bad:
            reasons.append("сцены 0 и 7–9: " + "; ".join(f"{r['layer']} {r['step']} {r['name'][:60]}" for r in bad[:4]))
        if soft:
            owners = sorted({r.get("owner") or "?" for r in soft})
            watch.append(f"сцены 7–9, качество вида: {len(soft)} FAIL (шрифт / зоны / контраст / термины) у {', '.join(owners)} — BUGS")
        # Сцена 0 и «смотреть»-строки (soft) на FINAL — не блокеры: без экрана R04 показ идёт без сцены 0 (П3).
        nr_hard = [r for r in v2["results"] if r["status"] == "NOT_RUN" and r["step"] != "0" and not r.get("soft")]
        nr0 = [r for r in v2["results"] if r["status"] == "NOT_RUN" and r["step"] == "0"]
        if final and nr_hard:
            reasons.append("сцены 7–9 на FINAL не проверены: " + "; ".join(f"{r['step']} {r['name'][:50]}" for r in nr_hard[:4]))
        elif c["NOT_RUN"]:
            watch.append(f"сцены 0 и 7–9: NOT_RUN {c['NOT_RUN']} (модулей/экранов нет в сборке" + (f"; сцена 0 — {len(nr0)}" if nr0 else "") + ")")
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

    # Производительность (perf_check): значок, «Хроника», «Спросить Birge».
    perf = load(out / "perf" / "PERF.json")
    if perf:
        rows = perf.get("rows") or perf.get("results") or []
        for r in rows:
            name, st = r.get("name", ""), r.get("status")
            if st == "FAIL" and re.search(r"доигрывает", name):
                reasons.append(f"«Хроника»: {name}")
            elif st == "FAIL":
                watch.append(f"производительность: {name} — {json.dumps(r.get('detail') or r.get('value'), ensure_ascii=False)[:100]}")
        lines.append("| Производительность | " + "; ".join(f"{r.get('status')} {r.get('name', '')[:40]}" for r in rows[:5]) + " |")
    # Аудит новых экранов (visual_audit).
    aud = load(out / "audit" / "AUDIT.json")
    if aud:
        ac = aud.get("counts") or {}
        lines.append(f"| Аудит экранов (VISUAL_BRIEF §4, П1) | PASS {ac.get('PASS')} · WARN {ac.get('WARN')} · FAIL {ac.get('FAIL')} · "
                     f"NOT_RUN {ac.get('NOT_RUN')} |")
        p1 = [r for r in aud.get("rows", []) if r.get("status") == "FAIL" and r.get("check", "").startswith("П1")]
        if p1:
            reasons.append("П1 «Без ИИ-слопа»: " + "; ".join(f"{r['screen']} ({r['owner']})" for r in p1[:4]))
        if ac.get("FAIL"):
            owners = sorted({r.get("owner") for r in aud.get("rows", []) if r.get("status") == "FAIL"})
            watch.append(f"аудит экранов: FAIL {ac.get('FAIL')} у {', '.join(o for o in owners if o)} — BUGS")

    # Эталон A: «не хуже FINAL-4» — число совпавших / близких элементов и доля совпавших пикселей.
    ref = load(out / "ref" / "TOTALS.json")
    if ref:
        sc = ref.get("score") or {}
        was = (load(Path(a.ref_before) / "TOTALS.json") or {}).get("score") or {}
        not_open = [k for k, v in ((load(out / "ref" / "REFERENCE.json") or {}).get("report") or {}).items()
                    if isinstance(v, dict) and not v.get("reached")]
        lines.append(f"| Эталон A (47 элементов) | совпадает/близко {sc.get('ok')} из {sc.get('total')}, пиксели {sc.get('pixels')} % "
                     f"(FINAL-4: {was.get('ok', '?')} из {was.get('total', '?')}, {was.get('pixels', '?')} %)"
                     + (f"; не открылось: {', '.join(not_open)}" if not_open else "") + " |")
        if was and isinstance(sc.get("ok"), int) and isinstance(was.get("ok"), int) and sc["ok"] < was["ok"]:
            watch.append(f"эталон A хуже FINAL-4: {sc['ok']} из {sc.get('total')} против {was['ok']} "
                         f"(по ролям {json.dumps(sc.get('roles'), ensure_ascii=False)})"
                         + (f"; состояние не открылось: {', '.join(not_open)}" if not_open else ""))

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
