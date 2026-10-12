# Birge · запуск на Windows с нуля (RUNBOOK)

> Документ R14 (раунд 14), обновлён ночью 10→11 октября 2026 и 12 октября (ночь, FINAL-2). Основан на `run.bat`, `run-city.bat`,
> `ui/web_server.py`, `research/round-14-results/R01/RUN.txt` и `DEMO_SCRIPT.md`, `research/round-14-results/R03/RUN.txt`,
> `research/round-14-results/LOCAL/LOCAL_B2.md` и `LOCAL_FINAL.md`.
> Проверено R14 в облаке (Linux, Python 3.13.16, `CIVIC_DEMO=1`): на B2 f54361d и FINAL-кандидатах до 8e67c65 — 37 маршрутов
> v2 `ready`; на **FINAL-2 0f5101a** — `civic-v2: ready R04, R06, R07, R08, R09, R12, R13`, **55 маршрутов v2 `ready`**, весь
> pytest 3 301 passed / 24 skipped / 2 failed (стыки тестов ролей, показ не затронут). **`run-city.bat` на Windows** запускал
> Codex на ноутбуке владельца: B2 (`LOCAL_B2.md`) и FINAL-кандидат 8e67c65 (`LOCAL_FINAL.md`: сценарий R10 140 / 0 с интернетом
> и без него, модель v2 ONNX, архив карты PMTiles).

## 0. Коротко (если всё уже стоит)

```bat
cd C:\Users\LEGION\Desktop\hackalem\hack-d3b2c613-stupits
git fetch origin
git switch --detach 0f5101a   & rem FINAL-2 (12.10; R10 предварительно принял шаг 3 28e23e3). Принятый FINAL-кандидат — 8e67c65. FINAL-3 (вечер 12.10) и FINAL 15.10 — SHA из STATUS.md R01
run-city.bat
```

Откроется `http://127.0.0.1:8611/`. Остановить — `Ctrl+C` в окне консоли.

## 1. Что нужно на компьютере

| Что | Зачем | Обязательно? |
|---|---|---|
| Windows 10/11 | ноутбук демо | да |
| Python 3.11–3.14 (проверены 3.12 и 3.13) с галочкой «Add python.exe to PATH» | сервер и все модули | да |
| Git | получить сборку | да |
| Интернет при первом запуске | `pip install` зависимостей (несколько минут) | только первый раз |
| Интернет во время демо | подложка карты и 3D-здания с OpenFreeMap | желательно; без него — упрощённый фон с сообщением |
| Браузер Chrome / Edge (WebGL2) | интерфейс, 3D-превью | да |
| Node.js 20+ и Playwright | только для браузерных тестов разработчика | нет |
| venv `C:\Users\LEGION\venvs\birge-ml` (Python 3.12, torch с CUDA) | только обучение модели (§6) | нет |

Ключ OpenAI/NVIDIA для работы Birge **не нужен**: в рантайме языковая модель не используется. Ключ нужен только советнику хакатонного режима (`#training`) и скриптам LLM-синтетики/разметки (§6).

## 2. Получить сборку

Рабочая папка владельца: `C:\Users\LEGION\Desktop\hackalem\hack-d3b2c613-stupits`.

```bat
cd C:\Users\LEGION\Desktop\hackalem\hack-d3b2c613-stupits
git fetch origin
git switch --detach origin/claude/sharp-dijkstra-0t87gl
```

- Ветка сборки — у интегратора R01; точный SHA текущей сборки (B1 / B2 / FINAL) — в `research/handoffs/astana/R01/round14/STATUS.md` этой ветки. Для демо лучше переключаться на **SHA**, а не на ветку, чтобы сборка не поменялась под руками.
- `main` для запуска не используется (там старая версия).
- Если в папке есть свои незакоммиченные изменения, `git switch` откажется — сначала `git status`, сохраните нужное (или возьмите отдельную папку: `git worktree add ..\birge-demo origin/claude/sharp-dijkstra-0t87gl`).

## 3. Запуск: `run-city.bat`

Двойной щелчок или из консоли `run-city.bat`. Что происходит по шагам:

1. `run-city.bat` задаёт `PORT=8611`, `CIVIC_DEMO=1`, `CIVIC_DB_PATH=<папка>\.runtime\round11-local.sqlite3` и вызывает `run.bat`.
2. `run.bat`:
   - переключает консоль на UTF-8 (`chcp 65001`, `PYTHONUTF8=1`);
   - **[1/4]** создаёт `.venv`, если его нет (ищет Python: переменная `PYTHON` → `py -3.13/3.12/3.11/3.14` → `python` из PATH);
   - **[2/4]** ставит зависимости из `requirements.txt` и `requirements-ui.txt` — только если эти файлы изменились с прошлого раза;
   - **[3/4]** создаёт `.env` из `.env.example`, если его нет (ключ туда вписывать не нужно);
   - при `CIVIC_DEMO=1` загружает **синтетический** демо-срез: `python -m ui.civic_store init` и `seed-demo --package data\civic\astana\demo_synthetic.json` (повторная загрузка ничего не дублирует);
   - **[4/4]** запускает `app.py --host 127.0.0.1 --port 8611 --open` и открывает браузер.
3. В консоли должно быть:

```
civic-v1: store=ready, feedback=ready, scenarios=ready, assistant=ready
civic-demo: R06 synthetic projects 5 (new 5), object stages 0     (только с шага B3 7227fce)
civic-v2: ready R04, R06, R07, R08, R09, R12, R13
classifier: off
Birge: http://127.0.0.1:8611
```

`classifier: off` относится к классификатору v1 раунда 12 (`--civic-classifier`); подсказку категории в Birge даёт `/classify`
R04 (модель v2, если есть папка с моделью, иначе словарь — §5).

**Демо-проекты и этапы (R06).** В сборке B2 их нужно загрузить один раз вручную (окно приложения можно не закрывать),
затем обновить страницу (F5):

```bat
set PYTHONUTF8=1
.venv\Scripts\python -B -m ui.civic_store --db .runtime\round11-local.sqlite3 seed-r14-demo
```

Без `PYTHONUTF8=1` в консоли с кодировкой CP1251 команда падает на печати казахского текста (`UnicodeEncodeError`) уже
после записи в базу; повтор с `PYTHONUTF8=1` ничего не дублирует. С шага B3 (7227fce) сервер с `CIVIC_DEMO=1` делает это
сам при старте — ручной шаг не нужен.

Проверка, какие модули раунда 14 подключены: откройте `http://127.0.0.1:8611/api/civic/v2/modules` — у каждого маршрута `status: ready` или `module_not_ready`.

### Другие варианты запуска

| Задача | Команда |
|---|---|
| Другой порт (у `run-city.bat` порт 8611 зашит, `set PORT` его не меняет) | `set PORT=8612& set CIVIC_DEMO=1& set CIVIC_DB_PATH=%CD%\.runtime\round11-local.sqlite3& run.bat` |
| Без автоматического браузера | `set NO_BROWSER=1` перед запуском |
| Чистая база без демо-данных | `run.bat` (порт 8501, база `.runtime\civic.sqlite3`) |
| Выбрать интерпретатор | `set PYTHON=py -3.12` перед запуском |
| Напрямую, без bat (уже есть `.venv`) | `.venv\Scripts\python -B app.py --port 8611 --civic-db .runtime\round11-local.sqlite3 --open` |
| Linux / macOS | `CIVIC_DEMO=1 PORT=8611 CIVIC_DB_PATH=.runtime/round11-local.sqlite3 bash run.sh` |
| Docker (весь сервер без демо-данных, порт 8501; в раунде 14 не проверялся — NOT_RUN) | `docker build -t birge . && docker run -p 8501:8501 birge` |

## 4. Вход сотрудника акимата

Нужен для «Взять в работу», смены статуса жалобы, этапов объектов, создания предложений. Один раз:

```bat
.venv\Scripts\python -m ui.civic_store --db .runtime\round11-local.sqlite3 create-editor operator
```

Пароль вводится скрыто (простые пароли не принимаются — R15 S15). В интерфейсе: «Для сотрудников» → логин и пароль. Сессия — cookie (HttpOnly, SameSite=Strict), для изменяющих запросов нужен заголовок `X-CSRF-Token` (интерфейс ставит его сам). Сессия гаснет через 60 минут без действий (R10 B-050) — на показе входить прямо перед шагом 5.

## 5. Что где лежит

| Что | Где | В Git? |
|---|---|---|
| Рабочая база (жалобы, объекты, этапы, предложения, голоса, сотрудники) | `.runtime\round11-local.sqlite3` (через `run-city.bat`) или `.runtime\civic.sqlite3` | нет |
| Виртуальное окружение приложения | `.venv\` | нет |
| Настройки советника хакатона | `.env` (создаётся из `.env.example`) | нет — не коммитить, не показывать |
| Объекты OSM (сырые) | `data\civic\astana\osm-objects\raw\*.json.gz` | да |
| Объекты, дворы, улицы для привязки | `data\civic\astana\geo\*.json` (ветка R12) | да |
| Граф улиц | `engine\civic_scenarios\graphs\osm-astana-walking-20260506.graph.json` | да |
| Категории | `research\round-14\categories_v2.json` | да |
| Переводы | `web\civic\i18n\ru.json`, `kk.json` | да |
| Модель классификатора v2 (ONNX int8, 266 МБ) | `ml\civic_classifier_v2\artifacts\onnx\` или путь в `BIRGE_CLF_V2_DIR` (на ноутбуке в приёмке B2 — `...\birge-r03\ml\civic_classifier_v2\artifacts\onnx_per_channel`) | **нет** (> 50 МБ) |
| Модель E5 для дублей (ONNX) | `ml\civic_dedup\artifacts\e5\` | **нет** |
| Кэш HuggingFace (xlm-roberta-base, multilingual-e5-base) | `%USERPROFILE%\.cache\huggingface\hub` | нет |
| Сырые ответы Google-формы, разметка людей | `private\` | **нет** (в `.gitignore`) |
| Окружение для обучения | `C:\Users\LEGION\venvs\birge-ml` | нет |

Без файлов моделей приложение работает: `/classify` честно опускается по цепочке «словарь + логрегрессия v1 → словарь → `other`» и всегда ставит `needs_review: true`; поиск дублей работает на n-граммах.

**Включить модель v2 в приложении** (ноутбук, где есть папка с моделью):

```bat
.venv\Scripts\python -m pip install -r ml\civic_classifier_v2\requirements-runtime.txt   & rem onnxruntime, tokenizers, numpy
set BIRGE_CLF_V2_DIR=C:\путь\к\artifacts\onnx_per_channel
set BIRGE_CLF_V2_THREADS=4
run-city.bat
```

Проверка: `POST /api/civic/v2/classify` с текстом отвечает `"source": "v2"` и `model_version`
`civic-clf-v2-xlm-roberta-base-synth_all-daaa6dae4-s20261011`. `needs_review` остаётся `true` — модель не проверена на
текстах людей (это правильно). На приёмке B2 смешанный текст «Аялдамада жарық жоқ, вечером на остановке темно» →
`lighting`, score 0.994.

## 6. Модели: обучение и обновление (ноутбук владельца)

Подробно по шагам — `research/round-14-results/R03/RUN.txt` (PowerShell, шаги 0–9). Кратко:

```powershell
$PY = "C:\Users\LEGION\venvs\birge-ml\Scripts\python.exe"
$env:HF_HUB_OFFLINE = "1"; $env:TRANSFORMERS_OFFLINE = "1"; $env:PYTHONUTF8 = "1"
# проверка GPU
& $PY -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# тесты конвейера (ожидается 66 passed на коде d472baf)
& $PY -m pytest tests\civic\R03\round14 -q -p no:cacheprovider
# главный эксперимент (LOCAL-4 10.10: ≈ 27 мин все этапы, пик GPU 5.2 ГБ), затем итоговая модель и ONNX
& $PY -m ml.civic_classifier_v2.experiments --synth-v3 "<папка R02>\ml\datasets\synth_v3" --v1-in-v2 "<папка R02>\ml\datasets\v1_in_v2" --human "<файл разметки>"
& $PY -m ml.civic_classifier_v2.train --synth-v3 "<папка R02>\ml\datasets\synth_v3" --human "<файл разметки>"
& $PY -m ml.civic_classifier_v2.export_onnx --texts "<папка R02>\ml\datasets\synth_v3\data\corpus_v3.jsonl" --n 200
```

- Модель: `FacebookAI/xlm-roberta-base` (старое имя `xlm-roberta-base` даёт 404). Пиковая память GPU на RTX 4060 — 5.23 ГБ (измерено в LOCAL-4). При нехватке памяти: `--set batch_size=8 --set grad_accum=4`, затем `--set freeze_embeddings=true`.
- Точные команды с путями к корпусам R02 и probe_v2 (`$PROBE`) — только из `RUN.txt` R03: там же шаг 8 (повторный ONNX-экспорт с умолчаниями d472baf — per-channel, 4 потока) и шаг 8б (качество int8 на probe_v2), которые на 11.10 ещё не выполнены.
- В Git коммитятся только `ml/civic_classifier_v2/results/*.json` и `RESULTS.md`; папки `artifacts\`, `private\`, файлы `*.onnx`, `*.safetensors` — никогда.
- Готовую папку `artifacts\onnx` положить в рабочую копию сборки (или указать `BIRGE_CLF_V2_DIR`) — после перезапуска `/classify` начнёт использовать v2.
- LLM-синтетика и LLM-разметчик (R02): ключ только в окне PowerShell — `$env:OPENAI_API_KEY="..."` или `$env:NVIDIA_API_KEY="..."`; всегда задавайте `--max-usd`; после работы `Remove-Item Env:OPENAI_API_KEY`. Команды — `research/round-14-results/R02/RUN.txt`.

## 7. Тесты (разработчику)

```bat
.venv\Scripts\python -m pytest -q tests                      & rem весь набор (на B2 f54361d: 2377 passed, 20 skipped, 1 xfailed; ~4 мин)
.venv\Scripts\python -m pytest -q tests\civic\R01            & rem шлюзы v1/v2
.venv\Scripts\python check.py                                & rem эталоны хакатонного движка (код 1 при расхождении)
.venv\Scripts\python -m engine.civic_geo report              & rem точность карты (954/954 на d13f49a)
```

- Команды тестов каждого модуля — `MODULES.md`, раздел модуля.
- Браузерные проверки — Node 20+ и Playwright: `set NODE_PATH=<путь к глобальным node_modules>` и `node tests\civic\<роль>\…\*.cjs <папка скриншотов>`. В облаке Chromium запускается без GPU (SwiftShader), поэтому плавность 3D там не измеряется.
- `bash tests\civic\R01\run_checks.sh <папка>` — всё сразу (нужен bash: Git Bash или WSL); на Windows без bash те же команды по одной.

## 8. Частые ошибки

| Симптом | Причина | Что сделать |
|---|---|---|
| «Не найден Python 3.11-3.14» | Python не установлен или не в PATH | Установить с python.org с галочкой «Add python.exe to PATH» или `set PYTHON=py -3.12` |
| «Не удалось установить зависимости» | нет интернета при первом запуске / прокси | подключить интернет и запустить снова; повторный запуск ставит только недостающее |
| «Порт занят» | открыто другое окно приложения | закрыть его или запустить на другом порту (§3, «Другие варианты») — `set PORT` перед `run-city.bat` не помогает: файл сам ставит `PORT=8611` (в `RUN.txt` R01 сказано иначе — там ошибка) |
| Белая страница / нет шапки Birge | старый кэш браузера | `Ctrl+F5`; проверить, что в консоли сервера нет ошибок |
| `civic-v1: store=unavailable` | не установлены зависимости `.venv` | `.venv\Scripts\python -m pip install -r requirements.txt -r requirements-ui.txt` |
| `civic-v2: ready none yet` или маршрут отвечает 503 `module_not_ready` | модуль роли ещё не подключён в этой сборке | норма для промежуточной сборки; смотреть `/api/civic/v2/modules` и STATUS R01 |
| Файл модуля (например `/civic/akim/akim.js`) отвечает 404 | файл не добавлен в белый список `CIVIC_ASSETS` в `ui/web_server.py` | задача интегратора (R01): добавить путь в `CIVIC_ASSETS` и `<script>` в `web/index.html` |
| Карта серая, «нет подложки» | нет доступа к `tiles.openfreemap.org` | подключить интернет; функции работают и без подложки |
| 3D-превью не появляется | браузер без WebGL2 или ошибка загрузки three.js | Chrome/Edge последней версии, аппаратное ускорение включено; проверить `/vendor/three/three.module.min.js` |
| Казахский текст показан по-русски, в консоли браузера `[i18n]` | ключа нет в `kk.json` | добавить ключ в оба словаря (`web/civic/i18n/ru.json`, `kk.json`), проверить `python tests\civic\R11\i18n_tools.py check` |
| Нужно начать демо с чистого листа | в базе накопились тестовые жалобы | закрыть приложение, удалить `.runtime\round11-local.sqlite3*`, снова `run-city.bat` |
| После обновления сборки старая база не открывается | миграция 6 (R06) необратима для кода раунда 13 | перед переключением на старую сборку сделать копию `.runtime\*.sqlite3` |
| `CUDA out of memory` при обучении | 8 ГБ GPU мало для batch 16 | `--set batch_size=8 --set grad_accum=4`, затем `--set freeze_embeddings=true` |
| `UnicodeEncodeError` (кодировка cp1251) при `seed-r14-demo` или другой команде | консоль Windows не в UTF-8 | `set PYTHONUTF8=1` (или `chcp 65001`) и повторить — данные не дублируются |
| `/classify` отвечает `"source": "kw"`, хотя модель есть | не задан `BIRGE_CLF_V2_DIR` или в `.venv` нет `onnxruntime`/`tokenizers` | §5 «Включить модель v2»; перезапустить сервер |
| Классификация медленная (≈ 100 мс на текст) | onnxruntime занял все потоки гибридного процессора | `set BIRGE_CLF_V2_THREADS=4` (с кода R03 d472baf это умолчание) |
| Тесты R03 падают с `ImportError` из `conftest`, когда запускаю несколько папок одной командой | тесты R03 импортируют свой `conftest` по имени | запускать `pytest tests` целиком или `pytest tests\civic\R03\round14` отдельно |
| В консоли браузера `Image "…" could not be loaded` / `Expected value to be of type number, but found null` | в стиле OpenFreeMap нет части значков POI | карта работает; это предупреждения стиля (LOCAL_B2, проблема 10) |
| Каталог «Что построить?» не виден на телефоне (B2) | шторка панели открыта | выбрать район в «Территория» — шторка опустится и каталог появится; на демо шаг 5 показывать на ноутбуке (в FINAL-кандидате 2b9e837 кнопка каталога видна над шторкой) |
| Действие отвечает 429 / «Слишком много запросов» | сработал лимит частоты (с FINAL-кандидата 2b9e837) | перезапустить сервер (`Ctrl+C`, снова `run-city.bat`); лимиты в памяти процесса |
| В ҚАЗ у объектов вместо названия слово «Нысан» | дефект B-029 (B3…daec72a; R07) | исправлен с FINAL-кандидата ef1ef44 — переключиться на него или новее; на старой сборке показывать тепловую карту и «Картину дня» на РУС |
| На шаге 2 нет похожих обращений и кнопки «Я тоже» | на чистой базе нет жалоб у остановки (B-030) или демо-жалобы у «Хан Шатыра» отмечены «исправленными» на репетиции | с 0a7a346 сервер при `CIVIC_DEMO=1` сам кладёт три жалобы «Пример»; на старой сборке или после репетиции — подать одну жалобу «Вечером на остановке нет света, темно» на ту же остановку из окна инкогнито |
| Лист QR-табличек (`/civic/qr/print.html`) без QR-кодов, кнопки «Печать» нет | в сборке нет генератора `web/vendor/qrcode/qrcode.js` (задача LOCAL-11) | скачать qrcode-generator 1.4.4 (MIT) в `web/vendor/qrcode/` по LOCAL-11; до этого страница честно показывает ссылку крупным шрифтом |
| Сотрудник отметил исправление с фото «после» в «Обращения», но жители ничего не получили | R10 B-056 (FINAL-2): CSP запрещает `fetch(blob:)`, отправка молча не проходит | отмечать без фото (работает) или через карточку на карте; исправление — у R09 |
| В «Мои обращения» нет блока «Ждут вашей проверки» | проверку ремонта видят только автор и нажавшие «Я тоже» из этого браузера; на этой базе сцена уже прошла | restore чистой базы (§9) или окно, где нажимали «Я тоже» |
| Цель на карте зелёная, хотя жители ещё не проверили (FINAL-2) | R10 B-055: карта R07 в FINAL-2 знает одно состояние «исправлено» | ждёт R07 9e337dc в FINAL-3; на показе сцену проверки вести по экрану жителя |
| `404` при загрузке `xlm-roberta-base` | устаревшее имя модели | использовать `FacebookAI/xlm-roberta-base`, `HF_HUB_OFFLINE=1` (модель уже в кэше) |

## 9. Перед демо (чек-лист)

Полный порядок с репликами — `docs/gton/SPEECH.md` (R14) и `research/round-14-results/R01/DEMO_SCRIPT.md` (R01).

1. **Сборка.** Показывать ту, приёмку которой закончил R10: принятый FINAL-кандидат 8e67c65 (6 шагов) или FINAL-2/FINAL-3
   (7 шагов, со сценой «Служба сообщила об устранении» → «Да, исправлено» → «Проверено жителями»; на 0f5101a R10 принял
   предварительно шаг 3 — 170 / 0 / 0).
2. **В день показа, до первой репетиции** (R10 B-048, B-049): остановить сервер, убрать старую базу
   (`ren .runtime\round11-local.sqlite3 round11-local-old.sqlite3`, и `-wal`/`-shm`), `run-city.bat` (демо засеется с
   текущим временем), `create-editor operator` (§4), сразу `backup`:
   `.venv\Scripts\python -m ui.civic_store --db .runtime\round11-local.sqlite3 backup .runtime\demo-clean.sqlite3`.
   Зачем: после репетиции «Хан Шатыр» уже «исправлен» — нет «Я тоже», красной остановки и проверки жителем; демо-жалобы
   «стареют» через ≈ 13 дней после первого запуска.
3. **За 5 минут:** `Ctrl+C`, `restore --yes .runtime\demo-clean.sqlite3`, снова `run-city.bat` — заодно обнулятся лимиты
   частоты (R15: жалобы 5 в минуту и 30 в час, «Я тоже» и проверка ремонта 20 в сутки на жалобу, голос 20 в сутки на проект;
   на ноутбуке все запросы — с одного адреса, а при показе зрителям по общей сети Wi-Fi все зрители — тоже «один адрес»).
4. `http://127.0.0.1:8611/api/civic/v2/modules` — все модули `ready` (FINAL-2: 55 маршрутов); в консоли строка
   `civic-v2: ready R04, R06, R07, R08, R09, R12, R13`.
5. **Сотрудником входить прямо перед шагом 5**, не заранее: сессия гаснет через 60 минут (B-050); на 8e67c65 заранее
   выполненный вход ещё и пропускает «Я тоже» в пути жителя (Codex, LOCAL_FINAL P1; R01 считает это исправленным в FINAL-2
   у R09 8a1d390 — R10 и Codex не проверяли). Вид «Житель» — в новом окне инкогнито.
6. Экран 1366×768 или больше; **проектор 1024×768 — масштаб браузера 80 %** (B-043/B-044); весь показ — на ноутбуке
   (FINAL-2: на 375 px карточка остановки открывается со второго нажатия, B-054).
7. Карта без интернета: архив `data\civic\astana\tiles\astana.pmtiles` (офлайн-режим Codex, `RUN.txt` R01 шаг 3б) —
   `http://127.0.0.1:8611/civic/offline/status.json` → `available: true`; без архива и без сети — оси улиц OSM.
8. Модель v2: `BIRGE_CLF_V2_DIR` (§5, «Включить модель v2») — `/classify` отвечает `source: v2`; без неё — словарь (`source: kw`), шаг 2 работает.
9. Шаги 6–7 на FINAL-2: только карточка «Хан Шатыра» (у остальных целей — примеры R07); сцену вести по экрану жителя,
   на карту не переключаться (B-055); «Проблема осталась» не нажимать (сцена — один раз на базе); фото «после» не прикладывать
   (B-056).
10. Демо-записи помечены «Пример» — это синтетика, так и говорим на защите.
