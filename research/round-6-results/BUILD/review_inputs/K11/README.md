# K11 round 5 (REVIEW): smoke-тест запуска демо `prototypes/city-evidence`

Проверяется готовый BUILD: `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`, путь `prototypes/city-evidence/`. Тест не меняет BUILD и не зависит от результатов других сессий.

## Как запустить на любой версии BUILD

```bash
# 1. Побайтно извлечь нужный SHA (или указать уже существующую копию)
git fetch origin claude/beautiful-clarke-sbzomj
python research/round-5-results/K11/extract_build.py --sha <SHA> --out <dir>

# 2. Smoke: статические проверки, свой serve.py на свободном порту, HTTP-проверки localhost,
#    явная остановка запущенного процесса, моделирование Windows
python research/round-5-results/K11/k11_demo_smoke.py --app-root <dir>/prototypes/city-evidence --label <SHA> --out report.json
#    + браузер (Playwright должен разрешаться из Node, например NODE_PATH=$(npm root -g)):
NODE_PATH=$(npm root -g) python research/round-5-results/K11/k11_demo_smoke.py --app-root <dir>/prototypes/city-evidence --browser --out report.json

# 3. Против уже запущенного сервера (ничего не запускает и не останавливает)
python research/round-5-results/K11/k11_demo_smoke.py --url http://127.0.0.1:8765/ [--browser]
```

Нужен только Python 3 stdlib. Для `--browser` и M3 дополнительно Node, для `--browser` ещё Playwright. Без них эти проверки получают статус `not_run`. Exit code 1, если есть `fail` или `modeled_fail`.

### Как тест останавливает свой сервер (L2)

1. На POSIX `SIGINT` группе процессов (эквивалент Ctrl+C), ожидание 5 с.
2. Затем `terminate()`, ещё 5 с.
3. Затем `kill()`.

Записываются шаги, код возврата и закрыт ли порт. На Windows путь такой: `CREATE_NEW_PROCESS_GROUP`, затем `terminate()`, затем `kill()` — **не запускался**.

## Проверки

| ID | Что | Где |
|---|---|---|
| S1 | стартовая страница, `serve.py`, README и `web/*.js` есть | копия |
| S2 | все свои текстовые файлы (вне `inputs/`) — строгий UTF-8; BOM/CRLF перечисляются | копия |
| S3 | нет скрытых абсолютных путей (`/tmp/`, `/home/…`, `/root/`, `C:\…`) в коде, документации и сгенерированных `web/*.js` | копия |
| S4 | Node-тесты строят `file://` через `url.pathToFileURL`, а не склейкой строк | копия |
| S5 | рядом с `serve.py` есть запускалка для Windows (`.bat`/`.cmd`/`.ps1`) | копия |
| S6 | в README есть команда запуска для Windows (запускалка, `py serve.py` или `python serve.py`; `python3` и `run.bat` основного сайта не считаются) | копия |
| S7 | текстовый ввод-вывод Python с явной кодировкой (`serve.py`, `tools/`, `tests/`) | копия |
| S8 | браузерный smoke по умолчанию пишет результаты внутрь копии, а не в `../../../research` | копия |
| L1 | `serve.py <port>` запускается и слушает 127.0.0.1 | процесс |
| H1–H8 | `/` → 200; UTF-8 и `<meta charset=utf-8>`; заголовки (info); нет внешних и `file://` ресурсов; нет `type=module`; все скрипты 200, JS MIME, UTF-8, те же байты, что на диске; 404 на отсутствующий файл; нет выхода за `web/` (`/../serve.py`, `%2e%2e`) | localhost |
| H9 | сервер недоступен по LAN-адресу (только loopback) | localhost |
| B1 | (`--browser`) headless Chromium открывает демо по http и по `file://` (через `pathToFileURL`): данные обоих городов, нет ошибок консоли и внешних запросов | браузер |
| L2 | запущенный тестом процесс остановлен явно, порт освобождён | процесс |
| L3 | вывод сервера при старте и остановке (info) | процесс |
| M1, M2 | **modeled**: `serve.py` стартует при перенаправленном stdout в cp1251 / cp1252 (ANSI-кодировки Windows) | процесс |
| M3 | **modeled**: `file://`-URL, склеенный из Windows-пути (`path.win32`), против `pathToFileURL` | Node |
| W1 | реальный запуск на Windows | `not_run`: Windows нет |

## Baseline `0bf27de` (Linux)

Файлы: `baseline_0bf27de.json`, `baseline_0bf27de.txt`. Итог: **15 pass, 4 fail, 2 modeled_fail, 1 modeled_pass, 2 info, 1 not_run.**

Ожидаемые падения baseline. Это дефекты именно `0bf27de`; новую версию по ним можно оценивать только после запуска теста на её SHA.

| ID | Факт на `0bf27de` |
|---|---|
| S4 fail | `tests/smoke.cjs` L8 `"file://" + path.resolve(...)` и L92 `"file://" + path.join(dir, "index.html")` |
| S5 fail | `.bat`/`.cmd`/`.ps1` рядом с `serve.py` нет |
| S6 fail | README запускает только `python3 serve.py`. Сам README пишет: «Windows/macOS не проверялись» |
| S8 fail | `tests/smoke.cjs` L6: вывод по умолчанию в `path.join(__dirname, "..", "..", "..", "research", "round-4-results", "BUILD", "smoke")` — вне копии приложения |
| M2 modeled_fail | `serve.py` при stdout=cp1252 завершается с exit 1 до `serve_forever()`: `UnicodeEncodeError` на русской строке приветствия, которую печатает `print` после создания сервера. Запросы не обслуживаются. Для cp1251 стартует (M1) |
| M3 modeled_fail | склейка даёт `file://C:\Users\u\city-evidence\web\index.html`, `pathToFileURL` — `file:///C:/Users/u/city-evidence/web/index.html` |

Остальное на baseline проходит:
- UTF-8, `meta charset`, абсолютных путей нет;
- `serve.py` слушает только loopback, отдаёт байты как на диске, выход за `web/` закрыт, порт освобождается после SIGINT;
- Chromium открывает демо по http и `file://`.

Как информация: заголовки `Content-type` без `charset` (`text/html`, `text/javascript`), кодировку браузер берёт из `<meta charset>`. При Ctrl+C сервер печатает трассировку `KeyboardInterrupt`.

## Patch-предложение (не FIXED)

`proposed_launch_fix.patch` — предложение для сборщика, а не изменение BUILD. Правит 4 файла `prototypes/city-evidence/`:
- `serve.py`: `sys.stdout.reconfigure(errors="replace")` перед печатью приветствия; чистый выход по Ctrl+C;
- новый `run-demo.bat`: `cd /d "%~dp0"`, `PYTHONUTF8=1`, `py -3 serve.py` или `python serve.py`;
- `tests/smoke.cjs`: `pathToFileURL` вместо склейки строк, вывод по умолчанию в `tests/_smoke_out/`;
- `README.md`: команда для Windows с пометкой «не проверено на Windows».

Что проверено на Linux:
- `git apply --check` на дереве `0bf27de`: OK;
- `k11_demo_smoke.py --browser` на копии с патчем: **19 pass, 3 modeled_pass, 2 info, 1 not_run, 0 fail** (`proposal_on_0bf27de.*`). На этой копии S4, S5, S6, S8, M2, M3 переключились на pass;
- собственный `tests/smoke.cjs` сборщика на этой копии: exit 0, 16 PASS, результаты в `tests/_smoke_out/`;
- остановка по SIGINT: код 0, без трассировки.

`run-demo.bat` на Windows **не запускался**: Windows нет. Сам `.bat` проверен только чтением.

В патче строки `run-demo.bat` записаны с CRLF. Если `.patch` выгружен с `core.autocrlf=true`, `git apply` может не совпасть по байтам. Эталон предложения — `make_proposal.py`: запустить его в корне копии.

## Другие прогоны

- `url_mode_0bf27de.*`: `--url` против отдельно запущенного `serve.py` из `0bf27de` с `--browser`: 8 pass, 1 info. Сервер запускал и останавливал проверяющий, а не тест.
- `info_fd43f9a.*`: новый коммит сборщика `fd43f9a` (этап A раунда 5, после `0bf27de`), только для информации. Те же 4 fail (S4, S5, S6, S8) и 2 modeled_fail (M2, M3). По проверкам запуска эта версия не отличается от baseline. Это не оценка всего этапа A.
