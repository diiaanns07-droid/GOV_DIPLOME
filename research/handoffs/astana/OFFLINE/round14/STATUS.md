# OFFLINE — завершено

Ветка claude/r14-offline, worktree birge-offline, основная папка не менялась.
Код и проверка: afbc6ee7e22fdf000364bbdca26d0a60dc6421c6, основа после rebase: 13ae79007e592ea45dba69a8ae41e0fc23d1c6c9.
Push кода подтверждён. Итоговые отчёт и доказательства — следующим коммитом.
Подложка Protomaps 20261010 (10 146 737 байт), глифы, спрайты, 3D-здания,
РУС/ҚАЗ, local-first и ?offline=1 работают без интернета.
13 transport tests PASS; 261 resource hashes PASS; 4/4 профиля карты,
4 новых проекта, 12 проверок якоря; heat 5→17, orange→red.
R10: 79 PASS / 18 FAIL / 4 NOT_RUN; объяснения в OFFLINE.md.
162 итоговых скриншотов. Внешних запросов 0, HTTP/MapLibre ошибок 0.
R09: две JS-ошибки после закрытия отправленной жалобы на телефоне; отдельно
воспроизведены с offline=true/false. Стек complaint.js:534:52, R09_ISSUE.md.
Тайлы НЕ в Git: data/civic/astana/tiles/astana.pmtiles. Восстановление RUN.txt.
Модули R01 подключены только минимальным patch из INTEGRATION.txt.
Далее R01 импортирует указанные файлы и архив, использует чистую seeded DB.
Не считать публичные тестовые обращения в acceptance DB реальными данными.
Тестовый сервер после приёмки остановить; запуск в RUN.txt. Никакие ключи не нужны.
