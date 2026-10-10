"""R08: GET /api/civic/v2/akim/summary — коды ответа, параметры, приватность."""
import json

from r08_helpers import NOW, rec
from ui.civic_akim import AkimService
from ui.civic_akim.api import PREFIX, handle_get

PATH = PREFIX + "/akim/summary"


class FixedNow(AkimService):
    """Сервис с «сейчас» = NOW (handle_get не передаёт now)."""

    def summary(self, date=None, district=None, now=None):
        return super().summary(date=date, district=district, now=NOW)


def service(records):
    return FixedNow(heat=False, records=lambda since: records, objects=None, proposals=None, clock=lambda: NOW)


def test_ok_with_parse_qs_style_query():
    status, body = handle_get(PATH, {"date": ["2026-10-12"], "district": ["nura"]}, service=service([rec(1, age_days=0.1)]))
    assert status == 200 and body["date"] == "2026-10-12" and body["district"]["id"] == "nura"
    assert body["kpi"]["new_day"]["value"] == 1
    json.dumps(body, ensure_ascii=False)  # ответ сериализуется в JSON


def test_defaults_today_and_whole_city():
    status, body = handle_get(PATH, {}, service=service([]))
    assert status == 200 and body["date"] == "2026-10-12" and body["district"] is None and body["empty"] is True


def test_bad_requests():
    svc = service([])
    for query, field in (({"date": "12.10.2026"}, "date"), ({"date": "2026-10-20"}, "date"), ({"district": "x"}, "district")):
        status, body = handle_get(PATH, query, service=svc)
        assert status == 400 and body["error"] == "bad_request" and body["field"] == field and body["message"]


def test_unknown_path_and_failure():
    assert handle_get(PREFIX + "/akim/other", {}, service=service([]))[0] == 404

    class Broken:
        def summary(self, **kw):
            raise RuntimeError("сломалось внутри")
    status, body = handle_get(PATH, {}, service=Broken())
    assert status == 500 and body["error"] == "akim_failed" and "сломалось" not in body["message"]


def test_no_resident_texts_in_answer():
    records = [rec(i, age_days=0.1 * i) for i in range(1, 6)]
    status, body = handle_get(PATH, {}, service=service(records))
    dump = json.dumps(body, ensure_ascii=False)
    assert status == 200 and "секретный текст" not in dump and "device" not in dump


def test_district_is_case_and_space_insensitive():
    svc = service([rec(1, age_days=0.1)])
    for value in ("Nura", " nura ", "NURA"):
        status, body = handle_get(PATH, {"district": value}, service=svc)
        assert status == 200 and body["district"]["id"] == "nura", value
    assert handle_get(PATH, {"district": "ALL"}, service=svc)[1]["district"] is None
