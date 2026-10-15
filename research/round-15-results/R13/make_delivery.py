"""R13 · раунд 15: собрать DELIVERY.json из git и итогов проверок (CONTRACT §12).

    python3 research/round-15-results/R13/make_delivery.py --code-sha <sha> --pytest "170/0" --browser "125/125" \
        [--push OK|FAILED|PENDING]

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
    ap.add_argument("--push", default="OK")
    args = ap.parse_args()
    code = git("rev-parse", args.code_sha)
    changed = [p for p in git("diff", "--name-only", BASE_SHA, code).splitlines() if p.startswith(OWN_PATHS)]
    passed, failed = (int(x) for x in args.pytest.split("/"))
    screens = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "research/round-15-results/R13/screens").glob("*.jpg"))
    browser = {"status": "NOT_RUN", "note": "нет стенда с маршрутами meetings.*"} if args.browser == "NOT_RUN" else {
        "status": "PASS" if args.browser.split("/")[0] == args.browser.split("/")[1] else "FAIL",
        "passed": int(args.browser.split("/")[0]), "total": int(args.browser.split("/")[1]),
        "command": "tests/civic/R13/meetings/meetings_browser.cjs --full (BIRGE_URL стенда)",
        "sha": git("rev-parse", args.browser_sha) if args.browser_sha else None,
        "env": "облако: FINAL-4 e91acb69 + патчи R13 для R01 (маршруты, ассеты, лист слева), CIVIC_DEMO=1, Chromium 1194; "
               "подложка карты — упрощённый фон (нет интернета)"}
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
            "r08_contract_on_r08_branch": {"status": "PASS", "note": "neighbors.meetings / neighbors.forecast R08 @ 7150379a "
                                           "поверх модулей R13: source r13 и r13-week, числа совпадают (ручной прогон)"},
            "seed_world_on_r02_world": {"status": "PASS", "note": "world_v1.json R02 @ 0c0a8636: 17 записей, повтор 0"},
        },
        "screens": screens,
        "integration": "research/round-15-results/R13/INTEGRATION.txt",
        "patches_for_r01": ["research/round-15-results/R13/patches/r01_meetings_routes.patch",
                            "research/round-15-results/R13/patches/r01_meetings_assets_sheet.patch"],
        "known_limits": [
            "Маршруты meetings.* и файлы раздела появятся в сборке только после патча R01 (INTEGRATION §2–§3); до этого "
            "раздел #meetings не открывается (модуль сам регистрируется, но шлюз отвечает 503).",
            "Адрес #meetings/<m-id> (ссылки ленты R06) работает полностью, когда R01 поставит путь раздела (IA_ROUND15 §7.3); "
            "в оболочке FINAL-4 — только при открытии страницы.",
            "Прогноз — прототип на синтетической истории жалоб (погода реальная); на настоящих обращениях не проверялся.",
            "В демо-мире R02 у прошедшей встречи нет итога и время суток встреч случайное — просьба к R02 (INTEGRATION §7).",
            "Кадры — облако без подложки карты (П1 правило 6); кадры с настоящей картой — LOCAL-12.",
        ],
        "next_step": "Сверить сборку B1 R01 (маршруты, SCREENS, путь раздела) и прогнать meetings_browser.cjs на ней; "
                     "ответы R02 по итогам/времени встреч; разбор экранов R11 (ключи meet.*, компоненты встречи).",
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: code_sha {code[:10]}, {len(changed)} путей, {len(screens)} кадров")


if __name__ == "__main__":
    main()
