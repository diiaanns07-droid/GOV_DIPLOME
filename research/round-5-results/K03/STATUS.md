# K03 round 5 — REVIEW «Границы в демо»: STATUS

| Поле | Значение |
|---|---|
| Роль / слот | REVIEW, K03 (`research/round-5/review/K03.txt` @ `2883aeb`) |
| Ветка | `claude/epic-curie-iitc43` |
| Проверяемая сборка | BUILD `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`, `prototypes/city-evidence/` |
| Свои входы | round-4 K03 @ `3660527` (patch v2, фикстуры) → `inputs/` с манифестом |
| Обновлено | 2026-10-05, ~07:45 UTC |
| Статус | этап 1 **done**: переносимый тест и baseline. Этап 2 (предложение исправления и его проверка во временной копии) — в работе |

## Этап 1: что сделано

- `extract_build.py` — побайтное извлечение `prototypes/city-evidence` из любого SHA (git blob сверяется у каждого файла). Используется для `--app-root`.
- `test_boundaries_demo.py` — переносимый тест: `--app-root <копия>` и/или `--url <serve.py>`. Исходы: PASS / FAIL / XFAIL (известный дефект baseline) / XPASS / SKIP; код выхода 1 только при FAIL.
  - **C1** — файлы K03 в сборке совпадают с `source_manifest.json`.
  - **C2** — модуль действительно тот, что в метке. Поведение на двух фикстурах-отпечатках D1/D2 сверяется с `assign()['rule']`, `evidence.assign_rule` и `method.id`.
  - **C3** — 5 ключевых фикстур v2 из round 4: R1 = D1, R2 = D2, R3 — эксклав, R4/R5 — порог допуска 0,99/1,01 м.
  - **C4** — фактический путь сборки: `tools/build_evidence.py` во временной копии воспроизводит `web/evidence.js` побайтно.
  - **C5** — каждая запись `place_district` соответствует месту из `data.js` и заново вычисленному `assign()`.
  - **C6** — `evidence.js` должен содержать `boundary_binding` (хеши кода и слоёв K03, точки `data.js`), чтобы устаревшая привязка обнаруживалась.
  - **C7** — сценарии устаревания на пути сборки во временной копии: S1 — реальная синхронизация слоёв; S2 — синтетически перенесённое место K10; S3 — применён patch v2.
- `baseline/baseline_0bf27de.json` — результат на сборке K04.

## Baseline 0bf27de (реально запущено)

`python3 research/round-5-results/K03/test_boundaries_demo.py --app-root <извлечённая копия 0bf27de>` → **PASS 7, XFAIL 6, FAIL 0**.

- **Модуль действительно v1, а не только по названию.**
  - Все 11 файлов `inputs/k03_root` побайтно равны K03 @ `44585de`.
  - Поведение v1: R1 → `unmatched`, R2 → `matched` Сарайшык.
  - `assign()['rule']`, `assign_rule` и `method.id` — все `k03_assign_v1`.
- **C3:** R1 и R2 — XFAIL (известные D1 и D2 правила v1); R3–R5 — PASS.
- **C4:** пересборка воспроизводит `evidence.js` побайтно.
- **C5:** 120 мест согласованы.
- **C6:** XFAIL. В `evidence.js` нет привязки `place_district` к коду, слоям или версии; `boundary_version = null`.
- **C7:**
  - **S1:** реальная синхронизация (геометрия Алматы и Сарайшыка ← Overture из пакета) — зона AST-Z3 становится пустой, K03 `assign()` падает с `AttributeError`, тесты приложения дают `errors=2`, пересборка невозможна. **Новый дефект D3** — в модуле K03 (round 3 и patch v2), не в BUILD.
  - **S2:** место перенесено, `data.js` пересобран — тесты приложения проходят, устаревший район показывается молча. После пересборки `evidence.js` меняется 1 место.
  - **S3:** код v2 — до пересборки ничего не ловит. После пересборки метка остаётся `k03_assign_v1`, потому что берётся из `boundary_registry.json`, а не из кода.
- **`--url`** (`serve.py` на 127.0.0.1): только URL — PASS 2, XFAIL 1, SKIP 1; URL + `--app-root` — PASS 6, XFAIL 3.

## Ограничения

- Все XFAIL — известные дефекты baseline (D1, D2, D3, отсутствие binding). Это не дефекты новой версии, пока она не проверена этим же тестом.
- S2 — синтетическое изменение данных. S1 — реальные геометрии пакета, но сама синхронизация смоделирована.
- Проверено только на Linux, Python 3.11.15, shapely 2.1.2, pyproj 3.7.2.

## Следующий шаг (этап 2)

Предложения: P1 — `boundary_binding` + `tools/check_evidence_fresh.py` + метка из кода в BUILD; P2 — K03 v2.1, защита от пустых зон (D3). Patch-файлы будут в этой папке и проверены во временной копии тем же тестом. В BUILD ничего не применяется, статус FIXED не заявляется.

## Воспроизведение

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-5-results/K03/extract_build.py --sha 0bf27deb8549b325b34a9610402613d745544edb --out /tmp/app
pip install shapely==2.1.2 pyproj
python3 research/round-5-results/K03/test_boundaries_demo.py --app-root /tmp/app --json /tmp/k03r5.json
# по URL: (cd /tmp/app && python3 serve.py 8765) &  затем  --url http://127.0.0.1:8765/ [--app-root /tmp/app]
```
