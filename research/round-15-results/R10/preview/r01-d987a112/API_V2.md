# R10 · API v2 раунда 15 (CONTRACT §7) R01 d987a112 (маршруты раунда 15)

Сборка: `<превью>` · демо-мир: да · PASS 59 · FAIL 0 · NOT_RUN 9

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
| R16 | 12 | 0 | 12 | 0 | 0 |
| R17 | 11 | 0 | 11 | 0 | 0 |

| Статус | Раздел | Проверка | Подробно | Владелец |
|---|---|---|---|---|
| PASS | FINAL-4 | маршруты FINAL-4 на месте (74) |  | R01 |
| PASS | FINAL-4 | модули FINAL-4 подключены, как в FINAL-4 (ready) |  | владелец модуля |
| PASS | §7 | GET together/initiatives: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | POST together/initiatives: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | GET together/initiatives/{initiative}: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | POST together/initiatives/{initiative}/join: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | POST together/initiatives/{initiative}/leave: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | POST together/initiatives/{initiative}/support: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | POST together/initiatives/{initiative}/moderate: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | POST together/initiatives/{initiative}/report: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | GET together/yards/{yard}: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | POST together/yards/{yard}/join: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | POST together/yards/{yard}/leave: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | GET together/updates: модуля нет → 503 module_not_ready | {"module": "ui.civic_together"} |  |
| PASS | §7 | GET agencies: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | GET agencies/board: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | GET agencies/joint: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | GET agencies/handoffs: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | GET incidents: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | GET incidents/{incident}: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | POST incidents: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | POST incidents/{incident}/task: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | POST incidents/{incident}/update: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | POST incidents/{incident}/close: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
| PASS | §7 | GET incidents/updates: модуля нет → 503 module_not_ready | {"module": "ui.civic_agencies"} |  |
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
| PASS | подготовка | id записей для проверки | {"idea": "i-demo-11193ec5", "complaint": "c-237e2d6f4a0001eb"} |  |
| PASS | доступ | POST complaints/{complaint}/handoff: без входа → 401 |  | R09 |
| PASS | доступ | POST complaints/{complaint}/handoff: вход без CSRF → 403 |  | R09 |
| NOT_RUN | ответ | POST complaints/{complaint}/handoff: сотрудник → 404 «Адрес не найден.» | "модуль R09 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R09 |
| PASS | ошибки | POST complaints/{complaint}/handoff: сотрудник, пустое тело → 404 понятная ошибка |  | R09 |
| PASS | доступ | POST complaints/{complaint}/services: без входа → 401 |  | R09 |
| PASS | доступ | POST complaints/{complaint}/services: вход без CSRF → 403 |  | R09 |
| NOT_RUN | ответ | POST complaints/{complaint}/services: сотрудник → 404 «Адрес не найден.» | "модуль R09 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R09 |
| PASS | ошибки | POST complaints/{complaint}/services: сотрудник, пустое тело → 404 понятная ошибка |  | R09 |
| PASS | доступ | POST complaints/{complaint}/part: без входа → 401 |  | R09 |
| PASS | доступ | POST complaints/{complaint}/part: вход без CSRF → 403 |  | R09 |
| NOT_RUN | ответ | POST complaints/{complaint}/part: сотрудник → 404 «Адрес не найден.» | "модуль R09 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R09 |
| PASS | ошибки | POST complaints/{complaint}/part: сотрудник, пустое тело → 404 понятная ошибка |  | R09 |
| PASS | доступ | GET works-calendar: без входа → 401 |  | R12 |
| NOT_RUN | ответ | GET works-calendar: сотрудник → 404 «Адрес API не найден.» | "модуль R12 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R12 |
| PASS | ошибки | GET works-calendar: неверный параметр → 400 понятная ошибка |  | R12 |
| PASS | доступ | GET works-conflicts: без входа → 401 |  | R12 |
| NOT_RUN | ответ | GET works-conflicts: сотрудник → 404 «Адрес API не найден.» | "модуль R12 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R12 |
| PASS | ошибки | GET works-conflicts: неверный параметр → 400 понятная ошибка |  | R12 |
| NOT_RUN | ответ | GET heat/replay: житель без входа → 404 «нет такого адреса» | "модуль R07 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R07 |
| PASS | ошибки | GET heat/replay: неверный параметр → 400 понятная ошибка |  | R07 |
| PASS | доступ | GET akim/board: без входа → 401 |  | R08 |
| NOT_RUN | ответ | GET akim/board: сотрудник → 404 «нет такого адреса» | "модуль R08 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R08 |
| PASS | доступ | GET akim/week: без входа → 401 |  | R08 |
| NOT_RUN | ответ | GET akim/week: сотрудник → 404 «нет такого адреса» | "модуль R08 ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)" | R08 |
| PASS | ошибки | GET akim/week: неверный параметр → 400 понятная ошибка |  | R08 |
| NOT_RUN | поведение | передача в другую службу: с причиной, срок ответа не начинается заново | "маршрута передачи в модуле R09 ещё нет (поставки нет в сборке)" | R09 |
| PASS | журнал | сервер без Traceback модулей во время проверки |  | по тексту ошибки |
