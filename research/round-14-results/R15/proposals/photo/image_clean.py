"""Предложение R15 для R09 (п. 5 «волны мелочей»): проверка и очистка фото без сторонних библиотек.

clean_photo(data) -> (mime, width, height, clean_bytes) или ValueError с понятной причиной.
Тип — по сигнатуре файла (не по имени и не по Content-Type). Из JPEG убираются APP1..APP15 (Exif с GPS, XMP,
IPTC, ICC) и комментарии; из PNG — текстовые и служебные чанки (eXIf, tEXt, zTXt, iTXt, tIME); из WebP — EXIF и XMP.
Сжатые данные изображения не меняются (не перекодируем — стандартной библиотеке это не по силам).
"""

from __future__ import annotations

import struct

MAX_BYTES = 3 * 1024 * 1024          # после уменьшения на телефоне фото ~0,3–1 МБ
MAX_SIDE = 4096                       # защита от «бомбы» размеров при декодировании у акимата
PNG_KEEP = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"pHYs"}


def clean_photo(data: bytes):
    if not isinstance(data, (bytes, bytearray)) or not 0 < len(data) <= MAX_BYTES:
        raise ValueError("Фото пустое или больше 3 МБ.")
    data = bytes(data)
    if data[:3] == b"\xff\xd8\xff":
        mime, (w, h), clean = "image/jpeg", *_jpeg(data)
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        mime, (w, h), clean = "image/png", *_png(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime, (w, h), clean = "image/webp", *_webp(data)
    else:
        raise ValueError("Только JPEG, PNG или WebP.")
    if not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE):
        raise ValueError("Слишком большое фото по размеру сторон.")
    return mime, w, h, clean


def _jpeg(data):
    out, i, size = [b"\xff\xd8"], 2, None
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise ValueError("Повреждённый JPEG.")
        marker = data[i + 1]
        if marker == 0xFF:                      # заполнитель
            i += 1
            continue
        if marker == 0xDA:                      # SOS: дальше сжатые данные до EOI — копируем как есть
            if size is None:
                raise ValueError("В JPEG нет размеров кадра.")
            out.append(data[i:])
            return size, b"".join(out)
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out.append(data[i:i + 2])
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if length < 2 or i + 2 + length > len(data):
            raise ValueError("Повреждённый JPEG.")
        segment = data[i:i + 2 + length]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            size = (w, h)
        if not (0xE1 <= marker <= 0xEF or marker == 0xFE):   # APP0 (JFIF) оставляем; APP1..15 и COM — нет
            out.append(segment)
        i += 2 + length
    raise ValueError("Повреждённый JPEG.")


def _png(data):
    out, i, size = [data[:8]], 8, None
    while i + 12 <= len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        end = i + 12 + length
        if end > len(data):
            raise ValueError("Повреждённый PNG.")
        if kind == b"IHDR":
            size = struct.unpack(">II", data[i + 8:i + 16])
        if kind in PNG_KEEP:
            out.append(data[i:end])
        i = end
        if kind == b"IEND":
            break
    if size is None:
        raise ValueError("Повреждённый PNG.")
    return size, b"".join(out)


def _webp(data):
    chunks, i, size = [], 12, None
    while i + 8 <= len(data):
        kind, length = data[i:i + 4], struct.unpack("<I", data[i + 4:i + 8])[0]
        end = i + 8 + length + (length & 1)
        if end > len(data) + (length & 1):
            raise ValueError("Повреждённый WebP.")
        body = bytearray(data[i + 8:i + 8 + length])
        if kind == b"VP8X":
            body[0] &= ~0x0C & 0xFF                       # флаги EXIF (0x08) и XMP (0x04) снять
            size = (int.from_bytes(body[4:7], "little") + 1, int.from_bytes(body[7:10], "little") + 1)
        elif kind == b"VP8 " and size is None and len(body) >= 10:
            size = (struct.unpack("<H", body[6:8])[0] & 0x3FFF, struct.unpack("<H", body[8:10])[0] & 0x3FFF)
        elif kind == b"VP8L" and size is None and len(body) >= 5:
            bits = int.from_bytes(body[1:5], "little")
            size = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        if kind not in (b"EXIF", b"XMP "):
            chunks.append(kind + struct.pack("<I", length) + bytes(body) + (b"\x00" if length & 1 else b""))
        i = end
    if size is None:
        raise ValueError("Повреждённый WebP.")
    payload = b"WEBP" + b"".join(chunks)
    return size, b"RIFF" + struct.pack("<I", len(payload)) + payload
