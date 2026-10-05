"""K02 round 3: изолированный прототип объяснения по ID проверенных фактов.

Схема:
  ответ движка ──build_catalog──► каталог фактов {fact_id: Fact}
  каталог (только id + подписи) ──selector──► план {sections: [{type, fact_ids}], comment?}
  план ──validate_plan──► ошибки или принятый план
  принятый план + каталог ──render──► текст ru/kk; значения и формулировки выдаёт код

Селектор — модель или детерминированная заглушка. Он выбирает только ID и тип секции.
Он не пишет числа и подписи. Свободный комментарий по умолчанию отбрасывается.
С comment_policy="separate" он печатается отдельным блоком «не проверяется» после
проверяемой части и не участвует в её построении.

Код agent/ и интерфейс продукта не меняются. Из agent.evidence используется только
format_value — та же запись чисел, что в продукте.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Корень репозитория — ближайший родитель с пакетом agent/ (файл может лежать на разной глубине).
REPO = next(p for p in Path(__file__).resolve().parents if (p / "agent" / "evidence.py").exists())
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agent.evidence import format_value  # noqa: E402

# Граница доверия: что считается каким видом данных.
KINDS = {"observed", "derived", "hypothesis", "model", "synthetic", "unknown"}
# «model» — учебная модель ТЗ (синтетический датасет хакатона), не измерение города.
HACKATHON_CITY = "astana_hackathon"
# R4: город допускает точки (kz.shymkent), сценарий/период — точки и дефисы (2026-09-23).
# Интервал периода с «/» в ID не помещается: catalog_from_k05 отклоняет его явно.
ID_PATTERN = re.compile(r"^(?P<city>[a-z][a-z0-9_.]*)/(?P<scenario>[A-Za-z0-9_.\-]+)/(?P<path>[a-z][a-z0-9_.]*)$")
_DIGIT = re.compile(r"\d")
SECTION_TYPES = ("summary", "weakest", "risks", "data_gaps")
MAX_FACTS_PER_SECTION = 6
MAX_SECTIONS = 4


@dataclass(frozen=True)
class Fact:
    fact_id: str
    city: str
    scenario_id: str
    kind: str
    value: float | int | str | None   # None = неизвестно, не ноль
    unit: str                          # "points", "ue", "count", "name"
    label: dict                        # {"ru": ..., "kk": ...}
    source: str                        # путь в ответе движка или ссылка на наблюдение
    signed: bool = False               # изменение: печатать со знаком
    coverage_complete: bool | None = None   # False → значение по неполному охвату/выборке
    missing_reason: str | None = None       # почему value = None (из источника)

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind {self.kind}")
        if self.unit not in _UNITS:
            raise ValueError(f"unknown unit {self.unit!r}: добавьте подписи ru/kk в _UNITS")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError(f"{self.fact_id}: неконечное значение {self.value}")
        for lang in ("ru", "kk"):
            if not isinstance(self.label.get(lang), str) or _DIGIT.search(self.label[lang]):
                raise ValueError(f"{self.fact_id}: подпись {lang} отсутствует или содержит цифры")
        m = ID_PATTERN.match(self.fact_id)
        if not m or m["city"] != self.city or m["scenario"] != self.scenario_id:
            raise ValueError(f"fact_id {self.fact_id} does not match city/scenario")


class PlanError(ValueError):
    """План селектора отклонён. code — машинная причина для тестов и журнала."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


# Подписи ru/kk. Казахские формулировки K02 — черновик для проверки носителем.
_LABELS = {
    "plan.score": {"ru": "Итоговый Score плана", "kk": "Жоспардың қорытынды Score көрсеткіші"},
    "base.score": {"ru": "Score без мер", "kk": "Шараларсыз Score"},
    "plan.delta_score": {"ru": "Изменение Score", "kk": "Score өзгерісі"},
    "plan.cost": {"ru": "Стоимость плана", "kk": "Жоспар құны"},
    "plan.budget": {"ru": "Бюджет", "kk": "Бюджет"},
    "plan.n_crit": {"ru": "Критических значений после мер", "kk": "Шаралардан кейінгі сыни мәндер саны"},
    "base.n_crit": {"ru": "Критических значений без мер", "kk": "Шараларсыз сыни мәндер саны"},
    "plan.min_district": {"ru": "Самый слабый район", "kk": "Ең әлсіз аудан"},
    "plan.min_district_d": {"ru": "Индекс самого слабого района", "kk": "Ең әлсіз ауданның индексі"},
}
_DISTRICT_KK = {"esil": "Есіл", "almaty": "Алматы", "saryarka": "Сарыарқа", "baikonur": "Байқоңыр",
                "nura": "Нұра", "saraishyk": "Сарайшық"}
_UNITS = {"points": {"ru": "", "kk": ""}, "ue": {"ru": " у.е.", "kk": " ш.б."},
          "count": {"ru": "", "kk": ""}, "name": {"ru": "", "kk": ""},
          # R4: единицы записей K05; kk — черновик K02.
          "records": {"ru": " записей", "kk": " жазба"}, "schools": {"ru": " школ", "kk": " мектеп"},
          # BUILD r5: единицы демо; kk — черновик
          "segments": {"ru": " сегментов", "kk": " сегмент"}, "places": {"ru": " мест", "kk": " орын"},
          "persons": {"ru": " чел.", "kk": " адам"}}
_TEXT = {
    "header": {"ru": "Проверяемая часть (значения из ответа движка)",
               "kk": "Тексерілетін бөлік (мәндер есептеу қозғалтқышының жауабынан)"},
    "summary": {"ru": "Итог", "kk": "Қорытынды"},
    "weakest": {"ru": "Самый слабый район", "kk": "Ең әлсіз аудан"},
    "risks": {"ru": "Риски", "kk": "Тәуекелдер"},
    "data_gaps": {"ru": "Нет данных", "kk": "Дерек жоқ"},
    "unknown": {"ru": "нет данных", "kk": "дерек жоқ"},
    "kind_model": {"ru": "учебная модель", "kk": "оқу моделі"},
    "kind_observed": {"ru": "наблюдение", "kk": "бақылау"},
    "kind_derived": {"ru": "расчёт", "kk": "есептелген"},
    "kind_synthetic": {"ru": "синтетика", "kk": "синтетикалық"},
    "kind_unknown": {"ru": "неизвестно", "kk": "белгісіз"},
    "kind_hypothesis": {"ru": "гипотеза", "kk": "болжам"},
    "incomplete": {"ru": "неполный охват", "kk": "толық емес қамту"},
    "scenario": {"ru": "Сценарий", "kk": "Сценарий"},
    "comment": {"ru": "Комментарий модели — НЕ проверяется, факты выше от него не зависят",
                "kk": "Модель түсініктемесі — ТЕКСЕРІЛМЕЙДІ, жоғарыдағы деректер оған тәуелді емес"},
}


# BUILD r5: подписи причин отсутствия (коды k05-obs missing_reason); kk — черновик
_REASON = {
    "source_access_denied": {"ru": "источник недоступен", "kk": "дереккөзге қол жетімсіз"},
    "not_collected": {"ru": "не собиралось", "kk": "жиналмаған"},
    "not_in_source": {"ru": "нет в источнике", "kk": "дереккөзде жоқ"},
    "zero_in_partial_coverage": {"ru": "ноль при неполном охвате", "kk": "толық емес қамтудағы нөл"},
    "suppressed_by_publisher": {"ru": "скрыто публикатором", "kk": "жариялаушы жасырған"},
}


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def build_catalog(result: dict, *, city: str = HACKATHON_CITY, kind: str = "model") -> dict[str, Fact]:
    """Каталог из ответа engine.simulation.simulate(). Отсутствующее поле → value=None."""
    if city != HACKATHON_CITY:
        # R4: ответ движка — всегда учебная модель; реальный город сюда не подставляется.
        raise ValueError(f"build_catalog: ответ движка относится к {HACKATHON_CITY}, не к {city}")
    event = result.get("event")
    scenario = event["id"] if isinstance(event, dict) and event.get("id") else "base"
    base = result.get("baseline") if isinstance(result.get("baseline"), dict) else {}
    delta = result.get("delta") if isinstance(result.get("delta"), dict) else {}
    weakest = result.get("min_district") if isinstance(result.get("min_district"), dict) else {}
    raw = {
        "plan.score": (_num(result.get("score")), "points", "/score", False),
        "base.score": (_num(base.get("score")), "points", "/baseline/score", False),
        "plan.delta_score": (_num(delta.get("score")), "points", "/delta/score", True),
        "plan.cost": (_num(result.get("cost")), "ue", "/cost", False),
        "plan.budget": (_num(result.get("budget")), "ue", "/budget", False),
        "plan.n_crit": (_num(result.get("N_crit")), "count", "/N_crit", False),
        "base.n_crit": (_num(base.get("N_crit")), "count", "/baseline/N_crit", False),
        "plan.min_district": (weakest.get("id"), "name", "/min_district/id", False),
        "plan.min_district_d": (_num(weakest.get("D")), "points", "/min_district/D", False),
    }
    catalog = {}
    for path, (value, unit, source, signed) in raw.items():
        fid = f"{city}/{scenario}/{path}"
        catalog[fid] = Fact(fid, city, scenario, kind if value is not None else "unknown",
                            value, unit, _LABELS[path], f"engine:{source}", signed)
    return catalog


def catalog_from_observations(rows: list[dict]) -> dict[str, Fact]:
    """Каталог реальных наблюдений (контракт K05 ещё не утверждён; поля минимальные).
    rows: {city, period, path, value|None, kind, unit, label_ru, label_kk, source}.
    period играет роль scenario_id: факт 2024 года не подставляется в ответ о 2025."""
    catalog = {}
    for r in rows:
        fid = f"{r['city']}/{r['period']}/{r['path']}"
        if fid in catalog:
            raise ValueError(f"{fid}: два наблюдения на один ID; выберите снимок до построения каталога")
        kind = r["kind"] if r["value"] is not None else "unknown"
        catalog[fid] = Fact(fid, r["city"], r["period"], kind, r["value"], r["unit"],
                            {"ru": r["label_ru"], "kk": r["label_kk"]}, r["source"],
                            coverage_complete=r.get("coverage_complete"),
                            missing_reason=r.get("missing_reason"))
    return catalog


# R4: подписи показателей K05 — закрытая таблица кода, без цифр (порог confidence — в source).
_K05_INDICATORS = {
    "k10_sample_rows": ("Строк в выборке-образце", "Үлгі іріктемесіндегі жолдар"),
    "overture_place_records": ("Записей Overture places", "Overture places жазбалары"),
    "official_registry": ("Официальный реестр", "Ресми тізілім"),
}
_K05_GROUPS = {"school": ("школы", "мектептер"), "school_count": ("школы", "мектептер"),
               "preschool": ("детсады", "балабақшалар"), "outpatient_clinic": ("поликлиники", "емханалар"),
               "hospital": ("больницы", "ауруханалар"), "pharmacy": ("аптеки", "дәріханалар"),
               "government_office": ("госучреждения", "мемлекеттік мекемелер"),
               "college_university": ("колледжи и вузы", "колледждер мен жоғары оқу орындары")}


def _k05_label(indicator_id: str, geo_unit_id: str) -> dict:
    parts = indicator_id.split(".")
    base = _K05_INDICATORS.get(parts[0])
    group = _K05_GROUPS.get(parts[1]) if len(parts) > 1 else None
    if base is None or group is None:
        raise ValueError(f"нет подписи для показателя {indicator_id}; добавьте в _K05_INDICATORS/_K05_GROUPS")
    unit = geo_unit_id.split(".")[-1]
    where_ru = "весь город" if unit in ("astana", "shymkent") else f"район {unit}"
    where_kk = "бүкіл қала" if unit in ("astana", "shymkent") else f"{unit} ауданы"
    note_ru = ", порог уверенности — в источнике" if len(parts) > 2 else ""
    note_kk = ", сенімділік шегі — дереккөзде" if len(parts) > 2 else ""
    return {"ru": f"{base[0]}: {group[0]} ({where_ru}{note_ru})",
            "kk": f"{base[1]}: {group[1]} ({where_kk}{note_kk})"}


def catalog_from_k05(records: list[dict]) -> dict[str, Fact]:
    """R4: прямой приём записей k05-obs-v1.1. Сохраняет охват и причину пропуска.
    Не выбирает снимок: два наблюдения на один ID → ValueError (решает контракт K05)."""
    rows = []
    for r in records:
        if r.get("schema_version") != "k05-obs-v1.1":
            raise ValueError(f"{r.get('obs_id')}: ожидается k05-obs-v1.1")
        if "/" in r["period"]:
            raise ValueError(f"{r['obs_id']}: интервальный период {r['period']} не поддержан в ID")
        label = _k05_label(r["indicator_id"], r["geo_unit_id"])
        rows.append({"city": r["city_id"], "period": r["period"],
                     "path": r["geo_unit_id"].split(".")[-1] + "." + r["indicator_id"],
                     "value": r["value"], "kind": r["kind"], "unit": r["unit"],
                     "label_ru": label["ru"], "label_kk": label["kk"],
                     "source": f"k05:{r['obs_id']}|{r['data_version']}|{r.get('boundary_version')}",
                     "coverage_complete": r["coverage"]["complete"],
                     "missing_reason": r.get("missing_reason")})
    return catalog_from_observations(rows)


def catalog_digest(catalog: dict[str, Fact]) -> str:
    """R4: отпечаток каталога (ID, значения, вид, охват). План без него или со старым — отказ."""
    payload = sorted((f.fact_id, repr(f.value), f.kind, f.coverage_complete, f.unit, f.missing_reason)
                     for f in catalog.values())  # BUILD r5: + unit, missing_reason
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()[:16]


def catalog_view(catalog: dict[str, Fact]) -> list[dict]:
    """Что видит селектор: ID, подпись, вид данных. Значения ему не нужны для выбора."""
    return [{"id": f.fact_id, "label_ru": f.label["ru"], "kind": f.kind,
             "has_value": f.value is not None} for f in catalog.values()]


# JSON Schema ответа селектора — для structured output будущей модели.
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {"type": "array", "maxItems": MAX_SECTIONS, "items": {
            "type": "object",
            "properties": {"type": {"enum": list(SECTION_TYPES)},
                           "fact_ids": {"type": "array", "maxItems": MAX_FACTS_PER_SECTION,
                                        "items": {"type": "string"}}},
            "required": ["type", "fact_ids"], "additionalProperties": False}},
        "comment": {"type": ["string", "null"]},
        "catalog_digest": {"type": "string"},
    },
    "required": ["sections", "catalog_digest"], "additionalProperties": False,
}


def validate_plan(plan, catalog: dict[str, Fact], *, city: str, scenario_id: str,
                  known_ids: dict[str, Fact] | None = None) -> dict:
    """Проверка плана. known_ids — факты других городов/сценариев, известные системе
    (нужны только для точной причины отказа). Возвращает нормализованный план."""
    known_ids = known_ids or {}
    if not isinstance(plan, dict) or set(plan) - {"sections", "comment", "catalog_digest"} or "sections" not in plan:
        raise PlanError("bad_shape", "ожидается объект {sections, catalog_digest, comment?}")
    if plan.get("catalog_digest") != catalog_digest(catalog):
        raise PlanError("stale_catalog", "план построен по другому каталогу (смена результата, города или сценария)")
    used_ids: set[str] = set()
    sections = plan["sections"]
    if not isinstance(sections, list) or not sections or len(sections) > MAX_SECTIONS:
        raise PlanError("bad_shape", f"нужно 1–{MAX_SECTIONS} секций")
    seen_types, normal = set(), []
    for section in sections:
        if not isinstance(section, dict) or set(section) != {"type", "fact_ids"}:
            raise PlanError("bad_shape", "секция = {type, fact_ids}")
        stype, ids = section["type"], section["fact_ids"]
        if stype not in SECTION_TYPES:
            raise PlanError("bad_section", f"тип секции {stype!r} не разрешён")
        if stype in seen_types:
            raise PlanError("bad_section", f"секция {stype} повторяется")
        seen_types.add(stype)
        if not isinstance(ids, list) or not ids or len(ids) > MAX_FACTS_PER_SECTION:
            raise PlanError("bad_shape", f"в секции 1–{MAX_FACTS_PER_SECTION} ID")
        for fid in ids:
            if not isinstance(fid, str):
                raise PlanError("not_an_id", f"{fid!r} не строка")
            m = ID_PATTERN.match(fid)
            if not m:
                raise PlanError("not_an_id", f"{fid[:60]!r} не является ID факта")
            if m["city"] != city:
                raise PlanError("foreign_city", f"{fid}: город {m['city']}, запрос по {city}")
            if m["scenario"] != scenario_id:
                raise PlanError("stale_scenario", f"{fid}: сценарий {m['scenario']}, текущий {scenario_id}")
            if fid not in catalog:
                raise PlanError("unknown_id", f"{fid} нет в каталоге текущего ответа"
                                + (" (известен системе, но не в этом ответе)" if fid in known_ids else ""))
            fact = catalog[fid]
            if fact.value is None and stype != "data_gaps":
                raise PlanError("null_as_fact", f"{fid} не имеет значения; его место только в data_gaps")
            if fact.value is not None and stype == "data_gaps":
                raise PlanError("value_in_gaps", f"{fid} имеет значение, а секция data_gaps для неизвестных")
        if len(set(ids)) != len(ids) or used_ids & set(ids):
            raise PlanError("duplicate_id", "ID повторяется в секции или между секциями")
        used_ids.update(ids)
        normal.append({"type": stype, "fact_ids": list(ids)})
    comment = plan.get("comment")
    if comment is not None and not isinstance(comment, str):
        raise PlanError("bad_shape", "comment — строка или null")
    return {"sections": normal, "comment": comment, "catalog_digest": plan["catalog_digest"]}


def _render_value(fact: Fact, lang: str) -> str:
    if fact.value is None:
        return _TEXT["unknown"][lang]
    if fact.unit == "name":
        return _DISTRICT_KK.get(fact.value, fact.value) if lang == "kk" else _district_ru(fact.value)
    text = format_value(fact.value)
    if fact.signed and fact.value > 0:
        text = "+" + text
    return text + _UNITS[fact.unit][lang]


_DISTRICT_RU = {"esil": "Есиль", "almaty": "Алматы", "saryarka": "Сарыарка", "baikonur": "Байконур",
                "nura": "Нура", "saraishyk": "Сарайшык"}


def _district_ru(slug: str) -> str:
    return _DISTRICT_RU.get(slug, slug)


def render(plan: dict, catalog: dict[str, Fact], *, lang: str, comment_policy: str = "drop") -> dict:
    """Текст строится только из каталога. Комментарий не влияет на проверяемую часть."""
    if lang not in ("ru", "kk"):
        raise ValueError("lang: ru | kk")
    if comment_policy not in ("drop", "separate"):
        raise ValueError("comment_policy: drop | separate")
    any_fact = next(iter(catalog.values()))
    lines = [f"**{_TEXT['header'][lang]}.** {_TEXT['scenario'][lang]}: {any_fact.scenario_id}."]
    used = []
    for section in plan["sections"]:
        lines.append(f"\n**{_TEXT[section['type']][lang]}**")
        for fid in section["fact_ids"]:
            fact = catalog[fid]
            kind = _TEXT["kind_" + fact.kind][lang]
            if fact.coverage_complete is False and fact.value is not None:
                kind += ", " + _TEXT["incomplete"][lang]
            if fact.value is None and fact.missing_reason:  # BUILD r5: причина пропуска видна в тексте
                kind += ", " + _REASON.get(fact.missing_reason, {}).get(lang, fact.missing_reason)
            lines.append(f"- {fact.label[lang]}: {_render_value(fact, lang)} ({kind})")
            used.append({"id": fid, "value": fact.value, "kind": fact.kind, "source": fact.source,
                         "coverage_complete": fact.coverage_complete, "missing_reason": fact.missing_reason})
    verified = "\n".join(lines)
    comment = plan.get("comment")
    shown_comment = comment if (comment_policy == "separate" and comment and comment.strip()) else None
    text = verified
    if shown_comment:
        text += f"\n\n---\n_{_TEXT['comment'][lang]}:_ {shown_comment.strip()}"
    return {"text": text, "verified_text": verified, "facts_used": used,
            "catalog_digest": plan.get("catalog_digest"),
            "comment_shown": shown_comment is not None, "comment_policy": comment_policy}


class StubSelector:
    """Детерминированная заглушка вместо LLM. Не вызывает модель и не притворяется ею."""
    name = "deterministic_stub (not an LLM)"

    def select(self, view: list[dict], question: str = "", lang: str = "ru", digest: str | None = None) -> dict:
        def pick(*suffixes):
            return [v["id"] for v in view for s in suffixes
                    if v["id"].endswith("/" + s) and v["has_value"]]
        sections = [{"type": "summary", "fact_ids": pick("plan.score", "plan.delta_score", "plan.cost")},
                    {"type": "weakest", "fact_ids": pick("plan.min_district", "plan.min_district_d")},
                    {"type": "risks", "fact_ids": pick("plan.n_crit")}]
        gaps = [v["id"] for v in view if not v["has_value"]]
        if gaps:
            sections.append({"type": "data_gaps", "fact_ids": gaps[:MAX_FACTS_PER_SECTION]})
        return {"sections": [s for s in sections if s["fact_ids"]], "comment": None, "catalog_digest": digest}


def explain(result: dict, *, lang: str = "ru", selector=None, city: str = HACKATHON_CITY,
            comment_policy: str = "drop", known_ids: dict | None = None) -> dict:
    """Полный проход: каталог → выбор → проверка → текст. Ошибка плана не скрывается."""
    selector = selector or StubSelector()
    catalog = build_catalog(result, city=city)
    scenario = next(iter(catalog.values())).scenario_id
    plan = selector.select(catalog_view(catalog), lang=lang, digest=catalog_digest(catalog))
    accepted = validate_plan(plan, catalog, city=city, scenario_id=scenario, known_ids=known_ids)
    out = render(accepted, catalog, lang=lang, comment_policy=comment_policy)
    out.update({"selector": getattr(selector, "name", type(selector).__name__), "scenario_id": scenario,
                "city": city})
    return out
