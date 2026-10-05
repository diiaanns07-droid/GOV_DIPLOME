"""AST-A11: проверка полноты и происхождения сведений в карточке территории, v0.2.

Общий код для Астаны и Шымкента; различаются только CITY_PROFILES (параметры).
Изолированный эксперимент, не часть продукта STUPITS. LLM не используется.
Результат — индекс ПУБЛИЧНОСТИ сведений, не оценка пригодности участка и не юридическое заключение.

Запуск: python AST_A11_completeness_check.py AST_A11_territory_card.schema.json <card.json> [<card.json> ...]
"""
from __future__ import annotations

import json
import sys
from datetime import date

import jsonschema

TODAY = date(2026, 10, 5)  # фиксировано для воспроизводимости
STALE_DAYS = 90
COUNTED = {"found_official", "not_applicable_confirmed"}

BASE_BLOCK = ["general_plan_zone", "pdp_status", "red_lines", "power_line_protection_zone",
              "gas_pipeline_protection_zone", "water_protection_zone", "sanitary_protection_zone",
              "heritage_protection_zone", "airport_restriction_zone", "seismic_zone", "flood_risk"]
BASE_PARCEL = ["land_category", "target_purpose", "cadastral_status"] + BASE_BLOCK + ["auction_status"]
BASE_DISTRICT = ["general_plan_zone", "pdp_status", "water_protection_zone", "heritage_protection_zone",
                 "airport_restriction_zone", "seismic_zone", "flood_risk"]

# ГИПОТЕЗЫ, требующие проверки по нормам каждого города (A11 / AST-A11, 2-й проход).
CITY_PROFILES = {
    "Шымкент": {
        "extra_topics": [],
        "neighbouring_region": "Туркестанская область",
        "former_region": "Южно-Казахстанская область",
        "former_city_names": [],
    },
    "Астана": {
        "extra_topics": ["green_belt_or_forest_fund"],
        "neighbouring_region": "Акмолинская область",
        "former_region": None,
        "former_city_names": ["Нур-Султан", "Nur-Sultan", "Акмола", "Целиноград"],
    },
}


def mandatory(city: str, level: str) -> list[str]:
    base = {"parcel": BASE_PARCEL, "block": BASE_BLOCK, "microdistrict": BASE_BLOCK,
            "district": BASE_DISTRICT, "city": BASE_DISTRICT}[level]
    return base + [t for t in CITY_PROFILES[city]["extra_topics"] if t not in base]


def check(card: dict, today: date = TODAY) -> dict:
    city = card["territory"]["city"]
    prof = CITY_PROFILES[city]
    flags, requests, counted, by_topic = [], [], set(), {}
    for it in card["items"]:
        by_topic.setdefault(it["topic"], []).append(it)

    jc = card["territory"].get("jurisdiction_check")
    territory_blocked = False
    if jc:
        # R8: территория у границы или данные о границе противоречивы — нужен официальный акт о границах
        if jc["result"] in {"near_boundary_needs_official_check", "boundary_data_inconsistent"}:
            flags.append(("territory", "R8", f"юрисдикция не установлена ({jc['result']}); нужен официальный акт о границах города"))
            territory_blocked = jc["boundary_legal_weight"] != "legally_certified"
        if jc["result"] == "outside_city_context_only":
            flags.append(("territory", "R8", f"по контекстным данным территория вне города {city}: карточка города неприменима"))
            territory_blocked = True

    for it in card["items"]:
        iid, st = it["item_id"], it["status"]
        est, geo, prov = it.get("establishing_act"), it["geometry"], it["provenance"]
        n0, ok = len(flags), st in COUNTED
        if st == "found_official":                                     # R1
            if not est or not est.get("official_url"):
                flags.append((iid, "R1", "нет ссылки на устанавливающий акт")); ok = False
            elif est["document_status"] != "in_force":
                flags.append((iid, "R1", f"акт в статусе {est['document_status']}: не текущее ограничение")); ok = False
            if est and not est.get("locator"):
                flags.append((iid, "R1b", "нет локатора (статья/лист/страница)"))
        if st == "found_official_draft" or (est and est["document_status"] in {"draft", "news_or_announcement"}):
            flags.append((iid, "R2", "проект или новость: показывать как планируемое изменение")); ok = False
        if geo["legal_weight"] in {"illustrative", "context_only"}:   # R3
            flags.append((iid, "R3", f"геометрия {geo['source_type']}: визуальное наложение, не граница"))
        if geo["legal_weight"] == "legally_certified" and geo["source_type"] not in {"certified_cadastral", "approved_plan_vector"}:
            flags.append((iid, "R3b", "юридический вес у неподходящего типа геометрии")); ok = False
        if prov["extracted_by"] == "llm_unchecked":                     # R4
            flags.append((iid, "R4", "извлечено LLM без проверки человеком")); ok = False
        acc = prov.get("accessed_at")                                   # R5
        if acc and (today - date.fromisoformat(acc[:10])).days > STALE_DAYS:
            flags.append((iid, "R5", f"источник проверялся {acc[:10]}, старше {STALE_DAYS} дней")); ok = False
        for a in (est, it.get("legal_basis")):                          # R6, R7
            if not a:
                continue
            j = a.get("issuer_jurisdiction")
            if j == "neighbouring_region":
                flags.append((iid, "R6", f"акт органа соседнего региона ({prof['neighbouring_region']}): к территории города не применяется без подтверждения")); ok = False
            elif j == "former_region":
                flags.append((iid, "R6", f"акт прежней области ({prof['former_region']}): проверить, действует ли на территории города")); ok = False
            name = a.get("city_name_at_issue")
            if name and name in prof["former_city_names"]:
                flags.append((iid, "R7", f"акт принят под названием «{name}»: проверить действующую редакцию и изменения"))
        if territory_blocked and ok:
            ok = False
            flags.append((iid, "R8", "не засчитано до подтверждения юрисдикции территории"))
        if ok:
            counted.add(it["topic"])
        if st in {"not_public", "not_found", "found_unofficial"} or not ok:
            failed = sorted({r for (_, r, _) in flags[n0:] if r in {"R1", "R2", "R3b", "R4", "R5", "R6", "R8"}})
            reason = st if not failed else f"{st}; не засчитано: {','.join(failed)}"
            requests.append({"topic": it["topic"], "ask": it["authority_for_binding_answer"], "reason": reason})

    mand = mandatory(city, card["territory"]["level"])
    missing = [t for t in mand if t not in by_topic]
    requests += [{"topic": t, "ask": "определить уполномоченный орган", "reason": "not_checked"} for t in missing]
    n_ok = len([t for t in mand if t in counted])
    return {
        "card_id": card["card_id"], "data_kind": card["data_kind"], "city": city,
        "level": card["territory"]["level"], "mandatory_topics": len(mand), "counted_topics": n_ok,
        "public_info_completeness": round(n_ok / len(mand), 3),
        "completeness_formula": "count(mandatory topics with found_official|not_applicable_confirmed passing R1,R2,R3b,R4,R5,R6,R8) / count(mandatory topics of city profile)",
        "missing_topics": missing,
        "flags": [{"item_id": a, "rule": b, "message": c} for a, b, c in flags],
        "requests_to_authorities": requests,
        "warning": "Индекс полноты публичных сведений. Не оценка пригодности участка и не юридическое заключение.",
    }


def main(schema_path: str, card_paths: list[str]) -> int:
    schema = json.load(open(schema_path, encoding="utf-8"))
    for p in card_paths:
        card = json.load(open(p, encoding="utf-8"))
        jsonschema.validate(card, schema)
        res = check(card)
        print(("SYNTHETIC " if card["data_kind"] == "synthetic" else "") + json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
