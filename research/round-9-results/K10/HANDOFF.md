# K10, раунд 9 — передача

**Состояние:** этап 1 из 3. Следующий шаг — этап 2: конверты `city-resilience-v1` и независимый оракул устойчивости.

## Этап 1: регрессия одной командой

```bash
python3 research/round-9-results/K10/regress.py --sha <BUILD sha>          # из корня репозитория; нужен node
python3 -m unittest discover -s research/round-9-results/K10/tests -p "test_regress.py" -v
```

Шаги (итог в `results/<sha7>/summary.json`):

1. **EXTRACT** — `prototypes/city-evidence` копируется из git побайтно, с пересчётом git blob id. Манифест сохраняется в `extract_manifest.json`.
2. **FROZEN_PACKS** — пакеты r8 (`research/round-8-results/K10/packs`, 161 файл) побайтно равны `frozen/r8_packs.json`, снятому с коммита `c8df74b`. Ожидания из BUILD не пересоздаются: они посчитаны оракулом K10 в r8.
3. **SOURCE_HASHES** — sha256 двух файлов `inputs/k10/.../places_social.geojson` и `package_manifest.json` равны значениям в пакете K10 (git `602f0c0`, `frozen/sources.json`). sha256, указанный в `web/data.js`, тоже совпадает.
4. **SOURCE_IDS** — в `web/data.js` по каждому городу те же ID и группы, что в пакете K10. lon/lat равны значениям пакета, округлённым до 6 знаков: Шымкент 55 записей, Астана 65; школ 15/8, поликлиник 16/16.
5. **R8_SUITE** — `research/round-8-results/K10/tests/run_build_suite.py`: пакеты против данных, пересчёт оракулом, JS-геометрия, unit-тесты, verify-inputs, прогон через `web/plan.js`, круг экспорта, мутанты `plan.js`.

Результат на `d865dd4a124291e10dd0b7bb1d9eada20d34c268`: все 5 шагов PASS, внутри R8_SUITE все 6 подшагов PASS. Экспорт 30/30, мутанты 15/15.

`tests/test_regress.py` проверяет, что регрессия замечает изменения: байт в geojson, сдвиг, удаление и смену группы записи, правку пакета r8.

`freeze.py` пересоздаёт `frozen/` из git-объектов. Запускать не нужно, файлы уже в репозитории.
