# data/civic/astana — пакет R05 (раунд 11)

Реальные городские объекты Астаны в формате civic-v1 с происхождением каждого значения, отдельный
синтетический демо-срез, реестр источников и лицензий. Владелец — роль R05. Код только stdlib Python 3.

## Состояние на 2026-10-06

**Реальных записей: 0.** Исходящий HTTPS облачной среды R05 закрыт политикой egress: gov.kz, astana.gov.kz,
data.egov.kz, новостные сайты, OSM, OpenFreeMap, Overture docs и т.д. отвечают proxy 403 (см. `sources.json` →
`network_audit` и `research/round-11-results/R05/fetch_audit_*.json`). Обход не выполнялся. Пустой
`objects.json` означает «не подтверждено в этой среде», а не «работ нет».

Получены только официальные тексты условий с raw.githubusercontent.com: OpenMapTiles, OpenFreeMap, Overture
(attribution), MapLibre.

## Файлы

| Файл | Что это | Для кого |
|---|---|---|
| `objects.json` | реальный текущий срез, `slice.demo=false`, все `publication=draft` | импорт R02 |
| `historical.json` | реальные явно исторические записи (завершены > 365 дней назад или помечены) | импорт R02 по флагу |
| `demo_synthetic.json` | **синтетический** срез, `slice.demo=true`, id `demo-astana-*` | демо/e2e R01, R03, R04, R10 |
| `evidence_index.json` | значение поля → источник → короткая выдержка/место | редактор (не публичный DTO) |
| `validation.json` | QA: ошибки/предупреждения, unknown-поля, готовность к публичному показу | R10, редактор |
| `sources.json` | реестр источников с реальными попытками доступа, sha256 полученных | все |
| `LICENSE_REGISTER.json` | обязанности OSM/ODbL, OpenFreeMap, OpenMapTiles, Overture, MapLibre; степень проверки | R01, R10 |
| `ATTRIBUTION.txt` | строки атрибуции для карты/карточек/демо | R01, R03 |
| `geofence.json` | полигоны районов OSM для проверки координат (ODbL) | валидатор |
| `slice_config.json` | дата среза `as_of`, пороги | сборка |
| `intake/real/*.json` | исходные записи R05 с claims (шаблон в `templates/`) | сборка |
| `intake/demo/demo_records.json` | исходник демо-среза | сборка |

## Команды

```sh
# пересобрать все срезы (детерминированно: та же сборка -> те же байты)
python3 -I data/civic/astana/tools/build_slice.py
python3 -I data/civic/astana/tools/build_slice.py --check     # exit 1, если файлы на диске устарели

# проверить любой файл/список/объект civic-v1
python3 -I data/civic/astana/tools/civic_v1.py data/civic/astana/objects.json --profile real --as-of 2026-10-06
python3 -I data/civic/astana/tools/civic_v1.py data/civic/astana/demo_synthetic.json --profile demo

# план импорта для R02 (dry run, БД не трогает, ничего не публикует)
python3 -I data/civic/astana/tools/import_helper.py                  # только реальные
python3 -I data/civic/astana/tools/import_helper.py --include-demo   # + синтетика, явным флагом

# тесты
python3 -m pytest tests/civic/R05 -q
```

## Правила, которые проверяет код

- Профиль `contract` — форма civic-v1 из CONTRACT.txt (allowlist полей, enum, даты, WGS84 [lon,lat],
  бюджет конечный неотрицательный или null, revision ≥ 1, ISO8601 с offset, без HTML).
- Профиль `real` — каждое ненулевое существенное значение (статус, сроки, бюджет и basis, организация,
  контакт, геометрия с precision=source) указано в `fields` **полученного** источника; бюджет ссылается на
  источник, где назван; `actual_end` только при `completed`, не в будущем и не позже даты публикации
  источника («завершим в июне» ≠ завершено); planned/in_progress на источнике старше 45 дней — ошибка
  `stale_status`; 0 ₸ вместо неизвестного — ошибка; геометрия Google/2GIS/Yandex — ошибка;
  телефоны/e-mail в тексте — ошибка; синтетика в реальном срезе — ошибка.
- Профиль `demo` — `evidence_type=synthetic`, id `demo-`, видимая пометка «Демо/синтетическая» в тексте,
  без бюджета в тенге, без организаций и без ссылок-«доказательств».
- Геозабор: точка вне Астаны или перепутанные lon/lat — ошибка; рядом с городом, но вне полигонов OSM —
  предупреждение (границы OSM не юридические).

## Как добавить реальную запись, когда сеть доступна

1. Получить страницу (`tools/probe_sources.py` фиксирует статус и sha256 без сохранения страницы),
   добавить источник в `sources.json` с `access_status=fetched`, `retrieved_at`, `sha256`, `published_on`.
2. Создать `intake/real/<slug>.json` по `templates/intake_record.template.json`: только сказанное в источнике,
   каждое значение — claim с короткой выдержкой (≤300 символов) и типом `stated|expected|reported_actual`.
   Ожидаемая дата окончания — `current_planned_end` (и `original_planned_end` при первой публикации), никогда
   не `actual_end`. Сумма всего проекта не приписывается одному участку. Организация — только если названа.
3. `build_slice.py` → проверить `validation.json` → commit.

## Версии и ID

- `id` реальной записи — `ast-r05-<латинский-слаг>` (≤ 64 символа, как `civic_objects.id` R02); не зависит от
  статуса/сроков, поэтому не меняется при обновлении источника.
- `slice.version` = `r05-astana-<name>-<as_of>-<первые 12 hex content_sha256>`; `content_sha256` — хэш
  канонического JSON items + входов. `import_helper` отказывается от среза, отредактированного вручную.
- Для идемпотентного импорта: `source` (`r05-astana-real` | `r05-astana-demo`), `external_id` (= id),
  `digest` (хэш содержимого без revision/updated_at/publication).
