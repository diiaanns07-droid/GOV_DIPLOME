# A06 — изолированные эксперименты (SYNTHETIC, не данные Шымкента)
Выполнено: 2026-10-04 (UTC), контейнер Ubuntu 24, Python 3.12.3, Eclipse SUMO 1.24.0 (PyPI `eclipse-sumo==1.24.0`, лицензия EPL-2.0), sumolib из $SUMO_HOME/tools.
Все сети, спрос и параметры придуманы для проверки метода. Числа НЕ являются оценкой эффекта для какого-либо реального перекрёстка или района.

## Команды
```
pip install --break-system-packages eclipse-sumo==1.24.0
export SUMO_HOME=$(python3 -c "import sumo;print(sumo.SUMO_HOME)")
export PYTHONPATH=$SUMO_HOME/tools
python3 e1_flyover.py   # -> e1/results.json
python3 e2_closure.py   # -> e2/results.json
python3 e3_access.py    # -> e3/results.json (без SUMO, чистый Python)
```
## Что проверяется
- E1: пересечение в одном уровне (A, светофор static), эстакада без съездов (B), эстакада + кольцо внизу со съездами (C). 2 структуры спроса x 3 уровня, горизонт 4500 с, спрос 0–3600 с, seed 42, time-to-teleport 300.
- E2: решётка 6x6 (250 м), «река» с двумя мостами, закрытие одного моста (closingReroute), сравнение статического графового объезда и динамики при 1200 и 3000 авт/ч.
- E3: прототип метрики доступности: сетевой охват 400 м против евклидова буфера при барьере-магистрали, разложение времени walk/wait/ride/transfer, диапазон optimistic/pessimistic, два локальных изменения (остановка, переход).
Модель ожидания в E3: E[wait] = E[H]/2*(1+CV^2) — классическая формула, первоисточник в этой сессии не открывался.
