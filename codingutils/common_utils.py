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
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from functools import wraps


# ============================================================================
# Configuration Classes
# ============================================================================

@dataclass(slots=True)
class FilterConfig:
    """Configuration for file filtering across scripts."""

    # Input roots (kept here because CLI tools in this repo pass it via config)
    directories: List[str] = field(default_factory=list)

    exclude_dirs: Set[str] = field(default_factory=set)
    exclude_names: Set[str] = field(default_factory=set)
    exclude_patterns: Set[str] = field(default_factory=set)

    include_pattern: str = "*"
    max_depth: Optional[int] = None

    follow_symlinks: bool = False

    # .gitignore support
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
        # Cache key includes file-type marker to reduce stale results when node type changes.
        self._cache: Dict[str, bool] = {}

    def load_from_file(self, gitignore_path: Optional[Path] = None) -> bool:
        """
        Load patterns from .gitignore file(s).

        If `gitignore_path` is None, auto-discovers .gitignore in root_dir and parents.
        """
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
        """
        Return True if path should be ignored based on loaded patterns.

        `path` is expected to be an absolute path or a path under root_dir.
        """
        # We intentionally use filesystem info here; caller code walks real FS.
        is_dir = path.is_dir()
        cache_key = f"{str(path)}|{'d' if is_dir else 'f'}"
        if cache_key in self._cache:
            return self._cache[cache_key]

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
        """
        Match gitignore-like pattern against a relative posix path.
        """
        if not pattern:
            return False

        # Directory-only pattern
        if pattern.endswith("/"):
            dir_pat = pattern.rstrip("/")
            # If pattern is just "node_modules/" (no slash inside), match any directory segment with that name.
            if "/" not in dir_pat.lstrip("/"):
                needle = dir_pat.lstrip("/")
                # Matches the directory itself OR any descendant of it.
                return needle in rel_parts
            # Multi-segment dir pattern: treat as anchored path pattern and check if rel path has such prefix.
            dir_pat_norm = dir_pat.lstrip("/")
            return self._match_path_segments(rel_parts, dir_pat_norm.split("/"), anchored=pattern.startswith("/"))

        # Non-directory pattern
        if "/" not in pattern.lstrip("/"):
            # Basename-style pattern: apply to file/dir name only
            name = rel_parts[-1] if rel_parts else ""
            return fnmatch.fnmatchcase(name, pattern.lstrip("/"))

        # Path pattern (contains '/')
        anchored = pattern.startswith("/")
        pat_parts = pattern.lstrip("/").split("/")
        return self._match_path_segments(rel_parts, pat_parts, anchored=anchored)

    def _match_path_segments(self, path_parts: List[str], pat_parts: List[str], *, anchored: bool) -> bool:
        """
        Segment-based glob matching where '*' doesn't cross '/' and '**' matches any number of segments.

        anchored=True means pattern is matched from the start of the path.
        anchored=False still matches from start here (repo tools use root-relative semantics),
        but we keep this flag for future extension.
        """
        # Anchored vs non-anchored: for now both are root-relative; to implement "match anywhere",
        # we would need to slide over start indices. Not required for current tools/tests.
        if not anchored and False:  # reserved for future
            pass

        i = j = 0
        # Backtracking points for '**'
        star_i = star_j = -1

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
                # Expand '**' to cover one more segment
                star_i += 1
                i = star_i
                j = star_j + 1
                continue

            return False

        # Consume trailing '**'
        while j < len(pat_parts) and pat_parts[j] == "**":
            j += 1

        return j == len(pat_parts)


# ============================================================================
# File System Utilities
# ============================================================================

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

    def find_files(self, root_dirs: Sequence[Path], *, recursive: Optional[bool] = None) -> List[Path]:
        """
        Find files matching criteria.

        `recursive` is kept for backward compatibility with callers in this repo.
        If None, uses self.config.recursive.
        """
        self._roots = [p.resolve() for p in root_dirs]
        self._reset_stats()

        do_recursive = self.config.recursive if recursive is None else recursive

        files: List[Path] = []
        for root in self._roots:
            if not root.exists():
                logging.warning("Directory does not exist: %s", root)
                continue
            if root.is_file():
                # Allow passing a file directly as root
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

        # Unique + stable order
        return sorted(set(files))

    def _reset_stats(self) -> None:
        for k in self.stats:
            self.stats[k] = 0

    def _walk_recursive(self, root_dir: Path) -> List[Path]:
        """
        Walk directory tree.

        Depth convention:
        - root_dir children (files/dirs directly inside) are at depth=1
        """
        results: List[Path] = []
        stack: List[Tuple[Path, int]] = [(root_dir, 0)]  # (dir, depth_of_dir)

        while stack:
            current_dir, depth = stack.pop()

            # Do not descend past max depth
            if self.config.max_depth is not None and depth > self.config.max_depth:
                continue

            try:
                for item in current_dir.iterdir():
                    # Handle symlinks
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
                        # next directory depth = depth + 1
                        stack.append((item, depth + 1))
                        continue

                    # It's a file
                    self.stats["files_found"] += 1

                    # Files are considered at (depth + 1)
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
        """Walk a single directory (non-recursive)."""
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

    def _should_exclude(self, path: Path, *, is_dir: bool) -> bool:
        """Return True if path should be excluded by config/gitignore rules."""
        # gitignore
        if self.gitignore_parser and self.gitignore_parser.should_ignore(path):
            return True

        # exclude dirs by name (match any segment)
        if is_dir and self.config.exclude_dirs:
            # path.parts includes drive on Windows; ok.
            for d in self.config.exclude_dirs:
                if d and d in path.parts:
                    return True

        # exclude names (wildcards against basename)
        if self.config.exclude_names:
            for pat in self.config.exclude_names:
                if fnmatch.fnmatchcase(path.name, pat):
                    return True

        # exclude patterns (match both basename and root-relative path)
        if self.config.exclude_patterns:
            rel = self._relative_to_nearest_root(path).as_posix()
            for pat in self.config.exclude_patterns:
                if fnmatch.fnmatchcase(path.name, pat) or fnmatch.fnmatchcase(rel, pat):
                    return True

        # include pattern applies only to files
        if not is_dir and not fnmatch.fnmatchcase(path.name, self.config.include_pattern):
            return True

        return False

    def _relative_to_nearest_root(self, path: Path) -> Path:
        """
        Compute path relative to the nearest root used in `find_files()`.
        Falls back to cwd-relative, then absolute.
        """
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

    # Note: Python triple quotes are docstrings/strings, not comments.
    # Kept as-is for backward compatibility with existing tools/tests in this repo.
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
        """
        Detect if file is text or binary.

        Heuristic:
        - Known binary extension => BINARY
        - Contains NUL byte in first 4KB => BINARY
        - UTF-8 decodable sample => TEXT
        - Otherwise => UNKNOWN
        """
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
        """
        Detect file encoding with a simple trial strategy.

        Returns one of the tried encodings; falls back to latin-1 (never fails).
        """
        encodings = ("utf-8", "latin-1", "cp1252", "utf-16")
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc) as f:
                    f.read(2048)
                return enc
            except UnicodeDecodeError:
                continue
            except Exception:
                # If file can't be read, default to utf-8 to reduce surprises.
                return "utf-8"
        return "latin-1"


# ============================================================================
# Safe File Operations
# ============================================================================

class SafeFileProcessor:
    """
    Context manager for safe file operations with optional backup.

    Behavior:
    - If backup=True and file exists, creates <name><suffix>.bak
    - If exception occurs inside context, restores original from backup
    - On success, removes backup unless keep_backup=True
    """

    def __init__(self, file_path: Path, *, backup: bool = True, keep_backup: bool = False) -> None:
        self.file_path = Path(file_path)
        self.backup = backup
        self.keep_backup = keep_backup
        self.backup_path: Optional[Path] = None

    def __enter__(self) -> "SafeFileProcessor":
        if self.backup and self.file_path.exists():
            self.backup_path = self.file_path.with_suffix(self.file_path.suffix + ".bak")
            shutil.copy2(self.file_path, self.backup_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # Restore from backup on error
        if exc_type is not None and self.backup_path and self.backup_path.exists():
            try:
                shutil.copy2(self.backup_path, self.file_path)
            finally:
                # keep backup on error? usually no; keep it for inspection if requested
                if not self.keep_backup:
                    try:
                        self.backup_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            logging.error("Error processing %s. Restored from backup.", self.file_path)
            return False  # re-raise

        # On success: cleanup backup if requested
        if self.backup_path and self.backup_path.exists() and not self.keep_backup:
            try:
                self.backup_path.unlink()
            except Exception:
                # Don't fail successful operation due to inability to delete .bak
                logging.debug("Failed to delete backup file: %s", self.backup_path)

        return False  # don't suppress exceptions


def safe_write(
    file_path: Path,
    content: str,
    encoding: str = "utf-8",
    backup: bool = True,
    *,
    keep_backup: bool = False,
) -> bool:
    """
    Safely write content to a file with optional backup and atomic replace.

    - Creates parent dirs if missing
    - Writes to a temporary file in the same directory
    - Atomically replaces the target
    - If error occurs, restores from backup (if created)
    """
    file_path = Path(file_path)
    tmp_path = file_path.with_name(file_path.name + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with SafeFileProcessor(file_path, backup=backup, keep_backup=keep_backup):
            with open(tmp_path, "w", encoding=encoding, newline="") as f:
                f.write(content)
                f.flush()
                try:
                    # Best effort (works on real files)
                    import os
                    os.fsync(f.fileno())
                except Exception:
                    pass

            # Atomic replace on most platforms
            tmp_path.replace(file_path)

        return True
    except Exception as e:
        logging.error("Failed to write %s: %s", file_path, e)
        return False
    finally:
        # Cleanup tmp if it still exists
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


# ============================================================================
# Progress Reporting
# ============================================================================

class ProgressReporter:
    """Report progress for long-running operations."""

    def __init__(self, total: int, description: str = "Processing", *, stream=None) -> None:
        self.total = max(0, int(total))
        self.description = description
        self.current = 0
        self.start_time: Optional[float] = None
        self.stream = stream or sys.stdout

        # Only draw a bar if we're on an interactive terminal
        try:
            self._enabled = self.stream.isatty() and self.total > 0
        except Exception:
            self._enabled = self.total > 0

    def __enter__(self) -> "ProgressReporter":
        self.start_time = time.time()
        self._print_progress()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.start_time is None:
            return
        elapsed = time.time() - self.start_time
        if self.total > 0:
            # Ensure final state is printed (especially if disabled bar)
            if not self._enabled:
                self.stream.write(f"{self.description}: {self.current}/{self.total}\n")
            self.stream.write(f"{self.description} completed in {elapsed:.2f}s\n")
            self.stream.flush()

    def update(self, increment: int = 1) -> None:
        if self.total <= 0:
            return
        self.current = min(self.total, self.current + max(0, int(increment)))
        self._print_progress()

    def _print_progress(self) -> None:
        if self.total <= 0:
            return

        if not self._enabled:
            return

        percent = (self.current / self.total) * 100.0
        bar_length = 40
        filled = int(bar_length * self.current // self.total)
        bar = "█" * filled + "░" * (bar_length - filled)

        self.stream.write(
            f"\r{self.description}: |{bar}| {percent:.1f}% ({self.current}/{self.total})"
        )
        self.stream.flush()


# ============================================================================
# Utility Functions
# ============================================================================

def format_size(size_bytes: int) -> str:
    """Format byte size in a human-readable form."""
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
    """
    Decorator to normalize common file operation errors.

    NOTE: Kept backward-compatible with existing tests in this repo:
    - FileNotFoundError / UnicodeDecodeError => log + return None
    - PermissionError => raise PermissionDeniedError
    - Other exceptions => logged and re-raised
    """
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
    # Configuration
    "FilterConfig",
    "FileType",
    # GitIgnore
    "GitIgnoreParser",
    # File System
    "FileSystemWalker",
    # Content Detection
    "FileContentDetector",
    # Safe Operations
    "SafeFileProcessor",
    "safe_write",
    # Progress
    "ProgressReporter",
    # Utilities
    "format_size",
    "get_relative_path",
    "create_directory_header",
    # Error Handling
    "FileOperationError",
    "PermissionDeniedError",
    "InvalidFileTypeError",
    "handle_file_errors",
]
