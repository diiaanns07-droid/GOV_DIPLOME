"""Explicit offline assets and bounded HTTP byte ranges; no directory serving."""
from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import unquote

PREFIX = "/civic/offline/"
STATIC = {
    "boot.js": "text/javascript; charset=utf-8",
    "style.json": "application/json; charset=utf-8",
    "sprites/v4/light.json": "application/json",
    "sprites/v4/light.png": "image/png",
    "sprites/v4/light@2x.json": "application/json",
    "sprites/v4/light@2x.png": "image/png",
    "LICENSE-ODbL-1.0.txt": "text/plain; charset=utf-8",
    "ATTRIBUTION.txt": "text/plain; charset=utf-8",
}


def byte_range(value: str, size: int) -> tuple[int, int]:
    """One RFC 9110 byte range. Reject multipart, invalid or unsatisfiable input."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError("invalid range")
    a, b = match.groups()
    if not a:
        suffix = int(b)
        if suffix <= 0:
            raise ValueError("invalid suffix")
        return max(0, size - suffix), size - 1
    start, end = int(a), min(int(b), size - 1) if b else size - 1
    if start >= size or end < start:
        raise ValueError("unsatisfiable range")
    return start, end


def serve(handler, path: str) -> bool:
    if not path.startswith(PREFIX):
        return False
    root = handler.server.backend.project
    asset_root = root / "web/civic/offline"
    name = unquote(path[len(PREFIX):])
    archive = root / "data/civic/astana/tiles/astana.pmtiles"
    if name == "status.json":
        available = False
        try:
            with archive.open("rb") as stream:
                available = stream.read(8) == b"PMTiles\x03"
        except OSError:
            pass
        handler.send_bytes(200, json.dumps({"available": available}).encode(), "application/json")
        return True
    content_type = STATIC.get(name)
    asset = asset_root / name
    font = re.fullmatch(r"fonts/Noto Sans Regular/(\d+)-(\d+)\.pbf", name)
    if font:
        start, end = map(int, font.groups())
        if start % 256 == 0 and end == start + 255 and end <= 65535:
            content_type = "application/x-protobuf"
    is_archive = name == "astana.pmtiles"
    if is_archive:
        asset, content_type = archive, "application/vnd.pmtiles"
    if not content_type or not asset.is_file():
        handler.error_reply(404, "Offline asset not found")
        return True
    # Also prevent symlinks/junctions from escaping the two explicit roots.
    allowed = archive.parent if is_archive else asset_root
    if not asset.resolve().is_relative_to(allowed.resolve()):
        handler.error_reply(404, "Offline asset not found")
        return True
    stat = asset.stat()
    size = stat.st_size
    etag = f'"{stat.st_mtime_ns:x}-{size:x}"'
    start, end, status = 0, size - 1, 200
    requested_range = handler.headers.get("Range") if is_archive else None
    if requested_range and handler.headers.get("If-Range", etag) == etag:
        try:
            start, end = byte_range(requested_range, size)
            status = 206
        except ValueError:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{size}")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return True
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(end - start + 1))
    handler.send_header("ETag", etag)
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("X-Content-Type-Options", "nosniff")
    if is_archive:
        handler.send_header("Accept-Ranges", "bytes")
        if status == 206:
            handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.end_headers()
    if handler.command != "HEAD":
        try:
            with asset.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining:
                    data = stream.read(min(64 * 1024, remaining))
                    if not data:
                        break
                    handler.wfile.write(data)
                    remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            handler.close_connection = True
    return True
