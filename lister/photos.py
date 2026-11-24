"""Photo loading: HEIC support, orientation, resizing and metadata removal.

Phone photos carry GPS coordinates. Everything leaving this machine (to Claude or
eBay) goes through `jpeg_bytes`, which re-encodes pixels only.
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
CLAUDE_MAX = 1568
EBAY_MAX = 2400


def list_photos(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in EXTS)


def resolve(folder: Path, name: str) -> Path:
    """Resolve a bare file name inside `folder`; reject anything else."""
    if name != Path(name).name or name in {"", ".", ".."}:
        raise ValueError(f"Bad photo name: {name!r}")
    path = folder / name
    if path.suffix.lower() not in EXTS or not path.is_file():
        raise ValueError(f"Photo not found: {name}")
    return path


def save_upload(folder: Path, name: str, data: bytes) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem)[:60] or "photo"
    ext = Path(name).suffix.lower()
    if ext not in EXTS:
        raise ValueError(f"Unsupported image type: {name}")
    Image.open(io.BytesIO(data)).verify()
    folder.mkdir(parents=True, exist_ok=True)
    out, n = folder / f"{stem}{ext}", 1
    while out.exists():
        if out.read_bytes() == data:
            return out.name
        out, n = folder / f"{stem}_{n}{ext}", n + 1
    out.write_bytes(data)
    return out.name


def jpeg_bytes(path: Path, max_side: int, quality: int = 88) -> bytes:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        clean = Image.new("RGB", im.size)
        clean.paste(im)
    buf = io.BytesIO()
    clean.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def claude_block(path: Path) -> dict:
    data = base64.standard_b64encode(jpeg_bytes(path, CLAUDE_MAX)).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}
