from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import List, Optional

from ..models.config import AIReviewConfig
from ..models.domain import ReviewSummary
from ..pipeline import (
    PipelineContext,
    ProcessingPipeline,
    FileDiscoveryStage,
    CodeAnalysisStage,
    ReviewGenerationStage,
    ResultSavingStage,
)
from ...infrastructure import FileManager, HashStorage, PromptEngineer, TokenCounter
from ...plugins import PluginRegistry
from ...plugins.builtin import register_builtin_plugins

logger = logging.getLogger(__name__)


class AIReviewService:
    def __init__(self, config: AIReviewConfig, registry: Optional[PluginRegistry] = None):
        self.config = config
        self.registry = registry or PluginRegistry()

        register_builtin_plugins(self.registry)

        # user plugins
        if config.auto_discover_plugins and config.plugin_dirs:
            self.registry.discover_plugins(config.plugin_dirs)

        self.file_manager = FileManager(max_memory_mb=config.processing.max_memory_mb)
        self.hash_storage = HashStorage(storage_path=config.output.hash_file, backend="json")
        self.token_counter = TokenCounter(method=config.processing.token_method)
        self.prompt_engineer = PromptEngineer(config.prompt)

    def review(self, directories: List[Path]) -> ReviewSummary:
        """
        Синхронный метод. Внутри запускаем event loop.
        """
        ctx = PipelineContext(self.config)
        pipeline = self._create_pipeline()

        try:
            result = asyncio.run(pipeline.run(directories, ctx))

            if isinstance(result, ReviewSummary):
                summary = result
            else:
                # Если последняя стадия упала, пайплайн вернёт промежуточные данные (например list[ReviewResult]).
                # Собираем summary из контекста, чтобы CLI не падал.
                summary = ReviewSummary(
                    total_elements=int(ctx.metrics.get("elements_reviewed", 0)) or 0,
                    saved_count=0,
                    errors=ctx.errors,
                    warnings=ctx.warnings,
                    metrics=ctx.metrics,
                    timestamp=ctx.metrics.get("end_time"),
                )

            self._log_summary(summary)
            self._write_error_log(summary)
            return summary
        finally:
            self.file_manager.cleanup()

    def _create_pipeline(self) -> ProcessingPipeline:
        stages = [
            FileDiscoveryStage(self.config),
            CodeAnalysisStage(self.registry, self.config.processing.method),
            ReviewGenerationStage(self.registry, self.prompt_engineer, self.hash_storage),
            ResultSavingStage(self.registry, self.hash_storage),
        ]
        return ProcessingPipeline(stages)

    def clean(self, everything: bool = True) -> bool:
        try:
            out = self.config.output.output_dir
            if out.exists():
                shutil.rmtree(out)
            return True
        except Exception as e:
            logger.error("Failed to clean output dir: %s", e)
            return False

    def _write_error_log(self, summary: ReviewSummary) -> None:
        if not summary.errors:
            return
        try:
            p = self.config.output.error_log
            p.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            for err in summary.errors:
                lines.append(f"[{getattr(err, 'timestamp', '')}] {getattr(err, 'stage', '?')}: {getattr(err, 'error', err)}")
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            logger.debug("Failed to write error log", exc_info=True)

    def _log_summary(self, summary: ReviewSummary) -> None:
        logger.info("=" * 60)
        logger.info("AI REVIEW COMPLETED")
        logger.info("=" * 60)
        logger.info("Total elements: %d", summary.total_elements)
        logger.info("Saved: %d", summary.saved_count)
        logger.info("Success rate: %.1f%%", summary.success_rate * 100.0)
        logger.info("Duration: %.2fs", summary.duration)
        logger.info("LLM requests: %s", summary.metrics.get("llm_requests", 0))
        logger.info("Tokens used(est): %s", summary.metrics.get("tokens_used", 0))
        if summary.errors:
            logger.warning("Errors: %d", len(summary.errors))
        if summary.warnings:
            logger.info("Warnings: %d", len(summary.warnings))
