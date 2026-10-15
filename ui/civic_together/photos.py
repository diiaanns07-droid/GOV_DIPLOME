"""Фото «после» инициативы (CONTRACT §10): публичное, без EXIF и GPS, небольшое.

Интерфейс уменьшает фото (canvas: до 960 px, JPEG) — это уже сбрасывает метаданные. Сервер не доверяет и чистит ещё раз
той же функцией, что у фото жалоб R09 (ui.civic_feedback.v2.photos.sanitize: тип по сигнатуре, выброс EXIF/XMP/IPTC,
проверка сторон). Тело запроса шлюза R01 — не больше 64 КБ, поэтому одно фото — один запрос: само фото до 46 000 байт
и миниатюра для карточки до 9 000 байт.
"""

from __future__ import annotations

import base64
import binascii
import re

MAX_PHOTO_BYTES = 46_000
MAX_THUMB_BYTES = 9_000
_DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/]+={0,2})\Z")


class PhotoError(ValueError):
    """Понятный текст для жителя: не фото, повреждено, слишком большое."""


def _decode(value, limit: int, field: str) -> bytes:
    if not isinstance(value, str):
        raise PhotoError(f"{field}: нужен data URL картинки.")
    match = _DATA_URL.match(value.strip())
    if not match:
        raise PhotoError("Подходят только фото JPEG, PNG или WebP.")
    if len(match.group(2)) > (limit * 4) // 3 + 8:
        raise PhotoError("Фото слишком большое — уменьшите его.")
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise PhotoError("Фото повреждено.") from None
    if not data or len(data) > limit:
        raise PhotoError("Фото слишком большое — уменьшите его.")
    return data


def _sanitize(data: bytes) -> tuple[str, bytes]:
    try:
        from ui.civic_feedback.v2.photos import PhotoError as R09PhotoError, sanitize
    except Exception:
        raise PhotoError("Фото сейчас нельзя добавить: нет проверки фото в этой сборке.") from None
    try:
        return sanitize(data)
    except R09PhotoError as exc:
        raise PhotoError(str(exc)) from None


def clean_photo(photo) -> dict:
    """{data_url, thumb?, width?, height?} -> {mime, data, thumb, thumb_mime, width, height} без метаданных."""
    if not isinstance(photo, dict):
        raise PhotoError("photo: нужен объект {data_url, thumb}.")
    mime, data = _sanitize(_decode(photo.get("data_url"), MAX_PHOTO_BYTES, "data_url"))
    thumb = thumb_mime = None
    if photo.get("thumb") not in (None, ""):
        thumb_mime, thumb = _sanitize(_decode(photo.get("thumb"), MAX_THUMB_BYTES, "thumb"))
    size = {}
    for key in ("width", "height"):
        value = photo.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 4096:
            size[key] = value
    return {"mime": mime, "data": data, "thumb": thumb, "thumb_mime": thumb_mime, **size}


def data_url(mime: str | None, data: bytes | None) -> str | None:
    if not mime or not data:
        return None
    return f"data:{mime};base64,{base64.b64encode(bytes(data)).decode('ascii')}"
