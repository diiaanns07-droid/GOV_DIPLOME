# STATUS — K12, раунд 5, REVIEW: негативные входы на пути сборки

- **Роль:** REVIEW (не BUILD). Слот K12. Ветка `claude/save-work-handoff-xuav3q`.
- **Задание:** `research/round-5/review/K12.txt` @ `codex/research-import-2026-10-05` `2883aeb`.
- **Статус: `partial`.** Этап 1 готов: тест и baseline. Проверка `--url` и patch-предложение — следующий этап.
- **Проверяемый BUILD:** `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`,
  `prototypes/city-evidence/`. Извлечён `extract_build.py` (`git show` → `write_bytes`, git blob каждого
  из 57 файлов сверен; список — `results/extract_0bf27de.json`) во временный каталог, а не в
  репозиторий. `prototypes/city-evidence/` и реальные данные не менялись.

## Этап 1 — сделано

- Прочитан путь сборки: `tools/build_data.py`, `tools/build_evidence.py`, `tools/copy_inputs.py`,
  `serve.py`, `tests/test_inputs.py`, `inputs/k10/scripts/offline_check.py`, README/STATUS/HANDOFF.
- `k12r5_negative_build.py` — тест с режимами `--app-root DIR` и `--url URL`.
  - Каждый случай идёт во временной копии: мутация одного входа, затем реальные
    `tools/build_data.py` и `tools/build_evidence.py` через subprocess.
  - Семантические случаи **корректны по hash**: пересчитаны `package_manifest.json` и `source_manifest.json`.
  - Требование: отказ обоих шагов с диагностикой; `web/data.js` и `web/evidence.js` побайтно не меняются.
- `BASELINE_0bf27de_EXPECTED.json` — ожидаемые исходы baseline; с `--expect-file` они помечаются XFAIL.

## Результат на baseline `0bf27de` (`results/baseline_0bf27de.json`)

| Случай | build_data / build_evidence | Выходы | Видно в артефактах | offline_check |
|---|---|---|---|---|
| C01 чистая копия | принят / принят | побайтно равны закоммиченным | чисто | ok |
| C02 байт без пересчёта hash | отказ целостности / отказ целостности | без изменений | — | ловит |
| I01 данные + package_manifest изменены, source_manifest нет | **принят / принят** | перезаписаны | нет | не ловит |
| N01 NaN в confidence | **принят / принят** | перезаписаны (`NaN` в data.js) | да | **не ловит** |
| N02 NaN в координате | **принят / принят** | перезаписаны | да | ловит (вне bbox) |
| N03 Infinity в длине | **принят / принят** | перезаписаны (`Infinity`) | да | ловит |
| N04 `1e999` в длине | **принят / принят** | перезаписаны (`Infinity`) | да | ловит |
| N05 повтор ключа `k10_group` | **принят / принят** | перезаписаны (школа стала аптекой) | **нет** | **не ловит** |
| N06 конфликт id | **принят / принят** | перезаписаны (`places.total` 56 при 55 id) | да | ловит |
| N07 точка Шымкента в квадрате Астаны | **принят / принят** | перезаписаны (`city_mismatch`) | да | ловит |
| N08 bbox заголовка ≠ манифест | **принят / принят** | перезаписаны | **нет** | ловит |
| N09 выпуск слоя 2026-08-20.0 ≠ 2026-09-23.1 | **принят / принят** | перезаписаны | **нет** | ловит |

Это **ожидаемые падения baseline**, а не дефекты новой версии: новая версия не проверялась.
`offline_check` K10 стоит в README отдельным шагом, но сборка его не вызывает и от него не зависит.

## Проверки, которые реально выполнены (Linux, Python 3.11.15, shapely 2.1.2, pyproj 3.7.2, Node 22)

- Извлечённая копия `0bf27de`:
  - `python -m unittest discover -s tests` — 7 OK;
  - `node tests/conformance.cjs` — all passed;
  - чистая пересборка `build_data` + `build_evidence` — `data.js` и `evidence.js` побайтно равны закоммиченным.
- `k12r5_negative_build.py --app-root <копия> --python <venv>`: таблица выше; 12 случаев, около 17 с.
- То же с `--expect-file BASELINE_0bf27de_EXPECTED.json`: exit 0, unexpected = [].

## Следующий шаг

Режим `--url` на `serve.py` (чистая и заражённая копия). Затем patch-предложение для `build_data.py`
в своей папке и его проверка тем же тестом. Это предложение, а не FIXED.

## Повтор на исправленной версии

```
git fetch origin claude/beautiful-clarke-sbzomj
python research/round-5-results/K12/extract_build.py <НОВЫЙ_SHA> /tmp/ce_new
python research/round-5-results/K12/k12r5_negative_build.py --app-root /tmp/ce_new --python <python с shapely+pyproj>
```

Для исправленной версии `--expect-file` не нужен: требование — все 12 случаев «OK».
