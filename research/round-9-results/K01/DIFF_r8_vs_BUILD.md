# Расхождения K01 r8 (свой модуль) ↔ BUILD d865dd4 (`web/plan.js`), по одному минимальному входу

Эталон политики — BUILD. Это различия контракта, не дефекты продукта, кроме явно отмеченных. Перевод ожиданий — `POLICY_r8_to_build.json`.

| # | Минимальный вход (на базе `fixtures/synthetic/shy_valid_clinic_constraints.json` r8) | r8 K01 | BUILD d865dd4 | Оценка |
|---|---|---|---|---|
| 1 | добавить `derived_results` с неверными значениями | принимает, отбрасывает | `forged_derived` | BUILD строже; оба не доверяют derived. r8-ожидание заменено |
| 2 | корректный файл Астаны при открытом Шымкенте | `foreign_city` | принят, UI переключает город (`plan-ui.js` importText) | политика BUILD; с явным чужим ctx `validatePlanScenario` → `other_city` |
| 3 | `required_ids == excluded_ids == ["cand-01"]` | `constraint_conflict` | `required_excluded_overlap` | только имя кода |
| 4 | 17 кандидатов | `bad_candidates` | `too_many_candidates` | только имя кода |
| 5 | v1-файл в режиме v2 | `bad_version`/`unknown_field` | `wrong_version` | BUILD даёт отдельный понятный код |
| 6 | `"budget": NaN` / `1e999` / повтор ключа через `budget` | `non_finite` / `duplicate_key` | `bad_json` (текст причины различает) | только гранулярность кода |
| 7 | ID `тчк-01`, `нүкте_Әң.1`, `cp٣` | `bad_id` (ASCII) | принят (NFC, `\p{L}\p{N}_.-`, ≤64 code points) | r8-запрет кириллицы снят по CORE_SPEC r9 |
| 8 | nested лишнее поле в точке | `unknown_field` | `bad_shape` | только имя кода |
| 9 | problem digest | `pd1:` своя канонизация | `sha256:` (кандидат без category/kind) | побайтно не сравнивается; свойства канонизации проверяются отдельно |

Совпадает без перевода: 34 из 46 r8-фикстур (snapshot, bbox, веса, стоимости, бюджет, радиус, ссылки, дубли, размер, кодировка, BOM).
Дефектов продукта на этапе 1 не найдено.
