"""
Common utilities for file processing scripts.
Handles .gitignore parsing, file filtering, and other shared functionality.
"""

import time
import fnmatch
import sys
import logging
from pathlib import Path
from typing import List, Optional, Set, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import shutil


# ============================================================================
# Configuration Classes
# ============================================================================

@dataclass
class FilterConfig:
    """Configuration for file filtering across all scripts."""
    exclude_dirs: Set[str] = field(default_factory=set)
    exclude_names: Set[str] = field(default_factory=set)
    exclude_patterns: Set[str] = field(default_factory=set)
    include_pattern: str = "*"
    max_depth: Optional[int] = None
    follow_symlinks: bool = False
    use_gitignore: bool = False
    custom_gitignore: Optional[Path] = None
    recursive: bool = True

    def __post_init__(self):
        """Validate and normalize configuration."""
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")


class FileType(Enum):
    """File type classification."""
    TEXT = "text"
    BINARY = "binary"
    UNKNOWN = "unknown"


# ============================================================================
# GitIgnore Parser
# ============================================================================

class GitIgnoreParser:
    """Unified .gitignore parser with proper pattern handling."""

    def __init__(self, root_dir: Optional[Path] = None):
        """
        Initialize parser.

        Args:
            root_dir: Root directory for relative paths. If None, uses current directory.
        """
        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.patterns: List[str] = []
        self._cache: Dict[str, bool] = {}

    def load_from_file(self, gitignore_path: Optional[Path] = None) -> bool:
        """
        Load patterns from .gitignore file(s).

        Args:
            gitignore_path: Specific .gitignore file. If None, auto-discovers.

        Returns:
            True if patterns were loaded, False otherwise.
        """
        if gitignore_path:
            return self._parse_single_file(gitignore_path)

        # Try to find .gitignore in current and parent directories
        current = self.root_dir
        found = False

        while current and current.exists():
            gitignore = current / '.gitignore'
            if gitignore.exists():
                if self._parse_single_file(gitignore):
                    found = True
            current = current.parent if current != current.parent else None

        return found

    def _parse_single_file(self, gitignore_path: Path) -> bool:
        """Parse a single .gitignore file."""
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    self.patterns.append(line)
            return True
        except Exception as e:
            logging.warning(f"Could not parse {gitignore_path}: {e}")
            return False

    def add_pattern(self, pattern: str) -> None:
        """Add a pattern manually."""
        self.patterns.append(pattern)

    def should_ignore(self, path: Path) -> bool:
        """
        Check if a path should be ignored.

        Args:
            path: Absolute path to check.

        Returns:
            True if path should be ignored.
        """
        # Check cache
        path_str = str(path)
        if path_str in self._cache:
            return self._cache[path_str]

        try:
            # Get relative path from root
            rel_path = path.relative_to(self.root_dir)
            rel_str = str(rel_path).replace('\\', '/')
        except ValueError:
            # Path is not under root directory
            self._cache[path_str] = False
            return False

        # Check if it's a directory
        is_dir = path.is_dir()

        # Apply patterns in order (gitignore logic)
        ignored = False

        for pattern in self.patterns:
            # Handle negation
            if pattern.startswith('!'):
                neg_pattern = pattern[1:]
                if self._fnmatch_pattern(rel_str, neg_pattern, is_dir):
                    ignored = False
                continue

            # Handle regular pattern
            if self._fnmatch_pattern(rel_str, pattern, is_dir):
                ignored = True

        # Cache result
        self._cache[path_str] = ignored
        return ignored

    # В common_utils.py исправим методы:

    def _fnmatch_pattern(self, rel_str: str, pattern: str, is_dir: bool) -> bool:
        """Match pattern using fnmatch with gitignore semantics."""
        # Handle ** pattern
        if '**' in pattern:
            if pattern == '**':
                return True
            pattern = pattern.replace('**/', '').replace('/**', '/*')
            if pattern.startswith('**'):
                pattern = pattern[2:]

        # Handle directory pattern
        if pattern.endswith('/'):
            dir_pattern = pattern.rstrip('/')
            if is_dir and fnmatch.fnmatch(rel_str, dir_pattern):
                return True
            # Для директорий проверяем, что все внутри игнорируется
            if fnmatch.fnmatch(rel_str, dir_pattern + '/*'):
                return True
            # Для файлов с таким же именем как директория - не игнорируем
            return False
        else:
            # Regular file pattern
            if fnmatch.fnmatch(rel_str, pattern):
                return True
            if fnmatch.fnmatch(rel_str + '/', pattern + '/*'):
                return True

        return False


    def _should_exclude(self, path: Path, is_dir: bool) -> bool:
        """Determine if a path should be excluded."""
        # Gitignore check
        if self.gitignore_parser and self.gitignore_parser.should_ignore(path):
            return True

        # Directory name exclusion
        if is_dir and self.config.exclude_dirs:
            for exclude_dir in self.config.exclude_dirs:
                if exclude_dir in path.parts:
                    return True

        # File name exclusion
        if self.config.exclude_names:
            for exclude_name in self.config.exclude_names:
                if fnmatch.fnmatch(path.name, exclude_name):
                    return True

        # Pattern exclusion
        if self.config.exclude_patterns:
            rel_path = self._get_relative_path(path)
            for pattern in self.config.exclude_patterns:
                if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(rel_path, pattern):
                    return True

        # Include pattern check - только для файлов!
        if not is_dir and not fnmatch.fnmatch(path.name, self.config.include_pattern):
            return True

        return False



# ============================================================================
# File System Utilities
# ============================================================================

class FileSystemWalker:
    """Efficient file system traversal with filtering."""

    def __init__(self, config: FilterConfig, gitignore_parser: Optional[GitIgnoreParser] = None):
        self.config = config
        self.gitignore_parser = gitignore_parser
        self.stats = {
            'files_found': 0,
            'directories_found': 0,
            'files_excluded': 0,
            'directories_excluded': 0
        }


    def find_files(self, root_dirs: List[Path]) -> List[Path]:
        """
        Find files matching criteria.

        Args:
            root_dirs: Directories to search.

        Returns:
            List of matching files.
        """
        files = []

        for root_dir in root_dirs:
            if not root_dir.exists():
                logging.warning(f"Directory does not exist: {root_dir}")
                continue

            if self.config.recursive:  # Используем config.recursive
                files.extend(self._walk_recursive(root_dir, depth=0))
            else:
                files.extend(self._walk_single(root_dir))

        return sorted(set(files))

    def _walk_recursive(self, current_dir: Path, depth: int) -> List[Path]:
        """Recursively walk directory tree."""
        files = []

        # Check max depth для директории
        if self.config.max_depth is not None and depth > self.config.max_depth:
            return files

        try:
            for item in current_dir.iterdir():
                # Handle symlinks
                if item.is_symlink() and not self.config.follow_symlinks:
                    continue

                # Resolve symlinks if following
                if item.is_symlink() and self.config.follow_symlinks:
                    try:
                        item = item.resolve()
                    except Exception:
                        continue

                if item.is_dir():
                    self.stats['directories_found'] += 1

                    # Check if directory should be excluded
                    if self._should_exclude(item, is_dir=True):
                        self.stats['directories_excluded'] += 1
                        continue

                    # Recurse into directory
                    files.extend(self._walk_recursive(item, depth + 1))
                else:
                    self.stats['files_found'] += 1

                    # Check if file should be excluded
                    if self._should_exclude(item, is_dir=False):
                        self.stats['files_excluded'] += 1
                        continue

                    # Проверка глубины для файлов
                    # Файлы находятся на глубине depth+1 (текущая директория + файл)
                    if self.config.max_depth is not None and (depth + 1) > self.config.max_depth:
                        self.stats['files_excluded'] += 1
                        continue

                    files.append(item)

        except PermissionError:
            logging.debug(f"Permission denied: {current_dir}")
        except Exception as e:
            logging.debug(f"Error accessing {current_dir}: {e}")

        return files

    def _walk_single(self, directory: Path) -> List[Path]:
        """Walk a single directory (non-recursive)."""
        files = []

        try:
            for item in directory.iterdir():
                if item.is_file():
                    self.stats['files_found'] += 1

                    if not self._should_exclude(item, is_dir=False):
                        files.append(item)
                    else:
                        self.stats['files_excluded'] += 1

        except PermissionError:
            logging.debug(f"Permission denied: {directory}")

        return files

    def _should_exclude(self, path: Path, is_dir: bool) -> bool:
        """Determine if a path should be excluded."""
        # Gitignore check
        if self.gitignore_parser and self.gitignore_parser.should_ignore(path):
            return True

        # Directory name exclusion
        if is_dir and self.config.exclude_dirs:
            for exclude_dir in self.config.exclude_dirs:
                if exclude_dir in path.parts:
                    return True

        # File name exclusion
        if self.config.exclude_names:
            for exclude_name in self.config.exclude_names:
                if fnmatch.fnmatch(path.name, exclude_name):
                    return True

        # Pattern exclusion
        if self.config.exclude_patterns:
            rel_path = self._get_relative_path(path)
            for pattern in self.config.exclude_patterns:
                if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(rel_path, pattern):
                    return True

        # Include pattern check - только для файлов!
        if not is_dir and not fnmatch.fnmatch(path.name, self.config.include_pattern):
            return True

        return False

    def _get_relative_path(self, path: Path) -> str:
        """Get relative path for pattern matching."""
        # Try to find a common root among the search directories
        try:
            # This is a simplified version - in practice, we'd track search roots
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return str(path)


# ============================================================================
# File Content Utilities
# ============================================================================

class FileContentDetector:
    """Detect file content type and encoding."""

    # Common binary file extensions
    BINARY_EXTENSIONS = {
        '.exe', '.dll', '.so', '.dylib', '.bin',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.zip', '.tar', '.gz', '.rar', '.7z',
        '.mp3', '.mp4', '.avi', '.mkv', '.mov'
    }

    # Text file extensions with known comment styles
    COMMENT_STYLES = {
        '.py': {'line': '#', 'block': ('"""', '"""'), 'alt_block': ("'''", "'''")},
        '.java': {'line': '//', 'block': ('/*', '*/')},
        '.cpp': {'line': '//', 'block': ('/*', '*/')},
        '.c': {'line': '//', 'block': ('/*', '*/')},
        '.js': {'line': '//', 'block': ('/*', '*/')},
        '.ts': {'line': '//', 'block': ('/*', '*/')},
        '.go': {'line': '//', 'block': ('/*', '*/')},
        '.rs': {'line': '//', 'block': ('/*', '*/')},
        '.rb': {'line': '#', 'block': ('=begin', '=end')},
        '.sh': {'line': '#'},
        '.pl': {'line': '#'},
        '.php': {'line': '//', 'block': ('/*', '*/')},
        '.sql': {'line': '--', 'block': ('/*', '*/')},
        '.html': {'block': ('<!--', '-->')},
        '.css': {'block': ('/*', '*/')},
        '.xml': {'block': ('<!--', '-->')},
    }

    @classmethod
    def detect_file_type(cls, path: Path) -> FileType:
        """Detect if file is text or binary."""
        # Check extension first
        if path.suffix.lower() in cls.BINARY_EXTENSIONS:
            return FileType.BINARY

        # Try to read first few bytes
        try:
            with open(path, 'rb') as f:
                sample = f.read(1024)

            # Check for null bytes (indicates binary)
            if b'\x00' in sample:
                return FileType.BINARY

            # Try to decode as UTF-8
            sample.decode('utf-8', errors='strict')
            return FileType.TEXT

        except Exception:
            return FileType.UNKNOWN

    @classmethod
    def get_comment_style(cls, path: Path) -> Optional[Dict[str, Any]]:
        """Get comment style for a file based on extension."""
        return cls.COMMENT_STYLES.get(path.suffix.lower())

    @classmethod
    def detect_encoding(cls, path: Path) -> str:
        """Detect file encoding."""
        encodings = ['utf-8', 'latin-1', 'cp1252', 'utf-16']

        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    f.read(1024)
                return encoding
            except UnicodeDecodeError:
                continue

        # Fallback to latin-1 (never fails)
        return 'latin-1'


# ============================================================================
# Safe File Operations
# ============================================================================

class SafeFileProcessor:
    """Context manager for safe file operations with backup."""

    def __init__(self, file_path: Path, backup: bool = True):
        self.file_path = file_path
        self.backup = backup
        self.backup_path = None
        self.original_content = None

    def __enter__(self):
        """Create backup and read original content."""
        if self.backup and self.file_path.exists():
            self.backup_path = self.file_path.with_suffix(self.file_path.suffix + '.bak')
            shutil.copy2(self.file_path, self.backup_path)

        if self.file_path.exists():
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.original_content = f.read()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore from backup if there was an error."""
        if exc_type is not None and self.backup_path and self.backup_path.exists():
            # Restore from backup
            shutil.copy2(self.backup_path, self.file_path)
            self.backup_path.unlink()
            logging.error(f"Error processing {self.file_path}. Restored from backup.")
            return False  # Re-raise exception

        # Clean up backup on success
        if self.backup_path and self.backup_path.exists():
            self.backup_path.unlink()

        return False  # Don't suppress exceptions


def safe_write(file_path: Path, content: str, encoding: str = 'utf-8', backup: bool = True) -> bool:
    """
    Safely write content to file with optional backup.

    Args:
        file_path: Path to write to.
        content: Content to write.
        encoding: File encoding.
        backup: Whether to create backup.

    Returns:
        True if successful, False otherwise.
    """
    try:
        with SafeFileProcessor(file_path, backup):
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(content)

            return True
    except Exception as e:
        logging.error(f"Failed to write {file_path}: {e}")
        return False


# ============================================================================
# Progress Reporting
# ============================================================================

class ProgressReporter:
    """Report progress for long-running operations."""

    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.description = description
        self.current = 0
        self.start_time = None

    def __enter__(self):
        """Start progress reporting."""
        self.start_time = time.time()
        self._print_progress()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finish progress reporting."""
        elapsed = time.time() - self.start_time
        if self.total > 0:  # Только если был прогресс
            print(f"\n{self.description} completed in {elapsed:.2f}s")

    def update(self, increment: int = 1):
        """Update progress."""
        self.current += increment
        self._print_progress()

    def _print_progress(self):
        """Print progress to console."""
        if self.total == 0:
            return

        percent = (self.current / self.total) * 100
        bar_length = 40
        filled_length = int(bar_length * self.current // self.total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)

        sys.stdout.write(f'\r{self.description}: |{bar}| {percent:.1f}% ({self.current}/{self.total})')
        sys.stdout.flush()


# ============================================================================
# Utility Functions
# ============================================================================

def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes == 0:
        return "0 B"

    size_units = ["B", "KB", "MB", "GB", "TB"]
    i = 0

    while size_bytes >= 1024 and i < len(size_units) - 1:
        size_bytes /= 1024
        i += 1

    return f"{size_bytes:.2f} {size_units[i]}"


def get_relative_path(path: Path, base_dir: Optional[Path] = None) -> str:
    """Get relative path from base directory."""
    base_dir = base_dir or Path.cwd()

    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def create_directory_header(file_path: Path, base_dir: Optional[Path] = None) -> str:
    """Create a formatted header for file inclusion in merged output."""
    rel_path = get_relative_path(file_path, base_dir)
    header = f"\n{'='*60}\n"
    header += f"FILE: {rel_path}\n"
    header += f"{'='*60}\n"
    return header


# ============================================================================
# Error Handling
# ============================================================================

class FileOperationError(Exception):
    """Base exception for file operations."""
    pass


class PermissionDeniedError(FileOperationError):
    """Raised when permission is denied."""
    pass


class InvalidFileTypeError(FileOperationError):
    """Raised when file type is not supported."""
    pass


def handle_file_errors(func: Callable) -> Callable:
    """Decorator to handle common file operation errors."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PermissionError as e:
            raise PermissionDeniedError(f"Permission denied: {e}")
        except FileNotFoundError as e:
            logging.warning(f"File not found: {e}")
            return None
        except UnicodeDecodeError as e:
            logging.warning(f"Encoding error: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            raise

    return wrapper


# ============================================================================
# Main Exports
# ============================================================================

__all__ = [
    # Configuration
    'FilterConfig',
    'FileType',

    # GitIgnore
    'GitIgnoreParser',

    # File System
    'FileSystemWalker',

    # Content Detection
    'FileContentDetector',

    # Safe Operations
    'SafeFileProcessor',
    'safe_write',

    # Progress
    'ProgressReporter',

    # Utilities
    'format_size',
    'get_relative_path',
    'create_directory_header',

    # Error Handling
    'FileOperationError',
    'PermissionDeniedError',
    'InvalidFileTypeError',
    'handle_file_errors',
]
