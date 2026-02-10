from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from ..models.config import AIReviewConfig

logger = logging.getLogger(__name__)


class PipelineContext:
    def __init__(self, config: AIReviewConfig):
        self.config = config
        self.errors: List[PipelineError] = []
        self.warnings: List[str] = []
        self.metrics: Dict[str, Any] = {
            "start_time": None,
            "end_time": None,
            "files_found": 0,
            "files_selected": 0,
            "elements_extracted": 0,
            "elements_reviewed": 0,
            "llm_requests": 0,
            "tokens_used": 0,
        }
        self.state: Dict[str, Any] = {}


@dataclass
class PipelineError:
    stage: str
    element: Any
    error: Exception
    timestamp: datetime = field(default_factory=datetime.now)


class PipelineStage:
    def __init__(self, name: str):
        self.name = name

    async def process(self, input_data: Any, context: PipelineContext) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def cleanup(self) -> None:
        return None


class ProcessingPipeline:
    def __init__(self, stages: List[PipelineStage]):
        self.stages = stages

    async def run(self, initial_input: Any, context: PipelineContext) -> Any:
        context.metrics["start_time"] = datetime.now()
        current = initial_input
        try:
            for stage in self.stages:
                logger.info("Starting stage: %s", stage.name)
                try:
                    current = await stage.process(current, context)
                except Exception as e:
                    context.errors.append(PipelineError(stage=stage.name, element=current, error=e))
                    logger.exception("Stage %s failed: %s", stage.name, e)
                    if not context.config.processing.continue_on_error:
                        raise
                finally:
                    try:
                        await stage.cleanup()
                    except Exception:
                        logger.debug("Cleanup failed for stage %s", stage.name, exc_info=True)
        finally:
            context.metrics["end_time"] = datetime.now()
        return current
