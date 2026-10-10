# Birge · запуск на Windows с нуля (RUNBOOK)

> Документ R14 (раунд 14), 10 октября 2026. Основан на `run.bat`, `run-city.bat`, `ui/web_server.py`,
> `research/round-14-results/R01/RUN.txt` и `research/round-14-results/R03/RUN.txt`.
> Проверено R14 в облаке (Linux, Python 3.13.16) на сборке R01 `claude/sharp-dijkstra-0t87gl` @ bc7c961:
> сервер стартует, `civic-v1` — все 4 модуля `ready`, `civic-v2` — `ready R08`, `GET /api/civic/v2/akim/summary` отвечает
> (демо-данные, 21.8 мс). Сам `run-city.bat` на Windows этой сессией **не запускался** (NOT_RUN — облако без Windows).

## 0. Коротко (если всё уже стоит)

```bat
cd C:\Users\LEGION\Desktop\hackalem\hack-d3b2c613-stupits
git fetch origin
git switch --detach origin/claude/sharp-dijkstra-0t87gl   & rem или SHA сборки B1/B2/FINAL из STATUS.md R01
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
civic-v2: ready R08            (по мере сборки здесь появятся R04, R06, R07, R09, R12)
classifier: off
Birge: http://127.0.0.1:8611
```

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

Пароль вводится скрыто. В интерфейсе: «Для сотрудников» → логин и пароль. Сессия — cookie, для изменяющих запросов нужен заголовок `X-CSRF-Token` (интерфейс ставит его сам).

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
| Модель классификатора v2 (ONNX) | `ml\civic_classifier_v2\artifacts\onnx\` (или путь в `BIRGE_CLF_V2_DIR`) | **нет** (> 50 МБ) |
| Модель E5 для дублей (ONNX) | `ml\civic_dedup\artifacts\e5\` | **нет** |
| Кэш HuggingFace (xlm-roberta-base, multilingual-e5-base) | `%USERPROFILE%\.cache\huggingface\hub` | нет |
| Сырые ответы Google-формы, разметка людей | `private\` | **нет** (в `.gitignore`) |
| Окружение для обучения | `C:\Users\LEGION\venvs\birge-ml` | нет |

Без файлов моделей приложение работает: `/classify` честно опускается по цепочке «словарь + логрегрессия v1 → словарь → `other`» и всегда ставит `needs_review: true`; поиск дублей работает на n-граммах.

## 6. Модели: обучение и обновление (ноутбук владельца)

Подробно по шагам — `research/round-14-results/R03/RUN.txt` (PowerShell, шаги 0–9). Кратко:

```powershell
$PY = "C:\Users\LEGION\venvs\birge-ml\Scripts\python.exe"
$env:HF_HUB_OFFLINE = "1"; $env:TRANSFORMERS_OFFLINE = "1"; $env:PYTHONUTF8 = "1"
# проверка GPU
& $PY -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# тесты конвейера (ожидается 65 passed)
& $PY -m pytest tests\civic\R03\round14 -q -p no:cacheprovider
# главный эксперимент (~1–1.5 ч), затем итоговая модель и ONNX
& $PY -m ml.civic_classifier_v2.experiments --synth-v3 "<папка R02>\ml\datasets\synth_v3" --v1-in-v2 "<папка R02>\ml\datasets\v1_in_v2" --human "<файл разметки>"
& $PY -m ml.civic_classifier_v2.train --synth-v3 "<папка R02>\ml\datasets\synth_v3" --human "<файл разметки>"
& $PY -m ml.civic_classifier_v2.export_onnx --texts "<папка R02>\ml\datasets\synth_v3\data\corpus_v3.jsonl" --n 200
```

- Модель: `FacebookAI/xlm-roberta-base` (старое имя `xlm-roberta-base` даёт 404). Пиковая память GPU 4–6 ГБ (оценка). При нехватке памяти: `--set batch_size=8 --set grad_accum=4`, затем `--set freeze_embeddings=true`.
- В Git коммитятся только `ml/civic_classifier_v2/results/*.json` и `RESULTS.md`; папки `artifacts\`, `private\`, файлы `*.onnx`, `*.safetensors` — никогда.
- Готовую папку `artifacts\onnx` положить в рабочую копию сборки (или указать `BIRGE_CLF_V2_DIR`) — после перезапуска `/classify` начнёт использовать v2.
- LLM-синтетика и LLM-разметчик (R02): ключ только в окне PowerShell — `$env:OPENAI_API_KEY="..."` или `$env:NVIDIA_API_KEY="..."`; всегда задавайте `--max-usd`; после работы `Remove-Item Env:OPENAI_API_KEY`. Команды — `research/round-14-results/R02/RUN.txt`.

## 7. Тесты (разработчику)

```bat
.venv\Scripts\python -m pytest -q tests                      & rem весь набор (на 2eaeacb: 1458 passed, 11 skipped)
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
| «Порт занят» | открыто другое окно приложения | закрыть его или запустить на другом порту (§3, «Другие варианты») — `set PORT` перед `run-city.bat` не помогает |
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
| `404` при загрузке `xlm-roberta-base` | устаревшее имя модели | использовать `FacebookAI/xlm-roberta-base`, `HF_HUB_OFFLINE=1` (модель уже в кэше) |

## 9. Перед демо (чек-лист)

1. Переключиться на SHA сборки FINAL, `run-city.bat`, в консоли нет ошибок.
2. `http://127.0.0.1:8611/api/civic/v2/modules` — нужные модули `ready`.
3. Пройти сценарий `research/round-14-results/R01/DEMO_SCRIPT.md` (или CONTRACT §0, шаги 1–6) в ҚАЗ и РУС, на 1366×768.
4. Проверить подложку карты (интернет) и 3D-превью на этом ноутбуке (GPU).
5. Создан вход сотрудника (§4).
6. Демо-записи помечены «Пример» — это синтетика, так и говорим на защите.
