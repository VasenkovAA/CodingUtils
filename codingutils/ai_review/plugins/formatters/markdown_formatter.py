from __future__ import annotations

from typing import List

from ...core.models.domain import ReviewResult, ReviewSummary
from ..base import BaseFormatter


class MarkdownFormatter(BaseFormatter):
    name = "markdown"

    def __init__(self, **_):
        pass

    @classmethod
    def get_supported_config_keys(cls) -> List[str]:
        return []

    def format_review(self, review: ReviewResult) -> str:
        e = review.element
        return (
            f"# AI Review: {e.name}\n\n"
            f"- File: `{e.file_path}`\n"
            f"- Type: `{e.type.value}`\n"
            f"- Model: `{review.model}`\n"
            f"- Provider: `{review.provider}`\n"
            f"- Tokens(est): `{review.tokens_used}`\n"
            f"- Time: `{review.timestamp.isoformat()}`\n\n"
            f"## Review\n\n"
            f"{review.review_text.strip()}\n"
        )

    def format_summary(self, summary: ReviewSummary) -> str:
        lines = [
            "# AI Review Summary",
            "",
            f"- Total reviewed elements: **{summary.total_elements}**",
            f"- Saved: **{summary.saved_count}**",
            f"- Success rate: **{summary.success_rate:.1%}**",
            f"- Duration: **{summary.duration:.2f}s**",
            f"- LLM requests: **{summary.metrics.get('llm_requests', 0)}**",
            f"- Tokens used(est): **{summary.metrics.get('tokens_used', 0)}**",
            "",
        ]
        if summary.warnings:
            lines += ["## Warnings", ""] + [f"- {w}" for w in summary.warnings] + [""]

        if summary.errors:
            lines += ["## Errors (first 10)", ""]
            for e in summary.errors[:10]:
                lines.append(f"- **{getattr(e, 'stage', '?')}**: {getattr(e, 'error', e)}")
            lines.append("")
        return "\n".join(lines) + "\n"
