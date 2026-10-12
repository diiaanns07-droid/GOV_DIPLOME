# R10 · стекло «Liquid Glass» · 61be62e6

```
{"root":"/home/user/bf3h","sha":"61be62e6","control":"/home/user/bf3g","when":"2026-10-12T13:39:07.300Z","sizes":["1366x768","1024x768"],"langs":["ru"],"delivered":true,"machine":{"cpu":"Intel(R) Xeon(R) Processor @ 2.10GHz","cores":4,"mem_gb":16,"platform":"linux 6.18.44-fc-v114","node":"v22.22.0"}}
```

Итого: PASS 1 · INFO 16

G-1 где стекло (и формы без стекла) · G-2 запасной вид (CSS, эмуляция, bk-glass-off, автовыключатель) · G-3 контраст текста на стекле над фонами (карта, тёмно-зелёный, синий, красный — строго; чёрный, полосы — предельные) · G-4 плавность (к/с): стекло против bk-glass-off и --control.

| Пункт | Где | Проверка | Итог | Подробно | Кадр |
|---|---|---|---|---|---|
| G-2 | CSS | запасной вид без стекла: @media (prefers-reduced-transparency: reduce) и @supports not (backdrop-filter) — непрозрачный белый | **PASS** | {"glass":["web/civic/akim/akim.css","web/civic/build3d/build3d.css","web/civic/feedback/complaint.css","web/civic/ideas/ideas.css","web/civic/qr/report.css","web/civic/shell/birge.css","web/civic/ui-kit/components.css"],"reduced":["web/civi |  |
| G-4 | 1366x768 | плавность карты, сдвиг без панели: 3 к/с против 4 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":3,"was":4,"ratio":0.75,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, сдвиг без панели: 3 к/с против 3 — 3d8c426f · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":3,"was":3,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, сдвиг с панелью: 5 к/с против 5 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":5,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, сдвиг с панелью: 5 к/с против 5 — 3d8c426f · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":5,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перелёт без панели: 4 к/с против 4 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":4,"was":4,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перелёт без панели: 4 к/с против 4 — 3d8c426f · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":4,"was":4,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перелёт с панелью: 4 к/с против 4 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":4,"was":4,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1366x768 | плавность карты, перелёт с панелью: 4 к/с против 3 — 3d8c426f · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":4,"was":3,"ratio":1.33,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, сдвиг без панели: 5 к/с против 4 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":4,"ratio":1.25,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, сдвиг без панели: 5 к/с против 6 — 3d8c426f · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":6,"ratio":0.83,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, сдвиг с панелью: 6 к/с против 7 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":6,"was":7,"ratio":0.86,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, сдвиг с панелью: 6 к/с против 6 — 3d8c426f · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":6,"was":6,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перелёт без панели: 5 к/с против 5 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":5,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перелёт без панели: 5 к/с против 4 — 3d8c426f · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":4,"ratio":1.25,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перелёт с панелью: 5 к/с против 5 — без стекла (bk-glass-off) · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":5,"ratio":1,"glass_on":true,"repeats":2} |  |
| G-4 | 1024x768 | плавность карты, перелёт с панелью: 5 к/с против 5 — 3d8c426f · программный WebGL — мерить на ноутбуке (Codex М9) | **INFO** | {"now":5,"was":5,"ratio":1,"glass_on":true,"repeats":2} |  |
