"""R13 · раунд 15: собрать DELIVERY.json из git и итогов проверок (CONTRACT §12).

    python3 research/round-15-results/R13/make_delivery.py --code-sha <sha> --pytest "176/0" --browser "146/146" \
        [--browser-quick 90/90] [--qa 95/95] [--push OK|FAILED|PENDING]

code_sha — коммит с кодом поставки (его берёт R01); tested_sha — на чём гонялись проверки (обычно тот же).
Пути — только R13 (CONTRACT §2) и их изменения от основы раунда (base_sha).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("DELIVERY.json")
BASE_SHA = "e91acb69b22d4076938a5f8f90c93501de495eeb"  # origin/claude/clever-hypatia-q6ts4g при старте роли (FINAL-4 + пакет)
BRANCH = "claude/gifted-mayer-p86myv"
OWN_PATHS = ("ml/civic_forecast/", "ui/civic_forecast/", "ui/civic_qa/", "web/civic/qa/", "ui/civic_meetings/",
             "web/civic/meetings/", "tests/civic/R13/", "research/round-15-results/R13/",
             "research/handoffs/astana/R13/round15/")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-sha", required=True)
    ap.add_argument("--tested-sha")
    ap.add_argument("--pytest", required=True, help="PASS/FAIL, напр. 170/0")
    ap.add_argument("--browser", default="NOT_RUN", help="PASS/всего браузерной проверки, напр. 125/125")
    ap.add_argument("--browser-sha", help="на каком коммите шла браузерная проверка (если не на code_sha)")
    ap.add_argument("--browser-quick", help="быстрый прогон 1366/375 × ru/kk, напр. 90/90")
    ap.add_argument("--qa", help="«Вопрос акиму» qa_browser.cjs, напр. 95/95")
    ap.add_argument("--browser-env", default="облако: FINAL-4 e91acb69 + патчи R13 для R01 (маршруты, ассеты, лист слева)",
                    help="на какой сборке шёл браузер")
    ap.add_argument("--regress", help="быстрый прогон на втором стенде (FINAL-4 + патчи), напр. 90/90")
    ap.add_argument("--push", default="OK")
    args = ap.parse_args()
    code = git("rev-parse", args.code_sha)
    changed = [p for p in git("diff", "--name-only", BASE_SHA, code).splitlines() if p.startswith(OWN_PATHS)]
    passed, failed = (int(x) for x in args.pytest.split("/"))

    def run(value, command, note):
        if not value:
            return {"status": "NOT_RUN", "note": "в этой поставке не гонялся"}
        ok, total = (int(x) for x in value.split("/"))
        return {"status": "PASS" if ok == total else "FAIL", "passed": ok, "total": total, "command": command,
                "sha": git("rev-parse", args.browser_sha or code), "note": note}
    screens = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "research/round-15-results/R13/screens").glob("*.jpg"))
    browser = {"status": "NOT_RUN", "note": "нет стенда с маршрутами meetings.*"} if args.browser == "NOT_RUN" else {
        "status": "PASS" if args.browser.split("/")[0] == args.browser.split("/")[1] else "FAIL",
        "passed": int(args.browser.split("/")[0]), "total": int(args.browser.split("/")[1]),
        "command": "tests/civic/R13/meetings/meetings_browser.cjs --full (BIRGE_URL стенда)",
        "sha": git("rev-parse", args.browser_sha or code),
        "env": args.browser_env + ", CIVIC_DEMO=1, Chromium 1194; подложка карты — упрощённый фон (нет интернета)",
        "note": "1366/1024/375 × ru/kk, все состояния; замер R10 B-118: зоны нажатия ≥ 44 px и текст ≥ 13 px на списке, "
                "встрече, вкладке «Вопросы» и у акимата; кадры screens/ — с этого прогона",
        "quick_run": run(args.browser_quick, "meetings_browser.cjs (1366/375 × ru/kk)", "быстрый прогон на свежей базе"),
        "regress_final4": run(args.regress, "meetings_browser.cjs (1366/375 × ru/kk)",
                              "второй стенд: FINAL-4 e91acb69 + патчи R13 (лист слева), свежая база")}
    data = {
        "role": "R13",
        "title": "Встречи с акимом, вопросы жителей, прогноз на экране",
        "branch": BRANCH,
        "base_sha": BASE_SHA,
        "restored_from": None,
        "restored_note": "путь R13 в FINAL-4 = поставка 6 раунда 14 (0487f2a6), восстанавливать нечего",
        "code_sha": code,
        "tested_sha": git("rev-parse", args.tested_sha or code),
        "push_status": args.push,
        "changed_paths": changed,
        "tests": {
            "pytest_tests_civic_R13": {"status": "PASS" if failed == 0 else "FAIL", "passed": passed, "failed": failed,
                                       "command": "python3 -m pytest -q tests/civic/R13"},
            "browser_meetings": browser,
            "browser_qa": run(args.qa, "tests/civic/R13/qa/qa_browser.cjs (BIRGE_REPO стенда)",
                              "«Вопрос акиму»: 375/1366 × ru/kk, житель и акимат; после правок B-118 (44 px, 13 px)"),
            "r08_contract_on_r08_branch": {"status": "PASS", "note": "R08 claude/inspiring-johnson-j7wksj @ eca77d34: "
                                           "neighbors.Neighbors + blocks.forecast / meetings_from_block поверх модулей R13 — "
                                           "прогноз source r13, 5 пунктов с причиной (reasons[0]); встречи source r13 (ручной прогон)"},
            "seed_world_on_r02_world": {"status": "PASS", "note": "world_v1.json R02 @ ac75f3a8: 3 встречи, 17 вопросов (9 общих) — "
                                        "24 записи, повтор reset 24; вкладки «Вопроса акиму» 8 / 6 / 2"},
            "r01_gateway": {"status": "PASS", "passed": 3, "total": 3,
                            "note": "test_r13_meetings_gateway.py на ui/web_server.py R01 @ c9069723 (8 маршрутов meetings.*)"},
            "r06_feed_contract": {"status": "PASS", "note": "R06 notify.py @ c2604ea2: updates(device, since, db_path=…, limit=…), "
                                  "LINK_RE и KINDS принимают события R13"},
        },
        "screens": screens,
        "integration": "research/round-15-results/R13/INTEGRATION.txt",
        "patches_for_r01": ["research/round-15-results/R13/patches/r01_meetings_routes.patch",
                            "research/round-15-results/R13/patches/r01_meetings_assets_sheet.patch"],
        "known_limits": [
            "Маршруты meetings.* и файлы раздела R01 уже взял в B0 (c9069723: 8 маршрутов, ассеты, теги); новые правки R13 "
            "войдут в сборку с B1 по code_sha этой поставки.",
            "Раздел в сборке R01 B0 — левой шторкой 412 px (патч R13 §3); если R11 + R01 переведут разделы в экран-колонку "
            "720 px (IA §5) — вёрстка готова (кадры 1366-ru-col720-*.jpg).",
            "Прогноз — прототип на синтетической истории жалоб (погода реальная); на настоящих обращениях не проверялся.",
            "Названия связанных проектов и работ — из R06 той же базы (публичные функции); без R06 строка поручения пишет "
            "«Связано с проектом акимата» / «…с работой службы», номер записи — только в подсказке сотруднику.",
            "Кадры — облако без подложки карты (П1 правило 6); кадры с настоящей картой — LOCAL-12.",
        ],
        "next_step": "B1 R01 (16 окт 14:00): сверить сборку (маршруты, ассеты, путь раздела) и прогнать meetings_browser.cjs на ней; "
                     "R10 — повтор B-105 и B-118; R11 — R13-2 (колонка 720 px) и новые ключи meet.staff.link_pick_*.",
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: code_sha {code[:10]}, {len(changed)} путей, {len(screens)} кадров")


if __name__ == "__main__":
    main()
