from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from codingutils.common_utils import FilterConfig

from .domain import ReviewMethod
from .errors import ConfigValidationError

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Конфигурация подключения к LLM."""
    provider: str = "lmstudio"
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model: str = "local-model"

    temperature: float = 0.7
    max_output_tokens: int = 2000
    context_window: Optional[int] = None

    timeout: int = 60
    max_retries: int = 3
    rate_limit_per_minute: int = 30

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.provider:
            errors.append("llm.provider is required")
        if not self.model:
            errors.append("llm.model is required")
        if not (0.0 <= self.temperature <= 2.0):
            errors.append("llm.temperature must be between 0 and 2")
        if self.max_output_tokens <= 0:
            errors.append("llm.max_output_tokens must be > 0")
        if self.timeout <= 0:
            errors.append("llm.timeout must be > 0")
        if self.max_retries < 0:
            errors.append("llm.max_retries must be >= 0")
        if self.rate_limit_per_minute <= 0:
            errors.append("llm.rate_limit_per_minute must be > 0")
        if self.context_window is not None and self.context_window <= 0:
            errors.append("llm.context_window must be > 0 when provided")
        if self.context_window is not None and self.max_output_tokens >= self.context_window:
            errors.append("llm.max_output_tokens must be < llm.context_window")
        return errors


@dataclass
class PromptConfig:
    """Конфигурация промтов."""
    system_prompt: Optional[str] = None
    user_prompt: str = "prompts/default.txt"
    include_context: bool = False
    context_files: List[str] = field(default_factory=list)
    placeholders: Dict[str, str] = field(default_factory=dict)

    def load_prompt(self, prompt_ref: Optional[str]) -> Optional[str]:
        if prompt_ref is None:
            return None

        if "\n" in prompt_ref:
            return prompt_ref

        p = Path(prompt_ref)
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8")

        return None


@dataclass
class ProcessingConfig:
    """Конфигурация обработки."""
    method: ReviewMethod = ReviewMethod.FUNCTIONS
    max_input_tokens: int = 1500

    skip_unchanged: bool = True
    force: bool = False

    max_workers: int = 1
    batch_size: int = 1

    continue_on_error: bool = True

    token_method: str = "approximate"
    max_memory_mb: int = 500

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.max_input_tokens <= 0:
            errors.append("processing.max_input_tokens must be > 0")
        if self.max_workers <= 0:
            errors.append("processing.max_workers must be >= 1")
        if self.batch_size <= 0:
            errors.append("processing.batch_size must be >= 1")
        if self.max_memory_mb <= 0:
            errors.append("processing.max_memory_mb must be > 0")
        if self.token_method not in ("approximate", "tiktoken"):
            errors.append("processing.token_method must be 'approximate' or 'tiktoken'")
        return errors


@dataclass
class OutputConfig:
    """Конфигурация вывода."""
    output_dir: Path = Path("reviews")
    preserve_structure: bool = True
    versioning: str = "incremental"
    formatter: str = "markdown"

    @property
    def hash_file(self) -> Path:
        return self.output_dir / ".review_hashes.json"

    @property
    def error_log(self) -> Path:
        return self.output_dir / "errors.log"

    @property
    def summary_file(self) -> Path:
        return self.output_dir / "summary.json"


@dataclass
class AIReviewConfig:
    """Полная конфигурация приложения."""
    filter_config: FilterConfig
    include_patterns: List[str] = field(default_factory=list)

    auto_discover_plugins: bool = True
    plugin_dirs: List[Path] = field(default_factory=list)

    llm: LLMConfig = field(default_factory=LLMConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    parser_plugin: Optional[str] = None
    formatter_plugin: str = "markdown"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        errors: List[str] = []
        errors.extend(self.llm.validate())
        errors.extend(self.processing.validate())

        if self.include_patterns and not all(isinstance(p, str) and p.strip() for p in self.include_patterns):
            errors.append("include_patterns must be a list of non-empty strings")

        if self.llm.context_window is not None:
            if (self.processing.max_input_tokens + self.llm.max_output_tokens) > self.llm.context_window:
                errors.append(
                    "processing.max_input_tokens + llm.max_output_tokens must be <= llm.context_window"
                )

        if errors:
            raise ConfigValidationError(errors)
