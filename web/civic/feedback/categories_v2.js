/* СГЕНЕРИРОВАНО: python -m ui.civic_feedback.v2.web_assets — не править руками.
 * Источник: research/round-14/categories_v2.json (+ сроки ответа R09). */
window.BirgeCategoriesV2 = {
 "version": "civic-categories-v2",
 "categories": [
  {
   "id": "roads",
   "ru": "Дороги",
   "kk": "Жолдар",
   "icon": "road",
   "examples_ru": "яма, разбитый асфальт, стёртая разметка",
   "target_kinds": [
    "segment"
   ],
   "response_days": 10
  },
  {
   "id": "snow_ice",
   "ru": "Снег и гололёд",
   "kk": "Қар және көктайғақ",
   "icon": "snowflake",
   "examples_ru": "не убран снег, наледь, сосульки",
   "target_kinds": [
    "segment",
    "area"
   ],
   "response_days": 1
  },
  {
   "id": "sidewalks",
   "ru": "Тротуары",
   "kk": "Жаяу жүргіншілер жолы",
   "icon": "walk",
   "examples_ru": "разбит тротуар, нет пандуса, бордюр",
   "target_kinds": [
    "segment"
   ],
   "response_days": 10
  },
  {
   "id": "transport",
   "ru": "Остановки и транспорт",
   "kk": "Аялдамалар мен көлік",
   "icon": "bus",
   "examples_ru": "сломан павильон, нет расписания, автобус не ходит",
   "target_kinds": [
    "object"
   ],
   "response_days": 5
  },
  {
   "id": "lighting",
   "ru": "Освещение",
   "kk": "Жарықтандыру",
   "icon": "bulb",
   "examples_ru": "не горят фонари, темно во дворе",
   "target_kinds": [
    "segment",
    "area"
   ],
   "response_days": 3
  },
  {
   "id": "yards",
   "ru": "Дворы и площадки",
   "kk": "Аулалар мен алаңдар",
   "icon": "trees",
   "examples_ru": "сломана площадка, деревья, благоустройство двора",
   "target_kinds": [
    "object",
    "area"
   ],
   "response_days": 10
  },
  {
   "id": "waste",
   "ru": "Мусор",
   "kk": "Қоқыс",
   "icon": "trash",
   "examples_ru": "переполнены баки, свалка, не вывозят",
   "target_kinds": [
    "area",
    "object"
   ],
   "response_days": 3
  },
  {
   "id": "utilities",
   "ru": "ЖКХ: тепло и вода",
   "kk": "ТКШ: жылу мен су",
   "icon": "droplet",
   "examples_ru": "нет отопления, нет воды, канализация",
   "target_kinds": [
    "area"
   ],
   "response_days": 1
  },
  {
   "id": "smell_air",
   "ru": "Запахи и воздух",
   "kk": "Иіс және ауа",
   "icon": "wind",
   "examples_ru": "вонь, дым, пыль, выбросы",
   "target_kinds": [
    "area"
   ],
   "response_days": 3
  },
  {
   "id": "noise_safety",
   "ru": "Шум и безопасность",
   "kk": "Шу және қауіпсіздік",
   "icon": "shield",
   "examples_ru": "шум ночью, опасное место, нет перехода",
   "target_kinds": [
    "area",
    "segment"
   ],
   "response_days": 3
  },
  {
   "id": "parking",
   "ru": "Парковки",
   "kk": "Тұрақтар",
   "icon": "parking",
   "examples_ru": "заставлены дворы, нет мест, парковка на газоне",
   "target_kinds": [
    "segment",
    "area"
   ],
   "response_days": 7
  },
  {
   "id": "other",
   "ru": "Другое",
   "kk": "Басқа",
   "icon": "dots",
   "examples_ru": "всё, что не подошло",
   "target_kinds": [
    "area"
   ],
   "response_days": 10
  }
 ],
 "heat_levels": [
  {
   "min_weight": 0,
   "level": 0,
   "ru": "нет жалоб",
   "kk": "шағым жоқ",
   "color": null
  },
  {
   "min_weight": 1,
   "level": 1,
   "ru": "1–2",
   "kk": "1–2",
   "color": "#FAC775"
  },
  {
   "min_weight": 3,
   "level": 2,
   "ru": "3–5",
   "kk": "3–5",
   "color": "#EF9F27"
  },
  {
   "min_weight": 6,
   "level": 3,
   "ru": "6–9",
   "kk": "6–9",
   "color": "#E24B4A"
  },
  {
   "min_weight": 10,
   "level": 4,
   "ru": "10+",
   "kk": "10+",
   "color": "#A32D2D"
  }
 ],
 "fixed_state": {
  "color": "#639922",
  "ru": "исправлено",
  "kk": "түзетілді",
  "days_visible": 7
 },
 "weight_half_life_days": 14
};
