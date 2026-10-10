# Раунд 14 — задачи на ноутбуке владельца (Codex / ChatGPT / сам владелец)

Облачные сессии Claude не могут скачивать из интернета. Эти задачи выполняются локально: в папке проекта `C:\Users\LEGION\Desktop\hackalem\hack-d3b2c613-stupits`. Ключи API задаются только переменными окружения в окне терминала — никогда в файлах репозитория.

---

## Сегодня вечером (10 октября): одно задание для Codex desktop — LOCAL-1 + LOCAL-2 + LOCAL-3

Скопируйте в Codex целиком:

```
Работаешь в репозитории C:\Users\LEGION\Desktop\hackalem\hack-d3b2c613-stupits (GOV_DIPLOME).
Выполни: git fetch origin; git switch claude/round-14-package. Прочитай research/round-14/COMMON.txt и CONTRACT.md.
Не читай .env. Не меняй файлы, кроме перечисленных ниже. Коммить только эти пути, затем push в origin claude/round-14-package.

LOCAL-1. Объекты OSM Астаны.
- Возьми bbox Астаны из engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json (поле bbox).
- Через Overpass API (https://overpass-api.de/api/interpreter, вежливо: один запрос за раз, timeout 180) скачай с `out geom;`:
  остановки (highway=bus_stop, public_transport=platform), детские площадки (leisure=playground),
  спортплощадки (leisure=pitch), парки и скверы (leisure=park, leisure=garden), жилые кварталы (landuse=residential),
  места для мусора (amenity=waste_disposal, amenity=recycling), фонари (highway=street_lamp),
  школы и детсады (amenity=school, amenity=kindergarten).
- Сохрани каждый набор в data/civic/astana/osm-objects/raw/<набор>.json.gz и data/civic/astana/osm-objects/SOURCE.json
  (тексты запросов, время скачивания, osm_base из ответа, лицензия ODbL, атрибуция «© OpenStreetMap contributors»).
- В README.md папки — таблица: набор, число объектов, размер. Общий размер ≤ 20 МБ.

LOCAL-2. three.js для 3D-превью.
- Скачай three@0.169.0 из npm (npm pack three@0.169.0 или https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.min.js)
  в web/vendor/three/three.module.min.js и LICENSE (MIT) рядом; в web/vendor/three/SOURCE.txt — версия и URL.

LOCAL-3. Окружение для обучения модели (без коммита, кроме отчёта).
- Проверь `py -0p`. Если нет Python 3.12 — сообщи владельцу и предложи установить (не ставь без подтверждения).
- Создай venv C:\Users\LEGION\venvs\birge-ml на Python 3.12; поставь torch с CUDA (официальный индекс PyTorch для CUDA 12.x),
  transformers, datasets, accelerate, scikit-learn, onnx, onnxruntime, pandas.
- Проверь: torch.cuda.is_available() == True и имя GPU (ожидается RTX 4060 Laptop, 8 ГБ).
- Скачай в кэш HuggingFace: xlm-roberta-base и intfloat/multilingual-e5-base.
- Запиши research/round-14-results/LOCAL/ENV.md: версии Python, torch, CUDA, transformers, GPU, где лежит venv и кэш. Без токенов.

В конце: коммиты (только перечисленные пути), push, короткий отчёт: что скачано, размеры, SHA, ошибки.
```

---

## Сегодня вечером: владелец — Google-форма (LOCAL-6)

Создайте форму и разошлите одногруппникам, родным, знакомым (просите написать 3–5 разных жалоб, форма принимает много ответов):

- **Название:** «Помогите сделать город удобнее · Қаланы ыңғайлы етуге көмектесіңіз»
- **Описание:** «Мы студенты, делаем приложение, которое помогает акимату быстрее решать проблемы жителей. Напишите жалобу так, как написали бы в 109 или в чат района: про дороги, снег, дворы, остановки, мусор, свет, запахи — что угодно. Не пишите имена, телефоны и точный адрес. Тексты используются анонимно для исследования и обучения ИИ.»
- Вопросы:
  1. «Текст жалобы / Шағым мәтіні» — абзац, обязательный.
  2. «Язык / Тіл» — қазақша · русский · аралас.
  3. «Район Астаны / Аудан» — Алматы, Байконур, Есиль, Нура, Сарайшык, Сарыарка, другой город (необязательный).
  4. Флажок, обязательный: «Согласен(на): текст будет использован анонимно для исследования и обучения ИИ».
- Ответы → «Скачать CSV» → положите в `private/` в папке проекта (эта папка не попадает в Git). Импорт и обезличивание — скрипт R02 `ml/labeling/import_form.py`.

Цель: 200–400 текстов к вечеру 13 октября.

---

## 11–13 октября: ChatGPT с поиском в интернете — реальные работы в районе Нура (LOCAL-5)

```
Найди 15–30 реальных строительных и ремонтных работ, перекрытий и благоустройства в районе Нура города Астаны
за 2025–2026 годы. Источники — только официальные (astana.gov.kz, gov.kz, akimat), крупные СМИ с датой публикации.
Для каждой: название, тип (стройка / ремонт дороги / благоустройство / перекрытие), адрес или улицы (с какой по какую),
сроки (начало, плановое окончание, перенос, если есть), статус, ссылка, дата публикации, короткая цитата-подтверждение.
Не придумывай: если чего-то нет в источнике — оставь пустым. Выдай таблицу CSV.
```

Сохраните CSV в `data/civic/astana/nura-real/records.csv` и запушьте в `claude/round-14-package` (или передайте R12 — он привяжет к улицам).

---

## 12 октября: Codex desktop — обучение модели на GPU (LOCAL-4)

Когда R03 запушит код (его STATUS.md): «Выполни команды из research/round-14-results/R03/RUN.txt в venv C:\Users\LEGION\venvs\birge-ml. Большие файлы оставь в ml/civic_classifier_v2/artifacts/ (не коммить). Закоммить и запушь только results/*.json и RESULTS.md в ветку R03 (её имя — в его STATUS.md) или пришли их мне текстом».

## 12–14 октября: LLM-синтетика и LLM-разметчик (LOCAL-8)

Скрипты R02 `ml/datasets/llm_synth.py` и `ml/labeling/llm_label.py`. Ключ — только в окне терминала:
`$env:OPENAI_API_KEY="..."` (OpenAI, $40 до 23.10) или `$env:NVIDIA_API_KEY="..."` (NVIDIA, $50 до 23.10, base_url https://integrate.api.nvidia.com/v1). Перед запуском проверьте `--max-usd`.

## 13–15 октября: Codex desktop — запуск сборки и скриншоты (LOCAL-7)

«Переключись на SHA сборки R01 (из его STATUS.md) в отдельном worktree, запусти run-city.bat, пройди research/round-14-results/R01/DEMO_SCRIPT.md, сделай скриншоты 1366×768 и 375×812 каждого шага в ҚАЗ и РУС → research/round-14-results/LOCAL/screens/<сборка>/, запушь в claude/round-14-package, перечисли всё, что работает не так».
