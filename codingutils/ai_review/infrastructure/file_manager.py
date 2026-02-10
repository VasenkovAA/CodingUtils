from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List


class FileManager:
    """
    Менеджер файлов с LRU кэшем содержимого и контролем памяти.
    В фазе 1 кэшируем только содержимое (без open file handles).
    """

    def __init__(self, max_memory_mb: int = 100):
        self.max_memory_bytes = int(max_memory_mb) * 1024 * 1024
        self._file_contents: Dict[str, str] = {}
        self._lru: List[str] = []
        self._total_memory = 0

    @contextmanager
    def read_file(self, file_path: Path, encoding: str = "utf-8") -> Iterator[str]:
        file_id = str(Path(file_path).resolve())

        if file_id in self._file_contents:
            self._touch(file_id)
            yield self._file_contents[file_id]
            return

        content = Path(file_path).read_text(encoding=encoding, errors="replace")
        content_bytes = len(content.encode("utf-8"))

        self._ensure_capacity(content_bytes)

        self._file_contents[file_id] = content
        self._lru.append(file_id)
        self._total_memory += content_bytes

        try:
            yield content
        finally:

            self._ensure_capacity(0)

    def _touch(self, file_id: str) -> None:
        try:
            self._lru.remove(file_id)
        except ValueError:
            pass
        self._lru.append(file_id)

    def _ensure_capacity(self, incoming_bytes: int) -> None:
        while self._lru and (self._total_memory + incoming_bytes) > self.max_memory_bytes:
            oldest = self._lru.pop(0)
            content = self._file_contents.pop(oldest, None)
            if content is not None:
                self._total_memory -= len(content.encode("utf-8"))

    def cleanup(self) -> None:
        self._file_contents.clear()
        self._lru.clear()
        self._total_memory = 0
