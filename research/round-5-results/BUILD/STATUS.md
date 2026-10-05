# BUILD раунд 5 — STATUS

- owner_branch: `claude/beautiful-clarke-sbzomj`; исходная сборка `0bf27deb8549b325b34a9610402613d745544edb` (продолжение, не пересоздание)
- Задание: `research/round-5/BUILD.txt` @ `codex/research-import-2026-10-05` `2883aeb6eb68babc9b346b0aa927d4c633f5163d`
- Статус: **in_progress** — этапы A и B в основном сделаны, этап C частично (см. ниже); финальная проверка не выполнена

## Входы
82 файла из `research/round-5/snapshots.json` скопированы побайтно в `prototypes/city-evidence/inputs/r4/` (`MANIFEST.json`: ветка, SHA, путь, sha256).

## Сделано
- Воспроизведено на прежнем контракте сборки (v1.1 без патча) и реальном наблюдении Шымкента: NaN/±Infinity принимаются, `1e999` → inf, повтор ключа молча побеждает, `json.dumps` пишет `NaN` → `research/round-5-results/BUILD/baseline_repro.json`.
- Контракт сборки: `k05-obs-v1.2+k12r4` = K05 r4 `k05r4_contract` (spatial_unit) поверх `k05r3_contract` с патчем K12 (отдельная копия `inputs/contract/`, исходные и изменённые sha256 в `CONTRACT_MANIFEST.json`).
- `tools/contract.py`: `loads_strict`, `dumps_strict(allow_nan=False)`, `validate_all` (запись + набор).

## Реально выполненные проверки
- `python3 tools/repro_baseline.py` — дефекты старой версии воспроизведены (baseline).
- `python3 -m unittest tests.test_contract -v` — 11/11 OK: NaN/Infinity/1e999/повтор ключа отклоняются; экспорт NaN запрещён; NaN-значение → VALUE_NOT_FINITE; проверки K12 (дата) работают под v1.2; без spatial_unit → ошибка; повтор obs_id → ошибка; v1.1+bbox → LEGACY_UNIT; реальные наблюдения K05 обоих городов — 0 ошибок; значения = независимый пересчёт из пакета K10 (sha256 источника совпадает).

## Промежуточно сделано (коммит 2)
- Демо собрано контрактом v1.2+k12r4 (evidence.js формат city-evidence/2), K03 v2 (отдельная пропатченная копия), QA-метки, K02 r4 + catalog_digest (unit/missing_reason), атрибуция K08, исправления K07 в app.js, smoke через pathToFileURL.
- Проверки на этот момент: unittest 22/22 (venv с shapely), conformance 37/37, smoke 23/23.

## Ограничения
- Финальная проверка, run-demo.bat, K01, clean checkout — ещё не выполнены.

## Следующий шаг
Перевести `tools/build_evidence.py` на v1.2+k12r4 и семантику «0 в полном ответе запроса ≠ неизвестно по городу»; затем этап B.
