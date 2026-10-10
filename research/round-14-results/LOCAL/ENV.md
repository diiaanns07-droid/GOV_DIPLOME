# LOCAL-3 — окружение обучения Birge

Проверено (UTC): 2026-10-10T13:14:23.674806+00:00
Статус: **PASS**.

Python 3.12.10 x64 установлен после явного подтверждения владельца в чате. Официальный установщик python.org; Authenticode: Valid, Python Software Foundation; MD5 совпал с опубликованным на странице релиза.
Источник Python: https://www.python.org/downloads/release/python-31210/

- Python: `3.12.10` (64bit).
- Интерпретатор: `C:\Users\LEGION\venvs\birge-ml\Scripts\python.exe`.
- Venv: `C:\Users\LEGION\venvs\birge-ml`.
- Кэш HuggingFace: `C:\Users\LEGION\.cache\huggingface\hub`.
- PyTorch CUDA runtime: `12.6`.
- NVIDIA driver: `591.74`.
- `torch.cuda.is_available()`: `True`.
- GPU: `NVIDIA GeForce RTX 4060 Laptop GPU`.
- Видеопамять: `8585216000` байт (8188 MiB).

## Пакеты

| Пакет | Версия |
|---|---|
| pip | 26.2.1 |
| torch | 2.14.1+cu126 |
| transformers | 5.19.0 |
| datasets | 5.1.0 |
| accelerate | 1.15.0 |
| scikit-learn | 1.9.1 |
| onnx | 1.23.2 |
| onnxruntime | 1.31.0 |
| pandas | 3.0.6 |
| sentencepiece | 0.2.2 |
| huggingface-hub | 2.2.0 |
| safetensors | 0.8.0 |

PyTorch установлен из официального CUDA 12.6 индекса: https://download.pytorch.org/whl/cu126
Команда: `python -m pip install torch --index-url https://download.pytorch.org/whl/cu126`.
Остальные пакеты установлены из PyPI. Дополнительно установлен `sentencepiece` для токенизаторов моделей.

## Модели в локальном кэше

Скачаны веса Safetensors, конфигурации, токенизаторы и доступные файлы описания. Дубли весов PyTorch pickle, TensorFlow, Flax, ONNX/OpenVINO не требуются для обучения и не загружались.

### xlm-roberta-base

- Канонический репозиторий: `FacebookAI/xlm-roberta-base`.
- Источник: https://huggingface.co/FacebookAI/xlm-roberta-base
- Revision: `e73636d4f797dec63c3081bb6ed5c7b0bb3f2089`.
- Snapshot: `C:\Users\LEGION\.cache\huggingface\hub\models--FacebookAI--xlm-roberta-base\snapshots\e73636d4f797dec63c3081bb6ed5c7b0bb3f2089`.
- Файлов: 6; размер: **1129739299 байт**.
- Локальная загрузка без сети и inference на CUDA (русский + казахский): **PASS**.
- Размер выхода: `[2, 15, 768]`; конечные значения: `True`.

### intfloat/multilingual-e5-base

- Канонический репозиторий: `intfloat/multilingual-e5-base`.
- Источник: https://huggingface.co/intfloat/multilingual-e5-base
- Revision: `d128750597153bb5987e10b1c3493a34e5a4502a`.
- Snapshot: `C:\Users\LEGION\.cache\huggingface\hub\models--intfloat--multilingual-e5-base\snapshots\d128750597153bb5987e10b1c3493a34e5a4502a`.
- Файлов: 10; размер: **1134534380 байт**.
- Локальная загрузка без сети и inference на CUDA (русский + казахский): **PASS**.
- Размер выхода: `[2, 15, 768]`; конечные значения: `True`.

## Проверки и повторный запуск

- GPU вычисление тензоров и backward: `PASS`.
- `pip check`: `PASS`.
- Импорт всех запрошенных библиотек: `PASS`.
- Для работы используйте `C:\Users\LEGION\venvs\birge-ml\Scripts\python.exe`.
- Модели проверены с `local_files_only=True` и `trust_remote_code=False`.
- Обучение LOCAL-4 в это задание не входит и не запускалось.
- Venv, установщик, кэш и веса не добавляются в Git. `.env` и файлы токенов не читались; загрузки моделей выполнены с `token=False`.

## Размеры и замечания

- HEAD репозитория при проверке окружения: `d2a4351666302ef97e1699b4c14f10eec677462f` (ветка `claude/round-14-package`). Это проверка окружения и моделей; код обучения R03 не запускался.
- Размер файлов venv после установки и проверок: **5 006 825 144 байта**. Общий размер двух снимков моделей: **2 264 273 679 байт** (16 файлов). Служебные файлы и кэши загрузчиков в размер снимков не входят.
- Старый алиас `xlm-roberta-base` вернул HTTP 404 на endpoint Xet. Загрузка выполнена через канонический ID **`FacebookAI/xlm-roberta-base`**. Для дальнейшей работы по имени используйте этот ID или точный путь snapshot выше.
- Разрешение `model.safetensors` для обеих моделей по каноническим ID с `local_files_only=True` проверено отдельно: **PASS**; `refs/main` присутствуют.
- При проверке энкодеров использовалось `add_pooling_layer=False`: сообщения о неиспользованных `lm_head` / `pooler` ожидаемы для такого способа загрузки. Веса сохранены целиком; оба CUDA forward прошли с конечными значениями.
- Нерешённых ошибок LOCAL-3 нет.
