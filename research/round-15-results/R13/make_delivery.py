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
        "note": "1366/1024/375 × ru/kk, все состояния; замер R10 B-118 и VISUAL_BRIEF §4 п. 3: зоны нажатия ≥ 44 px, текст "
                "≥ 13 px, не больше 3 размеров шрифта (13 / 15 / 19) на списке, встрече, вкладке «Вопросы», у акимата — "
                "список, новая встреча, форма поручения; кадры screens/ — с этого прогона",
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
                              "«Вопрос акиму»: 375/1366 × ru/kk, житель и акимат; 44 px, 13 px, не больше 3 размеров "
                              "шрифта (житель, «С ответом», очередь, отказ, ответ)"),
            "r08_contract_on_r08_branch": {"status": "PASS", "note": "R08 claude/inspiring-johnson-j7wksj @ eca77d34: "
                                           "neighbors.Neighbors + blocks.forecast / meetings_from_block поверх модулей R13 — "
                                           "прогноз source r13, 5 пунктов с причиной (reasons[0]); встречи source r13 (ручной прогон)"},
            "seed_world_on_r02_world": {"status": "PASS", "note": "world_v1.json R02 @ ac75f3a8: 3 встречи, 17 вопросов (9 общих) — "
                                        "24 записи, повтор reset 24; вкладки «Вопроса акиму» 8 / 6 / 2"},
            "r01_gateway": {"status": "PASS", "passed": 3, "total": 3,
                            "note": "test_r13_meetings_gateway.py на ui/web_server.py R01 @ c9069723 (8 маршрутов meetings.*)"},
            "r06_feed_contract": {"status": "PASS", "note": "R06 notify.py @ c2604ea2: updates(device, since, db_path=…, limit=…), "
                                  "LINK_RE и KINDS принимают события R13"},
            "r06_feed_e2e_on_r01_build": {"status": "PASS", "note": "сборка R01 197ad600 (B0.4, BirgeNotify R06), демо-мир: вопрос к "
                                          "m-w15-2 → публикация сотрудником → «Уведомления»: «Ваш вопрос к встрече опубликован» "
                                          "(sources R13 ok) → нажатие открывает #meetings/m-w15-2/q-… с прокруткой к вопросу"},
            "r08_contract_first_branch": {"status": "PASS", "note": "R08 claude/laughing-euler-iv3on3 @ b8838abe (её берёт R01 в B0.3): "
                                          "neighbors.forecast — r13-week, 5 пунктов с причиной; neighbors.meetings — r13, counts"},
            "neighbor_tests_on_r01_build": {"status": "PASS", "passed": 437, "failed": 0,
                                            "note": "сборка R01 197ad600 (B0.4) с модулями и тестами R13 этой поставки: tests/civic/R01/"
                                            "round15/test_r01_round15_routes.py, R03 test_analyst_neighbours.py, R06 test_r06r15_notify.py, "
                                            "R08 test_r08_board.py + test_r08_world.py, R15 test_r15_qa.py + round15 notify/meetings, tests/civic/R13"},
            "r15_meetings_tests": {"status": "PASS", "passed": 39, "total": 39,
                                   "note": "R15 @ b7b75ee3 на сборке R01 B0.15 с кодом R13 этой поставки: "
                                   "round15/test_r15_round15_meetings.py 27/27, test_r15_qa.py 12/12 (без NOT_RUN)"},
            "r08_day_forecast_on_r01_build": {"status": "PASS",
                                              "note": "сборка R01 B0.16 (4ac57b10), демо-мир, акимат → «Картина дня»: блок R08 "
                                              "«Прогноз на неделю» из ui.civic_forecast — метка «прототип», 3 территории с причиной, "
                                              "объяснение с числами проверки (57 % против 47 %); 1366 ru/kk и 375 ru, кадры "
                                              "screens/day-forecast-*.jpg (подписи мест — код 0ef104c2)"},
            "r10_visual_audit": {"status": "PASS", "passed": 124, "total": 124,
                                 "note": "tests/e2e/visual_audit.cjs R10 @ 7b254ef7 --only meetings,meetings-staff на сборке R01 "
                                 "B0.15 с модулями R13 9ca9bc72 (демо-мир, 1366/1024/375 × ru/kk): WARN 0, FAIL 0 — на pvG было "
                                 "WARN «4 размера шрифта» на всех 8 вариантах"},
            "browser_meetings_demo_world": {"status": "PASS", "passed": 115, "total": 115,
                                            "note": "meetings_browser.cjs на сборке R01 B0.15 (735a40b5) с CIVIC_DEMO_WORLD=1 (мир R02: "
                                            "R13 24 записи): проверки не зависят от набора данных"},
            "demo_world_on_r01_build": {"status": "PASS", "note": "сборка R01 c9069723, CIVIC_DEMO_WORLD=1: оболочка засевает R13 "
                                        "(m-w15-1/2/3), прошедшая встреча — итог и 4 поручения, связь с обращением мира R09 "
                                        "(«Двор: BI City Tokyo · Исправлено»); 1366-ru и 375-kk без ошибок JS"},
        },
        "screens": screens,
        "integration": "research/round-15-results/R13/INTEGRATION.txt",
        "patches_for_r01": ["research/round-15-results/R13/patches/r01_meetings_routes.patch",
                            "research/round-15-results/R13/patches/r01_meetings_assets_sheet.patch"],
        "known_limits": [
            "R01 взял поставку R13 07458571 в B0.11 и держит её до B0.15 (маршруты meetings.*, ассеты, теги — с B0); в B1 "
            "взять code_sha этой поставки (патч R04 PII, «♡» 32 px R13-3) — только пути R13.",
            "С B0.11 R01 ставит «Вопросы и встречи» своим экраном-колонкой 720 px (VISUAL_BRIEF §2 п. 2); строки шторки из "
            "патча R13 §3 не нужны. Кадры и браузер — на этой раскладке (B0.15).",
            "Кнопка «♡» у вопросов — рамка 44 px с прозрачной каймой, видимая таблетка 32 px (вариант R11 R13-3): тёмная "
            "кнопка 44 px на экране одна — «Приду».",
            "Прогноз — прототип на синтетической истории жалоб (погода реальная); на настоящих обращениях не проверялся.",
            "Названия связанных проектов и работ — из R06 той же базы (публичные функции); без R06 строка поручения пишет "
            "«Связано с проектом акимата» / «…с работой службы», номер записи — только в подсказке сотруднику.",
            "Кадры — облако без подложки карты (П1 правило 6); кадры с настоящей картой — LOCAL-12.",
        ],
        "next_step": "B1 R01 (16 окт 14:00): проверить, что взят code_sha этой поставки, и прогнать meetings_browser.cjs и "
                     "qa_browser.cjs на B1; R10 — строки B-105 и B-118 закрыты; R11 — ключи meet.staff.link_pick_* в словаре.",
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: code_sha {code[:10]}, {len(changed)} путей, {len(screens)} кадров")


if __name__ == "__main__":
    main()
