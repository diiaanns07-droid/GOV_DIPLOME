# BUILD раунд 7 — STATUS

Ветка: `claude/beautiful-clarke-sbzomj`. Проверенный код: **4e93f30251b3475775439aa28df1bbc6e48ddefb**.
База: c58a3b2 (код прототипа = кандидат b3e4dc4 раунда 6). Входы: `codex/research-import-2026-10-05 @ 7927fa8`
(`research/round-7/FEATURE_SPEC.txt`, `BUILD.txt`); sha256 — в `SOURCE_HASHES.json`.
Коммиты раунда: 37c8f47 (первый рабочий этап, запушен), 4e93f30 (BOM при импорте, подпись «менее 1 м»), затем этот документальный коммит.

## Итог: функция «Если добавить объект» готова для показа (оба этапа FEATURE_SPEC)
- Этап 1 (кандидат): `git diff b3e4dc4 -- prototypes/city-evidence` пуст; check_all 14/14, smoke 24/24 до изменений; регрессий нет.
- Этапы 2–3: чистый модуль `web/whatif.js` + Python-эталон `tools/whatif_ref.py`; UI-карточка, явные режимы, список точек,
  отдельный слой hypothetical «Проектный объект», таблица до/после/разница «по прямой в пределах среза», источник и QA ближайшей записи.
- Этап 4: экспорт/импорт `city-whatif-v1` (строгий, ≤256 KiB, пересчёт, без изменения состояния при отказе), шаблонное объяснение с digest.
- Соответствие требований тестам — `IMPLEMENTED_SPEC.json`; маршрут показа и ограничения — `DEMO_GUIDE.txt`.

## Проверки (реально запущены на чистом worktree 4e93f30, Linux, Chromium headless, file://)
| команда | результат |
|---|---|
| `python3 tools/check_all.py` (venv с shapely/pyproj) | 16 passed, 0 skipped, 0 failed (`results/check_all.json`) |
| то же системным python3 без shapely | 15 passed, 1 skipped, 0 failed |
| `node tests/smoke.cjs` | 24/24 PASS |
| `node tests/whatif_smoke.cjs` (3-минутный маршрут, оба города) | 32/32 PASS |
| `node tests/whatif.cjs` | 66/66 PASS |

Не запускалось: Windows / `run-demo.bat`; программа чтения экрана; ручной показ человеком.

## Пропуски и ограничения
- Подпись «В срезе нет исходных записей» проверена только в модульных тестах: в обоих реальных срезах есть и школы, и поликлиники.
- Открытые замечания раунда 6 (K10 low; K08 F5) не затрагивались.
- Merge в main и deploy не выполнялись (по BUILD.txt).
