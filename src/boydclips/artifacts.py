"""Small file-integrity checks shared by production and publication.

These checks establish that required artifacts exist, not editorial quality.
"""
from pathlib import Path

from PIL import Image


def require_file(path: Path) -> Path:
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"required artifact is missing or empty: {path}")
    return path


def require_thumbnail(path: Path) -> Path:
    path = require_file(path)
    try:
        with Image.open(path) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise ValueError("thumbnail must be JPEG or PNG")
            image.verify()
        with Image.open(path) as image:
            image.load()
    except Exception as exc:
        raise RuntimeError(f"thumbnail is not a decodable JPEG or PNG: {path}") from exc
    return path
