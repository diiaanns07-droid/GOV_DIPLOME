# K07 · Раунд 6 · REVIEW «Приёмка интерфейса» — STATUS

| Поле | Значение |
|---|---|
| Роль | **REVIEW** (не BUILD). Задание: `research/round-6/review/K07.txt` на `codex/research-import-2026-10-05` @ `edee718` |
| Ветка | `claude/save-work-handoff-ku3ej3` (своя; предыдущий результат `56c8bff`) |
| **Target (проверенная сборка)** | BUILD `claude/beautiful-clarke-sbzomj` @ **`064ed25368341edaa50289bc29e21dda7bdd9440`**, `prototypes/city-evidence/web/` |
| Test source | мой тест раунда 5: `claude/save-work-handoff-ku3ej3` @ `56c8bff`, `research/round-5-results/K07/tests/k07r5_regressions.cjs` (sha256 `7c614651…`); адаптер `tests/k07r6_acceptance.cjs` |
| Обновлено | 2026-10-05 UTC |
| Статус | **done** для объёма задания: приёмка выполнена; 3 инварианта не приняты (FAIL), см. ниже |
| Пути | только `research/round-6-results/K07/`; прототип и старые материалы не менялись |

## Итог приёмки `064ed25`: **24 PASS · 3 FAIL · 0 TEST_INCOMPATIBLE · 0 SKIP из 27**, повтор дал те же вердикты

- **Критический путь «группа из 10 записей» (Шымкент, 69.5958, 42.3167) — PASS (G1–G5).** Маркер на карте открывает карточку записи группы с 9 кнопками перехода к остальным. Все 10 записей достижимы:
  - через карточку;
  - через таблицу;
  - с клавиатуры: ссылка «Перейти к таблице», затем 1 нажатие Tab до строки, Enter на каждой из 10 строк и на кнопке в карточке;
  - на 390 px: кнопки целиком на экране и не перекрыты, горизонтальной прокрутки страницы нет.
- **Смена города и фильтра, устаревшее объяснение — PASS.** Проверки R3, R5a, R5b, R6, R7a, R7b, E1, E2. Объяснение, запрошенное до смены города, для нового города не показывается; после смены фильтра прежнее объяснение с экрана исчезает.
- **Исправлено по сравнению с `0bf27de` и подтверждено на `064ed25`:** R1, R2 (устаревшая подсказка), R4 (сброс точки), R6, R8–R10 (клавиатура, `role`).
- **FAIL — реальные дефекты интерфейса** (минимальный repro и строки — в `ACCEPTANCE.json` → `defects`):
  - **R11.** На экране 390×844 результат точки не виден после касания карты без прокрутки: карта начинается на 501 px, `#mapStatus` — на 977–1038 px. Причина: `web/index.html:153` (статус под картой) вместе с `:117` (высота карты 56vh). Средство чтения экрана статус озвучит (`role="status"`, `aria-live`), но это не прослушано.
  - **R12.** На 390 px значки `.badge` выходят за карточки «Выбор» (369/356 px) и «Срез данных» (409/356 px). Причина: правило `web/index.html:70` `.badge { white-space: normal; }` перекрыто более поздним `:80-81` `white-space: nowrap`. На снимке `G5_390_group_card.png` значок обрезан.
  - **R13.** `evidence.js` другого выпуска или другой версии данных (подменено 186 полей: `release`, `data_version`, SHA в `source.evidence`) используется молча. Причина: `web/facts.js:273` проверяет только `ev.format`, `:237` `districtOf` не сверяет с `data.js`. Сборщик сообщает о проверке при сборке (`tools/check_all.py`); я её не запускал.

## Несовместимости теста раунда 5 (TEST_INCOMPATIBLE) и адаптер

Неизменённый тест раунда 5 на `064ed25` дал 15 из 19 (`results/r5_test_unmodified/`). Его поле `baseline_expectation` относится к `0bf27de` и не применялось.

| Проверка r5 | Почему несовместима | Адаптер | Итог после адаптера |
|---|---|---|---|
| извлекатель r5 | `web/attribution/` — подпапка; r5 читал каждую запись как файл и падал | `scripts/extract_build.py` с рекурсивным обходом | 10 файлов, SHA-256 совпадают |
| R11 | строка статуса — `<p id="mapStatus">` под `.mapwrap`, а r5 искал внутри `.mapwrap` | ищется и `#mapStatus`; по-прежнему требуется видимость на экране (критерий не ослаблен) | FAIL (реальный) |
| R13 | формат `city-evidence/2`: нет `source.path`/`sha256`, у `data_version` нет суффикса коммита; подмена r5 изменяла 0 полей | подмена `release`, `data_version`, SHA в `source.evidence`; если изменено 0 полей — вердикт TEST_INCOMPATIBLE | FAIL (реальный), изменено 186 полей |
| R16 | показатель называется `overture_place_records.school.*`; r5 удалял 0 наблюдений и видел настоящее число 15 | удаление по новому имени и предусловие «удалено > 0» | PASS («Ошибка каталога», удалено 2) |
| R12 | совместим | — | FAIL (реальный), то же и в r5 |

## Реально выполненные проверки

- `python3 scripts/extract_build.py <dir> --sha 064ed25…` — 10 файлов `web/`, SHA-256 совпадают (`results/build_snapshot_064ed25.json`).
- Извлекатель r5 на `064ed25` — `CalledProcessError` на `…/web/attribution`: подтверждает несовместимость.
- `node <r5 test из 56c8bff> --app-root … --out results/r5_test_unmodified` — 15/19.
- `node tests/k07r6_acceptance.cjs --app-root … --label acceptance_064ed25_run1|run2 --sha 064ed25…` — оба прогона 24/3/0 из 27, вердикты совпадают.
- Снимки (`results/acceptance_064ed25_run2/screenshots/`, `results/r5_test_unmodified/screenshots/`) сделаны настоящим Chromium; `G5_390_group_card.png` просмотрен вручную. Снимки run1 совпадают по сценарию и в git не добавлены.

## Ограничения

- Только Chromium (Playwright 1.56.1). Ширина 390 px — эмуляция без сенсорного ввода. Средство чтения экрана не использовалось.
- Режим `--url` не запускался. Тесты сборщика (`smoke.cjs`, `check_all.py`) я не перезапускал.
- Данные — срез K10 (два квадрата), а не реестр; повреждения входов подставлены перехватом запросов.

## Следующий шаг

1. Сборщик исправляет R11, R12 и R13 (подсказки — в `ACCEPTANCE.json`), затем повторяет: `node research/round-6-results/K07/tests/k07r6_acceptance.cjs --app-root <извлечение нового SHA> --sha <NEW_SHA>`. Только такой прогон подтверждает исправление.

## Команда воспроизведения

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-6-results/K07/scripts/extract_build.py /tmp/k07r6/app --sha 064ed25368341edaa50289bc29e21dda7bdd9440
node research/round-6-results/K07/tests/k07r6_acceptance.cjs --app-root /tmp/k07r6/app --label acceptance_064ed25 --sha 064ed25368341edaa50289bc29e21dda7bdd9440
```
