# R10 · стекло «Liquid Glass» · 74834be0

```
{"root":"/home/user/bm10","sha":"74834be0","control":"/home/user/bf3h","when":"2026-10-12T20:38:34.904Z","sizes":["1366x768","1024x768"],"langs":["ru"],"delivered":true,"machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Итого: PASS 1 · INFO 24

G-1 где стекло (и формы без стекла) · G-2 запасной вид (CSS, эмуляция, bk-glass-off, автовыключатель) · G-3 контраст текста на стекле над фонами (карта, тёмно-зелёный, синий, красный — строго; чёрный, полосы — предельные) · G-4 плавность (к/с): стекло против bk-glass-off и --control.

| Пункт | Где | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| G-2 | CSS | запасной вид без стекла: @media (prefers-reduced-transparency: reduce) и @supports not (backdrop-filter) — непрозрачный белый | **PASS** | {"glass":["web/civic/akim/akim.css","web/civic/build3d/build3d.css","web/civic/feedback/complaint.css","web/civic/heat/heat.css","web/civic/ideas/ideas.css","web/civic/proposals/proposals.css","web/civic/qr/report.css","web/civic/shell/birg |  |
| G-4 | 1366x768 | плавность карты, перетаскивание мышью без панели: 5 к/с против 7 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":7,"ratio":0.71,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перетаскивание мышью без панели: 5 к/с против 6 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":6,"ratio":0.83,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перетаскивание мышью с панелью: 6 к/с против 7 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":6,"was":7,"ratio":0.86,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перетаскивание мышью с панелью: 6 к/с против 6 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":6,"was":6,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, сдвиг без панели: 3 к/с против 4 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":3,"was":4,"ratio":0.75,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, сдвиг без панели: 3 к/с против 4 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":3,"was":4,"ratio":0.75,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, сдвиг с панелью: 6 к/с против 5 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":6,"was":5,"ratio":1.2,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, сдвиг с панелью: 6 к/с против 6 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":6,"was":6,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перелёт без панели: 4 к/с против 5 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":4,"was":5,"ratio":0.8,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перелёт без панели: 4 к/с против 4 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":4,"was":4,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перелёт с панелью: 4 к/с против 4 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":4,"was":4,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перелёт с панелью: 4 к/с против 4 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":4,"was":4,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перетаскивание мышью без панели: 8 к/с против 9 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":8,"was":9,"ratio":0.89,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перетаскивание мышью без панели: 8 к/с против 8 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":8,"was":8,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перетаскивание мышью с панелью: 8 к/с против 9 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":8,"was":9,"ratio":0.89,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перетаскивание мышью с панелью: 8 к/с против 8 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":8,"was":8,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, сдвиг без панели: 6 к/с против 6 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":6,"was":6,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, сдвиг без панели: 6 к/с против 6 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":6,"was":6,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, сдвиг с панелью: 7 к/с против 9 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":7,"was":9,"ratio":0.78,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, сдвиг с панелью: 7 к/с против 7 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":7,"was":7,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перелёт без панели: 5 к/с против 5 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":5,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перелёт без панели: 5 к/с против 6 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":6,"ratio":0.83,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перелёт с панелью: 5 к/с против 6 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":6,"ratio":0.83,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перелёт с панелью: 5 к/с против 6 — 61be62e6 · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":6,"ratio":0.83,"glass_on":true,"repeats":2} |  |
