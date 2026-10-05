# STATUS — K08, раунд 3: независимая проверка K10

**Статус:** done для заданных 5 утверждений; ограничения (заблокированные OSM, Overture docs и госисточники) перечислены ниже.

- Ветка: `claude/dazzling-mayer-drhsxk`; предыдущий результат 15cd5f2. Задание из `research/round-3/prompts/K08.txt` на `codex/research-import-2026-10-05`.
- Вход: K10 `claude/save-work-handoff-j7pc05` @ e91898d (через `git archive`/`git show`, без merge). Манифест — `inputs_manifest.json`.
- Результаты: `scripts/e03_overcount_diagnostic.py`, `logs/E03_rerun_k08.json`, `logs/E03_overcount_diagnostic.json`, `logs/segment_rerun.sha256`, `AUDIT.md` (строится `render_audit.py` из `verdicts.json`), `verdicts.json`, `inputs_manifest.json`, `logs/E01_rerun_k08.json`, `logs/E02_rerun_k08.json`, `logs/division_area_rerun.sha256`, `logs/places_rerun.sha256`, `logs/spdx_license_texts.sha256`.

## Вердикты
- C1 выпуск Overture 2026-09-23.1 — подтверждено (sha256 повторной выгрузки совпал).
- C2 OSM relation@version и даты — подтверждено с поправками: версия снимка продукта есть только у Сарайшыка, у остальных районов version/timestamp пусты.
- C3 полнота samples относительно агрегатов — не воспроизведено по сохранённым файлам. E02 воспроизведён только повторной выгрузкой из S3.
- C4 E01/E02/E03 — подтверждено воспроизведением, с поправкой к E03: сумма по районам завышена двойным счётом дорог на общих границах (Астана, Алматы|Сарайшық, 15,3 км).
- C5 условия использования — подтверждено с поправками: нет текстов CDLA-P-2.0 и Apache-2.0 рядом с опубликованными samples, отброшено поле property, не упомянут ODbL 4.6. Юридического заключения нет.

## Проверки, которые реально выполнены
- Анонимный листинг S3 Overture (релизы и ключи division_area).
- Повторный `overture_extract.py` для division_area обоих городов: sha256 совпал с K10.
- `check_districts.py` на своей выгрузке: результат идентичен E01 K10.
- Повторный `overture_extract.py extract-multi` для segment (~297 МБ): sha256 совпал; `network_by_district.py` дал результат, идентичный E03; `scripts/e03_overcount_diagnostic.py` разложил избыток (остаток 0).
- Повторный `overture_extract.py` для places обоих городов: sha256 совпал; `places_by_district.py` дал результат, идентичный E02.
- Все 200 записей samples places найдены в выгрузке; группа и confidence совпадают.
- Тексты ODbL-1.0, CDLA-Permissive-2.0, CC0-1.0, Apache-2.0 прочитаны из SPDX license-list-data @31ba1a50e539. Колесо pycountry 26.2.16 скачано с PyPI, METADATA и COPYRIGHT прочитаны.
- Код K10 прочитан до запуска. Файлы K10 не изменялись.

## Ограничения
Госисточники, OSM и сайт Overture заблокированы (см. журнал K10 и раунда 2). S3 Overture доступен.

## Следующий шаг
Координатору или K05 при интеграции: считать километраж района по `g ∩ D_i`, относя линию на общей границе одному району (например, по средней точке сегмента), и приложить к samples тексты CDLA-Permissive-2.0 и Apache-2.0 со ссылкой на атрибуцию OSM и Overture. Чужие файлы K08 не исправлял. Официальный состав районов проверить после открытия adilet/stat.gov.kz.

## Воспроизведение
```bash
git fetch origin claude/save-work-handoff-j7pc05 && mkdir k10 && git archive e91898d596164bcf6e853b921a49f82126074a35 research/next-round/K10 | tar -x -C k10
cd k10/research/next-round/K10 && pip install pyarrow==25.0.1 shapely==2.1.2 pyproj==3.7.2 requests
for c in shymkent astana; do python scripts/overture_extract.py extract divisions division_area $c /tmp/raw/${c}_division_area.jsonl; done
sha256sum /tmp/raw/*_division_area.jsonl   # сравнить с provenance/raw_extracts.sha256
python scripts/check_districts.py /tmp/raw <GOV_DIPLOME>/data/astana_districts.geojson > E01.json
for c in shymkent astana; do python scripts/overture_extract.py extract places place $c /tmp/raw/${c}_places.jsonl --cols id,geometry,confidence,names,addresses,sources,operating_status,basic_category,taxonomy,version,bbox; done
python scripts/places_by_district.py /tmp/raw > E02.json
python scripts/overture_extract.py extract-multi transportation segment /tmp/raw --cols id,names,subtype,class,subclass,connectors,road_surface,road_flags,sources,geometry,version,bbox
python scripts/network_by_district.py /tmp/raw > E03.json
python <GOV_DIPLOME>/research/round-3-results/K08/scripts/e03_overcount_diagnostic.py /tmp/raw scripts
```
