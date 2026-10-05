"""K09-T1: набор поручений ru/kk (СИНТЕТИКА, написан K09; kk требует проверки носителем).

Эталон каждого примера задан по dataset/ANNOTATION_RULES.md при написании текста,
до реализации B2 и без запуска парсеров. Разбиение dev/held-out — по template_id и
вариантам сущностей (см. правила). Запуск из корня репозитория:
    python3 research/round-3-results/K09/scripts/make_dataset.py
Пишет dataset/t1_dataset.jsonl, dataset/measure_catalog.json, dataset/DATASET_SHA256.txt.
"""
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
D = ROOT / "research/round-3-results/K09/dataset"

# --- Каталог мер: ru — из data/city_data.json (synthetic); kk — перевод K09 (synthetic, проверить носителем)
KK = {"M1": "Автобустарға бөлінген жолақтар", "M2": "Ақылды бағдаршамдар (бейімделгіш басқару)",
      "M3": "ЛРТ желісі / кеңейту", "M4": "Саябақ / сквер", "M5": "Жеке секторды таза отынға көшіру",
      "M6": "Қалалық көгалдандыру және желден қорғау белдеулері бағдарламасы",
      "M7": "Мектеп + балабақша (модульдік құрылыс)", "M8": "Отбасылық денсаулық орталығы / емхана",
      "M9": "Аулалық спорт хабтары", "M10": "Жарықтандыру және камералар (Safe City кеңейту)",
      "M11": "Қауіпсіз өткелдер және мектеп аймақтары", "M12": "Өтініштердің бірыңғай цифрлық платформасы",
      "M13": "Жылу және су желілерін жаңғырту", "M14": "ТКШ авариялық бригадалары + ерте хабарландыру"}
city_data = json.loads((ROOT / "data/city_data.json").read_text(encoding="utf-8"))
catalog = {"source_ru": "data/city_data.json (учебная модель, synthetic)",
           "source_kk": "перевод K09, synthetic, требует проверки носителем",
           "measures": [{"id": m["id"], "scope": m["scope"], "name_ru": m["name"], "name_kk": KK[m["id"]]}
                        for m in city_data["measures"]]}


def ok(city, exclude=None, include=None, budget=None):
    c = {}
    if exclude: c["exclude"] = exclude
    if include: c["include"] = include
    if budget is not None: c["budget"] = budget
    return {"status": "ok", "reason": None, "city": city, "constraints": c}


def no(status, reason, city):
    return {"status": status, "reason": reason, "city": city, "constraints": None}


def inc(m, d):
    return {"measure": m, "district": d}


# (id, split, lang, template_id, class, context_city, text, gold)
EX = [
 # ---------------- DEV, ru
 ("d-ru-01", "dev", "ru", "D-A1", "include", "astana", "Обязательно поликлиника в Нуре", ok("astana", include=[inc("M8", "nura")])),
 ("d-ru-02", "dev", "ru", "D-B1", "exclude", "astana", "Подбери план без ЛРТ", ok("astana", exclude=["M3"])),
 ("d-ru-03", "dev", "ru", "D-C1", "budget", "astana", "Уложись в бюджет 80 у.е.", ok("astana", budget=80)),
 ("d-ru-04", "dev", "ru", "D-D1", "composite", "astana", "Без выделенных полос, парк в районе Есиль, бюджет 90",
  ok("astana", exclude=["M1"], include=[inc("M4", "esil")], budget=90)),
 ("d-ru-05", "dev", "ru", "D-E1", "infer_city", None, "Нужна школа в Абайском районе", ok("shymkent", include=[inc("M7", "abay")])),
 ("d-ru-06", "dev", "ru", "D-F1", "city_unspecified", None, "Исключи модернизацию сетей", no("clarify", "city_unspecified", None)),
 ("d-ru-07", "dev", "ru", "D-G1", "unknown_district", "astana", "Поставь камеры в районе Солнечный", no("clarify", "unknown_district", "astana")),
 ("d-ru-08", "dev", "ru", "D-H1", "unconfirmed_district", "shymkent", "Спорт-хабы в Туранском районе", no("clarify", "unconfirmed_district", "shymkent")),
 ("d-ru-09", "dev", "ru", "D-I1", "district_not_in_city", "astana", "Поликлиника в Енбекшинском районе", no("clarify", "district_not_in_city", "astana")),
 ("d-ru-10", "dev", "ru", "D-K1", "district_not_modeled", "astana", "Школа в районе Сарайшык", no("refuse", "district_not_modeled", "astana")),
 # ---------------- DEV, kk
 ("d-kk-01", "dev", "kk", "D-A2", "include", "astana", "Нұра ауданында емхана міндетті түрде болсын", ok("astana", include=[inc("M8", "nura")])),
 ("d-kk-02", "dev", "kk", "D-B2", "exclude", "astana", "ЛРТ-сыз жоспар құрыңыз", ok("astana", exclude=["M3"])),
 ("d-kk-03", "dev", "kk", "D-C2", "budget", "astana", "Бюджет 80 у.е.-ден аспасын", ok("astana", budget=80)),
 ("d-kk-04", "dev", "kk", "D-D2", "composite", "astana", "Бөлінген жолақтарсыз, Есіл ауданында саябақ, бюджет 90",
  ok("astana", exclude=["M1"], include=[inc("M4", "esil")], budget=90)),
 ("d-kk-05", "dev", "kk", "D-E2", "infer_city", None, "Абай ауданында мектеп салу керек", ok("shymkent", include=[inc("M7", "abay")])),
 ("d-kk-06", "dev", "kk", "D-F2", "city_unspecified", None, "Жылу желілерін жаңғыртуды алып тастаңыз", no("clarify", "city_unspecified", None)),
 ("d-kk-07", "dev", "kk", "D-G2", "unknown_district", "astana", "Күншуақ ауданына камера орнатыңыз", no("clarify", "unknown_district", "astana")),
 ("d-kk-08", "dev", "kk", "D-H2", "unconfirmed_district", "shymkent", "Тұран ауданында спорт хабтары болсын", no("clarify", "unconfirmed_district", "shymkent")),
 ("d-kk-09", "dev", "kk", "D-I2", "district_not_in_city", "astana", "Еңбекші ауданында емхана салыңыз", no("clarify", "district_not_in_city", "astana")),
 ("d-kk-10", "dev", "kk", "D-K2", "district_not_modeled", "astana", "Сарайшық ауданында мектеп", no("refuse", "district_not_modeled", "astana")),
 # ---------------- HELD-OUT, ru
 ("h-ru-01", "heldout", "ru", "H-A1", "include", "astana", "Нужны спорт-хабы в Байконуре", ok("astana", include=[inc("M9", "baikonur")])),
 ("h-ru-02", "heldout", "ru", "H-A2", "include", "astana", "Освещение и камеры обязательно в районе Алматы", ok("astana", include=[inc("M10", "almaty")])),
 ("h-ru-03", "heldout", "ru", "H-B1", "exclude", "astana", "Обойдёмся без ЛРТ и без перевода частного сектора на чистое топливо", ok("astana", exclude=["M3", "M5"])),
 ("h-ru-04", "heldout", "ru", "H-C1", "budget", "astana", "Денег не больше восьмидесяти пяти", ok("astana", budget=85)),
 ("h-ru-05", "heldout", "ru", "H-D1", "composite", "astana", "Школа в Сарыарке, без умных светофоров, лимит 95",
  ok("astana", exclude=["M2"], include=[inc("M7", "saryarka")], budget=95)),
 ("h-ru-06", "heldout", "ru", "H-D2", "composite", "shymkent", "В Каратауском районе нужна поликлиника, без ЛРТ",
  ok("shymkent", exclude=["M3"], include=[inc("M8", "karatau")])),
 ("h-ru-07", "heldout", "ru", "H-E1", "infer_city", None, "Безопасные переходы в Аль-Фарабийском районе", ok("shymkent", include=[inc("M11", "al_farabi")])),
 ("h-ru-08", "heldout", "ru", "H-E2", "infer_city", None, "Парк в Нуре, пожалуйста", ok("astana", include=[inc("M4", "nura")])),
 ("h-ru-09", "heldout", "ru", "H-F1", "city_unspecified", None, "Бюджет 70, без цифровой платформы", no("clarify", "city_unspecified", None)),
 ("h-ru-10", "heldout", "ru", "H-G1", "unknown_district", "shymkent", "Камеры в Зелёном районе", no("clarify", "unknown_district", "shymkent")),
 ("h-ru-11", "heldout", "ru", "H-H1", "unconfirmed_district", None, "Школа в Туранском районе Шымкента", no("clarify", "unconfirmed_district", "shymkent")),
 ("h-ru-12", "heldout", "ru", "H-I1", "district_not_in_city", "shymkent", "Парк в районе Есиль", no("clarify", "district_not_in_city", "shymkent")),
 ("h-ru-13", "heldout", "ru", "H-I2", "district_not_in_city", "astana", "Поставь школу в Каратауском районе", no("clarify", "district_not_in_city", "astana")),
 ("h-ru-14", "heldout", "ru", "H-J1", "ambiguous_toponym", "astana", "Освещение и камеры в Алматы", no("clarify", "ambiguous_toponym", "astana")),
 ("h-ru-15", "heldout", "ru", "H-J2", "ambiguous_toponym", "shymkent", "Поликлиника в Алматы", no("clarify", "ambiguous_toponym", "shymkent")),
 ("h-ru-16", "heldout", "ru", "H-K1", "district_not_modeled", "astana", "Парк в Сарайшыке", no("refuse", "district_not_modeled", "astana")),
 ("h-ru-17", "heldout", "ru", "H-L1", "explicit_city_overrides", "astana", "В Шымкенте нужна школа в Абайском районе", ok("shymkent", include=[inc("M7", "abay")])),
 # ---------------- HELD-OUT, kk
 ("h-kk-01", "heldout", "kk", "H-A3", "include", "astana", "Байқоңыр ауданында аулалық спорт хабтары керек", ok("astana", include=[inc("M9", "baikonur")])),
 ("h-kk-02", "heldout", "kk", "H-A4", "include", "astana", "Алматы ауданында жарықтандыру мен камералар міндетті", ok("astana", include=[inc("M10", "almaty")])),
 ("h-kk-03", "heldout", "kk", "H-B2", "exclude", "astana", "ЛРТ салмаңыз, жеке секторға тиіспеңіз", ok("astana", exclude=["M3", "M5"])),
 ("h-kk-04", "heldout", "kk", "H-C2", "budget", "astana", "Бюджет сексен бестен аспасын", ok("astana", budget=85)),
 ("h-kk-05", "heldout", "kk", "H-D3", "composite", "astana", "Сарыарқада мектеп, ақылды бағдаршамсыз, шегі 95",
  ok("astana", exclude=["M2"], include=[inc("M7", "saryarka")], budget=95)),
 ("h-kk-06", "heldout", "kk", "H-D4", "composite", "shymkent", "Қаратау ауданында емхана керек, ЛРТ-сыз",
  ok("shymkent", exclude=["M3"], include=[inc("M8", "karatau")])),
 ("h-kk-07", "heldout", "kk", "H-E3", "infer_city", None, "Әл-Фараби ауданында қауіпсіз өткелдер салыңыз", ok("shymkent", include=[inc("M11", "al_farabi")])),
 ("h-kk-08", "heldout", "kk", "H-E4", "infer_city", None, "Нұрада саябақ болсын", ok("astana", include=[inc("M4", "nura")])),
 ("h-kk-09", "heldout", "kk", "H-F2", "city_unspecified", None, "Бюджет 70, цифрлық платформасыз", no("clarify", "city_unspecified", None)),
 ("h-kk-10", "heldout", "kk", "H-G2", "unknown_district", "shymkent", "Жасыл ауданында камералар орнатыңыз", no("clarify", "unknown_district", "shymkent")),
 ("h-kk-11", "heldout", "kk", "H-H2", "unconfirmed_district", None, "Шымкенттің Тұран ауданында мектеп", no("clarify", "unconfirmed_district", "shymkent")),
 ("h-kk-12", "heldout", "kk", "H-I3", "district_not_in_city", "shymkent", "Есіл ауданында саябақ", no("clarify", "district_not_in_city", "shymkent")),
 ("h-kk-13", "heldout", "kk", "H-I4", "district_not_in_city", "astana", "Қаратау ауданында мектеп салыңыз", no("clarify", "district_not_in_city", "astana")),
 ("h-kk-14", "heldout", "kk", "H-J3", "ambiguous_toponym", "astana", "Алматыда жарықтандыру мен камералар", no("clarify", "ambiguous_toponym", "astana")),
 ("h-kk-15", "heldout", "kk", "H-J4", "ambiguous_toponym", "shymkent", "Алматыда емхана салыңыз", no("clarify", "ambiguous_toponym", "shymkent")),
 ("h-kk-16", "heldout", "kk", "H-K2", "district_not_modeled", "astana", "Сарайшықта саябақ", no("refuse", "district_not_modeled", "astana")),
 ("h-kk-17", "heldout", "kk", "H-L2", "explicit_city_overrides", "astana", "Шымкентте Абай ауданында мектеп керек", ok("shymkent", include=[inc("M7", "abay")])),
]


def main():
    ids = [e[0] for e in EX]
    assert len(ids) == len(set(ids))
    dev_t = {e[3] for e in EX if e[1] == "dev"}
    held_t = {e[3] for e in EX if e[1] == "heldout"}
    assert not dev_t & held_t, "template overlap"
    rows = [{"id": i, "split": s, "lang": l, "template_id": t, "class": c, "context_city": cc, "text": x, "gold": g,
             "synthetic": True, "author": "K09 (LLM)", "native_speaker_check": "required" if l == "kk" else "recommended"}
            for i, s, l, t, c, cc, x, g in EX]
    D.mkdir(parents=True, exist_ok=True)
    (D / "measure_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    (D / "t1_dataset.jsonl").write_text(body, encoding="utf-8")
    sums = {p: hashlib.sha256((D / p).read_bytes()).hexdigest()
            for p in ("t1_dataset.jsonl", "measure_catalog.json", "gazetteer.json", "ANNOTATION_RULES.md")}
    (D / "DATASET_SHA256.txt").write_text("".join(f"{v}  {k}\n" for k, v in sums.items()), encoding="utf-8")
    from collections import Counter
    print("n =", len(rows), Counter((r["split"], r["lang"]) for r in rows))
    print(Counter((r["split"], r["gold"]["status"]) for r in rows))
    print(sums)


if __name__ == "__main__":
    main()
