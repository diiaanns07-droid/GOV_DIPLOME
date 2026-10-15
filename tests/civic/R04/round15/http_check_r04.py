"""HTTP-проверка маршрутов R04 на стенде: шлюз R01 с маршрутами route / reply-draft / moderate.

Не pytest (нужен запущенный сервер). Запуск — research/round-15-results/R04/RUN.txt:
    python3 -B tests/civic/R04/round15/http_check_r04.py      # стенд на 127.0.0.1:8655, редактор operator
Пароль редактора — R04_STAND_PASSWORD (по умолчанию parol-r04-test, как в RUN.txt), адрес — R04_STAND. Без сети.
"""
import http.cookiejar, json, os, sys, time, urllib.request, urllib.error

BASE = os.environ.get("R04_STAND", "http://127.0.0.1:8655")
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
results = []


def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Origin", BASE)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    t0 = time.perf_counter()
    try:
        with opener.open(req, timeout=20) as resp:
            out = resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        out = exc.code, json.loads(exc.read() or b"{}")
    return out[0], out[1], round((time.perf_counter() - t0) * 1000, 1)


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))


st, body, ms = call("GET", "/api/civic/v2/modules")
mods = body.get("modules", {})
# Ключи маршрутов: patch R04 (route, reply_draft, moderate) или как назвал R01 (ml.route, ml.reply_draft, ml.text_check).
KEYS = (("route", "ml.route"), ("reply_draft", "ml.reply_draft"), ("moderate", "ml.text_check"))
check("modules: route/reply_draft/moderate ready",
      all(any(mods.get(k, {}).get("status") == "ready" for k in pair) for pair in KEYS),
      {k: mods.get(k) for pair in KEYS for k in pair if k in mods})

st, body, ms = call("POST", "/api/civic/v2/route", {"text": "Яма после раскопок водоканала"})
check("route scene 8 -> 200 water+road", st == 200 and [s["service"] for s in body["services"]] == ["water", "road"]
      and body["summary_ru"] == "Нужны 2 службы: Водоканал и Дорожная служба", (st, body))
print("   route ms", ms, body.get("summary_kk"))
st, body, ms = call("POST", "/api/civic/v2/route", {"category": "nope"})
check("route bad category -> 400", st == 400 and body.get("error") == "bad_request", (st, body))
st, body, ms = call("POST", "/api/civic/v2/route", {})
check("route empty -> 400", st == 400, (st, body))

st, body, ms = call("POST", "/api/civic/v2/moderate", {"text": "Субботник! Звоните 8 701 123 45 67, опять эта блядская яма"})
check("moderate -> 200 masked", st == 200 and body["text_public"] == "Субботник! Звоните ***, опять эта б******* яма"
      and {f["kind"] for f in body["flags"]} == {"phone", "rude"}, (st, body))
st, body, ms = call("POST", "/api/civic/v2/moderate", {"text": 5})
check("moderate bad text -> 400", st == 400, (st, body))

st, body, ms = call("POST", "/api/civic/v2/reply-draft", {"text": "Не горит фонарь"})
check("reply-draft without staff -> 401/403", st in (401, 403), (st, body))

st, body, ms = call("POST", "/api/civic/v1/session/login", {"username": "operator", "password": os.environ.get("R04_STAND_PASSWORD", "parol-r04-test")})
csrf = (body.get("data") or {}).get("csrf_token") or body.get("csrf_token")
check("staff login", st == 200 and csrf, (st, body))
st, body, ms = call("POST", "/api/civic/v2/reply-draft", {"text": "Не горит фонарь"})
check("reply-draft without CSRF -> 403", st == 403, (st, body))
st, body, ms = call("POST", "/api/civic/v2/reply-draft", {"text": "Яма после раскопок водоканала", "status": "new",
                                                           "lang": "kk"}, {"X-CSRF-Token": csrf})
check("reply-draft text -> 200 kk", st == 200 and body["lang"] == "kk" and "екі қызметке" in body["draft_kk"], (st, body))
print("   draft kk:", body.get("draft_kk"))

# Настоящая жалоба R09 демо-засева: черновик по номеру.
st, body, ms = call("GET", "/api/civic/v2/complaints/inbox", None, {"X-CSRF-Token": csrf})
items = (body.get("data") or {}).get("items") or body.get("items") or []
cid = None
def find_ids(o):
    if isinstance(o, dict):
        if isinstance(o.get("id"), str) and o["id"].startswith("c-"):
            yield o["id"]
        for v in o.values():
            yield from find_ids(v)
    elif isinstance(o, list):
        for v in o:
            yield from find_ids(v)
ids = list(dict.fromkeys(find_ids(body)))
check("inbox has R09 complaints", st == 200 and ids, (st, str(body)[:300]))
if ids:
    st, body, ms = call("POST", "/api/civic/v2/reply-draft", {"complaint_id": ids[0]}, {"X-CSRF-Token": csrf})
    check("reply-draft by complaint_id -> 200", st == 200 and body.get("facts", {}).get("code"), (st, body))
    print("   draft ru:", body.get("draft_ru"))
    print("   draft kk:", body.get("draft_kk"), "| ms", ms)
st, body, ms = call("POST", "/api/civic/v2/reply-draft", {"complaint_id": "c-nothere123"}, {"X-CSRF-Token": csrf})
check("reply-draft unknown -> 404", st == 404, (st, body))
st, body, ms = call("POST", "/api/civic/v2/reply-draft", {"complaint_id": "../../x"}, {"X-CSRF-Token": csrf})
check("reply-draft bad id -> 400", st == 400, (st, body))

print("SUMMARY", sum(ok for _, ok in results), "/", len(results))
sys.exit(0 if all(ok for _, ok in results) else 1)
