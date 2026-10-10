"""R11 · инструменты переводов Birge (только стандартная библиотека).

Команды (из корня репозитория):
  python3 tests/civic/R11/i18n_tools.py check            # проверка словарей; код выхода 1 при ошибках
  python3 tests/civic/R11/i18n_tools.py sync             # категории из research/round-14/categories_v2.json → ru/kk + копия в ui-kit
  python3 tests/civic/R11/i18n_tools.py add FILE.json    # добавить ключи, присланные ролью (см. формат ниже)
  python3 tests/civic/R11/i18n_tools.py review           # пересобрать research/round-14-results/R11/KK_REVIEW.md

Формат файла для add (роль кладёт его в свой INTEGRATION.txt, R11 сохраняет в JSON):
  {"heat.card.title": {"ru": "Остановка", "kk": "Аялдама", "where": "R07 · карточка цели", "note": "…"},
   "heat.card.other": "Только русский текст — kk переведёт R11"}
Уже существующие ключи не перезаписываются (печатается предупреждение, если текст ru отличается).
Ключ без kk получает пустую строку — check падает, пока перевода нет: так ничего не теряется.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
I18N = ROOT / "web/civic/i18n"
CATS_SRC = ROOT / "research/round-14/categories_v2.json"
CATS_WEB = ROOT / "web/civic/ui-kit/categories_v2.json"
NOTES = ROOT / "research/round-14-results/R11/kk_notes.json"  # ⚑ — настоящие сомнения в переводе
SOURCES = ROOT / "research/round-14-results/R11/key_sources.json"  # кто прислал ключ и где он на экране
REVIEW = ROOT / "research/round-14-results/R11/KK_REVIEW.md"

LANGS = ("ru", "kk")
RU_FORMS = {"one", "few", "many"}
KEY_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
PARAM_RE = re.compile(r"\{(\w+)\}")
# UX_BRIEF, правило 4: этих слов не должно быть в интерфейсе.
# Шаблоны регулярных выражений по нижнему регистру; «граф» не путаем с «графиком».
FORBIDDEN = (r"\bребр", r"\bрёбр", r"\bграф(?!ик)", r"геометри", r"сценари", r"payload", r"demo-ring", r"\bundefined\b",
             r"\bnull\b", r"\bnan\b")


def load(lang):
    return json.loads((I18N / f"{lang}.json").read_text("utf-8"))


def save(lang, data):
    (I18N / f"{lang}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")


def load_notes():
    return json.loads(NOTES.read_text("utf-8")) if NOTES.exists() else {}


def texts(value):
    """Все строки значения: сама строка или формы числа."""
    return list(value.values()) if isinstance(value, dict) else [value]


def params(value):
    return set().union(*(set(PARAM_RE.findall(t)) for t in texts(value)))


def check(ru=None, kk=None):
    """Список проблем словарей (пустой — всё в порядке)."""
    ru = load("ru") if ru is None else ru
    kk = load("kk") if kk is None else kk
    problems = []
    for key in sorted(set(ru) - set(kk)):
        problems.append(f"нет в kk: {key}")
    for key in sorted(set(kk) - set(ru)):
        problems.append(f"нет в ru: {key}")
    for lang, d in (("ru", ru), ("kk", kk)):
        for key, value in d.items():
            if not KEY_RE.match(key):
                problems.append(f"{lang}: неверное имя ключа {key!r} (нужно модуль.экран.что, латиница)")
            if isinstance(value, dict):
                if lang == "ru" and set(value) != RU_FORMS:
                    problems.append(f"ru: {key} — формы числа должны быть one/few/many, есть {sorted(value)}")
                if not params(value) & {"n", "count"}:
                    problems.append(f"{lang}: {key} — формы числа без {{n}}")
            elif not isinstance(value, str):
                problems.append(f"{lang}: {key} — значение должно быть строкой или формами числа")
                continue
            for t in texts(value):
                if not str(t).strip():
                    problems.append(f"{lang}: пустой перевод {key}")
                low = str(t).lower()
                for pattern in FORBIDDEN:
                    m = re.search(pattern, low)
                    if m:
                        problems.append(f"{lang}: {key} — техническое слово «{m.group(0)}»")
                if "  " in str(t) or str(t) != str(t).strip():
                    problems.append(f"{lang}: {key} — лишние пробелы")
                if "!" in str(t):
                    problems.append(f"{lang}: {key} — восклицательный знак (UX_BRIEF: без них)")
    for key in sorted(set(ru) & set(kk)):
        if params(ru[key]) != params(kk[key]):
            problems.append(f"{key}: параметры ru {sorted(params(ru[key]))} ≠ kk {sorted(params(kk[key]))}")
    # Категории: ключи cat.<id> совпадают с categories_v2.json, тексты — тоже.
    cats = json.loads(CATS_SRC.read_text("utf-8"))["categories"]
    ids = {c["id"] for c in cats}
    for key in ru:
        if key.startswith("cat.") and key.split(".")[1] not in ids:
            problems.append(f"{key}: нет такой категории в categories_v2.json")
    for c in cats:
        for lang in LANGS:
            d = ru if lang == "ru" else kk
            if d.get("cat." + c["id"]) != c[lang]:
                problems.append(f"cat.{c['id']} ({lang}) расходится с categories_v2.json — запустите sync")
            if "cat." + c["id"] + ".examples" not in d:
                problems.append(f"нет cat.{c['id']}.examples ({lang})")
    if CATS_WEB.read_bytes() != CATS_SRC.read_bytes():
        problems.append("web/civic/ui-kit/categories_v2.json устарел — запустите sync")
    return problems


def sync():
    """Категории из источника истины → словари и копия для браузера."""
    cats = json.loads(CATS_SRC.read_text("utf-8"))["categories"]
    ru, kk = load("ru"), load("kk")
    for c in cats:
        ru["cat." + c["id"]] = c["ru"]
        kk["cat." + c["id"]] = c["kk"]
        ru["cat." + c["id"] + ".examples"] = c["examples_ru"]
        kk.setdefault("cat." + c["id"] + ".examples", "")  # переводит R11; пусто → check напомнит
    save("ru", ru)
    save("kk", kk)
    shutil.copyfile(CATS_SRC, CATS_WEB)
    print(f"категорий: {len(cats)}; ключей ru: {len(ru)}")


def insert_grouped(existing, new_items):
    """Новые ключи встают в конец своей группы (первая часть ключа); порядок старых не меняется."""
    by_group = {}
    for key, value in new_items:
        by_group.setdefault(key.split(".")[0], []).append((key, value))
    last_of_group = {k.split(".")[0]: k for k in existing}
    out = {}
    for key, value in existing.items():
        out[key] = value
        g = key.split(".")[0]
        if last_of_group[g] == key:
            out.update(by_group.pop(g, []))
    for items in by_group.values():  # совсем новые группы — в конец
        out.update(items)
    return out


def add(path):
    incoming = json.loads(Path(path).read_text("utf-8"))
    ru, kk, notes = load("ru"), load("kk"), load_notes()
    sources = json.loads(SOURCES.read_text("utf-8")) if SOURCES.exists() else {}
    new_ru, new_kk = [], []
    for key, spec in incoming.items():
        if isinstance(spec, str) or (isinstance(spec, dict) and "ru" not in spec):
            spec = {"ru": spec}  # только русский текст или формы числа без обёртки
        if not KEY_RE.match(key):
            print(f"пропущен ключ с неверным именем: {key}")
            continue
        if key in ru:
            if ru[key] != spec["ru"]:
                print(f"уже есть, текст ru другой (оставлен старый): {key}: {ru[key]!r} ≠ {spec['ru']!r}")
            continue
        new_ru.append((key, spec["ru"]))
        new_kk.append((key, spec.get("kk") or ""))  # пусто → check напомнит перевести
        if spec.get("note"):
            notes[key] = spec["note"]
        if spec.get("where"):
            sources[key] = spec["where"]
    save("ru", insert_grouped(ru, new_ru))
    save("kk", insert_grouped(kk, new_kk))
    NOTES.write_text(json.dumps(notes, ensure_ascii=False, indent=1) + "\n", "utf-8")
    SOURCES.write_text(json.dumps(sources, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"добавлено ключей: {len(new_ru)}")


def fmt(value):
    if isinstance(value, dict):
        return " / ".join(f"{k}: {v}" for k, v in value.items())
    return value


def review():
    ru, kk, notes = load("ru"), load("kk"), load_notes()
    sources = json.loads(SOURCES.read_text("utf-8")) if SOURCES.exists() else {}
    flagged = [k for k in ru if k in notes]
    lines = [
        "# KK_REVIEW — казахский текст Birge для проверки владельцем",
        "",
        "Собрано автоматически из `web/civic/i18n/ru.json`, `kk.json` и пометок `research/round-14-results/R11/kk_notes.json`",
        "(`python3 tests/civic/R11/i18n_tools.py review`). Правки пишите прямо в столбец «қаз» или списком «ключ → как надо» —",
        "R11 вносит их в `kk.json` сразу.",
        "",
        "Условные обозначения: ⚑ — место, где переводчик сомневается или выбрал один из вариантов; {n}, {name} — подставляемые",
        "значения, их не переводить. Формы числа в русском: one (1, 21), few (2–4), many (5–20); в казахском одна форма —",
        "существительное после числа не меняется («12 адам»).",
        "",
        f"Ключей: {len(ru)}. С пометкой ⚑: {len(flagged)}.",
        "",
        "## 1. Сначала проверьте — места с пометкой ⚑",
        "",
        "| ключ | рус | қаз | комментарий |",
        "|---|---|---|---|",
    ]
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    for k in flagged:
        src = f" <sub>{esc(sources[k])}</sub>" if k in sources else ""
        lines.append(f"| `{k}` | {esc(fmt(ru[k]))} | {esc(fmt(kk.get(k, '')))} | ⚑ {esc(notes[k])}{src} |")
    lines += ["", "## 2. Весь словарь по разделам", ""]
    group = None
    titles = {
        "cat": "Категории", "common": "Общее", "dates": "Даты", "district": "Районы", "status": "Статусы обращения",
        "stage": "Этапы объекта", "object": "Объект и сроки", "heat": "Тепловая карта", "target": "Карточка места",
        "akim": "Картина дня", "complaint": "Путь жителя", "mine": "Мои обращения", "proposal": "Предложения и 3D",
        "uikit": "Витрина ui-kit (только для разработчиков)", "proto": "Макеты R11 (только для сверки вида)",
        "shell": "Оболочка (R01)", "editor": "Редактор карты (R12)", "geo": "Точность карты (R12)",
        "build3d": "3D-превью предложений (R05)", "forecast": "Прогноз на месяц — прототип (R13)",
    }
    for k in ru:
        g = k.split(".")[0]
        if g != group:
            group = g
            lines += ["", f"### {titles.get(g, g)}", "", "| ключ | рус | қаз | комментарий |", "|---|---|---|---|"]
        mark = " ".join(x for x in ("⚑ " + esc(notes[k]) if k in notes else "", "<sub>" + esc(sources[k]) + "</sub>" if k in sources else "") if x)
        lines.append(f"| `{k}` | {esc(fmt(ru[k]))} | {esc(fmt(kk.get(k, '')))} | {mark} |")
    extra = REVIEW.parent / "kk_review_extra.md"  # тексты вне словаря (код и данные ролей), ведётся вручную
    if extra.exists():
        lines += ["", extra.read_text("utf-8").rstrip()]
    REVIEW.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"{REVIEW.relative_to(ROOT)}: {len(ru)} ключей, ⚑ {len(flagged)}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "check":
        problems = check()
        for p in problems:
            print("FAIL", p)
        print("PASS" if not problems else f"проблем: {len(problems)}")
        return 1 if problems else 0
    if cmd == "sync":
        sync()
    elif cmd == "add":
        add(argv[2])
    elif cmd == "review":
        review()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
