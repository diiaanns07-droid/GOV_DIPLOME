"""A11: проверка полноты и происхождения сведений в карточке территории.

Изолированный эксперимент (не часть продукта STUPITS). Проверяет гипотезу:
полноту публичных сведений можно оценить детерминированными правилами, без LLM.
Результат — НЕ юридическое заключение и НЕ оценка пригодности участка.

Запуск: python A11_completeness_check.py A11_territory_card.schema.json A11_synthetic_card.json
"""
from __future__ import annotations

import json
import sys
from datetime import date

import jsonschema

# Обязательные темы по уровню территории (версия 0.1, требует юридической проверки во 2-м проходе)
MANDATORY = {
    "parcel": ["land_category", "target_purpose", "cadastral_status", "general_plan_zone", "pdp_status",
               "red_lines", "power_line_protection_zone", "gas_pipeline_protection_zone",
               "water_protection_zone", "sanitary_protection_zone", "heritage_protection_zone",
               "airport_restriction_zone", "seismic_zone", "flood_risk", "auction_status"],
    "block": ["general_plan_zone", "pdp_status", "red_lines", "power_line_protection_zone",
              "gas_pipeline_protection_zone", "water_protection_zone", "sanitary_protection_zone",
              "heritage_protection_zone", "airport_restriction_zone", "seismic_zone", "flood_risk"],
}
MANDATORY["microdistrict"] = MANDATORY["block"]
MANDATORY["district"] = ["general_plan_zone", "pdp_status", "water_protection_zone", "heritage_protection_zone",
                         "airport_restriction_zone", "seismic_zone", "flood_risk"]
MANDATORY["city"] = MANDATORY["district"]

STALE_DAYS = 90
COUNTED = {"found_official", "not_applicable_confirmed"}


def check(card: dict, today: date) -> dict:
    flags, requests, counted = [], [], set()
    by_topic = {}
    for it in card["items"]:
        by_topic.setdefault(it["topic"], []).append(it)
    for it in card["items"]:
        iid, st = it["item_id"], it["status"]
        n_before = len(flags)
        est, geo, prov = it.get("establishing_act"), it["geometry"], it["provenance"]
        ok = st in COUNTED
        # R1: «официально найдено» требует ссылки на действующий устанавливающий акт
        if st == "found_official":
            if not est or not est.get("official_url"):
                flags.append((iid, "R1", "нет ссылки на устанавливающий акт")); ok = False
            elif est["document_status"] != "in_force":
                flags.append((iid, "R1", f"акт в статусе {est['document_status']}: не текущее ограничение")); ok = False
            if est and not est.get("locator"):
                flags.append((iid, "R1b", "нет локатора (статья/лист/страница)"))
        # R2: проект/новость показываются как «планируемое», в полноту не засчитываются
        if st == "found_official_draft" or (est and est["document_status"] in {"draft", "news_or_announcement"}):
            flags.append((iid, "R2", "проект или новость: показывать как планируемое изменение"))
        # R3: геометрия без юридического веса — только визуальная подсказка
        if geo["legal_weight"] in {"illustrative", "context_only"}:
            flags.append((iid, "R3", f"геометрия {geo['source_type']}: визуальное наложение, не граница"))
        if geo["legal_weight"] == "legally_certified" and geo["source_type"] not in {"certified_cadastral", "approved_plan_vector"}:
            flags.append((iid, "R3b", "заявлен юридический вес для неподходящего типа геометрии")); ok = False
        # R4: извлечение LLM без проверки человеком не засчитывается
        if prov["extracted_by"] == "llm_unchecked":
            flags.append((iid, "R4", "извлечено LLM без проверки человеком")); ok = False
        # R5: устаревшая проверка источника
        acc = prov.get("accessed_at")
        if acc and (today - date.fromisoformat(acc[:10])).days > STALE_DAYS:
            flags.append((iid, "R5", f"источник проверялся {acc[:10]}, старше {STALE_DAYS} дней")); ok = False
        if ok:
            counted.add(it["topic"])
        if st in {"not_public", "not_found", "found_unofficial"} or not ok:
            failed = sorted({r for (i, r, _) in flags[n_before:] if r in {"R1", "R2", "R3b", "R4", "R5"}})
            reason = st if not failed else f"{st}; не засчитано: {','.join(failed)}"
            requests.append({"topic": it["topic"], "ask": it["authority_for_binding_answer"], "reason": reason})
    mand = MANDATORY[card["territory"]["level"]]
    missing = [t for t in mand if t not in by_topic]
    for t in missing:
        requests.append({"topic": t, "ask": "определить уполномоченный орган (2-й проход)", "reason": "not_checked"})
    n_ok = len([t for t in mand if t in counted])
    return {
        "card_id": card["card_id"],
        "data_kind": card["data_kind"],
        "level": card["territory"]["level"],
        "mandatory_topics": len(mand),
        "counted_topics": n_ok,
        "public_info_completeness": round(n_ok / len(mand), 3),
        "completeness_formula": "count(mandatory topics with found_official|not_applicable_confirmed passing R1,R3b,R4,R5) / count(mandatory topics)",
        "missing_topics": missing,
        "flags": [{"item_id": a, "rule": b, "message": c} for a, b, c in flags],
        "requests_to_authorities": requests,
        "warning": "Индекс полноты публичных сведений. Не оценка пригодности участка и не юридическое заключение.",
    }


def main(schema_path: str, card_path: str) -> int:
    schema = json.load(open(schema_path, encoding="utf-8"))
    card = json.load(open(card_path, encoding="utf-8"))
    jsonschema.validate(card, schema)  # бросит исключение при нарушении контракта
    result = check(card, date(2026, 10, 4))
    prefix = "SYNTHETIC " if card["data_kind"] == "synthetic" else ""
    print(prefix + json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
