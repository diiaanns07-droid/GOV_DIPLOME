# STATUS — K08, раунд 3: независимая проверка K10

**Статус:** partial — все 5 утверждений получили вердикт; E03 ещё не воспроизведён (выгрузка segments ~300 МБ).

- Ветка: `claude/dazzling-mayer-drhsxk`; предыдущий результат 15cd5f2. Задание из `research/round-3/prompts/K08.txt` на `codex/research-import-2026-10-05`.
- Вход: K10 `claude/save-work-handoff-j7pc05` @ e91898d (через `git archive`/`git show`, без merge). Манифест — `inputs_manifest.json`.
- Результаты: `AUDIT.md` (строится `render_audit.py` из `verdicts.json`), `verdicts.json`, `inputs_manifest.json`, `logs/E01_rerun_k08.json`, `logs/E02_rerun_k08.json`, `logs/division_area_rerun.sha256`, `logs/places_rerun.sha256`, `logs/spdx_license_texts.sha256`.

## Вердикты
- C1 выпуск Overture 2026-09-23.1 — подтверждено (sha256 повторной выгрузки совпал).
- C2 OSM relation@version и даты — подтверждено с поправками: версия снимка продукта есть только у Сарайшыка, у остальных районов version/timestamp пусты.
- C3 полнота samples относительно агрегатов — не воспроизведено по сохранённым файлам. E02 воспроизведён только повторной выгрузкой из S3.
- C4 E01 — подтверждено воспроизведением.
- C5 условия использования — подтверждено с поправками: нет текстов CDLA-P-2.0 и Apache-2.0 рядом с опубликованными samples, отброшено поле property, не упомянут ODbL 4.6. Юридического заключения нет.

## Проверки, которые реально выполнены
- Анонимный листинг S3 Overture (релизы и ключи division_area).
- Повторный `overture_extract.py` для division_area обоих городов: sha256 совпал с K10.
- `check_districts.py` на своей выгрузке: результат идентичен E01 K10.
- Повторный `overture_extract.py` для places обоих городов: sha256 совпал; `places_by_district.py` дал результат, идентичный E02.
- Все 200 записей samples places найдены в выгрузке; группа и confidence совпадают.
- Тексты ODbL-1.0, CDLA-Permissive-2.0, CC0-1.0, Apache-2.0 прочитаны из SPDX license-list-data @31ba1a50e539. Колесо pycountry 26.2.16 скачано с PyPI, METADATA и COPYRIGHT прочитаны.
- Код K10 прочитан до запуска. Файлы K10 не изменялись.

## Ограничения
Госисточники, OSM и сайт Overture заблокированы (см. журнал K10 и раунда 2). S3 Overture доступен.

## Следующий шаг
Проверить гипотезу K10 о завышении E03 (сумма по районам на 0,07% и 0,3% больше городской). В network_by_district.py длина по району — пересечение сегмента с полигоном района без обрезки по городу, а линия на общей границе засчитывается обоим районам. Для проверки нужна выгрузка segments (~300 МБ).

## Воспроизведение
```bash
git fetch origin claude/save-work-handoff-j7pc05 && mkdir k10 && git archive e91898d596164bcf6e853b921a49f82126074a35 research/next-round/K10 | tar -x -C k10
cd k10/research/next-round/K10 && pip install pyarrow==25.0.1 shapely==2.1.2 pyproj==3.7.2 requests
for c in shymkent astana; do python scripts/overture_extract.py extract divisions division_area $c /tmp/raw/${c}_division_area.jsonl; done
sha256sum /tmp/raw/*_division_area.jsonl   # сравнить с provenance/raw_extracts.sha256
python scripts/check_districts.py /tmp/raw <GOV_DIPLOME>/data/astana_districts.geojson > E01.json
```
