from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


from codingutils.ai_review.core.config_loader import load_ai_review_config
from codingutils.ai_review.core.models.domain import ReviewMethod
from codingutils.ai_review.core.services import AIReviewService

logger = logging.getLogger(__name__)


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="codingutils ai-review",
        description="AI code review module",
    )

    # directories
    p.add_argument("directories", nargs="*", default=["."], help="Directories to review (default: .)")

    # FilterConfig-like
    p.add_argument("-p", "--pattern", default=None, help='Single include pattern (e.g. "*.py")')
    p.add_argument("--include", action="append", dest="include_patterns", help="Repeatable include pattern (YAML-list equivalent)")
    p.add_argument("-r", "--recursive", action="store_true", help="Recursive search")
    p.add_argument("--max-depth", type=int, default=None, help="Maximum recursion depth")

    p.add_argument("-ed", "--exclude-dir", action="append", dest="exclude_dirs", help="Exclude directory by name (repeatable)")
    p.add_argument("-en", "--exclude-name", action="append", dest="exclude_names", help="Exclude file by name/wildcard (repeatable)")
    p.add_argument("-ep", "--exclude-pattern", action="append", dest="exclude_patterns", help="Exclude by path wildcard (repeatable)")

    p.add_argument("-ig", "--use-gitignore", action="store_true", help="Auto-discover and use .gitignore")
    p.add_argument("--gitignore", type=Path, default=None, help="Use specific .gitignore file")

    # AI config
    p.add_argument("--config", type=Path, default=None, help="Config YAML file")
    p.add_argument("--profile", type=str, default=None, help="Profile name from config")

    p.add_argument("--method", choices=[m.value for m in ReviewMethod], default=None)

    p.add_argument("--llm-provider", dest="llm_provider", default=None, help="LLM provider (lmstudio/openai/mock/...)")
    p.add_argument("--model", default=None)
    p.add_argument("--api-base", default=None)
    p.add_argument("--api-key", default=None)

    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--max-output-tokens", type=int, default=None)
    p.add_argument("--context-window", type=int, default=None)

    p.add_argument("--system-prompt", type=str, default=None)
    p.add_argument("--user-prompt", type=str, default=None)
    p.add_argument("--include-context", action="store_true", default=None)
    p.add_argument("--context-file", action="append", dest="context_files", help="Repeatable glob pattern for extra context files")

    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--formatter", type=str, default=None)

    p.add_argument("--max-workers", type=int, default=None)
    p.add_argument("--max-input-tokens", type=int, default=None)
    p.add_argument("--batch-size", type=int, default=None)

    p.add_argument("--skip-unchanged", action="store_true", default=None)
    p.add_argument("--no-skip-unchanged", action="store_true", default=None)
    p.add_argument("--force", action="store_true", default=None)

    p.add_argument("--dry-run", action="store_true", help="Run with mock provider (no network LLM calls)")
    p.add_argument("--clean", action="store_true", help="Remove output directory and exit")

    p.add_argument("--verbose", action="store_true", help="Verbose logging")

    return p.parse_args(argv)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, handlers=[logging.StreamHandler(sys.stderr)], force=True)


def create_config(args: argparse.Namespace) -> Any:
    cli_overrides: Dict[str, Any] = {}

    # filter overrides
    if args.pattern is not None:
        cli_overrides["include_pattern"] = args.pattern
    if args.include_patterns:
        cli_overrides["include_patterns"] = args.include_patterns

    if args.exclude_dirs:
        cli_overrides["exclude_dirs"] = args.exclude_dirs
    if args.exclude_names:
        cli_overrides["exclude_names"] = args.exclude_names
    if args.exclude_patterns:
        cli_overrides["exclude_patterns"] = args.exclude_patterns

    if args.max_depth is not None:
        cli_overrides["max_depth"] = args.max_depth

    cli_overrides["recursive"] = bool(args.recursive)

    if args.use_gitignore:
        cli_overrides["use_gitignore"] = True
    if args.gitignore:
        cli_overrides["custom_gitignore"] = str(args.gitignore)

    # processing
    proc: Dict[str, Any] = {}
    if args.method is not None:
        proc["method"] = args.method
    if args.max_workers is not None:
        proc["max_workers"] = args.max_workers
    if args.max_input_tokens is not None:
        proc["max_input_tokens"] = args.max_input_tokens
    if args.batch_size is not None:
        proc["batch_size"] = args.batch_size

    if args.force is not None:
        proc["force"] = bool(args.force)

    if args.skip_unchanged:
        proc["skip_unchanged"] = True
    if args.no_skip_unchanged:
        proc["skip_unchanged"] = False

    if proc:
        cli_overrides["processing"] = proc

    # llm
    llm: Dict[str, Any] = {}
    if args.llm_provider is not None:
        llm["provider"] = args.llm_provider
    if args.model is not None:
        llm["model"] = args.model
    if args.api_base is not None:
        llm["api_base"] = args.api_base
    if args.api_key is not None:
        llm["api_key"] = args.api_key
    if args.temperature is not None:
        llm["temperature"] = args.temperature
    if args.max_output_tokens is not None:
        llm["max_output_tokens"] = args.max_output_tokens
    if args.context_window is not None:
        llm["context_window"] = args.context_window

    if llm:
        cli_overrides["llm"] = llm

    # prompt
    prompt: Dict[str, Any] = {}
    if args.system_prompt is not None:
        prompt["system_prompt"] = args.system_prompt
    if args.user_prompt is not None:
        prompt["user_prompt"] = args.user_prompt
    if args.include_context is not None and args.include_context:
        prompt["include_context"] = True
    if args.context_files:
        prompt["context_files"] = args.context_files
    if prompt:
        cli_overrides["prompt"] = prompt

    # output
    out: Dict[str, Any] = {}
    if args.output_dir is not None:
        out["output_dir"] = args.output_dir
    if args.formatter is not None:
        out["formatter"] = args.formatter
    if out:
        cli_overrides["output"] = out

    cfg = load_ai_review_config(
        config_path=args.config,
        profile=args.profile,
        cli_overrides=cli_overrides,
        directories=args.directories,
    )

    # dry-run => mock provider
    if args.dry_run:
        cfg.llm.provider = "mock"

    return cfg


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_arguments(argv)
    _configure_logging(bool(args.verbose))

    cfg = create_config(args)
    service = AIReviewService(cfg)

    if args.clean:
        ok = service.clean(everything=True)
        return 0 if ok else 1

    try:
        summary = service.review([Path(d) for d in args.directories])
        return 0 if summary.saved_count >= 0 else 1
    except KeyboardInterrupt:
        print("\nCancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        return 1
