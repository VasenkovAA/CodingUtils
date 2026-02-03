from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

import yaml

from codingutils.common_utils import FilterConfig

from .models.config import AIReviewConfig, LLMConfig, OutputConfig, ProcessingConfig, PromptConfig
from .models.domain import ReviewMethod

logger = logging.getLogger(__name__)


DEFAULT_CONFIG_FILENAMES = (".codingutils.yaml", ".codingutils.yml")


def find_config_file(start_dir: Optional[Path] = None) -> Optional[Path]:
    current = (start_dir or Path.cwd()).resolve()
    while True:
        for name in DEFAULT_CONFIG_FILENAMES:
            candidate = current / name
            if candidate.exists() and candidate.is_file():
                return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge dictionaries recursively:
    override wins. Lists are replaced entirely.
    """
    out = dict(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_profile(doc: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    profiles = doc.get("profiles") or {}
    if profile_name not in profiles:
        raise KeyError(f"Profile '{profile_name}' not found in config")

    visiting = set()

    def build(name: str) -> Dict[str, Any]:
        if name in visiting:
            raise ValueError(f"Cyclic 'extends' detected at profile '{name}'")
        visiting.add(name)

        node = dict(profiles.get(name) or {})
        parent = node.get("extends")
        if parent:
            parent_cfg = build(parent)

            merged = _deep_merge(parent_cfg, node)
        else:
            merged = node

        visiting.remove(name)
        return merged

    return build(profile_name)


def _normalize_keys(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map YAML schema to dataclass schema (best-effort).
    Example: output.directory -> output.output_dir
    """
    cfg = dict(cfg)

    output = dict(cfg.get("output") or {})
    if "directory" in output and "output_dir" not in output:
        output["output_dir"] = output.pop("directory")
    cfg["output"] = output


    llm = dict(cfg.get("llm") or {})
    if "max_tokens" in llm and "max_output_tokens" not in llm:
        llm["max_output_tokens"] = llm.pop("max_tokens")
    cfg["llm"] = llm

    processing = dict(cfg.get("processing") or {})

    cfg["processing"] = processing

    return cfg


def _warn_unknown_keys(where: str, data: Dict[str, Any], allowed: Tuple[str, ...]) -> None:
    for k in data.keys():
        if k not in allowed:
            logger.warning("Unknown config key ignored (%s): %s", where, k)


def _parse_filter_config(merged: Dict[str, Any], *, directories: Optional[list] = None) -> FilterConfig:
    directories = directories or merged.get("directories") or ["."]
    include_patterns = merged.get("include_patterns") or []
    if isinstance(include_patterns, str):
        include_patterns = [include_patterns]

    include_pattern = str(merged.get("include_pattern") or "*")
    if include_patterns:
        include_pattern = "*"

    return FilterConfig(
        directories=list(directories),
        exclude_dirs=set(merged.get("exclude_dirs") or []),
        exclude_names=set(merged.get("exclude_names") or []),
        exclude_patterns=set(merged.get("exclude_patterns") or []),
        include_pattern=include_pattern,
        max_depth=merged.get("max_depth"),
        follow_symlinks=bool(merged.get("follow_symlinks") or False),
        use_gitignore=bool(merged.get("use_gitignore") or False),
        custom_gitignore=Path(merged["custom_gitignore"]) if merged.get("custom_gitignore") else None,
        recursive=bool(merged.get("recursive") if "recursive" in merged else True),
    )


def _to_review_method(value: Any) -> ReviewMethod:
    if isinstance(value, ReviewMethod):
        return value
    if isinstance(value, str):
        return ReviewMethod(value)
    return ReviewMethod.FUNCTIONS


def load_ai_review_config(
    *,
    config_path: Optional[Path] = None,
    profile: Optional[str] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
    start_dir: Optional[Path] = None,
    directories: Optional[list] = None,
) -> AIReviewConfig:
    """
    Load config from YAML + profile + CLI overrides.
    Priority: CLI > profile > globals.
    Unknown keys => warning.
    """
    path = config_path or find_config_file(start_dir)
    doc: Dict[str, Any] = {}
    config_dir = None
    if path:
        doc = load_yaml(path)
        config_dir = path.parent

    globals_cfg = doc.get("globals") or {}
        # Support top-level `plugins:` (not under globals) as global defaults.
    # This is needed for configs like:
    # plugins:
    #   auto_discover: true
    #   plugin_dirs: [...]
    root_plugins = doc.get("plugins") or {}
    if root_plugins:
        # root_plugins -> base, globals_cfg -> override
        globals_cfg = _deep_merge({"plugins": root_plugins}, globals_cfg)
    profile_cfg: Dict[str, Any] = {}
    if profile:
        profile_cfg = _resolve_profile(doc, profile)

    merged = _deep_merge(globals_cfg, profile_cfg)
    merged = _deep_merge(merged, cli_overrides or {})
    merged = _normalize_keys(merged)


    _warn_unknown_keys(
        "root",
        merged,
        allowed=(
            "directories",
            "exclude_dirs",
            "exclude_names",
            "exclude_patterns",
            "include_pattern",
            "include_patterns",
            "max_depth",
            "follow_symlinks",
            "use_gitignore",
            "custom_gitignore",
            "recursive",
            "llm",
            "prompt",
            "processing",
            "output",
            "plugins",
            "description",
            "extends",
        ),
    )


    def resolve_maybe_path(s: Any) -> Any:
        if not config_dir:
            return s
        if not isinstance(s, str):
            return s
        if "\n" in s:
            return s
        p = Path(s)
        if p.is_absolute():
            return str(p)

        if ("/" in s or "\\" in s or p.suffix in (".md", ".txt", ".yaml", ".yml")):
            return str((config_dir / p).resolve())
        return s

    llm_dict = dict(merged.get("llm") or {})
    prompt_dict = dict(merged.get("prompt") or {})
    processing_dict = dict(merged.get("processing") or {})
    output_dict = dict(merged.get("output") or {})

    prompt_dict["system_prompt"] = resolve_maybe_path(prompt_dict.get("system_prompt"))
    prompt_dict["user_prompt"] = resolve_maybe_path(prompt_dict.get("user_prompt", "prompts/default.txt"))

    if "output_dir" in output_dict:
        output_dict["output_dir"] = Path(resolve_maybe_path(output_dict["output_dir"]))

    if "custom_gitignore" in merged and merged["custom_gitignore"]:
        merged["custom_gitignore"] = resolve_maybe_path(merged["custom_gitignore"])

    filter_config = _parse_filter_config(merged, directories=directories)

    llm = LLMConfig(**llm_dict) if llm_dict else LLMConfig()
    prompt = PromptConfig(**prompt_dict) if prompt_dict else PromptConfig()
    processing = ProcessingConfig(**processing_dict) if processing_dict else ProcessingConfig()
    processing.method = _to_review_method(processing_dict.get("method", processing.method))
    output = OutputConfig(**output_dict) if output_dict else OutputConfig()

    formatter_plugin = merged.get("formatter_plugin") or merged.get("output", {}).get("formatter") or "markdown"
    include_patterns = merged.get("include_patterns") or []
    if isinstance(include_patterns, str):
        include_patterns = [include_patterns]
    plugins_cfg = dict(merged.get("plugins") or {})
    auto_discover = bool(plugins_cfg.get("auto_discover", True))
    plugin_dirs_raw = plugins_cfg.get("plugin_dirs") or []
    if isinstance(plugin_dirs_raw, str):
        plugin_dirs_raw = [plugin_dirs_raw]
    plugin_dirs = [Path(p).expanduser() for p in plugin_dirs_raw if isinstance(p, str) and p.strip()]
    # plugins
    plugins_cfg = dict(merged.get("plugins") or {})
    auto_discover = bool(plugins_cfg.get("auto_discover", True))
    plugin_dirs_raw = plugins_cfg.get("plugin_dirs") or []
    if isinstance(plugin_dirs_raw, str):
        plugin_dirs_raw = [plugin_dirs_raw]

    plugin_dirs: List[Path] = []
    for item in plugin_dirs_raw:
        if not isinstance(item, str) or not item.strip():
            continue
        p = Path(item).expanduser()
        if config_dir and not p.is_absolute():
            p = (config_dir / p).resolve()
        plugin_dirs.append(p)

    return AIReviewConfig(
        filter_config=filter_config,
        include_patterns=[p for p in include_patterns if isinstance(p, str) and p.strip()],
        auto_discover_plugins=auto_discover,
        plugin_dirs=plugin_dirs,
        llm=llm,
        prompt=prompt,
        processing=processing,
        output=output,
        parser_plugin=merged.get("parser_plugin"),
        formatter_plugin=formatter_plugin,
    )
