# K06 round 4 — REVIEW: проверка геометрической длины (K10 раунда 3)

Роль: REVIEW, слот K06. Ветка: claude/ecstatic-curie-hzfzn0 (начало раунда от a49e3c88acee60c60a8ff495194f25fef7a01128).
Статус: done (в объёме задания: оракул, тесты, расчёт на реальном срезе, обнаружение ошибок единиц).
Задание: origin/codex/research-import-2026-10-05 @ cadba4d, research/round-4/review/K06.txt.

Входные SHA:
- K10: claude/save-work-handoff-j7pc05 @ ea703f1ddd3a411430a981164a78a7dda64ec909, research/round-3-results/K10/
  (6 файлов данных извлечены через git show → write_bytes; SHA256 и байты совпали с package_manifest.json).
- K07 (только чтение кода): claude/save-work-handoff-ku3ej3 @ 6778deda6d3f3a7f27698f651c1b0046d2a9aae9, scripts/graph_check.py.

Сделано: geo_oracle.py, test_geo_oracle.py, review_k10.py, extract_k10.py, crosscheck_shapely_k07.py,
out/review_k10.json, out/crosscheck_shapely_k07.json, REPORT.md, K07_edge_split.patch.txt (предложение, не применено).

Реально запущенные проверки:
- python3 -m unittest -v test_geo_oracle → 8 OK (Python 3.11.15).
- extract_k10.py → 6/6 OK по SHA256; review_k10.py → повторный запуск побайтно идентичен.
- crosscheck_shapely_k07.py (venv: shapely 2.1.2, pyproj 3.7.2) → оракул и pyproj ≤ 2,5e-6; эмуляция и shapely 0,0 м.
Не запускались: K07 graph_check.py целиком (networkx не ставился), тесты K10 (вне задачи).

Главное: длины K10 верны (метры, [lon, lat], компоненты совпадают). Ошибка у потребителя K07: деление по `at` через
normalized=True в градусах; до 58 м на ребре и до 61 м смещения узла в Астане. Присваивание длины сегмента каждому
ребру дало бы +357/+432 км.

Ограничения: см. REPORT.md. Топологическая длина ≠ время пешком.
Следующий шаг: сборщику (BUILD) — длину ребра брать как (at_b − at_a)·L_geodesic или по review_k10.sub_polyline,
положение узла — из connectors.geojson; хранить параллельные рёбра.
