# R10 · приёмка сборки B6.9 R01 63bb6e6d

Код: `63bb6e6d` · отчёт: `<scratch R10>/runs/b6-63bb6e6d-acc`

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
| Время части 1, с | 1366-ru 176.0 (FINAL-4 226.9), 1366-kk 178.3 (FINAL-4 233.8), 375-ru 160.4 (FINAL-4 181.3), 375-kk 164.0 (FINAL-4 185.5) |
| Сцены 0 и 7–9 «Бірге» | PASS 352 · FAIL 0 · NOT_RUN 2 |
| Первый значок карты, мс | 1366x768-ru-resident 1509, 1366x768-ru-akimat 1558, 1366x768-kk-resident 1547, 1366x768-kk-akimat 1514, 375x812-ru-resident 1378, 375x812-ru-akimat 1472, 375x812-kk-resident 1398, 375x812-kk-akimat 1415 |
| Производительность | PASS первый значок с числом, 1366x768; ИНФО перемещение карты, 1366x768; PASS «Хроника города» доигрывает до конца, 13; ИНФО «Хроника города» плавность, 1366x768; PASS «Спросить Birge»: время ответа |

Шаги (код возврата, время):

```
label B6.9 R01 63bb6e6d
root <scratch R10>/builds/r01-b6-63bb6e6d
sha 63bb6e6d
pytest {'rc': 0, 'time': '38s'}
api {'rc': 0, 'time': '15s'}
numbers {'rc': 0, 'time': '14s'}
intake {'rc': 0, 'time': '18s'}
e2e {'rc': 0, 'time': '692s'}
v2 {'rc': 0, 'time': '306s'}
map {'rc': 0, 'time': '292s'}
perf {'rc': 0, 'time': '58s'}
```
