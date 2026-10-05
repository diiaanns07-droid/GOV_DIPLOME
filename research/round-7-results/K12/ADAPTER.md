# Как подключить свой импортёр к `whatif_import_stress.cjs`

Тестовый модуль не знает, как устроен будущий импортёр BUILD. Ему нужен маленький адаптер на 10–20
строк: CommonJS-файл, который экспортирует функцию.

```js
// my_adapter.cjs
module.exports = function ({ appRoot, D, EV, ctx, requireWeb }) {
  // D = window.CITY_EVIDENCE, EV = window.CITY_OBS из web/data.js и web/evidence.js копии по --app-root
  // requireWeb("whatif.js") — require файла из <app-root>/web/
  const W = requireWeb("whatif.js");                    // имя модуля BUILD — пример
  return {
    snapshot: (city, category) => W.snapshot(D, city, category),              // обязательно
    initialState: (city, category) => W.emptyScenario(city, category),        // обязательно
    importScenario: (text, state) => {                                        // обязательно
      const r = W.importScenario(D, text, state);   // НЕ должен менять `state`
      return { ok: r.ok, code: r.code || null, state: r.ok ? r.scenario : state };
    },
    compute: (state) => W.compute(D, state).map((row) => ({                   // желательно
      id: row.id, before_m: row.before, after_m: row.after, delta_m: row.delta, nearest_before_id: row.nearest_id })),
    // currentState: () => W.activeScenario(),   // если активный сценарий хранится внутри модуля
  };
};
```

## Что проверяет модуль

- **Отказ.** Для каждой негативной фикстуры `ok === false` без исключения. Коды ошибок сверяются
  со списком ожидаемых только как advisory; с `--strict-codes` расхождение становится ошибкой.
- **Неизменность.** Возвращённое состояние совпадает с состоянием до импорта (стартовое — принятый P01).
  Переданный объект не изменён. `currentState()` и `compute()` не изменились.
- **Окружение.** Нет сетевых обращений (`http`, `https`, `net`, `tls`, `fetch`, `XMLHttpRequest`
  перехвачены), `Object.prototype` не изменён, глобальные переменные не добавлены.
- **Позитивные случаи.** Фикстура принята. `compute()` совпадает с независимым оракулом модуля
  (гаверсинус по FEATURE_SPEC, R = 6371008,8 м), допуск 1e-6 м. Подделанные `results` в P03 не
  должны попасть в вывод.

## Отпечаток среза

Фикстуры содержат плейсхолдеры `"__SNAPSHOT__"`, `"__SNAPSHOT_OTHER_CITY__"` и
`"__SNAPSHOT_OTHER_CATEGORY__"`. Модуль подставляет значения из `snapshot()` вашего импортёра,
поэтому алгоритм отпечатка остаётся за BUILD. N15 (отпечаток другой категории) — advisory: отказ
ожидается, только если категория входит в параметры отпечатка.

## Запуск

```bash
python research/round-5-results/K12/extract_build.py <SHA> /tmp/ce      # побайтная копия prototypes/city-evidence
node research/round-7-results/K12/whatif_import_stress.cjs --app-root /tmp/ce --adapter my_adapter.cjs --out r.json
```

Exit 0 — нет FAIL и ERROR. Advisory-расхождения выводятся, но к FAIL не относятся.
Если адаптера нет, модуль запускается с эталонным импортёром K12 (`adapters/reference_adapter.cjs`).
