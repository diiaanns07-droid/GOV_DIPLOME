"""B2: детерминированный разбор поручений ru/kk с нормализацией и словарём явных алиасов.

Источники справочников (не тексты примеров):
- районы и города — dataset/gazetteer.json (OSM/Overture/K03, уровни подтверждения сохранены);
- меры — dataset/measure_catalog.json (ru из учебной модели, kk — перевод K09) + явные основы ниже;
- правила статуса — dataset/ANNOTATION_RULES.md (R1–R7).
Настраивался только на dev-части. LLM не используется.
"""
import json, re
from pathlib import Path

K = Path(__file__).resolve().parents[1]

KK2RU = str.maketrans({"і": "и", "қ": "к", "ң": "н", "ғ": "г", "ү": "у", "ұ": "у", "ө": "о", "ә": "а", "һ": "х", "ё": "е"})
GENERIC = {"район", "ауданы", "аудан"}
DISTRICT_MARKER = ("район", "аудан")           # префиксы: районе, района, ауданында, ауданына ...
STOP_NEAR_MARKER = {"в", "во", "на", "по", "этом", "каждом", "любом", "том", "и", "мен", "және"}
CITY_STEMS = {"астан": "astana", "шымкент": "shymkent"}
AMBIGUOUS_WITHOUT_MARKER = {"astana.almaty"}   # R3: «Алматы» без «район/ауданы»

# Явные основы мер (префиксы токенов после нормализации; кортеж = подряд идущие токены).
MEASURE_ALIASES = {
    "M1": ["полос", "жолак"],
    "M2": ["светофор", "багдаршам"],
    "M3": ["лрт"],
    "M4": ["парк", "сквер", "саябак"],
    "M5": [("частн", "сектор"), "топлив", ("жеке", "сектор"), "отын"],
    "M6": ["озеленени", "ветрозащит", "когалдандыр"],
    "M7": ["школ", "детсад", "мектеп", "балабакша"],
    "M8": ["поликлиник", ("семейн", "здоров"), "емхана", "денсаулык"],
    "M9": ["спорт-хаб", "спортхаб", ("спорт", "хаб")],
    "M10": ["освещени", "камер", "жарыктандыр"],
    "M11": ["переход", ("школьн", "зон"), "откел", ("мектеп", "аймак")],
    "M12": ["платформ", "обращени", "отиниш"],
    "M13": [("модерниз", "сет"), "теплосет", "водосет", ("жылу", "жели"), ("су", "жели"), "жангырт"],
    "M14": ["бригад", "аварийн", "авариялык"],
}
# Более специфичные алиасы подавляют общие внутри того же окна токенов.
SUPPRESS = {("M11", "M7")}                      # «школьные зоны», «мектеп аймақтары» -> не школа

RU_NEG_TOKENS = {"без", "не", "исключи", "исключить", "исключите", "кроме", "убери", "уберите"}
KK_NEG_SUFFIX = ("сыз", "сиз")                  # после нормализации: -сыз/-сіз
KK_NEG_TOKENS = {"жок", "емес"}
KK_NEG_VERB = re.compile(r"(ма|ме|ба|бе|па|пе)(ныз|низ|у|йык|йик)$")   # отрицательный императив/отглаг. сущ.
KK_REMOVE = ("алып", "таста")                   # «алып тастаңыз»
BUDGET_CUES = ("бюджет", "денег", "деньг", "лимит", "больше", "шег", "аспа", "у.е")

NUM_RU = {"один": 1, "одн": 1, "два": 2, "двух": 2, "три": 3, "трех": 3, "четыр": 4, "пят": 5, "шест": 6, "сем": 7,
          "восем": 8, "восьм": 8, "девят": 9, "десят": 10, "двадцат": 20, "тридцат": 30, "сорок": 40,
          "пятьдесят": 50, "пятидесят": 50, "шестьдесят": 60, "шестидесят": 60, "семьдесят": 70, "семидесят": 70,
          "восемьдесят": 80, "восьмидесят": 80, "девяност": 90, "сто": 100}
NUM_KK = {"бир": 1, "еки": 2, "уш": 3, "торт": 4, "бес": 5, "алты": 6, "жети": 7, "сегиз": 8, "тогыз": 9, "он": 10,
          "жиырма": 20, "отыз": 30, "кырык": 40, "елу": 50, "алпыс": 60, "жетпис": 70, "сексен": 80, "токсан": 90, "жуз": 100}
KK_CASE = ("", "тен", "тан", "нен", "нан", "ден", "дан", "ке", "ге", "ка", "га", "та", "те", "да", "де")


def norm(s):
    return s.lower().translate(KK2RU)


def tokenize(text):
    """[(norm_token, original_token, clause_index)] — клаузы делятся запятой/«и»/«және»/«а также»."""
    toks, clause = [], 0
    for m in re.finditer(r"[^\W\d_]+(?:-[^\W\d_]+)*|\d+|[,;:]", text, flags=re.UNICODE):
        t = m.group(0)
        if t in ",;:":
            clause += 1
            continue
        n = norm(t)
        if n in ("и", "жане"):
            clause += 1
            continue
        toks.append((n, t, clause))
    return toks


def _ru_number(tokens):
    vals = []
    for n in tokens:
        for stem in sorted(NUM_RU, key=len, reverse=True):
            if n.startswith(stem):
                vals.append(NUM_RU[stem]); break
    return sum(vals) if vals else None


def _kk_number(tokens):
    vals = []
    for n in tokens:
        for w in sorted(NUM_KK, key=len, reverse=True):
            if n.startswith(w) and n[len(w):] in KK_CASE:
                vals.append(NUM_KK[w]); break
    return sum(vals) if vals else None


class B2:
    name = "B2_normalized_alias_parser"

    def __init__(self):
        gz = json.loads((K / "dataset/gazetteer.json").read_text(encoding="utf-8"))
        cat = json.loads((K / "dataset/measure_catalog.json").read_text(encoding="utf-8"))
        self.scope = {m["id"]: m["scope"] for m in cat["measures"]}
        self.district = {}          # entity_id -> info
        self.stems = []             # (stem, entity_id)
        for e in gz["districts"]:
            self.district[e["entity_id"]] = e
            for name in e["names"]["ru"] + e["names"]["kk"]:
                core = " ".join(w for w in norm(name).split() if w not in GENERIC)
                for stem in self._stems(core):
                    self.stems.append((stem, e["entity_id"]))
        self.stems.sort(key=lambda x: -len(x[0]))

    @staticmethod
    def _stems(core):
        out = {core}
        if core.endswith("ский"):
            out.add(core[:-4])
        if len(core) >= 4 and core[-1] in "аеиоуыья":
            out.add(core[:-1])
            if core[-2] in "аеиоуыья":
                out.add(core[:-2])
        return {s for s in out if len(s) >= 3}

    def _match_district(self, n):
        for stem, eid in self.stems:
            if n.startswith(stem) and len(n) - len(stem) <= 7:
                return eid
        return None

    def _measures(self, toks):
        """[(measure_id, token_index)] в порядке первого упоминания."""
        norm_toks = [t[0] for t in toks]
        found = []                                   # (measure, start, length)
        for i, n in enumerate(norm_toks):
            parts = [p for p in n.split("-") if p]
            for mid, aliases in MEASURE_ALIASES.items():
                for al in aliases:
                    if isinstance(al, tuple):
                        if i + len(al) <= len(norm_toks) and all(norm_toks[i + k].startswith(al[k]) for k in range(len(al))):
                            found.append((mid, i, len(al)))
                    elif n.startswith(al) or any(p.startswith(al) for p in parts):
                        found.append((mid, i, 1))
        drop = set()
        for spec, gen in SUPPRESS:                   # специфичный многословный алиас подавляет общий
            spans = [(i, ln) for m, i, ln in found if m == spec]
            for k, (m, i, ln) in enumerate(found):
                if m == gen and any(a <= i < a + l for a, l in spans):
                    drop.add(k)
        out, seen = [], set()
        for k, (m, i, ln) in enumerate(found):
            if k not in drop and m not in seen:
                seen.add(m); out.append((m, i))
        return out

    def _negated(self, toks, idx):
        clause = toks[idx][2]
        n, _, _ = toks[idx]
        if n.endswith(KK_NEG_SUFFIX) or any(p.endswith(KK_NEG_SUFFIX) or p in ("сыз", "сиз") for p in n.split("-")[1:]):
            return True
        same = [t for t in toks if t[2] == clause]
        before = [t[0] for t in toks[:idx] if t[2] == clause]
        if any(t in RU_NEG_TOKENS for t in before):
            return True
        after = [t[0] for t in toks[idx + 1:] if t[2] == clause]
        if any(t in KK_NEG_TOKENS or KK_NEG_VERB.search(t) for t in after):
            return True
        clause_norm = [t[0] for t in same]
        if any(clause_norm[k].startswith(KK_REMOVE[0]) and k + 1 < len(clause_norm) and clause_norm[k + 1].startswith(KK_REMOVE[1])
               for k in range(len(clause_norm))):
            return True
        return False

    def predict(self, text, context_city):
        toks = tokenize(text)
        norm_toks = [t[0] for t in toks]
        # --- город (R1): текст > контекст > вывод по району
        text_cities = {c for n in norm_toks for stem, c in CITY_STEMS.items() if n.startswith(stem)}
        # --- районы и маркеры
        marker_idx = [i for i, n in enumerate(norm_toks) if n.startswith(DISTRICT_MARKER)]
        mentions = []        # (entity_id, token_index)
        for i, n in enumerate(norm_toks):
            if n.startswith(DISTRICT_MARKER):
                continue
            eid = self._match_district(n)
            if eid:
                mentions.append((eid, i))
        unknown = False
        for mi in marker_idx:
            near = [j for j in (mi - 1, mi + 1) if 0 <= j < len(toks)]
            if any(self._match_district(norm_toks[j]) for j in near):
                continue
            cand = [j for j in near if norm_toks[j] not in STOP_NEAR_MARKER and toks[j][1][:1].isupper()]
            if cand:
                unknown = True
        measures = self._measures(toks)
        # --- бюджет
        digits = [int(n) for n in norm_toks if n.isdigit()]
        budget = digits[0] if digits else None
        if budget is None:                           # числительные словами — только в клаузе с признаком бюджета
            measure_idx = {i for _, i in measures}
            cue_clauses = {c for n, _, c in toks if n.startswith(BUDGET_CUES)}
            words = [n for k, (n, _, c) in enumerate(toks) if c in cue_clauses and k not in measure_idx]
            budget = _ru_number(words) or _kk_number(words)
        if len(text_cities) == 1:
            city = next(iter(text_cities))
        elif context_city:
            city = context_city
        else:
            cities = {self.district[e]["city"] for e, _ in mentions}
            city = next(iter(cities)) if len(cities) == 1 else None
        has_constraint = bool(measures) or budget is not None
        # --- статус (R7)
        if city is None and (has_constraint or mentions or unknown):
            return {"status": "clarify", "reason": "city_unspecified", "city": None, "constraints": None}
        for eid, i in mentions:
            if eid in AMBIGUOUS_WITHOUT_MARKER and not any(abs(i - m) == 1 for m in marker_idx):
                return {"status": "clarify", "reason": "ambiguous_toponym", "city": city, "constraints": None}
        for eid, _ in mentions:
            if self.district[eid]["level"] == "district_unconfirmed":
                return {"status": "clarify", "reason": "unconfirmed_district", "city": city, "constraints": None}
            if self.district[eid]["city"] != city:
                return {"status": "clarify", "reason": "district_not_in_city", "city": city, "constraints": None}
        if unknown:
            return {"status": "clarify", "reason": "unknown_district", "city": city, "constraints": None}
        for eid, _ in mentions:
            if city == "astana" and not self.district[eid]["modeled_in_training_model"]:
                return {"status": "refuse", "reason": "district_not_modeled", "city": city, "constraints": None}
        # --- ограничения
        dists = []
        for eid, _ in mentions:
            d = eid.split(".", 1)[1]
            if d not in dists:
                dists.append(d)
        cons = {}
        exclude = [m for m, i in measures if self._negated(toks, i)]
        include_ids = [m for m, i in measures if m not in exclude]
        inc = []
        for m in include_ids:
            if self.scope[m] == "district" and dists:
                inc += [{"measure": m, "district": d} for d in dists]
            else:
                inc.append(m)
        if exclude: cons["exclude"] = exclude
        if inc: cons["include"] = inc
        if budget is not None: cons["budget"] = budget
        return {"status": "ok", "reason": None, "city": city, "constraints": cons}
