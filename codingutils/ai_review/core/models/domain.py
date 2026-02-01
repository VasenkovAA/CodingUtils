from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ReviewMethod(str, Enum):
    FUNCTIONS = "functions"
    CLASSES = "classes"
    FILES = "files"
    MULTI_FILE = "multi_file"


@dataclass(frozen=True)
class CodeElement:
    """Элемент кода для ревью (функция, класс, файл)."""

    class Type(str, Enum):
        FUNCTION = "function"
        METHOD = "method"
        CLASS = "class"
        FILE = "file"
        UNKNOWN = "unknown"

    type: "CodeElement.Type"
    name: str
    content: str
    file_path: Path
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    language: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.file_path}:{self.name}"

    @property
    def size(self) -> int:
        return len(self.content.encode("utf-8"))


@dataclass(frozen=True)
class FileArtifact:
    """Файл для обработки."""
    path: Path
    size: int
    modified: float
    encoding: str = "utf-8"

    @property
    def relative_path(self) -> Path:
        try:
            return self.path.relative_to(Path.cwd())
        except ValueError:
            return self.path


@dataclass(frozen=True)
class ReviewResult:
    """Результат ревью от LLM."""
    element: CodeElement
    review_text: str
    tokens_used: int
    timestamp: datetime
    model: Optional[str] = None
    provider: Optional[str] = None

    @property
    def is_meaningful(self) -> bool:
        text = (self.review_text or "").strip()
        if len(text) <= 50:
            return False
        lowered = text.lower()
        return not (lowered.startswith("i cannot review") or lowered.startswith("cannot review"))


@dataclass(frozen=True)
class ReviewSummary:
    """Сводка по выполненному ревью."""
    total_elements: int
    saved_count: int
    errors: List[Any]
    warnings: List[str]
    metrics: Dict[str, Any]
    timestamp: datetime

    @property
    def success_rate(self) -> float:
        if self.total_elements <= 0:
            return 0.0
        return self.saved_count / self.total_elements

    @property
    def duration(self) -> float:
        start = self.metrics.get("start_time")
        end = self.metrics.get("end_time")
        if start and end:
            return (end - start).total_seconds()
        return 0.0
