"""Загрузка исходных записей среза из data.js по закреплённому SHA прототипа (байты из Git, sha256 фиксируется)."""
import hashlib, json, subprocess

BASE_SHA = "a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d"      # claude/beautiful-clarke-sbzomj, round-8 base
DATA_PATH = "prototypes/city-evidence/web/data.js"
EXPECTED_DATA_SHA256 = "bb2a7e6673ff4f9e46ef40df2db7830521603fd0a548ae6a581608a27e9d7d72"


def load_slice(repo=None, sha=BASE_SHA):
    raw = subprocess.run(["git", "show", f"{sha}:{DATA_PATH}"], cwd=repo, capture_output=True, check=True).stdout
    digest = hashlib.sha256(raw).hexdigest()
    s = raw.decode("utf-8")
    i = s.index("{")
    j = s.rstrip().rstrip(";").rstrip()
    return json.loads(s[i:len(j)]), digest


def sources(data, city, category):
    """Исходные записи категории (поле group) внутри bbox; QA-записи не удаляются."""
    w, s, e, n = data["cities"][city]["bbox"]
    return sorted(({"id": p["id"], "lon": p["lon"], "lat": p["lat"]} for p in data["cities"][city]["places"]
                   if p.get("group") == category and w <= p["lon"] <= e and s <= p["lat"] <= n), key=lambda r: r["id"])


def bbox(data, city):
    return data["cities"][city]["bbox"]
