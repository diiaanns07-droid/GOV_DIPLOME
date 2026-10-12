"""R15: безопасность нового интерфейса дизайн-марафона (research/round-14/DESIGN_MARATHON.md, 12–14 окт).

Марафон меняет только вид, движение и тексты; тесты держат то, что вид сломать не должен:
1. Clickjacking: каждая страница и ответ API — X-Frame-Options: DENY и frame-ancestors 'none' (стеклянную шапку или
   кнопку «Взять в работу» нельзя подложить под чужой сайт в рамке).
2. Анимации и стекло без чужого кода: в web/vendor — только сверенные R15 выпуски (sha256 = npm / SOURCE.txt). Новая
   библиотека анимаций или иконок — сначала сверка R15 (CSP и сторож test_r15_glass.py ловят загрузку из интернета).
3. Паспорт объекта по QR (R12 /?report=…) открывает любой прохожий: ровно те запросы, что делает report.js
   (/target, /heat/target → open_ids, /complaints/{id}), не отдают ФИО, телефон, почту, id устройства, точную точку,
   заметку и логин сотрудника, текст «Я тоже».
"""

from __future__ import annotations

import hashlib
import json

import pytest

from r15_common import ROOT, live_server, request
from test_r15_glass import PAGES
from test_r15_public_routes import MARKERS, _seed

# Сверены R15: MapLibre 5.6.2 и PMTiles 4.5.0 (npm), three.js 0.169.0 (SOURCE.txt), qrcode-generator 1.4.4 (npm).
VENDOR = {
    "LICENSE.txt": "ee5fc05a0677eaf69601d2c7db0d9ecd6cc27c3abc1d0733bc9ed34707cf8ef2",
    "maplibre-gl.css": "43c1d886b5fdf0aac4e7135bd6f84b823d9f48283a648012665f9be52c01389f",
    "maplibre-gl.js": "1525f971223d81f169f049f1ce50083e6f1643aa6b0ea0716653a550d2d57fc2",
    "pmtiles/.gitattributes": "49a2d015da504f0d542c40c106307b108908ff8cf56ba36823713e81d60b869e",
    "pmtiles/FFLATE-LICENSE": "805f6cb28bb8b6d3a0badd83c93bccd9671fa01a3b4b92b7042b0743325ac243",
    "pmtiles/LICENSE": "0371c38f338835f7fc13ed71176f3d92144e22c8b736a31cced57adbbeb647b3",
    "pmtiles/SOURCE.txt": "1d9451b475e818a66eef6d701afe46e91f96a0e4cfddef334b34f436348faf9e",
    "pmtiles/pmtiles.js": "caf981bc46f6327ee7e65d5dc964d89d38a69f60edca2bd4c5c890c21b554c6c",
    "qrcode/.gitattributes": "b46f07b378f42ed75870c5c4beb07df6812e25481dbbe6906ad2adfa0a54a730",
    "qrcode/LICENSE": "3a850fa5f08101db6f40676c2786e10bd2cd5fff7b12ffdf1e0c434d4e49d90c",
    "qrcode/SOURCE.txt": "06c27fd7168190a08d4bd9a42fc680d55e8a967ef00f1dd8c83cf0ce6daf8491",
    "qrcode/qrcode.js": "18ae399f81182bc9de916e9c77b195df20cc58d6f2d55a62b085a299f1bf1780",
    "three/LICENSE": "4c40a1ef62450b857c3b2aaf294936304cd552d965fbcd9d32d4c5bcf4ba4454",
    "three/SOURCE.txt": "a2974a02f387768af0079e8c677cfc1e6eef1943b9d955733af1b33fd31c1d82",
    "three/three.module.min.js": "f7cee3c7533449a1505cc12cb5128b89e3d4fd3d7ea62b05f9f5464a217472ee",
}


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    with live_server(tmp_path_factory.mktemp("marathon")) as server:
        yield server


@pytest.mark.parametrize("path", PAGES + ["/api/civic/v2/modules", "/civic/ui-kit/components.css"])
def test_no_page_can_be_framed_by_another_site(srv, path):
    status, headers, _ = request(srv, "GET", path)
    if status == 404:
        pytest.skip(f"{path} нет в этой сборке")
    assert headers.get("x-frame-options") == "DENY", (path, headers.get("x-frame-options"))
    assert "frame-ancestors 'none'" in headers.get("content-security-policy", ""), path


def test_vendor_holds_only_checked_releases():
    vendor = ROOT / "web" / "vendor"
    if not vendor.is_dir():
        pytest.skip("в этой сборке нет web/vendor")
    wrong = []
    for path in sorted(p for p in vendor.rglob("*") if p.is_file()):
        rel = path.relative_to(vendor).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if VENDOR.get(rel) != digest:
            wrong.append(f"{rel} sha256 {digest[:16]}… — {'новый файл' if rel not in VENDOR else 'изменён'}")
    assert not wrong, "web/vendor: не сверено R15 (сверить с npm/SOURCE.txt и дописать сюда):\n" + "\n".join(wrong)


def test_qr_passport_requests_reveal_nothing_personal(srv):
    if not hasattr(srv, "civic_v2"):
        pytest.skip("в этой сборке нет шлюза /api/civic/v2 (R01)")
    complaint = _seed(srv)
    target = complaint.get("target") or {}
    stranger = {"X-Birge-Device": "device-r15-passer-by-0001"}
    api = "/api/civic/v2"
    bodies = {}
    status, _h, raw = request(srv, "GET", f"{api}/target?id={target.get('id')}", headers=stranger)
    if status == 503:
        pytest.skip("в этой сборке нет паспорта объекта R12")
    bodies["target"] = raw
    status, _h, raw = request(srv, "GET", f"{api}/heat/target?kind={target.get('kind')}&id={target.get('id')}&days=30",
                              headers=stranger)
    assert status == 200, raw[:200]
    bodies["heat/target"] = raw
    open_ids = (json.loads(raw).get("item") or {}).get("open_ids") or []
    assert complaint["id"] in open_ids, ("паспорт не видит жалобу — проверка ничего бы не нашла", open_ids)
    for cid in open_ids[:3]:                         # report.js берёт не больше трёх
        status, _h, raw = request(srv, "GET", f"{api}/complaints/{cid}", headers=stranger)
        assert status == 200, raw[:200]
        bodies[f"complaints/{cid}"] = raw
    status, _h, raw = request(srv, "GET", "/?report=" + str(target.get("id")), headers=stranger)
    bodies["/?report="] = raw
    leaks = [f"{where}: {what}" for where, raw in bodies.items() for what, marker in MARKERS.items()
             if marker.encode("utf-8") in raw]
    assert not leaks, "паспорт по QR раскрывает личное:\n" + "\n".join(leaks)
