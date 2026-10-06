Прогон tests/civic/R01/browser/p0_flow.cjs --backend=real (2026-10-06 ~16:15Z).
Backend: настоящие модули R02 ui/civic_store @92f7aba (SQLite во временной папке) + R06
ui/civic_feedback @eaa113d, через CivicGateway R01. Редактор создан CLI R02 (пароль через stdin),
демо-данные — встроенный синтетический пакет R02 (seed-demo) + запись, созданная смоуком.
UI: оболочка R01; карта/карточка и редактор — резервные модули R01 (R03/R04 ещё не импортированы);
форма сообщения и модерация — модуль R06.
Итог: 39 PASS / 0 FAIL / 2 NOT_RUN (подложка OpenFreeMap и attribution — хост недоступен).
Сохранность после перезапуска сервера проверена HTTP-приёмкой tests/civic/R01/test_r01_p0_api.py
(test_data_survives_restart[r02] PASS).
