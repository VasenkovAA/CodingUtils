from __future__ import annotations

from typing import Iterable, List


class AIReviewError(Exception):
    """Base error for ai_review module."""


class ConfigValidationError(AIReviewError):
    def __init__(self, errors: Iterable[str]):
        self.errors: List[str] = list(errors)
        super().__init__("\n".join(self.errors))
