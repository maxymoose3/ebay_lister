"""Drafts on disk, one JSON file each."""
from __future__ import annotations

import re
import threading
from pathlib import Path

from .models import Draft

_lock = threading.RLock()


class Store:
    def __init__(self, folder: Path):
        self.folder = folder

    def _path(self, id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9-]{4,40}", id):
            raise KeyError(id)
        return self.folder / f"{id}.json"

    def save(self, d: Draft) -> Draft:
        with _lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self._path(d.id)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(d.model_dump_json(indent=2))
            tmp.replace(path)
        return d

    def get(self, id: str) -> Draft:
        path = self._path(id)
        if not path.exists():
            raise KeyError(id)
        return Draft.model_validate_json(path.read_text())

    def all(self) -> list[Draft]:
        if not self.folder.is_dir():
            return []
        return sorted((Draft.model_validate_json(p.read_text()) for p in self.folder.glob("*.json")),
                      key=lambda d: (d.created, d.id))

    def delete(self, id: str) -> None:
        self._path(id).unlink(missing_ok=True)
