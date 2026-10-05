# STATUS — K08, раунд 3: независимая проверка K10

**Статус:** partial — проверено 2 из 5 (C1, C4).

- Ветка: `claude/dazzling-mayer-drhsxk`; предыдущий результат 15cd5f2. Задание из `research/round-3/prompts/K08.txt` на `codex/research-import-2026-10-05`.
- Вход: K10 `claude/save-work-handoff-j7pc05` @ e91898d (через `git archive`/`git show`, без merge). Манифест — `inputs_manifest.json`.
- Результаты: `AUDIT.md`, `verdicts.json`, `logs/E01_rerun_k08.json`, `logs/division_area_rerun.sha256`.

## Проверки, которые реально выполнены
- Анонимный листинг S3 Overture (релизы и ключи division_area).
- Повторный `overture_extract.py` для division_area обоих городов: sha256 совпал с K10.
- `check_districts.py` на своей выгрузке: результат идентичен E01 K10.
- Код K10 прочитан до запуска. Файлы K10 не изменялись.

## Ограничения
Госисточники, OSM и сайт Overture заблокированы (см. журнал K10 и раунда 2). S3 Overture доступен.

## Следующий шаг
C2: сверить OSM relation@version и update_time из samples с OSM-снимками продукта (`data/geo_sources`). C3: проверить, можно ли получить агрегаты E02 и E03 из сохранённых samples. C5: условия использования по полям записей и доступным текстам.

## Воспроизведение
```bash
git fetch origin claude/save-work-handoff-j7pc05 && mkdir k10 && git archive e91898d596164bcf6e853b921a49f82126074a35 research/next-round/K10 | tar -x -C k10
cd k10/research/next-round/K10 && pip install pyarrow==25.0.1 shapely==2.1.2 pyproj==3.7.2 requests
for c in shymkent astana; do python scripts/overture_extract.py extract divisions division_area $c /tmp/raw/${c}_division_area.jsonl; done
sha256sum /tmp/raw/*_division_area.jsonl   # сравнить с provenance/raw_extracts.sha256
python scripts/check_districts.py /tmp/raw <GOV_DIPLOME>/data/astana_districts.geojson > E01.json
```
