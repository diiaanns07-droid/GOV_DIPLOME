Скриншоты реально запущенного интерфейса R06 (round 13), снятые Playwright/Chromium 2026-10-07.

harness_* — FIXTURE-стенд tests/civic/R06/harness/serve_r06.py --classifier r08: синтетические объекты и
  fixture-учётные записи, временная БД; подсказка — НАСТОЯЩИЙ ml.civic_classifier (R08 9660885,
  обучен только на синтетике). Сценарий: tests/civic/R06/browser_r13_r06.cjs (24/24 PASS).
app_* — настоящее приложение ui.web_server (56538a3 + R06 + R08 + предложенный
  research/round-13-results/R06/r01_r13_integration.patch), временная БД с синтетическим seed-demo R02,
  ширина 360 px; карта не загружена — в облачной среде нет доступа к тайлам. Сценарий: app_e2e_r06.cjs (18/18 PASS).
Реальных обращений жителей и персональных данных на снимках нет.
