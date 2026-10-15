"""R16 → R01: подключить «Мой двор» и «Сделаем вместе» к сборке по якорям (если R01_together_b1.patch не ложится).

    python3 research/round-15-results/R16/r01_together_apply.py [корень сборки]      # по умолчанию — текущая папка

Что делает (то же, что patch): 3 маршрута [доп.] R16 (GET together/yards; POST together/yards/{id}/captain;
POST together/yards/{id}/moderate — сотрудник) + V2_HANDLERS + лимит «старшего»; прогрев «Мой двор» в фоне при старте
(рядом с warm_up R12, R10 B-124); CIVIC_ASSETS together/*;
index.html — together.css и два script; в тест R01 test_r01_round15_routes.py — 3 строки таблицы [доп.].
Повторный запуск ничего не дублирует. Файлы R16 (ui/civic_together/, web/civic/together/) — из ветки роли.
    «Сделаем вместе» — лист слева 412 px поверх карты, как «Проекты и идеи» и «Вопросы и встречи» (IA R11 §5.2
    «Житель, лист»; web/civic/shell/birge.css). Не нужен — --no-sheet: модуль раскладывается по своей ширине и так.
"""

from __future__ import annotations

from pathlib import Path
import sys

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = Path(ARGS[0] if ARGS else ".").resolve()
SHEET = "--no-sheet" not in sys.argv   # «Сделаем вместе» — лист слева 412 px (IA R11 §5.2, эталон A); --no-sheet — без него


def edit(rel: str, steps: list[tuple]) -> None:
    """steps: (якорь, вставка, «after» | «instead»[, признак]). Уже есть признак (по умолчанию — первая строка вставки)
    — шаг пропускается: R01 мог взять ту же правку своими словами (B0.2 взял маршруты, файлы и теги R16)."""
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    for step in steps:
        anchor, insert, mode = step[:3]
        marker = step[3] if len(step) > 3 else insert.strip().splitlines()[0].strip()
        if marker in text:
            continue
        if text.count(anchor) != 1:
            raise SystemExit(f"{rel}: якорь не найден или не один: {anchor[:70]!r}")
        text = text.replace(anchor, anchor + insert if mode == "after" else insert, 1)
    path.write_text(text, encoding="utf-8")
    print("ok", rel)


edit("ui/web_server.py", [
    ('"meetings/meetings.js", "meetings/meetings.css", "meetings/forecast-week.js",  # + блок «Прогноз на неделю» для R08\n',
     '                # R16 раунд 15: «Мой двор» (#yard) и «Сделаем вместе» (#together), слой «Инициативы».\n'
     '                "together/together.js", "together/together-text.js", "together/together.css",\n', "after",
     '"together/together.js"'),
    ('    ("GET", ("together", "yards", "{id}"), "together.yards.get"),\n',
     '    ("GET", ("together", "yards"), "together.yards.list"),   # R16 [доп.]: выбор двора — дворы, где уже есть соседи\n'
     '    ("GET", ("together", "yards", "{id}"), "together.yards.get"),\n', "instead", '"together.yards.list")'),
    ('    ("POST", ("together", "yards", "{id}", "leave"), "together.yards.leave"),\n',
     '    ("POST", ("together", "yards", "{id}", "captain"), "together.yards.captain"),     # R16 [доп.]: «старший по двору»\n'
     '    ("POST", ("together", "yards", "{id}", "moderate"), "together.yards.moderate"),   # R16 [доп.]: имя старшего — акимат\n',
     "after", '"together.yards.captain")'),
    ('    "together.yards.leave": V2Handler("R16", _TOGETHER, "make_service", kind="service"),\n',
     '    "together.yards.list": V2Handler("R16", _TOGETHER, "make_service", kind="service", query={"district": "district"}),\n'
     '    # «Старший по двору»: сосед предлагает только имя (на проверку); снять / опубликовать имя — сотрудник.\n'
     '    "together.yards.captain": V2Handler("R16", _TOGETHER, "make_service", kind="service"),\n'
     '    "together.yards.moderate": V2Handler("R16", _TOGETHER, "make_service", kind="service", staff=True),\n', "after",
     '"together.yards.list": V2Handler('),
    ('    "together.yards.leave": ((60, 20, False), (86400, 20, True)),\n',
     '    "together.yards.captain": ((3600, 10, False),),   # R16: имя старшего — редко\n', "after",
     '"together.yards.captain": (('),
    ('            LOGGER.info("civic-v2: R12 warm-up skipped")\n',
     '        # R16 (R10 B-124): «Мой двор» — соседи двора сцены демо (форма R12, индексы карты R07) прогреваются в фоне.\n'
     '        try:\n'
     '            together, together_db = importlib.import_module("ui.civic_together"), server.civic_v2.db_path\n'
     '            threading.Thread(target=lambda: together.warm_up(together_db), daemon=True).start()\n'
     '        except Exception:  # R16 не сдан — «Мой двор» посчитается при первом открытии\n'
     '            LOGGER.info("civic-v2: R16 warm-up skipped")\n', "after"),
])
edit("web/index.html", [
    ('    <link rel="stylesheet" href="/civic/meetings/meetings.css" />\n',
     '    <link rel="stylesheet" href="/civic/together/together.css" />\n', "after", "/civic/together/together.css"),
    ('    <script defer src="/civic/meetings/forecast-week.js"></script>\n',
     '    <script defer src="/civic/together/together-text.js"></script>\n'
     '    <script defer src="/civic/together/together.js"></script>\n', "after", "/civic/together/together.js"),
])
test = ROOT / "tests/civic/R01/round15/test_r01_round15_routes.py"
if test.exists():
    edit("tests/civic/R01/round15/test_r01_round15_routes.py", [
        ('    ("POST", "together/yards/{id}/leave", "R16", "ui.civic_together", "make_service"),\n',
         '    # R16 [доп.] (INTEGRATION R16 §1): выбор двора, «старший по двору» и его проверка акиматом.\n'
         '    ("GET", "together/yards", "R16", "ui.civic_together", "make_service"),\n'
         '    ("POST", "together/yards/{id}/captain", "R16", "ui.civic_together", "make_service"),\n'
         '    ("POST", "together/yards/{id}/moderate", "R16", "ui.civic_together", "make_service"),\n', "after",
         '"together/yards/{id}/captain"'),
        ('    ("POST", "together/initiatives/{id}/support"), ("POST", "together/initiatives/{id}/moderate"),\n',
         '    ("POST", "together/yards/{id}/moderate"),\n', "after", '("POST", "together/yards/{id}/moderate"),'),
    ])

SHEET_CSS = """
/* R16 → R01 (IA R11 §5.2 «Житель, лист», эталон A): «Сделаем вместе» — лист слева 412 px под поиском, справа видна карта
   (капсулы слоя «Инициативы»). Модуль R16 раскладывается по своей ширине (@container tg), прокручивается весь лист;
   «Мой двор» остаётся листом по центру. Телефон — шторка, как у остальных разделов (правило не нужно). */
@media (min-width: 761px) {
  body.civic-mode[data-birge-section="together"] .birge-day.bk-glass {
    left: 20px; right: auto; top: 84px; bottom: 20px; width: min(var(--sheet-w, 412px), calc(100vw - 40px));
    padding: 18px; border-radius: var(--r-xl, 18px);
    --glass-panel: var(--glass-strong, rgba(255, 255, 255, 0.86));
    --c-text-2: #4b5752; --c-text-3: #7e8a85; --c-warn: #754c0f; --c-ok: #2b6110; --c-danger: #9a2e28;
  }
}
"""
if SHEET:
    css = ROOT / "web/civic/shell/birge.css"
    text = css.read_text(encoding="utf-8")
    if 'data-birge-section="together"] .birge-day.bk-glass' not in text:
        css.write_text(text.rstrip("\n") + "\n" + SHEET_CSS, encoding="utf-8")
    print("ok web/civic/shell/birge.css (лист слева)")
