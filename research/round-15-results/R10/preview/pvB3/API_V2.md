# R10 · API v2 раунда 15 (CONTRACT §7) превью pvB3: R01 dbf25c05 + R02 + R07 + R08 + R09 + R16 c5836427 + R17

Сборка: `<превью pvB3>` · демо-мир: да · PASS 118 · FAIL 0 · NOT_RUN 2

| Роль | маршрутов | готово | ждёт модуль (503) | модуль упал | нет в шлюзе |
|---|---|---|---|---|---|
| R03 | 1 | 0 | 1 | 0 | 0 |
| R04 | 3 | 0 | 3 | 0 | 0 |
| R06 | 3 | 0 | 3 | 0 | 0 |
| R07 | 1 | 1 | 0 | 0 | 0 |
| R08 | 2 | 2 | 0 | 0 | 0 |
| R09 | 3 | 3 | 0 | 0 | 0 |
| R12 | 2 | 2 | 0 | 0 | 0 |
| R13 | 8 | 0 | 8 | 0 | 0 |
| R16 | 12 | 12 | 0 | 0 | 0 |
| R17 | 11 | 11 | 0 | 0 | 0 |

| Статус | Раздел | Проверка | Подробно | Владелец |
|---|---|---|---|---|
| PASS | FINAL-4 | маршруты FINAL-4 на месте (74) |  | R01 |
| PASS | FINAL-4 | модули FINAL-4 подключены, как в FINAL-4 (ready) |  | владелец модуля |
| PASS | §7 | GET meetings: модуля нет → 503 module_not_ready | {"module": "ui.civic_meetings"} |  |
| PASS | §7 | GET meetings/{meeting}: модуля нет → 503 module_not_ready | {"module": "ui.civic_meetings"} |  |
| PASS | §7 | GET meetings/updates: модуля нет → 503 module_not_ready | {"module": "ui.civic_meetings"} |  |
| PASS | §7 | POST meetings: модуля нет → 503 module_not_ready | {"module": "ui.civic_meetings"} |  |
| PASS | §7 | POST meetings/{meeting}/order: модуля нет → 503 module_not_ready | {"module": "ui.civic_meetings"} |  |
| PASS | §7 | POST meetings/{meeting}/result: модуля нет → 503 module_not_ready | {"module": "ui.civic_meetings"} |  |
| PASS | §7 | POST meetings/{meeting}/register: модуля нет → 503 module_not_ready | {"module": "ui.civic_meetings"} |  |
| PASS | §7 | POST meetings/{meeting}/question: модуля нет → 503 module_not_ready | {"module": "ui.civic_meetings"} |  |
| PASS | §7 | POST route: модуля нет → 503 module_not_ready | {"module": "ui.civic_ml_api"} |  |
| PASS | §7 | POST reply-draft: модуля нет → 503 module_not_ready | {"module": "ui.civic_ml_api"} |  |
| PASS | §7 | POST moderate: модуля нет → 503 module_not_ready | {"module": "ui.civic_ml_api"} |  |
| PASS | §7 | POST assistant/ask: модуля нет → 503 module_not_ready | {"module": "agent.civic_assistant.api"} |  |
| PASS | §7 | GET notifications: модуля нет → 503 module_not_ready | {"module": "ui.civic_store.v2"} |  |
| PASS | §7 | POST notifications/read: модуля нет → 503 module_not_ready | {"module": "ui.civic_store.v2"} |  |
| PASS | §7 | POST ideas/{idea}/to-initiative: модуля нет → 503 module_not_ready | {"module": "ui.civic_store.v2"} |  |
| PASS | подготовка | id записей для проверки | {"initiative": "i-w15-04", "yard": "yard-1531186335", "_yard_point": [71.2768929, 51.1308766], "incident": "inc-w15-buran", "idea": "i-demo-d1c790ce", "complain |  |
| PASS | ответ | GET together/initiatives: житель без входа → 200 |  | R16 |
| PASS | формат | GET together/initiatives: житель без входа: §5 и §10 |  | R16 |
| PASS | ошибки | GET together/initiatives: неверный параметр → 400 понятная ошибка |  | R16 |
| PASS | доступ | POST together/initiatives: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/initiatives: житель → 201 |  | R16 |
| PASS | формат | POST together/initiatives: житель: §5 и §10 |  | R16 |
| PASS | ответ | GET together/initiatives/{initiative}: житель без входа → 200 |  | R16 |
| PASS | формат | GET together/initiatives/{initiative}: житель без входа: §5 и §10 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/join: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/initiatives/{initiative}/join: житель → 200 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/leave: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/initiatives/{initiative}/leave: житель → 200 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/support: без входа → 401 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/support: вход без CSRF → 403 |  | R16 |
| PASS | ответ | POST together/initiatives/{initiative}/support: сотрудник → 200 |  | R16 |
| PASS | ошибки | POST together/initiatives/{initiative}/support: сотрудник, пустое тело → 200 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/moderate: без входа → 401 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/moderate: вход без CSRF → 403 |  | R16 |
| PASS | ответ | POST together/initiatives/{initiative}/moderate: сотрудник → 409 (правило модуля) | "already_moderated: Инициатива уже проверена." | R16 |
| PASS | ошибки | POST together/initiatives/{initiative}/moderate: сотрудник, пустое тело → 422 понятная ошибка |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/report: не автор и не сотрудник → 400 |  | R16 |
| PASS | ошибки | POST together/initiatives/{initiative}/report: сотрудник, пустое тело → 422 понятная ошибка |  | R16 |
| PASS | ответ | GET together/yards/{yard}: житель без входа → 200 |  | R16 |
| PASS | формат | GET together/yards/{yard}: житель без входа: §5 и §10 |  | R16 |
| PASS | доступ | POST together/yards/{yard}/join: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/yards/{yard}/join: житель → 200 |  | R16 |
| PASS | доступ | POST together/yards/{yard}/leave: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/yards/{yard}/leave: житель → 200 |  | R16 |
| PASS | доступ | GET together/updates: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | GET together/updates: житель → 200 |  | R16 |
| PASS | формат | GET together/updates: житель: §5 и §10 |  | R16 |
| PASS | ошибки | GET together/updates: неверный параметр → 400 понятная ошибка |  | R16 |
| PASS | ответ | GET agencies: житель без входа → 200 |  | R17 |
| PASS | формат | GET agencies: житель без входа: §5 и §10 |  | R17 |
| PASS | доступ | GET agencies/board: без входа → 401 |  | R17 |
| PASS | ответ | GET agencies/board: сотрудник → 200 |  | R17 |
| PASS | формат | GET agencies/board: сотрудник: §5 и §10 |  | R17 |
| PASS | ошибки | GET agencies/board: неверный параметр → 400 понятная ошибка |  | R17 |
| PASS | доступ | GET agencies/joint: без входа → 401 |  | R17 |
| PASS | ответ | GET agencies/joint: сотрудник → 200 |  | R17 |
| PASS | формат | GET agencies/joint: сотрудник: §5 и §10 |  | R17 |
| PASS | доступ | GET agencies/handoffs: без входа → 401 |  | R17 |
| PASS | ответ | GET agencies/handoffs: сотрудник → 200 |  | R17 |
| PASS | формат | GET agencies/handoffs: сотрудник: §5 и §10 |  | R17 |
| PASS | ошибки | GET agencies/handoffs: неверный параметр → 400 понятная ошибка |  | R17 |
| PASS | ответ | GET incidents: житель без входа → 200 |  | R17 |
| PASS | формат | GET incidents: житель без входа: §5 и §10 |  | R17 |
| PASS | ответ | GET incidents/{incident}: житель без входа → 200 |  | R17 |
| PASS | формат | GET incidents/{incident}: житель без входа: §5 и §10 |  | R17 |
| PASS | доступ | POST incidents: без входа → 401 |  | R17 |
| PASS | доступ | POST incidents: вход без CSRF → 403 |  | R17 |
| PASS | ответ | POST incidents: сотрудник → 201 |  | R17 |
| PASS | формат | POST incidents: сотрудник: §5 и §10 |  | R17 |
| PASS | ошибки | POST incidents: сотрудник, пустое тело → 422 понятная ошибка |  | R17 |
| PASS | доступ | POST incidents/{incident}/task: без входа → 401 |  | R17 |
| PASS | доступ | POST incidents/{incident}/task: вход без CSRF → 403 |  | R17 |
| PASS | ответ | POST incidents/{incident}/task: сотрудник → 200 |  | R17 |
| PASS | ошибки | POST incidents/{incident}/task: сотрудник, пустое тело → 422 понятная ошибка |  | R17 |
| PASS | доступ | POST incidents/{incident}/update: без входа → 401 |  | R17 |
| PASS | доступ | POST incidents/{incident}/update: вход без CSRF → 403 |  | R17 |
| PASS | ответ | POST incidents/{incident}/update: сотрудник → 200 |  | R17 |
| PASS | ошибки | POST incidents/{incident}/update: сотрудник, пустое тело → 422 понятная ошибка |  | R17 |
| PASS | доступ | POST incidents/{incident}/close: без входа → 401 |  | R17 |
| PASS | доступ | POST incidents/{incident}/close: вход без CSRF → 403 |  | R17 |
| PASS | ответ | POST incidents/{incident}/close: сотрудник → 200 |  | R17 |
| PASS | ошибки | POST incidents/{incident}/close: сотрудник, пустое тело → 422 понятная ошибка |  | R17 |
| PASS | доступ | GET incidents/updates: житель без X-Birge-Device → 200 (общая часть) |  | R17 |
| PASS | ответ | GET incidents/updates: житель → 200 |  | R17 |
| PASS | формат | GET incidents/updates: житель: §5 и §10 |  | R17 |
| PASS | ошибки | GET incidents/updates: неверный параметр → 400 понятная ошибка |  | R17 |
| PASS | доступ | POST complaints/{complaint}/handoff: без входа → 401 |  | R09 |
| PASS | доступ | POST complaints/{complaint}/handoff: вход без CSRF → 403 |  | R09 |
| PASS | ответ | POST complaints/{complaint}/handoff: сотрудник → 200 |  | R09 |
| PASS | ошибки | POST complaints/{complaint}/handoff: сотрудник, пустое тело → 422 понятная ошибка |  | R09 |
| PASS | доступ | POST complaints/{complaint}/services: без входа → 401 |  | R09 |
| PASS | доступ | POST complaints/{complaint}/services: вход без CSRF → 403 |  | R09 |
| PASS | ответ | POST complaints/{complaint}/services: сотрудник → 200 |  | R09 |
| PASS | ошибки | POST complaints/{complaint}/services: сотрудник, пустое тело → 422 понятная ошибка |  | R09 |
| PASS | доступ | POST complaints/{complaint}/part: без входа → 401 |  | R09 |
| PASS | доступ | POST complaints/{complaint}/part: вход без CSRF → 403 |  | R09 |
| PASS | ответ | POST complaints/{complaint}/part: сотрудник → 200 |  | R09 |
| PASS | ошибки | POST complaints/{complaint}/part: сотрудник, пустое тело → 422 понятная ошибка |  | R09 |
| PASS | доступ | GET works-calendar: без входа → 401 |  | R12 |
| NOT_RUN | ответ | GET works-calendar: сотрудник → 404 «Адрес API не найден.» | "модуль R12 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R12 |
| PASS | ошибки | GET works-calendar: неверный параметр → 400 понятная ошибка |  | R12 |
| PASS | доступ | GET works-conflicts: без входа → 401 |  | R12 |
| NOT_RUN | ответ | GET works-conflicts: сотрудник → 404 «Адрес API не найден.» | "модуль R12 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R12 |
| PASS | ошибки | GET works-conflicts: неверный параметр → 400 понятная ошибка |  | R12 |
| PASS | ответ | GET heat/replay: житель без входа → 200 |  | R07 |
| PASS | формат | GET heat/replay: житель без входа: §5 и §10 |  | R07 |
| PASS | ошибки | GET heat/replay: неверный параметр → 400 понятная ошибка |  | R07 |
| PASS | доступ | GET akim/board: без входа → 401 |  | R08 |
| PASS | ответ | GET akim/board: сотрудник → 200 |  | R08 |
| PASS | доступ | GET akim/week: без входа → 401 |  | R08 |
| PASS | ответ | GET akim/week: сотрудник → 200 |  | R08 |
| PASS | ошибки | GET akim/week: неверный параметр → 400 понятная ошибка |  | R08 |
| PASS | поведение | «Я приду»: дважды с одного устройства → +1 (6 → 7) |  | R16 |
| PASS | поведение | «Я приду»: «Не приду / выйти» → обратно 6 |  | R16 |
| PASS | поведение | «Я живу здесь»: дважды с одного устройства → +1 (59 → 60) |  | R16 |
| PASS | поведение | «Я живу здесь»: «Не приду / выйти» → обратно 59 |  | R16 |
| PASS | поведение | передача в другую службу: с причиной, срок ответа не начинается заново |  | R09 |
| PASS | журнал | сервер без Traceback модулей во время проверки |  | по тексту ошибки |
