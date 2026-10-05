# Запуск демо и файлы сценария «Если добавить объект» (K11, раунд 7)

Статус на кандидате `c58a3b2b175cf978ad785fef7f88d8fd9b1338f2` (код = `b3e4dc4`):
- **запуск демо проверен на Linux**;
- **функции «Если добавить объект» в сборке нет** (`city-whatif-v1` в `web/` не найден);
- раздел 2 описывает работу с файлами сценария по контракту `FEATURE_SPEC.txt`, проверенную на изолированном эталоне `whatif_io.py` и fixtures, а не в интерфейсе.

Метки:
- **[RUN-linux]** — выполнено здесь;
- **[MODELED]** — поведение Windows смоделировано на Linux;
- **[NOT_RUN]** — не запускалось. Windows-команды ниже — [NOT_RUN].

## 1. Запуск демо

**Linux / macOS** [RUN-linux на `c58a3b2`, Python 3.11]:

```bash
cd prototypes/city-evidence
python3 serve.py                 # http://127.0.0.1:8765/ ; остановка — Ctrl+C
python3 serve.py 8770 --open     # другой порт и открыть браузер
```

**Windows** [NOT_RUN]:
- двойной щелчок по `prototypes\city-evidence\run-demo.bat`. Он выполняет `chcp 65001`, задаёт `PYTHONIOENCODING=utf-8` и запускает `py -3 serve.py 8765 --open` или `python serve.py 8765 --open`. При ошибке окно ставится на паузу.
- или в cmd:

```bat
cd prototypes\city-evidence
py -3 serve.py 8765 --open
```

Если порт 8765 занят, `run-demo.bat` покажет ошибку `OSError` и паузу. Тогда запустить вручную: `py -3 serve.py 8770 --open`. Это смоделировано X2 [RUN-linux]: при занятом порте выход с кодом 1. Без сервера можно открыть `web\index.html` напрямую (`file://`).

[MODELED]: вывод `serve.py` в cp1251/cp1252 не падает (M1, M2). `file://`-адреса тестов корректны для путей Windows (M3).

## 2. Файлы сценария (по контракту; проверено на эталоне, не в интерфейсе)

- **Сохранение (экспорт):** UTF-8 **без BOM**, переводы строк LF, кириллица и казахский пишутся буквами, без `\uXXXX`. Порядок полей фиксирован: `schema_version`, `city_id`, `source_snapshot`, `category`, `control_points`, `proposed_object`. Запись атомарная: временный файл, затем `os.replace`. Недопустимый сценарий не записывается [RUN-linux].
- **Имя файла** может содержать кириллицу, казахский и пробелы: `Астана емхана ұсынысы.json`, `Шымкент_мектеп_жоба.json` [RUN-linux, ext4]. На NTFS (Windows) такие имена хранятся в UTF-16 [NOT_RUN]. macOS может хранить имя в форме NFD — эталон имена файлов не нормализует, а ID внутри файла обязаны быть в NFC.
- **Повторное открытие из другого каталога:** файл читается байтами и декодируется как UTF-8, а не в кодировке системы. Поэтому результат не зависит от текущего каталога и кодовой страницы. Проверено: открытие по относительному и абсолютному пути из другого каталога с казахским именем, сохранение → открытие → сохранение даёт те же байты [RUN-linux].
- **Блокнот Windows:** файл с BOM и CRLF принимается, BOM снимается (пометка `utf8_bom_stripped`) [RUN-linux, fixture `с_BOM_блокнот.json`]. Сохранять файл в кодировке «ANSI»/cp1251 нельзя: казахские буквы (ә, ғ, қ, ң, ө, ұ, ү, һ, і) в cp1251 не кодируются вовсе, а русский текст в cp1251 отклоняется с кодом `E_NOT_UTF8`.
- **Импорт отклоняет** (код → fixture):

| Код | Случай | Fixture |
|---|---|---|
| `E_NONFINITE` | `NaN`, `Infinity`, `1e999` | `nan.json`, `infinity.json`, `1e999.json` |
| `E_DUPLICATE_KEY` | повторный ключ JSON | `дубль_ключа.json` |
| `E_DUPLICATE_ID` | повторный ID | `дубль_id.json` |
| `E_SNAPSHOT` | чужой срез | `чужой_срез.json` |
| `E_CITY` | чужой или неизвестный город | `чужой_город.json`; также сценарий другого города при уже выбранном городе |
| `E_OUTSIDE_BBOX` | точка вне квадрата | `вне_квадрата_Астана.json` |
| `E_POINTS` | 0 или больше 10 точек | `11_точек.json` |
| `E_MULTIPLE_PROJECTS` | больше одного проекта | `два_проекта.json` |
| `E_ID_FORBIDDEN` | URL, разметка или путь в ID | `url_в_id.json` |
| `E_ID_NOT_NFC` | ID не в NFC | `nfd_id.json` |
| `E_NOT_UTF8` | файл не в UTF-8 | `cp1251.json` |
| `E_TOO_LARGE` | больше 256 KiB, до разбора | создаётся тестом |
| `E_VERSION` | неизвестная версия | `версия_2.json` |
| `E_CATEGORY` | категория проекта ≠ категории | `категория_проекта.json` |
| `E_UNKNOWN_FIELD` | лишнее поле | `лишнее_поле.json` |

- `results` из файла **отбрасываются**, расстояния пересчитываются приложением (`с_результатами.json`, пометка `untrusted_results_dropped`).
- Решения K11 там, где спецификация не задаёт числа: длина ID 1..64, ID только NFC, BOM допускается, целые длиннее 30 цифр запрещены. `source_snapshot` в fixtures — **соглашение K11** (`k11fx-sha256:` от байтов `web/data.js`, города и параметров формулы), а не API сборщика. Загрузчик принимает ожидаемый snapshot параметром.

## 3. Воспроизводимая проверка

**Linux** [RUN-linux]:

```bash
git fetch origin claude/beautiful-clarke-sbzomj
python3 research/round-5-results/K11/extract_build.py --sha <SHA> --out <dir>
NODE_PATH=$(npm root -g) python3 research/round-7-results/K11/run_k11r7.py --app-root <dir>/prototypes/city-evidence --label <SHA> --browser --out report.json
# только файлы сценария:
python3 research/round-7-results/K11/test_whatif_io.py
# проверить отдельный файл (вывод только ASCII):
python3 research/round-7-results/K11/whatif_io.py fingerprint --app-root <dir>/prototypes/city-evidence --city astana
python3 research/round-7-results/K11/whatif_io.py check "Астана емхана ұсынысы.json" --snapshot <source_snapshot> --bbox <minlon,minlat,maxlon,maxlat>
```

**Windows** [NOT_RUN]: те же команды через `py -3`, пути с `\`. Без `--browser`, если не установлен Playwright: шаг браузера тогда `not_run`.

Шаги `run_k11r7.py`:

| Шаг | Что делает | Итог |
|---|---|---|
| 1 | smoke запуска (свой `serve.py`, явная остановка) | pass/fail |
| 2 | X1–X3 | pass/fail |
| 3 | тесты файлов сценария против `data.js` этой копии | pass / `fixtures_stale` (fixtures от другого `data.js`: перегенерировать `make_fixtures.py --app-root … --app-sha …`) / fail |
| 4 | есть ли `city-whatif-v1` в `web/` | `present` / `not_present`; интеграционные проверки в интерфейсе пока `not_run` |

## 4. Не проверено

- Windows целиком: `run-demo.bat`, `py -3`, NTFS-имена, браузер.
- Экспорт и импорт в интерфейсе: функции нет в `c58a3b2`.
- macOS (NFD-имена файлов).
