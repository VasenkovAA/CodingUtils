"""
Common utilities for file-processing scripts.

Includes:
- Shared filtering config
- .gitignore-style ignore parser (simplified but predictable semantics)
- File system walker with filtering & stats
- File type / encoding detection
- Safe write with backup (atomic replace)
- Progress reporting
- Small helpers and error-handling utilities
"""

from __future__ import annotations

import fnmatch
import logging
import shutil
import sys
import time
import shlex
from collections.abc import Mapping as ABCMapping
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


# ============================================================================
# Configuration Classes
# ============================================================================

@dataclass(slots=True)
class FilterConfig:
    """Configuration for file filtering across scripts."""

    directories: List[str] = field(default_factory=list)

    exclude_dirs: Set[str] = field(default_factory=set)
    exclude_names: Set[str] = field(default_factory=set)
    exclude_patterns: Set[str] = field(default_factory=set)

    include_pattern: str = "*"
    max_depth: Optional[int] = None

    follow_symlinks: bool = False

    use_gitignore: bool = False
    custom_gitignore: Optional[Path] = None

    recursive: bool = True

    def __post_init__(self) -> None:
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")


class FileType(Enum):
    """File type classification."""
    TEXT = "text"
    BINARY = "binary"
    UNKNOWN = "unknown"


# ============================================================================
# GitIgnore Parser (simplified semantics)
# ============================================================================

class GitIgnoreParser:
    """
    Simplified .gitignore parser.

    Notes:
    - Supports: comments (# at beginning), blank lines, negation (!), directory patterns (ending with '/')
    - Supports glob tokens: *, ?, [], and ** (as "any directories")
    - Matching is done against a posix-style relative path from `root_dir`
    - This is not a full reimplementation of gitignore, but stable and testable.
    """

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.patterns: List[str] = []
        self._cache: Dict[str, bool] = {}

    def load_from_file(self, gitignore_path: Optional[Path] = None) -> bool:
        if gitignore_path is not None:
            loaded = self._parse_single_file(gitignore_path)
            if loaded:
                self._cache.clear()
            return loaded

        found = False
        for p in self._discover_gitignore_files():
            if self._parse_single_file(p):
                found = True

        if found:
            self._cache.clear()
        return found

    def _discover_gitignore_files(self) -> Iterable[Path]:
        current = self.root_dir
        while True:
            candidate = current / ".gitignore"
            if candidate.exists():
                yield candidate
            parent = current.parent
            if parent == current:
                break
            current = parent

    def _parse_single_file(self, gitignore_path: Path) -> bool:
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    self.patterns.append(line)
            return True
        except Exception as e:
            logging.warning("Could not parse %s: %s", gitignore_path, e)
            return False

    def add_pattern(self, pattern: str) -> None:
        self.patterns.append(pattern)
        self._cache.clear()

    def should_ignore(self, path: Path) -> bool:
        cache_key = str(path)
        if cache_key in self._cache:
            return self._cache[cache_key]

        is_dir = path.is_dir()

        try:
            rel_path = path.resolve().relative_to(self.root_dir)
        except Exception:
            self._cache[cache_key] = False
            return False

        rel_str = rel_path.as_posix()
        rel_parts = rel_str.split("/") if rel_str else []

        ignored = False
        for pattern in self.patterns:
            negated = pattern.startswith("!")
            pat = pattern[1:] if negated else pattern

            if self._match(rel_str, rel_parts, pat, is_dir=is_dir):
                ignored = not negated

        self._cache[cache_key] = ignored
        return ignored

    def _match(self, rel_str: str, rel_parts: List[str], pattern: str, *, is_dir: bool) -> bool:
        if not pattern:
            return False

        if pattern.endswith("/"):
            dir_pat = pattern.rstrip("/")

            if "/" not in dir_pat.lstrip("/"):
                needle = dir_pat.lstrip("/")
                if is_dir:
                    return needle in rel_parts
                return needle in rel_parts[:-1]

            dir_parts = dir_pat.lstrip("/").split("/")
            anchored = pattern.startswith("/")

            parts_to_match = rel_parts if is_dir else rel_parts[:-1]
            return self._match_path_segments_prefix(parts_to_match, dir_parts, anchored=anchored)

        if "/" not in pattern.lstrip("/"):
            name = rel_parts[-1] if rel_parts else ""
            return fnmatch.fnmatchcase(name, pattern.lstrip("/"))

        anchored = pattern.startswith("/")
        pat_parts = pattern.lstrip("/").split("/")
        return self._match_path_segments(rel_parts, pat_parts, anchored=anchored)

    def _match_path_segments_prefix(self, path_parts: List[str], prefix_parts: List[str], *, anchored: bool) -> bool:
        if anchored:
            if len(path_parts) < len(prefix_parts):
                return False
            for i, pat in enumerate(prefix_parts):
                if not fnmatch.fnmatchcase(path_parts[i], pat):
                    return False
            return True

        if not prefix_parts:
            return False
        for start in range(0, len(path_parts) - len(prefix_parts) + 1):
            ok = True
            for i, pat in enumerate(prefix_parts):
                if not fnmatch.fnmatchcase(path_parts[start + i], pat):
                    ok = False
                    break
            if ok:
                return True
        return False

    def _match_path_segments(self, path_parts: List[str], pat_parts: List[str], *, anchored: bool) -> bool:
        _ = anchored

        i = j = 0
        star_i = star_j = -1  # backtracking points for '**'

        while i < len(path_parts):
            if j < len(pat_parts) and pat_parts[j] == "**":
                star_i, star_j = i, j
                j += 1
                continue

            if j < len(pat_parts) and fnmatch.fnmatchcase(path_parts[i], pat_parts[j]):
                i += 1
                j += 1
                continue

            if star_j != -1:
                star_i += 1
                i = star_i
                j = star_j + 1
                continue

            return False

        while j < len(pat_parts) and pat_parts[j] == "**":
            j += 1

        return j == len(pat_parts)


# ============================================================================
# File System Utilities
# ============================================================================

def _normalize_include_patterns(value: object) -> List[str]:
    """
    Normalize include patterns.

    Backward compatible:
    - config.include_pattern historically was a string, e.g. "*.py"
    Now we also support multiple patterns encoded as:
    - "*.py *.txt *.*" (space-separated)
    - ["*.py", "*.txt"] (if someone passes a list)
    """
    if value is None:
        return ["*"]

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return ["*"]
        # allow both quoted and non-quoted multi patterns
        try:
            parts = shlex.split(s)
        except ValueError:
            parts = s.split()
        parts = [p.strip() for p in parts if p.strip()]
        return parts or ["*"]

    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            out.extend(_normalize_include_patterns(item))
        return out or ["*"]

    return [str(value)]


class FileSystemWalker:
    """Efficient file system traversal with filtering and stats."""

    def __init__(self, config: FilterConfig, gitignore_parser: Optional[GitIgnoreParser] = None) -> None:
        self.config = config
        self.gitignore_parser = gitignore_parser
        self.stats: Dict[str, int] = {
            "files_found": 0,
            "directories_found": 0,
            "files_excluded": 0,
            "directories_excluded": 0,
        }
        self._roots: List[Path] = []

        # cache for include patterns to avoid shlex per file
        self._include_patterns_cache_key: object = object()
        self._include_patterns_cache_value: List[str] = ["*"]

    def find_files(self, root_dirs: Sequence[Path], *, recursive: Optional[object] = None) -> List[Path]:
        """
        Find files matching criteria.

        Backward compatible:
        - recursive=None: uses self.config.recursive
        - recursive=bool: apply to all roots

        Extended (additive):
        - recursive can be a mapping {root_path: bool} for per-root recursion.
          Keys may be Path or str; matching is done against resolved root paths.
        """
        self._roots = [p.resolve() for p in root_dirs]
        self._reset_stats()

        rec_map_resolved: Optional[Dict[str, bool]] = None
        do_recursive_global: bool

        if isinstance(recursive, ABCMapping):
            rec_map_resolved = {}
            for k, v in recursive.items():
                try:
                    rk = Path(k).resolve()
                    rec_map_resolved[str(rk)] = bool(v)
                except Exception:
                    rec_map_resolved[str(k)] = bool(v)
            do_recursive_global = self.config.recursive
        else:
            do_recursive_global = self.config.recursive if recursive is None else bool(recursive)

        files: List[Path] = []
        for root in self._roots:
            if not root.exists():
                logging.warning("Directory does not exist: %s", root)
                continue

            # choose recursion for this root
            if rec_map_resolved is not None:
                do_recursive = rec_map_resolved.get(str(root.resolve()), do_recursive_global)
            else:
                do_recursive = do_recursive_global

            if root.is_file():
                self.stats["files_found"] += 1
                if not self._should_exclude(root, is_dir=False):
                    files.append(root)
                else:
                    self.stats["files_excluded"] += 1
                continue

            if do_recursive:
                files.extend(self._walk_recursive(root))
            else:
                files.extend(self._walk_single(root))

        return sorted(set(files))

    def _reset_stats(self) -> None:
        for k in self.stats:
            self.stats[k] = 0

    def _walk_recursive(self, root_dir: Path) -> List[Path]:
        results: List[Path] = []
        stack: List[Tuple[Path, int]] = [(root_dir, 0)]  # (dir, depth_of_dir)

        while stack:
            current_dir, depth = stack.pop()

            if self.config.max_depth is not None and depth > self.config.max_depth:
                continue

            try:
                for item in current_dir.iterdir():
                    if item.is_symlink() and not self.config.follow_symlinks:
                        continue

                    if item.is_symlink() and self.config.follow_symlinks:
                        try:
                            item = item.resolve()
                        except Exception:
                            continue

                    if item.is_dir():
                        self.stats["directories_found"] += 1
                        if self._should_exclude(item, is_dir=True):
                            self.stats["directories_excluded"] += 1
                            continue
                        stack.append((item, depth + 1))
                        continue

                    self.stats["files_found"] += 1

                    if self.config.max_depth is not None and (depth + 1) > self.config.max_depth:
                        self.stats["files_excluded"] += 1
                        continue

                    if self._should_exclude(item, is_dir=False):
                        self.stats["files_excluded"] += 1
                        continue

                    results.append(item)

            except PermissionError:
                logging.debug("Permission denied: %s", current_dir)
            except Exception as e:
                logging.debug("Error accessing %s: %s", current_dir, e)

        return results

    def _walk_single(self, directory: Path) -> List[Path]:
        results: List[Path] = []
        try:
            for item in directory.iterdir():
                if not item.is_file():
                    continue
                self.stats["files_found"] += 1
                if self._should_exclude(item, is_dir=False):
                    self.stats["files_excluded"] += 1
                    continue
                results.append(item)
        except PermissionError:
            logging.debug("Permission denied: %s", directory)
        return results

    def _get_include_patterns(self) -> List[str]:
        key = self.config.include_pattern
        if key is self._include_patterns_cache_key:
            return self._include_patterns_cache_value
        pats = _normalize_include_patterns(key)
        self._include_patterns_cache_key = key
        self._include_patterns_cache_value = pats
        return pats

    def _should_exclude(self, path: Path, *, is_dir: bool) -> bool:
        if self.gitignore_parser and self.gitignore_parser.should_ignore(path):
            return True

        if is_dir and self.config.exclude_dirs:
            for d in self.config.exclude_dirs:
                if d and d in path.parts:
                    return True

        if self.config.exclude_names:
            for pat in self.config.exclude_names:
                if fnmatch.fnmatchcase(path.name, pat):
                    return True

        if self.config.exclude_patterns:
            rel = self._relative_to_nearest_root(path).as_posix()
            for pat in self.config.exclude_patterns:
                if fnmatch.fnmatchcase(path.name, pat) or fnmatch.fnmatchcase(rel, pat):
                    return True

        # include patterns only apply to files
        if not is_dir:
            patterns = self._get_include_patterns()
            if not any(fnmatch.fnmatchcase(path.name, pat) for pat in patterns):
                return True

        return False

    def _relative_to_nearest_root(self, path: Path) -> Path:
        p = path.resolve()
        for r in self._roots:
            try:
                return p.relative_to(r)
            except Exception:
                continue
        try:
            return p.relative_to(Path.cwd().resolve())
        except Exception:
            return p


# ============================================================================
# File Content Utilities
# ============================================================================

class FileContentDetector:
    """Detect file content type and encoding."""

    BINARY_EXTENSIONS: Set[str] = {
        ".exe", ".dll", ".so", ".dylib", ".bin",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".tar", ".gz", ".rar", ".7z",
        ".mp3", ".mp4", ".avi", ".mkv", ".mov",
    }

    COMMENT_STYLES: Dict[str, Dict[str, object]] = {
        ".py": {"line": "#", "block": ('"""', '"""'), "alt_block": ("'''", "'''")},
        ".java": {"line": "//", "block": ("/*", "*/")},
        ".cpp": {"line": "//", "block": ("/*", "*/")},
        ".c": {"line": "//", "block": ("/*", "*/")},
        ".js": {"line": "//", "block": ("/*", "*/")},
        ".ts": {"line": "//", "block": ("/*", "*/")},
        ".go": {"line": "//", "block": ("/*", "*/")},
        ".rs": {"line": "//", "block": ("/*", "*/")},
        ".rb": {"line": "#", "block": ("=begin", "=end")},
        ".sh": {"line": "#"},
        ".pl": {"line": "#"},
        ".php": {"line": "//", "block": ("/*", "*/")},
        ".sql": {"line": "--", "block": ("/*", "*/")},
        ".html": {"block": ("<!--", "-->")},
        ".css": {"block": ("/*", "*/")},
        ".xml": {"block": ("<!--", "-->")},
    }

    @classmethod
    def detect_file_type(cls, path: Path) -> FileType:
        if path.suffix.lower() in cls.BINARY_EXTENSIONS:
            return FileType.BINARY

        try:
            with open(path, "rb") as f:
                sample = f.read(4096)

            if b"\x00" in sample:
                return FileType.BINARY

            sample.decode("utf-8", errors="strict")
            return FileType.TEXT
        except Exception:
            return FileType.UNKNOWN

    @classmethod
    def get_comment_style(cls, path: Path) -> Optional[Dict[str, object]]:
        return cls.COMMENT_STYLES.get(path.suffix.lower())

    @classmethod
    def detect_encoding(cls, path: Path) -> str:
        encodings = ("utf-8", "latin-1", "cp1252", "utf-16")
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc) as f:
                    f.read(2048)
                return enc
            except UnicodeDecodeError:
                continue
            except Exception:
                return "utf-8"
        return "latin-1"


# ============================================================================
# Safe File Operations
# ============================================================================

class SafeFileProcessor:
    def __init__(self, file_path: Path, *, backup: bool = True, keep_backup: bool = False) -> None:
        self.file_path = Path(file_path)
        self.backup = backup
        self.keep_backup = keep_backup
        self.backup_path: Optional[Path] = None
        self.original_content: Optional[str] = None

    def __enter__(self) -> "SafeFileProcessor":
        if self.file_path.exists():
            try:
                self.original_content = self.file_path.read_text(encoding="utf-8")
            except Exception:
                self.original_content = None

        if self.backup and self.file_path.exists():
            self.backup_path = self.file_path.with_suffix(self.file_path.suffix + ".bak")
            shutil.copy2(self.file_path, self.backup_path)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None and self.backup_path and self.backup_path.exists():
            try:
                shutil.copy2(self.backup_path, self.file_path)
            finally:
                if not self.keep_backup:
                    try:
                        self.backup_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            logging.error("Error processing %s. Restored from backup.", self.file_path)
            return False

        if self.backup_path and self.backup_path.exists() and not self.keep_backup:
            try:
                self.backup_path.unlink()
            except Exception:
                logging.debug("Failed to delete backup file: %s", self.backup_path)

        return False


def safe_write(
    file_path: Path,
    content: str,
    encoding: str = "utf-8",
    backup: bool = True,
    *,
    keep_backup: bool = False,
) -> bool:
    file_path = Path(file_path)
    tmp_path = file_path.with_name(file_path.name + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with SafeFileProcessor(file_path, backup=backup, keep_backup=keep_backup):
            with open(tmp_path, "w", encoding=encoding, newline="") as f:
                f.write(content)
                f.flush()
                try:
                    import os
                    os.fsync(f.fileno())
                except Exception:
                    pass

            tmp_path.replace(file_path)

        return True
    except Exception as e:
        logging.error("Failed to write %s: %s", file_path, e)
        return False
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


# ============================================================================
# Progress Reporting
# ============================================================================

class ProgressReporter:
    def __init__(self, total: int, description: str = "Processing", *, stream=None) -> None:
        self.total = max(0, int(total))
        self.description = description
        self.current = 0
        self.start_time: Optional[float] = None
        self.stream = stream or sys.stdout

        try:
            self._isatty = bool(self.stream.isatty())
        except Exception:
            self._isatty = False

        self._enabled = self.total > 0

    def __enter__(self) -> "ProgressReporter":
        self.start_time = time.time()
        self._print_progress()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.start_time is None:
            return

        if self.total <= 0:
            return

        self.current = min(self.current, self.total)
        if self.current != self.total:
            self.current = self.total
        self._print_progress(final=True)

        elapsed = time.time() - self.start_time
        self.stream.write(f"{self.description} completed in {elapsed:.2f}s\n")
        self.stream.flush()

    def update(self, increment: int = 1) -> None:
        if self.total <= 0:
            return
        self.current = min(self.total, self.current + max(0, int(increment)))
        self._print_progress()

    def _print_progress(self, *, final: bool = False) -> None:
        if not self._enabled or self.total <= 0:
            return

        percent = (self.current / self.total) * 100.0

        if self._isatty:
            bar_length = 40
            filled = int(bar_length * self.current // self.total)
            bar = "█" * filled + "░" * (bar_length - filled)
            self.stream.write(
                f"\r{self.description}: |{bar}| {percent:.1f}% ({self.current}/{self.total})"
            )
            if final:
                self.stream.write("\n")
        else:
            self.stream.write(
                f"{self.description}: {percent:.1f}% ({self.current}/{self.total})\n"
            )

        self.stream.flush()


# ============================================================================
# Utility Functions
# ============================================================================

def format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"

    units = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)
    unit_idx = 0
    while size >= 1024.0 and unit_idx < len(units) - 1:
        size /= 1024.0
        unit_idx += 1
    return f"{size:.2f} {units[unit_idx]}"


def get_relative_path(path: Path, base_dir: Optional[Path] = None) -> str:
    base_dir = (base_dir or Path.cwd()).resolve()
    try:
        return str(path.resolve().relative_to(base_dir))
    except Exception:
        return str(path)


def create_directory_header(file_path: Path, base_dir: Optional[Path] = None) -> str:
    rel_path = get_relative_path(file_path, base_dir)
    sep = "=" * 60
    return f"\n{sep}\nFILE: {rel_path}\n{sep}\n"


# ============================================================================
# Error Handling
# ============================================================================

class FileOperationError(Exception):
    """Base exception for file operations."""


class PermissionDeniedError(FileOperationError):
    """Raised when permission is denied."""


class InvalidFileTypeError(FileOperationError):
    """Raised when file type is not supported."""


def handle_file_errors(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PermissionError as e:
            raise PermissionDeniedError(f"Permission denied: {e}") from e
        except FileNotFoundError as e:
            logging.warning("File not found: %s", e)
            return None
        except UnicodeDecodeError as e:
            logging.warning("Encoding error: %s", e)
            return None
        except Exception as e:
            logging.error("Unexpected error: %s", e)
            raise

    return wrapper


# ============================================================================
# Main Exports
# ============================================================================

__all__ = [
    "FilterConfig",
    "FileType",
    "GitIgnoreParser",
    "FileSystemWalker",
    "FileContentDetector",
    "SafeFileProcessor",
    "safe_write",
    "ProgressReporter",
    "format_size",
    "get_relative_path",
    "create_directory_header",
    "FileOperationError",
    "PermissionDeniedError",
    "InvalidFileTypeError",
    "handle_file_errors",
]
