from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class NodeSelectMode(str, Enum):
    NONE = "none"
    FLAT = "flat"
    RECURSIVE = "recursive"


@dataclass(slots=True)
class CleanerSettings:
    # map abs_path -> mode
    selected_paths: Dict[Path, NodeSelectMode] = field(default_factory=dict)

    include_patterns: str = "*"
    recursive_default: bool = True
    max_depth: Optional[int] = None

    exclude_dirs: List[str] = field(default_factory=list)
    exclude_names: List[str] = field(default_factory=list)
    exclude_path_patterns: List[str] = field(default_factory=list)

    use_gitignore: bool = False
    custom_gitignore: Optional[Path] = None
    ignore_gitignore: bool = False

    # comment syntax (Variant A, пока оставляем auto)
    syntax_mode: str = "auto"  # "auto" | "custom"
    custom_line_marker: str = ""
    custom_block_start: str = ""
    custom_block_end: str = ""
    custom_alt_block_start: str = ""
    custom_alt_block_end: str = ""

    exclude_comment_prefixes: List[str] = field(default_factory=list)

    use_langdetect: bool = False
    langdetect_language: str = ""
    min_langdetect_len: int = 20

    preserve_line_count: bool = False
    incremental_by_mtime: bool = False

    decisions_path: Path = Path(".codingutils/comment_cleaner.json")

    # pagination
    page_size: int = 350

    # diff / apply / backups
    enable_preview_diff: bool = True
    # If True, first Apply (F8) only builds diff and switches to Diff tab; second F8 writes files.
    preview_diff_before_apply: bool = True
    diff_max_kb_per_file: int = 200

    make_backups: bool = False
    backup_dir: Path = Path(".codingutils/backups")
    overwrite_backups: bool = False

    # export
    export_path: Path = Path(".codingutils/comment_cleaner_report.json")
    export_format: str = "json"  # "txt" | "json" | "jsonl"


@dataclass(slots=True)
class CommentItem:
    id: str
    file_path: Path
    rel_path: str
    cell_index: Optional[int]
    kind: str  # "line" | "block" | "line_group"
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    raw: str
    text: str

    signature: str
    decision_key: str  # "cell:<idx>|sig:<hash>"

    excluded: bool = False
    excluded_reason: str = ""

    lang: str = ""
    is_new: bool = True
    delete: bool = False

    context_cached: Optional[str] = None


@dataclass(slots=True)
class FileRecord:
    file_path: Path
    rel_path: str

    total: int = 0
    excluded: int = 0
    new: int = 0
    to_delete: int = 0

    comments: List[CommentItem] = field(default_factory=list)

    visible_count: int = 0


@dataclass(slots=True)
class ScanResult:
    files: Dict[str, FileRecord]  # rel_path -> record
    total_files: int
    total_comments: int
    scan_errors: List[str] = field(default_factory=list)