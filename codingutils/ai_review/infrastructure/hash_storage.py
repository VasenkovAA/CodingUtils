from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Optional


class HashStorage:
    def __init__(self, storage_path: Path, backend: str = "json"):
        self.storage_path = Path(storage_path)
        self.backend = backend
        self._data: Dict[str, str] = {}

        if backend != "json":
            raise ValueError("Only json backend is supported in phase 1")

        self._load_json()

    def _load_json(self) -> None:
        if self.storage_path.exists():
            self._data = json.loads(self.storage_path.read_text(encoding="utf-8"))

    def get_hash(self, element_id: str) -> Optional[str]:
        return self._data.get(element_id)

    def update_hash(self, element_id: str, content: str) -> None:
        self._data[element_id] = hashlib.sha256(content.encode("utf-8")).hexdigest()

    def has_changed(self, element_id: str, content: str) -> bool:
        old = self.get_hash(element_id)
        if old is None:
            return True
        new = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return new != old

    def save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")

    def clear(self) -> None:
        self._data.clear()
        if self.storage_path.exists():
            self.storage_path.unlink()
