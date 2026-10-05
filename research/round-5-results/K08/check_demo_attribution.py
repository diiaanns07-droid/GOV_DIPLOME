"""K08 R5: checker атрибуции поставляемого демо prototypes/city-evidence.

Проверяет файлы, уведомления и ссылки в том, что получает пользователь демо, а также
неизменность скопированных upstream-входов. Это техническая проверка наличия
текстов и указаний, а не юридическое заключение.

Режимы:
  --app-root DIR   извлечённая копия prototypes/city-evidence (читаются web/, inputs/, source_manifest.json)
  --url BASE       работающее демо (например, http://127.0.0.1:8765/); читается только то, что отдаёт сервер
  --repo DIR       (необязательно, с --app-root) git-репозиторий с нужными объектами: сверить каждую запись
                   source_manifest.json с `git show <sha>:<path>` и найти изменённые файлы
  --json FILE      записать отчёт

Код выхода: 0 — все проверки PASS/WARN; 1 — есть FAIL.
Только stdlib. В режиме --url запросы идут только на указанный BASE.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Тексты SPDX license-list-data @31ba1a50e5397e00a304dbadc76531740e89ee48 (пакет K08 раунда 4)
LICENSE_SHA256 = {
    "ODbL-1.0": "77d2692c3d64efdd4db18dce2407699baf62930e2b50d6e5ed90b48acf16b7c1",
    "CDLA-Permissive-2.0": "4531a67d443284d93ffed0803df5b10634aff21c3d77e381f2d48af01d875868",
    "Apache-2.0": "074e6e32c86a4c0ef8b3ed25b721ca23aca83df277cd88106ef7177c354615ff",
    "CC0-1.0": "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499",
}
# Где в поставке искать тексты (относительно корня, который видит пользователь: web/ для --app-root и BASE для --url)
LICENSE_DIRS = ["LICENSES/", "attribution/LICENSES/", "licenses/"]
ATTRIBUTION_FILES = ["ATTRIBUTION.md", "ATTRIBUTION.txt", "ATTRIBUTION.html", "attribution/ATTRIBUTION.md", "attribution.html"]
# Поставщик (dataset в sources) -> что должно встречаться в UI/уведомлении
PROVIDER_PATTERNS = {
    "OpenStreetMap": r"OpenStreetMap",
    "Overture": r"Overture",
    "meta": r"\bMeta\b",
    "Foursquare": r"Foursquare",
    "TomTom": r"TomTom",
    "Microsoft": r"Microsoft",
    "AllThePlaces": r"AllThePlaces|All the Places",
}
OSM_COPYRIGHT_LINK = r"openstreetmap\.org/copyright"
UI_FILES = ["index.html", "app.js"]


class Source:
    """Единый доступ к поставке: файл в web/ (app-root) или по HTTP (url)."""

    def __init__(self, app_root=None, url=None):
        self.app_root = Path(app_root) if app_root else None
        self.url = url.rstrip("/") + "/" if url else None

    def label(self):
        return f"--app-root {self.app_root}" if self.app_root else f"--url {self.url}"

    def get(self, rel):
        if self.app_root:
            p = self.app_root / "web" / rel
            return p.read_bytes() if p.is_file() else None
        try:
            with urllib.request.urlopen(self.url + rel, timeout=20) as r:
                return r.read() if r.status == 200 else None
        except (urllib.error.HTTPError, urllib.error.URLError):
            return None


def load_data(src):
    raw = src.get("data.js")
    if raw is None:
        return None
    txt = raw.decode("utf-8")
    m = re.search(r"window\.CITY_EVIDENCE\s*=\s*(\{.*\})\s*;?\s*$", txt, re.S)
    return json.loads(m.group(1)) if m else None


def providers_and_licenses(data):
    """Поставщики и лицензии, которые реально присутствуют в данных демо (по полям записей data.js)."""
    prov, lic, seg_no_dataset = set(), set(), 0
    for c in data["cities"].values():
        for p in c.get("places", []):
            for s in p.get("sources", []):
                prov.add(s.get("dataset"))
                lic.add(s.get("license"))
        for g in c.get("segments", []):
            if g.get("license"):
                lic.add(g["license"])
            if "dataset" in g:
                prov.add(g["dataset"])
            else:
                seg_no_dataset += 1
    prov.discard(None)
    lic.discard(None)
    return prov, lic, seg_no_dataset


def check(src, inputs_root=None, repo=None):
    res = []

    def add(cid, status, text, **kw):
        res.append({"id": cid, "status": status, "text": text, **kw})

    data = load_data(src)
    if data is None:
        add("A0", "FAIL", "web/data.js не найден или не разобран")
        return res
    prov, lic, seg_no_dataset = providers_and_licenses(data)
    # Поставщики, которые встречаются только в исходных GeoJSON (у сегментов data.js нет dataset)
    hidden = set()
    if inputs_root:
        for f in sorted((inputs_root / "inputs" / "k10" / "data").glob("*/*.geojson")):
            for ft in json.loads(f.read_bytes())["features"]:
                for s in ft["properties"].get("sources") or []:
                    if not s.get("property"):
                        hidden.add(s.get("dataset"))
        hidden -= prov
        hidden.discard(None)
    add("A1", "INFO", "Поставщики и лицензии в данных демо", providers=sorted(prov), licenses=sorted(lic),
        providers_only_in_inputs=sorted(hidden))

    # A2: тексты лицензий для каждой лицензии в данных
    for l in sorted(lic):
        found = None
        for d in LICENSE_DIRS:
            b = src.get(f"{d}{l}.txt")
            if b is not None:
                found = (d + f"{l}.txt", hashlib.sha256(b).hexdigest())
                break
        if not found:
            add("A2", "FAIL", f"Текст лицензии {l} не поставляется рядом с демо", license=l, searched=[d + f"{l}.txt" for d in LICENSE_DIRS])
        elif l in LICENSE_SHA256 and found[1] != LICENSE_SHA256[l]:
            add("A2", "FAIL", f"Текст {l} найден ({found[0]}), но sha256 не совпадает с SPDX @31ba1a50", license=l, path=found[0], sha256=found[1])
        else:
            add("A2", "PASS", f"Текст {l} поставляется: {found[0]}", license=l, path=found[0], sha256=found[1])

    # A3: файл атрибуции в поставке
    att = next(((p, src.get(p)) for p in ATTRIBUTION_FILES if src.get(p) is not None), None)
    add("A3", "PASS" if att else "FAIL",
        f"Файл атрибуции поставляется: {att[0]}" if att else "Отдельный файл атрибуции в поставке отсутствует",
        searched=ATTRIBUTION_FILES)

    # A4: поставщики названы в общем уведомлении: статический текст UI (index.html + app.js) или файл атрибуции.
    # Отдельно отмечается, что карточка места выводит src.dataset из данных (видно только при открытии карточки).
    ui = b"".join(src.get(f) or b"" for f in UI_FILES).decode("utf-8", "replace")
    att_txt = att[1].decode("utf-8", "replace") if att else ""
    card_shows_dataset = "src.dataset" in ui
    place_prov = {s.get("dataset") for c in data["cities"].values() for p in c.get("places", []) for s in p.get("sources", [])}
    for p in sorted(prov | hidden):
        pat = PROVIDER_PATTERNS.get(p, re.escape(p))
        in_ui, in_att = bool(re.search(pat, ui)), bool(re.search(pat, att_txt))
        status = "PASS" if (in_ui or in_att) else ("FAIL" if p in prov else "WARN")
        note = ""
        if p in place_prov and card_shows_dataset and not (in_ui or in_att):
            note = "; в карточке места поставщик выводится из данных, но в общем уведомлении не назван"
        if p not in prov:
            note += " (есть во входах, но у записей data.js поставщик не сохранён)"
        add("A4", status, f"Поставщик {p} в общем уведомлении: UI={in_ui}, файл атрибуции={in_att}{note}", provider=p)

    # A5: ссылка на условия OSM
    link = re.search(OSM_COPYRIGHT_LINK, ui + att_txt)
    add("A5", "PASS" if link else "WARN",
        "Ссылка на openstreetmap.org/copyright есть" if link else
        "Ссылки на openstreetmap.org/copyright нет (сама страница из этой среды не проверялась; формулировка — по практике OSM)")

    # A6: у сегментов в данных демо есть поставщик, иначе UI не может отличить TomTom от OSM
    total_seg = sum(len(c.get("segments", [])) for c in data["cities"].values())
    add("A6", "FAIL" if seg_no_dataset and hidden else ("WARN" if seg_no_dataset else "PASS"),
        f"Сегментов без поля dataset в data.js: {seg_no_dataset} из {total_seg}"
        + (f"; во входах есть поставщики, не видимые в демо: {sorted(hidden)}" if hidden else ""))

    # A7: подпись карточки дороги не утверждает OSM для всех сегментов, если есть не-OSM поставщики
    hard_osm = re.search(r"Дорога \(OSM через Overture\)", ui)
    add("A7", "FAIL" if (hard_osm and hidden) else ("WARN" if hard_osm else "PASS"),
        "Карточка дороги всегда подписана «OSM через Overture»" if hard_osm else "Жёсткой подписи OSM у карточки дороги нет")

    # A8: неизменность upstream-входов
    if inputs_root:
        man = json.loads((inputs_root / "source_manifest.json").read_text(encoding="utf-8"))
        bad_local, modified, checked = [], [], 0
        for e in man["files"]:
            p = inputs_root / e["copied_to"]
            h = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            if h != e["sha256"]:
                bad_local.append({"copied_to": e["copied_to"], "manifest": e["sha256"], "actual": h})
            if repo:
                try:
                    up = subprocess.check_output(["git", "show", f"{e['sha']}:{e['path']}"], cwd=repo, stderr=subprocess.DEVNULL)
                    uh = hashlib.sha256(up).hexdigest()
                    checked += 1
                    if uh != h:
                        modified.append({"copied_to": e["copied_to"], "upstream": f"{e['sha']}:{e['path']}",
                                         "upstream_sha256": uh, "delivered_sha256": h})
                except subprocess.CalledProcessError:
                    modified.append({"copied_to": e["copied_to"], "upstream": f"{e['sha']}:{e['path']}", "error": "объект не найден в --repo"})
        add("A8", "FAIL" if bad_local else "PASS",
            f"Файлы inputs/ совпадают с source_manifest.json: {len(man['files']) - len(bad_local)}/{len(man['files'])}", mismatches=bad_local)
        if repo:
            add("A9", "FAIL" if modified else "PASS",
                f"Сверка с upstream git-объектами: проверено {checked}, отличаются {len(modified)}", modified=modified)
        flagged = [e for e in man["files"] if e.get("modified") or e.get("modified_sha256")]
        add("A10", "INFO", f"Записей manifest с явной пометкой modified: {len(flagged)} "
            "(поле в схеме manifest отсутствует; изменённые файлы надо помечать отдельным hash)")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app-root")
    g.add_argument("--url")
    ap.add_argument("--repo")
    ap.add_argument("--json")
    a = ap.parse_args()
    src = Source(a.app_root, a.url)
    res = check(src, Path(a.app_root) if a.app_root else None, a.repo)
    rep = {"checker": "K08 R5 check_demo_attribution", "target": src.label(),
           "disclaimer": "Проверка наличия текстов, уведомлений и ссылок; не юридическое заключение. "
                         "sources.license — поле записи, а не полная проверка условий поставщика.",
           "results": res,
           "summary": {s: sum(1 for r in res if r["status"] == s) for s in ("PASS", "WARN", "FAIL", "INFO")}}
    out = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.json:
        Path(a.json).write_text(out + "\n", encoding="utf-8")
    for r in res:
        print(f"[{r['status']}] {r['id']} {r['text']}")
    print(json.dumps(rep["summary"]))
    sys.exit(1 if rep["summary"]["FAIL"] else 0)


if __name__ == "__main__":
    main()
