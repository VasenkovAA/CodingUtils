from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from ..core.models.domain import CodeElement
from ..core.models.config import LLMConfig


class BasePlugin(ABC):
    name: str
    version: str = "1.0.0"

    @classmethod
    @abstractmethod
    def get_supported_config_keys(cls) -> List[str]:
        raise NotImplementedError


class BaseParser(BasePlugin):
    @classmethod
    @abstractmethod
    def supported_extensions(cls) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def parse_functions(self, file_path) -> List[CodeElement]:
        raise NotImplementedError

    @abstractmethod
    def parse_classes(self, file_path) -> List[CodeElement]:
        raise NotImplementedError

    def parse_whole_file(self, file_path) -> CodeElement:

        content = file_path.read_text(encoding="utf-8", errors="replace")
        return CodeElement(
            type=CodeElement.Type.FILE,
            name=file_path.name,
            content=content,
            file_path=file_path,
            language=file_path.suffix.lstrip(".") or None,
        )


class BaseLLMProvider(BasePlugin):
    def __init__(self, config: LLMConfig, **_: Any):
        self.config = config
        self._session = None

    @abstractmethod
    async def complete(self, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        raise NotImplementedError

    async def close(self) -> None:
        session = getattr(self, "_session", None)
        if session is not None:
            close = getattr(session, "close", None)
            if callable(close):
                await close()


class BaseFormatter(BasePlugin):
    @abstractmethod
    def format_review(self, review) -> str:
        raise NotImplementedError

    @abstractmethod
    def format_summary(self, summary) -> str:
        raise NotImplementedError
