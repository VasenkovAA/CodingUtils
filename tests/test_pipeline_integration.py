import asyncio
from pathlib import Path

from codingutils.common_utils import FilterConfig
from codingutils.ai_review.core.models.config import AIReviewConfig
from codingutils.ai_review.core.models.domain import ReviewMethod
from codingutils.ai_review.core.pipeline import (
    PipelineContext,
    ProcessingPipeline,
    FileDiscoveryStage,
    CodeAnalysisStage,
    ReviewGenerationStage,
    ResultSavingStage,
)
from codingutils.ai_review.infrastructure import HashStorage, PromptEngineer
from codingutils.ai_review.plugins import PluginRegistry
from codingutils.ai_review.plugins.builtin import register_builtin_plugins


def test_pipeline_end_to_end_with_mock_llm(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    py = src / "a.py"
    py.write_text(
        "def f():\n"
        "    return 1\n\n"
        "class C:\n"
        "    def m(self):\n"
        "        return 2\n",
        encoding="utf-8",
    )

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    user_prompt = prompts / "u.md"
    user_prompt.write_text("Review {{element_type}} {{element_name}}\n\n```py\n{{code}}\n```", encoding="utf-8")

    fc = FilterConfig(directories=[str(tmp_path)], recursive=True, include_pattern="*")
    cfg = AIReviewConfig(filter_config=fc)
    cfg.include_patterns = ["*.py"]
    cfg.processing.method = ReviewMethod.FUNCTIONS
    cfg.llm.provider = "mock"
    cfg.prompt.user_prompt = str(user_prompt)
    cfg.output.output_dir = tmp_path / "reviews"

    registry = register_builtin_plugins(PluginRegistry())
    hs = HashStorage(cfg.output.hash_file)

    pe = PromptEngineer(cfg.prompt)

    pipeline = ProcessingPipeline(
        [
            FileDiscoveryStage(cfg),
            CodeAnalysisStage(registry, cfg.processing.method),
            ReviewGenerationStage(registry, pe, hs),
            ResultSavingStage(registry, hs),
        ]
    )

    ctx = PipelineContext(cfg)

    summary = asyncio.run(pipeline.run([tmp_path], ctx))

    assert summary.saved_count >= 1
    assert (cfg.output.output_dir / "summary.md").exists()
    assert cfg.output.hash_file.exists()
