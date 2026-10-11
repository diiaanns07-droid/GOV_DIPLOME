"""Тесты предложения R15 clean_photo (для R09, п. 5 «волны мелочей»). Фото с метаданными делает Pillow —
если его нет, тесты пропускаются: python -m pytest research/round-14-results/R15/proposals/photo -q"""
import io, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import pytest
Image = pytest.importorskip("PIL.Image", reason="нужен Pillow (pip install pillow) — только для этих тестов")
from image_clean import clean_photo  # noqa: E402

GPS = {1: "N", 2: (51.0, 7.0, 30.12), 3: "E", 4: (71.0, 25.0, 41.5)}


def photo(fmt, size=(640, 480)):
    img = Image.new("RGB", size, (120, 160, 200))
    exif = img.getexif()
    exif[0x010F] = "PhoneMaker"; exif[0x0110] = "Model X"; exif[0x9003] = "2026:10:11 09:30:00"
    exif.get_ifd(0x8825).update(GPS)
    buf = io.BytesIO()
    kw = {"exif": exif.tobytes()}
    if fmt == "PNG":
        PngInfo = pytest.importorskip("PIL.PngImagePlugin").PngInfo
        info = PngInfo(); info.add_text("Comment", "Иванов Иван, ул. Кенесары 40, кв. 12"); kw["pnginfo"] = info
    if fmt == "JPEG":
        kw["comment"] = b"secret comment"
    img.save(buf, fmt, **kw)
    return buf.getvalue()


@pytest.mark.parametrize("fmt,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_metadata_removed_and_image_still_decodes(fmt, mime):
    raw = photo(fmt)
    before = Image.open(io.BytesIO(raw)).getexif()
    assert before.get_ifd(0x8825), "фикстура без GPS"
    got_mime, w, h, clean = clean_photo(raw)
    assert (got_mime, w, h) == (mime, 640, 480)
    img = Image.open(io.BytesIO(clean)); img.load()
    assert img.size == (640, 480)
    assert not img.getexif() and not img.getexif().get_ifd(0x8825)
    assert b"Exif" not in clean and b"PhoneMaker" not in clean and b"Kenesary" not in clean
    assert "Кенесары".encode() not in clean and b"secret comment" not in clean and b"XMP" not in clean


@pytest.mark.parametrize("data", [b"", b"GIF89a....", b"<svg onload=alert(1)>", b"%PDF-1.7", b"\xff\xd8\xff\xe0garbage", b"\x89PNG\r\n\x1a\n\x00\x00"])
def test_rejects_other_or_broken_files(data):
    with pytest.raises(ValueError):
        clean_photo(data)


def test_rejects_huge_dimensions():
    buf = io.BytesIO(); Image.new("L", (5000, 10)).save(buf, "PNG")
    with pytest.raises(ValueError):
        clean_photo(buf.getvalue())


def test_rejects_too_many_bytes():
    with pytest.raises(ValueError):
        clean_photo(b"\xff\xd8\xff" + b"\x00" * (3 * 1024 * 1024))
