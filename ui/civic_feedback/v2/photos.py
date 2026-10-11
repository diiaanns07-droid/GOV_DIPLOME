"""Фото к жалобе (POLISH_WAVE п. 5): только jpeg/png/webp, метаданные удаляются, размер ограничен.

Интерфейс уже уменьшает фото до ~1600 px и перекодирует его (canvas), что само по себе сбрасывает EXIF.
Сервер не доверяет этому и чистит ещё раз — только стандартная библиотека, без декодирования картинки:
  JPEG — выбрасываются сегменты APP1 (EXIF с GPS, XMP), APP13 (IPTC), прочие APPn кроме JFIF/ICC/Adobe, COM;
  PNG  — выбрасываются чанки eXIf, tEXt, zTXt, iTXt, tIME;
  WebP — выбрасываются чанки EXIF и «XMP », флаги EXIF/XMP в VP8X сбрасываются.
Тип определяется по сигнатуре байтов, а не по присланному mime.
"""

from __future__ import annotations

import struct

MAX_BYTES = 1_500_000          # после уменьшения до 1600 px jpeg ~0.2–0.6 МБ; больше — отказ
MAX_RESIDENT = 3               # фото жителя на жалобу
MAX_AFTER = 3                  # фото «после» на один раунд «исправлено»
CHUNK_BYTES = 36_000           # часть загрузки: base64 ≈ 48 КБ, шлюз R01 пропускает ≤ 64 КБ тела
MIMES = ("image/jpeg", "image/png", "image/webp")
# R15-S23: стороны не больше 4096 px — иначе PNG 16000×16000 одного цвета весит < 1 МБ, а у сотрудника в браузере
# разворачивается в ~1 ГБ и вешает карточку («фото-бомба»). Интерфейс и так уменьшает фото до 1600 px.
MAX_SIDE = 4096
_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}

_JPEG_KEEP_APP = {0xE0, 0xE2, 0xEE}            # APP0 JFIF, APP2 ICC-профиль, APP14 Adobe (цвета)
_PNG_DROP = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}
_WEBP_DROP = {b"EXIF", b"XMP "}


class PhotoError(ValueError):
    """Файл не похож на фото, повреждён или слишком большой — понятный текст для жителя."""


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _strip_jpeg(data: bytes) -> tuple[bytes, tuple[int, int] | None]:
    out = bytearray(b"\xff\xd8")
    size = None
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise PhotoError("Фото повреждено.")
        while i < len(data) and data[i] == 0xFF:      # заполняющие 0xFF перед маркером
            i += 1
        if i >= len(data):
            raise PhotoError("Фото повреждено.")
        marker = data[i]
        i += 1
        if marker == 0xD9:                            # EOI без данных — пустой файл
            raise PhotoError("Фото повреждено.")
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # маркеры без длины
            out += bytes((0xFF, marker))
            continue
        if i + 2 > len(data):
            raise PhotoError("Фото повреждено.")
        length = struct.unpack(">H", data[i:i + 2])[0]
        if length < 2 or i + length > len(data):
            raise PhotoError("Фото повреждено.")
        segment = data[i:i + length]
        i += length
        if marker == 0xDA:
            # SOS: сжатые данные идут до следующего маркера (FF00 и RSTn — часть данных). R15-S22: после EOI телефоны
            # дописывают второе изображение (MPF) или видео «живого фото» со своими EXIF/GPS — их не берём.
            out += bytes((0xFF, marker)) + segment
            j = i
            while True:
                k = data.find(b"\xff", j)
                if k < 0 or k + 1 >= len(data):
                    raise PhotoError("Фото повреждено.")
                nxt = data[k + 1]
                if nxt == 0x00 or 0xD0 <= nxt <= 0xD7 or nxt == 0xFF:
                    j = k + (1 if nxt == 0xFF else 2)
                    continue
                break
            out += data[i:k]
            if nxt == 0xD9:                           # EOI — конец картинки, хвост отбрасываем
                return bytes(out) + b"\xff\xd9", size
            i = k                                     # прогрессивный JPEG: следующий проход (DHT, SOS …)
            continue
        if marker in _JPEG_SOF and length >= 7:
            size = (struct.unpack(">H", segment[5:7])[0], struct.unpack(">H", segment[3:5])[0])
        if (0xE0 <= marker <= 0xEF and marker not in _JPEG_KEEP_APP) or marker == 0xFE:
            continue                                  # EXIF/GPS, XMP, IPTC, комментарии — выбрасываем
        out += bytes((0xFF, marker)) + segment
    raise PhotoError("Фото повреждено.")


def _strip_png(data: bytes) -> bytes:
    out = bytearray(data[:8])
    i = 8
    seen_end = False
    first = True
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        end = i + 12 + length
        if end > len(data):
            raise PhotoError("Фото повреждено.")
        if first and kind != b"IHDR":
            raise PhotoError("Фото повреждено.")
        first = False
        if kind not in _PNG_DROP:
            out += data[i:end]
        i = end
        if kind == b"IEND":
            seen_end = True
            break
    if not seen_end:
        raise PhotoError("Фото повреждено.")
    return bytes(out)


def _strip_webp(data: bytes) -> bytes:
    if len(data) < 12:
        raise PhotoError("Фото повреждено.")
    chunks = []
    i = 12
    end = min(len(data), 8 + struct.unpack("<I", data[4:8])[0])
    while i + 8 <= end:
        kind = data[i:i + 4]
        size = struct.unpack("<I", data[i + 4:i + 8])[0]
        stop = i + 8 + size + (size & 1)
        if i + 8 + size > len(data):
            raise PhotoError("Фото повреждено.")
        body = bytearray(data[i + 8:i + 8 + size])
        i = stop
        if kind in _WEBP_DROP:
            continue
        if kind == b"VP8X" and body:
            body[0] &= ~(0x08 | 0x04) & 0xFF          # флаги «есть EXIF» и «есть XMP»
        chunks.append(kind + struct.pack("<I", size) + bytes(body) + (b"\x00" if size & 1 else b""))
    if not chunks:
        raise PhotoError("Фото повреждено.")
    payload = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(payload)) + payload


def _size(mime: str, clean: bytes) -> tuple[int, int] | None:
    """Ширина и высота из заголовка PNG/WebP (без декодирования картинки)."""
    if mime == "image/png" and len(clean) >= 24:
        return struct.unpack(">II", clean[16:24])
    if mime == "image/webp":
        i = 12
        while i + 8 <= len(clean):
            kind, size = clean[i:i + 4], struct.unpack("<I", clean[i + 4:i + 8])[0]
            body = clean[i + 8:i + 8 + size]
            if kind == b"VP8X" and len(body) >= 10:
                return int.from_bytes(body[4:7], "little") + 1, int.from_bytes(body[7:10], "little") + 1
            if kind == b"VP8 " and len(body) >= 10:
                return struct.unpack("<H", body[6:8])[0] & 0x3FFF, struct.unpack("<H", body[8:10])[0] & 0x3FFF
            if kind == b"VP8L" and len(body) >= 5:
                bits = int.from_bytes(body[1:5], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            i += 8 + size + (size & 1)
    return None


def sanitize(data: bytes) -> tuple[str, bytes]:
    """-> (mime, байты без метаданных). PhotoError — не фото, повреждено или больше MAX_BYTES."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise PhotoError("Пустой файл.")
    if len(data) > MAX_BYTES:
        raise PhotoError("Фото слишком большое.")
    mime = sniff(bytes(data[:16]))
    if mime is None:
        raise PhotoError("Подходят только фото JPEG, PNG или WebP.")
    if mime == "image/jpeg":
        clean, size = _strip_jpeg(bytes(data))
    else:
        clean = {"image/png": _strip_png, "image/webp": _strip_webp}[mime](bytes(data))
        size = _size(mime, clean)
    if size is None or not (0 < size[0] <= MAX_SIDE and 0 < size[1] <= MAX_SIDE):
        raise PhotoError("Фото слишком большое по размеру сторон.")
    return mime, clean
