# K11 round 5 — STATUS

Роль: **REVIEW**, задание `research/round-5/review/K11.txt` («Проверка запуска демо»).
Ветка: `claude/save-work-handoff-fmjw6r`. Предыдущий результат: `03fa7fa` (раунд 4).
Обновлено: 2026-10-05, UTC.
Статус: **partial**. Готовы smoke-тест и baseline. Проверка теста на исправленной копии — следующий этап.

Входы:
- назначение: `origin/codex/research-import-2026-10-05` @ `2883aeb6eb68babc9b346b0aa927d4c633f5163d` (`research/round-5/snapshots.json`, `review/K11.txt`);
- проверяемый BUILD: `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`, `prototypes/city-evidence/`. Извлечено `extract_build.py`: 57 файлов, id blob всех совпали.

Мой путь: `research/round-5-results/K11/`. `prototypes/city-evidence/` и чужие отчёты не менялись.

## Сделано

- `extract_build.py`: побайтное извлечение снимка (`git cat-file blob` → `write_bytes`, сверка id blob).
- `k11_demo_smoke.py`: smoke с `--app-root` или `--url`, опциональный `--browser`. Сам запускает `serve.py` на свободном порту, проверяет localhost и явно останавливает свой процесс. Есть моделирование Windows.
- `baseline_0bf27de.json` и `.txt`: результат на BUILD `0bf27de`.
- `README.md`: команды, список проверок, ожидаемые падения baseline.

## Реально выполненные проверки (Linux, Python 3.11.15, Node 22.22.0, Playwright 1.56.1)

- `k11_demo_smoke.py --app-root <extract 0bf27de> --browser`: 15 pass, 4 fail (S4, S5, S6, S8), modeled_fail M2 и M3, modeled_pass M1, not_run W1, exit 1.
- Ошибки самого теста найдены и исправлены до сохранения baseline:
  - регистр заголовка `Content-type`;
  - ложное совпадение `run.bat` в S6;
  - индекс `argv` в Node-скрипте.
- Регулярное выражение S6 проверено на 8 примерах строк.

## Ограничения

- Windows не запускался. M1–M3 — моделирование: перенаправленный stdout в cp1251/cp1252, `path.win32`.
- Ветка остановки для Windows (`CREATE_NEW_PROCESS_GROUP`, `terminate`) не исполнялась.
- `--url` проверялся только косвенно: те же HTTP-функции используются в `--app-root`.

## Следующий шаг

1. Прогнать тест на копии `0bf27de` с моим patch-предложением (только в моей папке, не FIXED), чтобы показать, что проверки переключаются. Затем отдельно проверить `--url`.
