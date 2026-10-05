# STATUS — K12, раунд 5, REVIEW: негативные входы на пути сборки

- **Роль:** REVIEW (не BUILD). Слот K12. Ветка `claude/save-work-handoff-xuav3q`.
- **Задание:** `research/round-5/review/K12.txt` @ `codex/research-import-2026-10-05` `2883aeb`.
- **Статус: `done`** для объёма задания: тест `--app-root`/`--url`, baseline, ожидаемые падения,
  patch-предложение с проверкой. Исправление **только предложено**, BUILD не менялся, FIXED не заявляется.
- **Проверяемый BUILD:** `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`,
  `prototypes/city-evidence/`.
  - Извлечён `extract_build.py` (`git show` → `write_bytes`, git blob 57 файлов сверен,
    `results/extract_0bf27de.json`) во временный каталог.
  - Patch проверялся во временном detached worktree на том же SHA; worktree удалён.
  - `prototypes/city-evidence/`, реальные данные и чужие отчёты не менялись.

## Сделано

- `k12r5_negative_build.py`: 12 случаев на реальном пути `build_data.py` → `build_evidence.py` во
  временных копиях.
  - Семантические мутации корректны по hash: пересчитаны `package_manifest` и `source_manifest`.
  - Различаются отказ целостности, отказ семантики и падение.
  - Требование — отказ обоих шагов и побайтно неизменные `web/data.js` и `web/evidence.js`.
  - Режим `--url` проверяет доставленные артефакты.
- `extract_build.py` — извлечение любого SHA для повторного запуска.
- `BASELINE_0bf27de_EXPECTED.json` — исходы baseline; с `--expect-file` они помечаются XFAIL.
- `patches/build_path_strict_inputs.patch` и `patched/tools/` — предложение исправления.
- `tests/test_harness.py` — самопроверка инструмента (синтетика).
- `REPORT.md` — таблица, выводы, команды повтора.

## Проверки, которые реально выполнены (Linux, Python 3.11.15, shapely 2.1.2, pyproj 3.7.2, Node 22.22)

- Baseline `0bf27de` (извлечённая копия):
  - unittest BUILD — 7 OK; `conformance.cjs` — all passed;
  - чистая пересборка — `data.js` и `evidence.js` побайтно равны закоммиченным;
  - `k12r5_negative_build.py`: OK — C01, C02; не выполнено требование — I01, N01–N09. Оба выхода
    перезаписываются. С `--expect-file`: exit 0, unexpected = [].
- `--url` на `serve.py` (127.0.0.1): чистая копия — clean, exit 0. Копия после принятия N01 —
  `JSON_NONFINITE` и `NONFINITE_CONFIDENCE`, exit 1.
- Patch-предложение на `0bf27de`:
  - `git apply --check` — ok;
  - `k12r5_negative_build.py` — 12 из 12 OK;
  - unittest BUILD — 7 OK; `conformance.cjs` — all passed;
  - worktree после прогонов изменён только в двух файлах patch.
- `python -m unittest discover -s tests` (самопроверка) — 6 OK, в том числе с `-W error::ResourceWarning`.

**Не выполнялось:** `smoke.cjs` (Playwright) с patch; обрыв записи посреди `write_atomic`; Windows.

## Ограничения

- `--url` не видит N05, N08, N09 и I01: следа в артефактах нет. Для них нужен `--app-root`.
- Классификация отказа опирается на текст сообщения: `INTEGRITY`/`sha256`/«размер не совпад…»/«нет
  файла» — целостность, `SEMANTIC` — семантика. Исправленной сборке лучше явно ставить эти префиксы.
- Случаи взяты по одному на тип: это минимальный набор, а не полный перечень атак.

## Следующий шаг

1. BUILD решает, принимать ли patch или своё исправление, и сообщает новый SHA.
2. Затем на этом SHA:

   ```
   extract_build.py <SHA> <dir>
   k12r5_negative_build.py --app-root <dir> --python <venv>
   ```

   Требование — 12/12 OK. Только после этого можно говорить об исправлении.
