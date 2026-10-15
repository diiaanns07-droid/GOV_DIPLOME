# Раунд 15 — задачи на ноутбуке владельца (Codex / ChatGPT / сам владелец)

Облачные сессии Claude не скачивают из интернета и не видят подложку карты. Эти задачи — локально, в папке проекта
`C:\Users\LEGION\Desktop\hackalem\hack-d3b2c613-stupits`. Ключи API — только переменными окружения в окне терминала,
никогда в файлах репозитория. Результаты пушить в ветку, которую назовёт роль-заказчик (или прислать ей текстом).

---

## LOCAL-12 · Сборки на Windows и кадры с настоящей картой (Codex, после каждой сборки R01)

```
Работаешь в репозитории C:\Users\LEGION\Desktop\hackalem\hack-d3b2c613-stupits (GOV_DIPLOME). Не читай .env.
git fetch origin. Возьми SHA сборки R01 (FINAL-4.1 / B1 / B2 / FINAL-5) из его STATUS.md в отдельный worktree.
Положи архив карты astana.pmtiles (как в раунде 14) в data\civic\astana\tiles\. Запусти run-city.bat
(для демо-мира: set CIVIC_DEMO_WORLD=1). Пройди DEMO_SCRIPT.md R01 (шаги 1–9), сними кадры 1366×768, 1024×768 и 375×812
каждого шага в ҚАЗ и РУС → research/round-15-results/LOCAL/screens/<сборка>/. Запиши всё, что работает не так
(шаг, что ожидалось, что увидел). Закоммить только эту папку в ветку R01 раунда 15 (из его STATUS) и push; отчёт — SHA и список проблем.
```

## LOCAL-13 · Ориентиры Астаны из OSM для 3D (Codex, по просьбе R05)

```
Работай в отдельной рабочей папке ветки R05 раунда 15 (имя — из его STATUS). git pull --rebase перед началом и перед push.
Возьми bbox Астаны из engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json (поле bbox).
Через Overpass API (https://overpass-api.de/api/interpreter, вежливо: один запрос, timeout 180) скачай с out geom;
nwr["name"~"Бәйтерек|Байтерек|Хан Шатыр|Ақорда|Акорда|Нұр Әлем|Нур Алем|Бейбітшілік және келісім|Дворец мира и согласия|Хазрет Сұлтан|Хазрет Султан"](bbox);
Сохрани data/civic/astana/landmarks/raw/landmarks.json.gz и SOURCE.json (запрос, время, osm_base, ODbL, «© OpenStreetMap contributors»).
Коммить только эту папку, push. Отчёт: какие объекты найдены (id, название, тип), SHA.
```

## LOCAL-14 · Тексты живых людей для оценки модели (владелец + Codex, для R03 и диплома)

1. Если в раунде 14 собраны ответы Google-формы (LOCAL-6) — CSV в `private/` (папка не попадает в Git).
2. Импорт и обезличивание — `ml/labeling/import_form.py` (R02), разметка 300 текстов — `web/labeling/` (без мыши, ~2 часа).
3. Codex: «Выполни команды оценки из research/round-15-results/R03/RUN.txt на размеченном файле; закоммить только
   results/*.json и RESULTS_HUMAN.md в ветку R03 раунда 15». Тексты людей в Git не попадают.

## LOCAL-15 · Юзабилити-тест с людьми, SUS (владелец, для диплома, по протоколу R14)

Протокол — `docs/diploma/07_aprobatsiya.md` (R14): 5–8 человек разного возраста (житель на телефоне, «акимат» на ноутбуке),
задачи по сценарию v2, анкета SUS на ru или kk, согласие. Ответы — в `private/`, сводка без имён —
`research/round-15-results/LOCAL/SUS.md` (среднее SUS, время задач, главные трудности). Это сильный раздел «апробация» в дипломе.

## LOCAL-16 · Демо-ролик с настоящей картой (Codex, после FINAL-5)

```
Возьми FINAL-5 (SHA из STATUS R01), архив карты, CIVIC_DEMO_WORLD=1, run-city.bat. Запусти
NODE_PATH=<глобальные модули npm> node tests/e2e/demo_video.cjs --url http://127.0.0.1:8611 --lang ru и --lang kk
(R10, параметры — в его RUN.txt). Видео — в research/round-15-results/LOCAL/video/ (если > 50 МБ — не коммить, положи рядом
и напиши путь). Отчёт: длительность, разрешение, замечания по кадрам.
```

## LOCAL-17 · Проверка «Спросить Birge» с языковой моделью (по желанию, R03)

В окне терминала: `$env:OPENAI_API_KEY="..."`, `$env:OPENAI_MODEL="gpt-4.1-mini"` (или NVIDIA: `OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1`).
Прогнать оценку R03 в режиме LLM (команда — его RUN.txt), записать задержку и долю ответов, где модель не понадобилась.
Без ключа всё работает офлайн — это нормально.

## LOCAL-18 · Обновить презентацию Gton на gh-pages (владелец или координатор, после R14)

Ветка `gh-pages` (index.html — колода Birge для Gton 2026). Обновить по `docs/gton/` R14 раунда 15: новые сцены «Бірге»,
кадры LOCAL-12. Публикация — только с подтверждения владельца.
