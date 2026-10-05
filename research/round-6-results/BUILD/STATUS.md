# BUILD раунд 6 — STATUS

- owner_branch: `claude/beautiful-clarke-sbzomj`; target (база): `064ed25368341edaa50289bc29e21dda7bdd9440`
- Задание: `research/round-6/BUILD.txt` @ `codex/research-import-2026-10-05` `edee718366ee4f085ea540c4e53a8dabf3c93fce`
- Статус: **in_progress** — baseline сохранён; исправлены K12-вход, K05-контракт, K03 v2.1 + привязка, переносимость эталона K02; UI и финальная приёмка впереди

## Входы
87 файлов REVIEW раунда 5 (K01–K03, K05–K08, K10–K12) → `review_inputs/` побайтно, `review_inputs/MANIFEST.json`.

## Baseline 064ed25 (`results/baseline_064ed25/`, запуск `tools/run_acceptance.py` на извлечении `git archive`)
Предварительно (полная интерпретация — в ACCEPTANCE.json после исправлений). Ожидаемые падения старого 0bf27de не применяются.
- **BUILD check_all на извлечённой папке: FAIL** — эталон K02 искал `agent/evidence.py` вне `prototypes/city-evidence` (StopIteration). Реальный дефект переносимости.
- **K12:**
  - N03/N04 (Infinity, `1e999` в длине сегмента): `build_evidence` принимает вход и перезаписывает `evidence.js`;
  - остальные отказы — случайные, из-за хэша атрибуции K08 или источника K05, а не семантической проверки;
  - I01: `source_manifest` не используется как якорь. Подтверждено.
- **K05:**
  - M09: `BOUNDARY_MIX` на раздельных bbox; M10: `expected_units` не проходит через v1.2; M12: COUNT_DOMAIN не работает для `records`/`segments`. Подтверждено;
  - D08: тест применяет v1.1 validate к записям v1.2 — разбор в ACCEPTANCE.
- **K03:** C6/C7 — в `evidence.js` нет привязки к коду и слоям K03, устаревший район не обнаруживается (подтверждено); C2 читает `inputs/k03_root` (v1), сборка использует `k03v2_root` — TEST_INCOMPATIBLE, нужен адаптер.
- **K08 A7:** карточка дороги подписана «OSM через Overture» и для сегментов TomTom. Подтверждено.
- **K07:** R11, R12, R13, R16; **K10:** SHOULD «каждая запись группы выбирается с карты» (1 из 10); **K11:** S8 (smoke пишет вывод вне папки приложения).
- **K02, K06, K01 N1:** тесты рассчитаны на API или путь 0bf27de — разбор в ACCEPTANCE.

## Исправлено (коммит 2, рабочее дерево — ещё не candidate)
- Переносимость: вендорная копия `agent/evidence.py` (main @ 834a25f) в `inputs/product_agent`; извлечённая папка проходит `check_all`.
- K12: строгий вход `build_data` (`INTEGRITY:` якорь source_manifest; `SEMANTIC:` NaN/Inf/1e999/повтор ключа/заголовок/id/bbox/диапазоны). K12 r5 на рабочем дереве: 12/12.
- K05: в контракт добавлены патчи K05 r5 (count units, v1.2 compat); контракт `k05-obs-v1.2+k12r4+k05r5`. Тест K05 (адаптер D08 и таблица вариантов): 20/20, 0 неожиданных.
- K03: копия `k03v21_root` (патч v2.1), сверка с MANIFEST_K03, `boundary_binding`, правило из кода, `tools/check_evidence_fresh.py`. Тест K03 (адаптер пути и S2): PASS 13, FAIL/XFAIL/SKIP 0.

## Следующий шаг
Исправить подтверждённое (K12-вход, K05-патчи, K03 привязка и v2.1, K08 A7, K07/K10 UI, K11 S8), адаптеры тестов с описанием, повторный прогон.
