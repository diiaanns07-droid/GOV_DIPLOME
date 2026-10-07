"""Снимки настоящих ответов civic_store для R04 (кабинет редактора).

Запуск из корня репозитория: python3 research/round-13-results/R02/tools/make_r04_fixtures.py OUT_DIR
Временная база во временном каталоге (удаляется), фиксированные часы, случайный пароль;
содержимое — тестовое (example.org), не реальные городские работы. В файлы попадают только тела
ответов API; cookie, CSRF-токен и пароль не сохраняются.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from ui.civic_store.importer import import_package  # noqa: E402
from ui.civic_store.service import CivicService  # noqa: E402


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        self.now += timedelta(seconds=30)
        return self.now


def ctx(cookie=None, csrf=None):
    headers = {"Host": "127.0.0.1:8611"}
    if cookie:
        headers["Cookie"] = f"civic_session={cookie}"
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "client_ip": "127.0.0.1", "host_allowed": True, "is_same_origin": True,
            "is_https": False}


def item(title="ТЕСТ: ремонт участка (не реальная работа)", end="2026-10-20", **extra):
    data = {"id": "r02-fixture-1", "kind": "roadworks", "title": title,
            "description": "Тестовая запись для R04; фактов не содержит.", "status": "planned",
            "geometry": {"type": "Point", "coordinates": [71.43, 51.17]}, "geometry_precision": "approximate",
            "schedule": {"planned_start": "2026-10-14", "original_planned_end": None,
                         "current_planned_end": end, "actual_end": None},
            "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
            "responsible": {"organization": None, "public_contact": None},
            "evidence_type": "hypothesis",
            "source_refs": [{"id": "src-1", "url": "https://example.org/fixture/1", "publisher": "ТЕСТ",
                             "published_on": "2026-10-01", "retrieved_at": "2026-10-07T10:00:00Z",
                             "access_status": "not_fetched", "license": None,
                             "fields": ["title", "schedule.current_planned_end"]}],
            "evidence_notes": "Тестовая запись."}
    data.update(extra)
    return data


def pkg(version, **kw):
    return {"schema_version": "civic-v1", "city": "astana",
            "slice": {"name": "r02-r04-fixture", "version": version, "demo": False, "source": "r02-r04-fixture"},
            "items": [item(**kw)]}


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    saved = {}

    def save(name, result, note):
        saved[name] = note
        body = {"_fixture": note, "status": result["status"], "body": result["body"]}
        (out / f"{name}.json").write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        svc = CivicService(Path(tmp) / "fixture.sqlite3", clock=Clock())
        password = secrets.token_urlsafe(18) + "-Aa1"
        svc.accounts.create_user("editor1", password, display_name="Тестовый редактор")
        svc.accounts.create_user("editor2", password + "x", display_name="Второй редактор")

        def login(user, pw):
            r = svc.handle("POST", "/api/civic/v1/session/login", None,
                           json.dumps({"username": user, "password": pw}).encode(), ctx())
            cookie = r["headers"]["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]
            return cookie, r["body"]["data"]["csrf_token"]

        def call(method, path, body=None, who=None):
            raw = json.dumps(body).encode() if body is not None else None
            return svc.handle(method, "/api/civic/v1" + path, None, raw, ctx(*who) if who else ctx())

        e1, e2 = login("editor1", password), login("editor2", password + "x")
        save("meta", call("GET", "/staff/meta", who=e1), "GET /staff/meta (редактор)")
        save("error_401_unauthenticated", call("GET", "/staff/meta"), "GET /staff/meta без входа")
        import_package(svc.objects, pkg("v1"))
        obj = call("GET", "/staff/objects/r02-fixture-1", who=e1)["body"]["data"]["item"]
        pub = call("POST", "/staff/objects/r02-fixture-1/publish",
                   {"expected_revision": obj["revision"], "reason": "Первая публикация"}, who=e1)
        rev = pub["body"]["data"]["item"]["revision"]
        call("POST", "/staff/objects/r02-fixture-1/update",
             {"expected_revision": rev, "reason": "Уточнение редактора",
              "changes": {"title": "ТЕСТ: ремонт участка, название уточнено редактором"}}, who=e1)
        report = import_package(svc.objects, pkg("v2", title="ТЕСТ: новое название из источника", end="2026-11-30"))
        (out / "import_report_editor_review.json").write_text(
            json.dumps({"_fixture": "import_package(...) отчёт: опубликованная запись, источник изменился",
                        "report": report}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        save("staff_object_with_pending_candidate", call("GET", "/staff/objects/r02-fixture-1", who=e1),
             "GET /staff/objects/{id}: staff.pending_import_candidates=1")
        listing = call("GET", "/staff/objects/r02-fixture-1/import-candidates", who=e1)
        save("candidates_review", listing, "GET /staff/objects/{id}/import-candidates: review по полям, конфликт title")
        cand = listing["body"]["data"]["items"][0]
        rev = cand["object_revision"]
        save("error_422_unknown_field", call("POST", f"/staff/objects/r02-fixture-1/import-candidates/{cand['id']}/apply",
                                             {"expected_revision": rev, "reason": "x", "fields": ["budget.amount_kzt"]},
                                             who=e1), "apply с полем, которого нет среди изменений")
        save("error_409_stale_revision", call("POST", f"/staff/objects/r02-fixture-1/import-candidates/{cand['id']}/apply",
                                              {"expected_revision": rev - 1, "reason": "x"}, who=e2),
             "apply со старой ревизией (второй редактор)")
        save("apply_partial", call("POST", f"/staff/objects/r02-fixture-1/import-candidates/{cand['id']}/apply",
                                   {"expected_revision": rev, "reason": "Срок по источнику, название оставлено",
                                    "fields": ["schedule.current_planned_end"]}, who=e1),
             "частичное принятие: только срок; ответ — staff item")
        save("candidates_decided", call("GET", "/staff/objects/r02-fixture-1/import-candidates", who=e1),
             "после решения: resolution=partially_applied, decision{...}")
        import_package(svc.objects, pkg("v3", end="2026-12-15"))
        old = call("GET", "/staff/objects/r02-fixture-1/import-candidates", who=e1)["body"]["data"]["items"][0]
        import_package(svc.objects, pkg("v4", end="2026-12-20"))
        cur = call("GET", "/staff/objects/r02-fixture-1", who=e1)["body"]["data"]["item"]["revision"]
        save("error_409_superseded", call("POST", f"/staff/objects/r02-fixture-1/import-candidates/{old['id']}/apply",
                                          {"expected_revision": cur, "reason": "x"}, who=e1),
             "форма открыта на версии v3, источник уже дал v4")
        save("error_422_validation", call("POST", "/staff/objects/r02-fixture-1/update",
                                          {"expected_revision": cur, "reason": "x",
                                           "changes": {"status": "done", "geometry": {"type": "Point",
                                                                                      "coordinates": [10, 10]}}},
                                          who=e1), "update с недопустимыми status и geometry")
        staff = call("GET", "/staff/objects/r02-fixture-1", who=e1)["body"]["data"]["item"]
        call("POST", "/staff/objects/r02-fixture-1/publish",
             {"expected_revision": staff["revision"], "reason": "Срок перенесён на 30 ноября по данным источника"}, who=e1)
        save("public_object_after_move", call("GET", "/objects/r02-fixture-1"),
             "GET /objects/{id}: публичная история с причиной публикации, без служебной причины")
    (out / "INDEX.json").write_text(json.dumps(saved, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fixtures-r04")
