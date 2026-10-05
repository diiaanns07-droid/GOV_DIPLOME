# MIGRATION: демо city-evidence, раунд 4 → раунд 5

Исходная сборка: `claude/beautiful-clarke-sbzomj` @ `0bf27de`. Демо продолжено, а не пересоздано.

## Контракт данных: `k05-obs-v1.1` → `k05-obs-v1.2+k12r4`

| Было (r4) | Стало (r5) | Почему |
|---|---|---|
| `k05r3_contract.validate` (v1.1) без патча | `k05r4_contract.validate` (v1.2, K05 r4) → `k05r3_contract` **с патчем K12 r4** → `k05_validator` v1 | v1.2 добавляет `spatial_unit`; патч K12 запрещает NaN/±Infinity, несуществующие даты, счётчик < 0 или дробный, `retrieved_at` не в ISO, вложенные территории и смешение слоёв в агрегате. При сочетании проверки K12 не теряются: k05r4 вызывает пропатченный k05r3 |
| `json.loads` / `json.dumps` | `loads_strict` (нет NaN/Infinity, 1e999, повторных ключей), `dumps_strict(allow_nan=False)` | дефекты K12 #1–#2 воспроизведены на r4 (`baseline_repro.json`) |
| проверка записи по отдельности | плюс `validate_dataset`: повтор `obs_id`, конфликт ячейки | K12 #5 |
| наблюдения без `spatial_unit`, `geo_unit_id = kz.<city>.k10r3_bbox` | v1.2: `kz.<city>.k10sq_r<row>_c<col>`, `spatial_unit.type=bbox`, `boundary_version = k10_r3_square:…@<sha selection>` | квадрат нельзя сложить с районом (`LEGACY_UNIT`, `SPATIAL_MIX`) |

Состав файлов: `inputs/contract/CONTRACT_MANIFEST.json` (исходные и используемые sha256; пропатчен только `k05r3_contract.py`; копия не является upstream). Пересборка: `python3 tools/setup_contract.py`.

### Совместимость
- Записи v1.1 (`evidence.js` r4) новым контрактом отклоняются: `SCHEMA_VERSION`, `SPATIAL_UNIT`. Это намеренно. Тест: `test_contract.py::RecordRules.test_missing_spatial_unit_rejected`.
- Агрегат записи v1.1 вместе с v1.2 → `LEGACY_UNIT`. Тест: `test_v11_district_record_cannot_be_summed_with_bbox`.
- Реальные наблюдения K05 r4 обоих городов проходят без ошибок. Их значения совпадают с независимым пересчётом из пакета K10 (sha256 источника совпадает).

## Смысл нуля и пропуска (одинаково в контракте, каталоге фактов и UI)

| Ситуация | Запись | UI / объяснение |
|---|---|---|
| 0 записей группы в полном ответе запроса по квадрату | `value 0`, `reported_zero`, `coverage.complete=true` | «0 записей» + подпись «ноль в полном ответе запроса по квадрату» |
| Сколько объектов во всём городе | `kz.<city>`, `spatial_unit.city_polygon`, `value null`, `missing`, `not_collected` | «Соцобъекты по всему городу: нет данных (не собиралось)» |
| Официальный реестр школ | `missing`, `source_access_denied` | «нет данных (источник недоступен)» |
| Мощность школ | `missing`, `not_in_source` | «нет данных (нет в источнике)», никогда 0 |
| Число детей | `missing`, `not_collected` | «нет данных (не собиралось)» |
| Отсутствует файл `evidence.js` | — | явная ошибка «Каталог фактов недоступен», а не нули |

**В r4 было иначе:** группа без записей шла как `missing / zero_in_partial_coverage`, потому что охват квадрата считался неполным. В r5 полнота относится к ответу запроса, а неполнота по городу вынесена в отдельное наблюдение.

## Формат `web/evidence.js`: `CITY_OBS` r4 → `city-evidence/2`
- `format`, `contract`, `assign_rule = k03_assign_v2`, `release`, `spatial_unit`.
- `observations`: 26 на город — 14 K05 (7 групп × порог confidence 0 и 0,5), 4 статуса K03, 4 класса прохода, 4 городских пропуска.
- `qa`: `colocated` (группы id), `possible_duplicates` (пары), `category_doubt` (id → правило и причина), `rules`.
- `validation`: `errors` (всегда 0, иначе сборка останавливается), коды предупреждений.

## Объяснения: K02 r3 → K02 r4 fixed + адаптация BUILD
- ID: `kz.<city>/k10r3-<release>-g<mask>/<path>`. Город с точкой, выпуск в ID среза.
- План обязан содержать `catalog_digest`. **Старые планы без отпечатка отклоняются** (`stale_catalog`), тесты K02 r3 к новой сборке неприменимы.
- Отпечаток = sha256 от (id, repr(value), kind, coverage_complete, unit, missing_reason)[:16]. По сравнению с K02 r4 добавлены `unit` и `missing_reason`; это изменённая копия `inputs/k02v4`, хэши в её MANIFEST.
- Один ID в двух секциях → `duplicate_id`. Причина пропуска печатается в тексте.
- Селектор — по-прежнему детерминированная заглушка с подписью «не LLM».

## Районы: `k03_assign_v1` → `k03_assign_v2`
- Патч K03 r4 применён к отдельной копии `inputs/k03v2_root`; `inputs/k03_root` побайтно равен K03 @ 44585de.
- v1 расходился с ожиданием в 3 из 45 пограничных fixtures K03 r4, v2 — в 0. На реальных записях двух квадратов результат не изменился: все `matched`.

## Пересборка после обновления входов
```bash
cd prototypes/city-evidence
python3 tools/copy_round5_inputs.py      # нужен git fetch веток из research/round-5/snapshots.json
python3 tools/setup_contract.py && python3 tools/setup_k03_v2.py && python3 tools/setup_k02.py
python3 tools/build_data.py
python3 tools/build_evidence.py          # нужны shapely, pyproj (requirements-build.txt)
python3 tools/explain_ref.py
python3 tools/check_all.py
```
