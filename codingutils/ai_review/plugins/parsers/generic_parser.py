from __future__ import annotations

from pathlib import Path
from typing import List

from ...core.models.domain import CodeElement
from ..base import BaseParser


class GenericParser(BaseParser):
    name = "generic"

    def __init__(self, **_):
        pass

    @classmethod
    def get_supported_config_keys(cls):
        return []

    @classmethod
    def supported_extensions(cls) -> List[str]:
        return []

    def parse_functions(self, file_path: Path) -> List[CodeElement]:
        return []

    def parse_classes(self, file_path: Path) -> List[CodeElement]:
        return []
