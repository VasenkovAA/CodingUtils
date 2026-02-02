from __future__ import annotations

import asyncio
import fnmatch
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from codingutils.common_utils import FileContentDetector, FileSystemWalker, FileType, safe_write

from ..models.domain import CodeElement, FileArtifact, ReviewResult, ReviewSummary, ReviewMethod
from ..models.config import AIReviewConfig
from ...infrastructure.hash_storage import HashStorage
from ...utils.patterns import expand_braces
from ...plugins.registry import PluginRegistry

from .base import PipelineContext, PipelineError, PipelineStage

logger = logging.getLogger(__name__)


def _match_any(path: Path, patterns: List[str]) -> bool:
    name = path.name
    rel = str(path.as_posix())
    for pat in patterns:
        for p in expand_braces(pat):
            if fnmatch.fnmatchcase(name, p) or fnmatch.fnmatchcase(rel, p):
                return True
    return False


def _safe_name(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".", "@") else "_" for ch in s)[:150]


class FileDiscoveryStage(PipelineStage):
    def __init__(self, config: AIReviewConfig):
        super().__init__("file_discovery")
        self.config = config
        self.walker = FileSystemWalker(config.filter_config)

    async def process(self, directories: List[Path], context: PipelineContext) -> List[FileArtifact]:
        roots = [Path(d).resolve() for d in directories]
        files = self.walker.find_files(roots)

        context.metrics["files_found"] = len(files)

        include_patterns = list(self.config.include_patterns or [])
        if include_patterns:
            selected = [p for p in files if _match_any(p, include_patterns)]
        else:
            selected = files

        context.metrics["files_selected"] = len(selected)

        artifacts: List[FileArtifact] = []
        for p in selected:
            try:
                if FileContentDetector.detect_file_type(p) == FileType.BINARY:
                    context.warnings.append(f"Skipped binary file: {p}")
                    continue
                st = p.stat()
                artifacts.append(FileArtifact(path=p, size=st.st_size, modified=st.st_mtime))
            except Exception as e:
                context.errors.append(PipelineError(self.name, p, e))
        return artifacts


class CodeAnalysisStage(PipelineStage):
    def __init__(self, registry: PluginRegistry, method: ReviewMethod):
        super().__init__("code_analysis")
        self.registry = registry
        self.method = method

    async def process(self, file_artifacts: List[FileArtifact], context: PipelineContext) -> List[CodeElement]:
        elements: List[CodeElement] = []
        for art in file_artifacts:
            try:
                parser = self.registry.create_parser(
                    name=context.config.parser_plugin,
                    file_extension=art.path.suffix,
                )

                if self.method == ReviewMethod.FUNCTIONS:
                    elems = parser.parse_functions(art.path)
                elif self.method == ReviewMethod.CLASSES:
                    elems = parser.parse_classes(art.path)
                else:
                    elems = [parser.parse_whole_file(art.path)]

                elements.extend(elems)
            except Exception as e:
                context.errors.append(PipelineError(self.name, art.path, e))

        context.metrics["elements_extracted"] = len(elements)
        return elements


class ReviewGenerationStage(PipelineStage):
    def __init__(self, registry: PluginRegistry, prompt_engineer, hash_storage: HashStorage):
        super().__init__("review_generation")
        self.registry = registry
        self.prompt_engineer = prompt_engineer
        self.hash_storage = hash_storage

    async def process(self, elements: List[CodeElement], context: PipelineContext) -> List[ReviewResult]:
        llm = self.registry.create_llm_provider(context.config.llm.provider, config=context.config.llm)
        sem = asyncio.Semaphore(context.config.processing.max_workers)

        async def one(elem: CodeElement) -> Optional[ReviewResult]:
            async with sem:
                element_id = elem.full_name

                if context.config.processing.skip_unchanged and not context.config.processing.force:
                    if not self.hash_storage.has_changed(element_id, elem.content):
                        return None

                messages = self.prompt_engineer.build_messages(elem)
                token_est = sum(llm.estimate_tokens(m["content"]) for m in messages)
                if token_est > context.config.processing.max_input_tokens:
                    context.warnings.append(f"Token limit exceeded, skipped: {elem.full_name}")
                    return None

                try:
                    text = await llm.complete(messages)
                    context.metrics["llm_requests"] += 1
                    context.metrics["tokens_used"] += token_est
                    return ReviewResult(
                        element=elem,
                        review_text=text,
                        tokens_used=token_est,
                        timestamp=datetime.now(),
                        model=context.config.llm.model,
                        provider=context.config.llm.provider,
                    )
                except Exception as e:
                    context.errors.append(PipelineError(self.name, elem.full_name, e))
                    return None

        tasks = [one(e) for e in elements]
        results: List[ReviewResult] = []
        for coro in asyncio.as_completed(tasks):
            r = await coro
            if r is not None:
                results.append(r)

        try:
            await llm.close()
        except Exception:
            pass

        context.metrics["elements_reviewed"] = len(results)
        return results


class ResultSavingStage(PipelineStage):
    def __init__(self, registry: PluginRegistry, hash_storage: HashStorage):
        super().__init__("result_saving")
        self.registry = registry
        self.hash_storage = hash_storage

    async def process(self, results: List[ReviewResult], context: PipelineContext) -> ReviewSummary:
        formatter = self.registry.create_formatter(context.config.formatter_plugin)

        saved = 0
        for r in results:
            try:
                out_dir = context.config.output.output_dir
                rel = None
                try:
                    rel = r.element.file_path.resolve().relative_to(Path.cwd().resolve())
                except Exception:
                    rel = r.element.file_path.name


                file_dir = out_dir / str(rel)
                file_dir = file_dir.with_suffix(file_dir.suffix + "")

                file_dir = out_dir / str(rel)
                review_dir = file_dir

                review_dir.mkdir(parents=True, exist_ok=True)

                base_name = _safe_name(r.element.name)
                version = self._next_version(review_dir, base_name)

                review_path = review_dir / f"review_{version}_{base_name}.md"
                bak_path = review_dir / f"review_{version}_{base_name}.bak"

                formatted = formatter.format_review(r)
                safe_write(review_path, formatted, encoding="utf-8", backup=True)
                safe_write(bak_path, r.element.content, encoding="utf-8", backup=False)

                self.hash_storage.update_hash(r.element.full_name, r.element.content)
                saved += 1
            except Exception as e:
                context.errors.append(PipelineError(self.name, r.element.full_name, e))

        summary = ReviewSummary(
            total_elements=len(results),
            saved_count=saved,
            errors=context.errors,
            warnings=context.warnings,
            metrics=context.metrics,
            timestamp=datetime.now(),
        )


        summary_text = formatter.format_summary(summary)
        safe_write(context.config.output.output_dir / "summary.md", summary_text, encoding="utf-8", backup=True)


        self.hash_storage.save()
        return summary

    @staticmethod
    def _next_version(review_dir: Path, element_safe_name: str) -> int:

        mx = 0
        for p in review_dir.glob(f"review_*_{element_safe_name}.md"):
            try:
                stem = p.name.split("_", 2)[1]
                mx = max(mx, int(stem))
            except Exception:
                continue
        return mx + 1
