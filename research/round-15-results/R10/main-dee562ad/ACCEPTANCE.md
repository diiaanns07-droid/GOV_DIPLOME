# R10 · приёмка сборки main-integration dee562ad

Код: `dee562ad` · отчёт: `research/round-15-results/R10/main-dee562ad (только сводка; полные логи — в облачной сессии)`

## Можно показывать: **да**

- блокеров нет

Смотреть (не блокирует):
- сцены 0 и 7–9: NOT_RUN 2 (модулей/экранов нет в сборке)

| Проверка | Итог |
|---|---|
| pytest tests/civic/R10 | 58 passed |
| API v2 (CONTRACT §7) | PASS 155 · FAIL 0 · NOT_RUN 0 (жёстких FAIL 0) |
| Согласованность чисел | PASS 16 · FAIL 0 · NOT_RUN 0 |
| Сцена 0 «ИИ-разбор» (API intake) | PASS 51 · FAIL 0 (ломают показ 0) · NOT_RUN 0 — 301 обращений → 127 задач · 19 служб · 9 срочных · 174 склеено · ready 106 |
| Часть 1 (шаги 1–7 FINAL-4) | PASS 176 · FAIL 0 · NOT_RUN 2 (база FINAL-4: 172 / 0 / 0) |
| Время части 1, с | 1366-ru 186.1 (FINAL-4 226.9), 1366-kk 192.3 (FINAL-4 233.8), 375-ru 166.4 (FINAL-4 181.3), 375-kk 169.9 (FINAL-4 185.5) |
| Сцены 0 и 7–9 «Бірге» | PASS 352 · FAIL 0 · NOT_RUN 2 |
| Первый значок карты, мс | 1366x768-ru-resident 1831, 1366x768-ru-akimat 1902, 1366x768-kk-resident 1829, 1366x768-kk-akimat 2072, 375x812-ru-resident 1414, 375x812-ru-akimat 1472, 375x812-kk-resident 1516, 375x812-kk-akimat 1606 |
| Производительность | PASS первый значок с числом, 1366x768; ИНФО перемещение карты, 1366x768; PASS «Хроника города» доигрывает до конца, 13; ИНФО «Хроника города» плавность, 1366x768; PASS «Спросить Birge»: время ответа |

Шаги (код возврата, время):

```
label main-integration dee562ad
root <рабочая копия main>
sha dee562ad
pytest {'rc': 0, 'time': '34s'}
api {'rc': 0, 'time': '13s'}
numbers {'rc': 0, 'time': '13s'}
intake {'rc': 0, 'time': '16s'}
e2e {'rc': 0, 'time': '727s'}
v2 {'rc': 0, 'time': '318s'}
map {'rc': 0, 'time': '314s'}
perf {'rc': 0, 'time': '63s'}
```
