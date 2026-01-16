"""
Advanced file merger with intelligent filtering and formatting.
Merges multiple files into a single organized output with headers.
"""
from dataclasses import dataclass


import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple
import logging
from datetime import datetime

from codingutils.common_utils import (
    FilterConfig,
    GitIgnoreParser,
    FileSystemWalker,
    FileContentDetector,
    FileType,
    ProgressReporter,
    format_size,
    get_relative_path,
    handle_file_errors
)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class MergerConfig(FilterConfig):
    """Configuration for file merging."""
    output_file: Path = Path("merged_output.txt")
    preview_mode: bool = False
    include_headers: bool = True
    include_metadata: bool = True
    add_line_numbers: bool = False
    remove_empty_lines: bool = False
    deduplicate_lines: bool = False
    sort_files: bool = False
    max_file_size: Optional[int] = None  # in bytes
    encoding: str = 'utf-8'

    # Output formatting
    header_separator: str = "=" * 60
    file_separator: str = "\n" + "-" * 40 + "\n"
    line_number_format: str = "{:>4}: "

    # Performance
    chunk_size: int = 65536  # 64KB chunks for large files
    max_total_size: Optional[int] = None  # 100MB default

    def __post_init__(self):
        """Validate configuration."""
        super().__post_init__()
        self.output_file = Path(self.output_file)

        if self.max_file_size and self.max_file_size <= 0:
            raise ValueError("max_file_size must be positive")

        if self.max_total_size and self.max_total_size <= 0:
            raise ValueError("max_total_size must be positive")


# ============================================================================
# File Processing Strategies
# ============================================================================

class FileProcessor:
    """Base class for file processing strategies."""

    def __init__(self, config: MergerConfig):
        self.config = config

    def process(self, file_path: Path) -> Tuple[str, int]:
        """Process a file and return content with size."""
        raise NotImplementedError


class SimpleFileProcessor(FileProcessor):
    """Process files with basic reading."""

    @handle_file_errors
    def process(self, file_path: Path) -> Tuple[str, int]:
        """Read file content."""
        # Check file size limit
        if self.config.max_file_size:
            file_size = file_path.stat().st_size
            if file_size > self.config.max_file_size:
                logging.warning(f"File {file_path} exceeds size limit ({format_size(file_size)} > {format_size(self.config.max_file_size)})")
                return "[FILE SKIPPED: Exceeds size limit]\n", 0

        # Detect encoding
        encoding = FileContentDetector.detect_encoding(file_path)

        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()

            # Apply post-processing
            content = self._post_process(content, file_path)
            return content, len(content)

        except UnicodeDecodeError:
            # Try fallback encodings
            for fallback_encoding in ['latin-1', 'cp1252', 'utf-16']:
                try:
                    with open(file_path, 'r', encoding=fallback_encoding) as f:
                        content = f.read()
                    content = self._post_process(content, file_path)
                    return content, len(content)
                except UnicodeDecodeError:
                    continue

            # If all encodings fail
            return "[ERROR: Could not decode file with supported encodings]\n", 0

    def _post_process(self, content: str, file_path: Path) -> str:
        """Apply post-processing to content."""
        if self.config.remove_empty_lines:
            lines = [line for line in content.splitlines() if line.strip()]
            content = '\n'.join(lines)

        if self.config.deduplicate_lines:
            lines = content.splitlines()
            seen = set()
            unique_lines = []
            for line in lines:
                if line not in seen:
                    seen.add(line)
                    unique_lines.append(line)
            content = '\n'.join(unique_lines)

        if self.config.add_line_numbers:
            lines = content.splitlines()
            numbered_lines = []
            for i, line in enumerate(lines, 1):
                numbered_lines.append(f"{self.config.line_number_format.format(i)}{line}")
            content = '\n'.join(numbered_lines)

        return content


class ChunkedFileProcessor(FileProcessor):
    """Process large files in chunks."""

    @handle_file_errors
    def process(self, file_path: Path) -> Tuple[str, int]:
        """Read file content in chunks."""
        if self.config.max_file_size:
            file_size = file_path.stat().st_size
            if file_size > self.config.max_file_size:
                return f"[FILE SKIPPED: Exceeds size limit ({format_size(file_size)})]\n", 0

        encoding = FileContentDetector.detect_encoding(file_path)
        content_parts = []
        total_size = 0

        try:
            with open(file_path, 'r', encoding=encoding) as f:
                while True:
                    chunk = f.read(self.config.chunk_size)
                    if not chunk:
                        break
                    content_parts.append(chunk)
                    total_size += len(chunk)

            content = ''.join(content_parts)
            content = self._post_process(content, file_path)
            return content, total_size

        except UnicodeDecodeError:
            return "[ERROR: Could not decode file]\n", 0

    def _post_process(self, content: str, file_path: Path) -> str:
        """Apply post-processing to chunked content."""
        # Simplified post-processing for large files
        if self.config.remove_empty_lines:
            lines = [line for line in content.splitlines() if line.strip()]
            content = '\n'.join(lines)

        return content


# ============================================================================
# File Merger
# ============================================================================

class SmartFileMerger:
    """Intelligent file merger with advanced features."""

    def __init__(self, config: MergerConfig):
        self.config = config
        self._setup_logging()
        self._setup_file_walker()
        self._stats = {
            'files_found': 0,
            'files_processed': 0,
            'files_skipped': 0,
            'total_size': 0,
            'output_size': 0,
            'start_time': None,
            'end_time': None
        }

    def _setup_logging(self) -> None:
        """Configure logging."""
        log_level = logging.DEBUG if self.config.preview_mode else logging.INFO

        handlers = []

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        handlers.append(console_handler)

        # Configure root logger
        logging.basicConfig(
            level=log_level,
            handlers=handlers,
            force=True
        )

    def _setup_file_walker(self) -> None:
        """Initialize file system walker."""
        gitignore_parser = None

        if self.config.use_gitignore or self.config.custom_gitignore:
            gitignore_parser = GitIgnoreParser()

            if self.config.custom_gitignore:
                gitignore_parser.load_from_file(self.config.custom_gitignore)
            else:
                gitignore_parser.load_from_file()

        self.file_walker = FileSystemWalker(self.config, gitignore_parser)

    def find_files(self) -> List[Path]:
        """Find files to merge based on configuration."""
        root_dirs = []

        if self.config.directories:
            root_dirs = [Path(d).resolve() for d in self.config.directories]
        else:
            root_dirs = [Path('.').resolve()]

        files = self.file_walker.find_files(root_dirs, recursive=self.config.recursive)

        # Sort files if requested
        if self.config.sort_files:
            files.sort(key=lambda x: (x.suffix, x.name.lower()))

        self._stats['files_found'] = len(files)

        # Check total size limit
        if self.config.max_total_size:
            total_size = sum(f.stat().st_size for f in files if f.exists())
            if total_size > self.config.max_total_size:
                logging.warning(f"Total file size ({format_size(total_size)}) exceeds limit ({format_size(self.config.max_total_size)})")
                # We'll process files until we hit the limit

        return files

    def _create_metadata_header(self, files: List[Path]) -> str:
        """Create metadata header for the merged file."""
        if not self.config.include_metadata:
            return ""

        header_lines = []

        # Title
        header_lines.append("MERGED FILE REPORT")
        header_lines.append(self.config.header_separator)

        # Generation info
        header_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        header_lines.append("Tool: File Merger v1.0")

        # File statistics
        total_files = len(files)
        total_size = sum(f.stat().st_size for f in files if f.exists())
        header_lines.append(f"Files merged: {total_files}")
        header_lines.append(f"Total input size: {format_size(total_size)}")

        # Configuration summary
        header_lines.append("")
        header_lines.append("CONFIGURATION:")

        if self.config.directories:
            dirs_str = ', '.join(str(d) for d in self.config.directories)
            header_lines.append(f"  Directories: {dirs_str}")

        header_lines.append(f"  Pattern: {self.config.include_pattern}")
        header_lines.append(f"  Recursive: {self.config.recursive}")

        # Filters applied
        filters_applied = []
        if self.config.exclude_dirs:
            filters_applied.append(f"Excluded dirs: {', '.join(self.config.exclude_dirs)}")
        if self.config.exclude_names:
            filters_applied.append(f"Excluded names: {', '.join(self.config.exclude_names)}")
        if self.config.exclude_patterns:
            filters_applied.append(f"Excluded patterns: {', '.join(self.config.exclude_patterns)}")

        if filters_applied:
            header_lines.append("  Filters applied:")
            for filter_str in filters_applied:
                header_lines.append(f"    - {filter_str}")

        if self.config.use_gitignore or self.config.custom_gitignore:
            header_lines.append("  Gitignore: Enabled")

        # Processing options
        header_lines.append("  Options:")
        header_lines.append(f"    Add line numbers: {self.config.add_line_numbers}")
        header_lines.append(f"    Remove empty lines: {self.config.remove_empty_lines}")
        header_lines.append(f"    Deduplicate lines: {self.config.deduplicate_lines}")

        if self.config.max_file_size:
            header_lines.append(f"    Max file size: {format_size(self.config.max_file_size)}")

        if self.config.max_total_size:
            header_lines.append(f"    Max total size: {format_size(self.config.max_total_size)}")

        header_lines.append("")
        header_lines.append("FILE LIST:")
        header_lines.append(self.config.header_separator)

        # File list
        for i, file_path in enumerate(files, 1):
            rel_path = get_relative_path(file_path)
            size = file_path.stat().st_size if file_path.exists() else 0
            header_lines.append(f"{i:3}. {rel_path} ({format_size(size)})")

        header_lines.append(self.config.header_separator)
        header_lines.append("")

        return '\n'.join(header_lines)

    def _create_file_header(self, file_path: Path, index: int, total: int) -> str:
        """Create header for individual file."""
        if not self.config.include_headers:
            return ""

        rel_path = get_relative_path(file_path)
        size = file_path.stat().st_size if file_path.exists() else 0
        encoding = FileContentDetector.detect_encoding(file_path)

        header_lines = []
        header_lines.append(self.config.file_separator.strip())
        header_lines.append(f"FILE {index}/{total}: {rel_path}")
        header_lines.append(f"Size: {format_size(size)} | Encoding: {encoding}")
        header_lines.append(f"Modified: {datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        header_lines.append(self.config.header_separator[:40])
        header_lines.append("")

        return '\n'.join(header_lines)

    def _select_processor(self, file_path: Path) -> FileProcessor:
        """Select appropriate processor based on file size and type."""
        file_size = file_path.stat().st_size if file_path.exists() else 0

        # For very large files, use chunked processor
        if file_size > 10 * 1024 * 1024:  # 10MB
            return ChunkedFileProcessor(self.config)

        # For binary files, create a placeholder
        if FileContentDetector.detect_file_type(file_path) == FileType.BINARY:
            return BinaryFileProcessor(self.config)

        # Default to simple processor
        return SimpleFileProcessor(self.config)

    def merge_files(self) -> bool:
        """Merge files into single output."""
        self._stats['start_time'] = time.time()

        files = self.find_files()

        if not files:
            logging.error("No files found to merge")
            return False

        # Preview mode - just show what would be done
        if self.config.preview_mode:
            return self._preview_merge(files)

        # Prepare output directory
        self.config.output_file.parent.mkdir(parents=True, exist_ok=True)

        # Calculate total size for progress tracking
        sum(f.stat().st_size for f in files if f.exists())

        try:
            with open(self.config.output_file, 'w', encoding=self.config.encoding) as output_file:
                # Write metadata header
                if self.config.include_metadata:
                    metadata = self._create_metadata_header(files)
                    output_file.write(metadata)
                    self._stats['output_size'] += len(metadata)

                # Process files
                with ProgressReporter(len(files), "Merging files") as progress:
                    for i, file_path in enumerate(files, 1):
                        try:
                            # Create file header
                            header = self._create_file_header(file_path, i, len(files))
                            if header:
                                output_file.write(header)
                                self._stats['output_size'] += len(header)

                            # Process file content
                            processor = self._select_processor(file_path)
                            content, content_size = processor.process(file_path)

                            if content:
                                output_file.write(content)
                                self._stats['output_size'] += content_size

                                # Add newline if content doesn't end with one
                                if content and not content.endswith('\n'):
                                    output_file.write('\n')
                                    self._stats['output_size'] += 1

                            self._stats['files_processed'] += 1

                        except Exception as e:
                            error_msg = f"[ERROR processing {file_path}: {e}]\n"
                            output_file.write(error_msg)
                            self._stats['output_size'] += len(error_msg)
                            self._stats['files_skipped'] += 1
                            logging.error(f"Failed to process {file_path}: {e}")

                        progress.update()

                # Write footer
                footer = self._create_footer()
                if footer:
                    output_file.write(footer)
                    self._stats['output_size'] += len(footer)

            self._stats['end_time'] = time.time()
            self._log_results(files)

            return True

        except Exception as e:
            logging.error(f"Failed to write output file: {e}")
            return False

    def _preview_merge(self, files: List[Path]) -> bool:
        """Preview what would be merged without actually merging."""
        logging.info("=" * 60)
        logging.info("MERGE PREVIEW")
        logging.info("=" * 60)
        logging.info(f"Output file: {self.config.output_file}")
        logging.info(f"Files to merge: {len(files)}")
        logging.info("")

        total_size = 0
        max_file_size = 0

        for i, file_path in enumerate(files, 1):
            rel_path = get_relative_path(file_path)
            size = file_path.stat().st_size if file_path.exists() else 0
            total_size += size
            max_file_size = max(max_file_size, size)

            # Show file info
            file_type = FileContentDetector.detect_file_type(file_path)
            file_marker = "📄" if file_type == FileType.TEXT else "🔧" if file_type == FileType.BINARY else "❓"

            logging.info(f"{i:3}. {file_marker} {rel_path}")
            logging.info(f"     Size: {format_size(size)} | Type: {file_type.value}")

            # Show size warning if applicable
            if self.config.max_file_size and size > self.config.max_file_size:
                logging.info("     ⚠️  Exceeds max file size limit")

        logging.info("")
        logging.info("SUMMARY:")
        logging.info(f"  Total files: {len(files)}")
        logging.info(f"  Total size: {format_size(total_size)}")
        logging.info(f"  Largest file: {format_size(max_file_size)}")
        logging.info(f"  Average size: {format_size(total_size // len(files) if files else 0)}")

        # Check limits
        if self.config.max_total_size and total_size > self.config.max_total_size:
            logging.info(f"  ⚠️  Total size exceeds limit of {format_size(self.config.max_total_size)}")

        # Show configuration
        logging.info("")
        logging.info("CONFIGURATION:")
        logging.info(f"  Include headers: {self.config.include_headers}")
        logging.info(f"  Include metadata: {self.config.include_metadata}")
        logging.info(f"  Add line numbers: {self.config.add_line_numbers}")
        logging.info(f"  Remove empty lines: {self.config.remove_empty_lines}")
        logging.info(f"  Deduplicate lines: {self.config.deduplicate_lines}")

        logging.info("=" * 60)

        return True

    def _create_footer(self) -> str:
        """Create footer for merged file."""
        if not self.config.include_metadata:
            return ""

        elapsed = self._stats['end_time'] - self._stats['start_time']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        footer_lines = []
        footer_lines.append("\n" + self.config.header_separator)
        footer_lines.append("MERGE COMPLETE")
        footer_lines.append(self.config.header_separator)
        footer_lines.append(f"Generated: {timestamp}")
        footer_lines.append(f"Processing time: {elapsed:.2f} seconds")
        footer_lines.append(f"Files processed: {self._stats['files_processed']}")
        footer_lines.append(f"Files skipped: {self._stats['files_skipped']}")
        footer_lines.append(f"Output size: {format_size(self._stats['output_size'])}")
        footer_lines.append("")
        footer_lines.append("End of merged file")

        return '\n'.join(footer_lines)

    def _log_results(self, files: List[Path]) -> None:
        """Log merging results."""
        elapsed = self._stats['end_time'] - self._stats['start_time']

        logging.info("=" * 60)
        logging.info("MERGE COMPLETE")
        logging.info("=" * 60)
        logging.info(f"Output file: {self.config.output_file}")
        logging.info(f"Total files: {len(files)}")
        logging.info(f"Files processed: {self._stats['files_processed']}")
        logging.info(f"Files skipped: {self._stats['files_skipped']}")
        logging.info(f"Output size: {format_size(self._stats['output_size'])}")
        logging.info(f"Processing time: {elapsed:.2f} seconds")

        # Show file list summary
        if len(files) <= 20:  # Only show all files if there aren't too many
            logging.info("\nMerged files:")
            for file_path in files:
                rel_path = get_relative_path(file_path)
                logging.info(f"  • {rel_path}")
        else:
            # Show top 5 and bottom 5 files
            logging.info("\nSample of merged files:")
            for i, file_path in enumerate(files[:5], 1):
                rel_path = get_relative_path(file_path)
                logging.info(f"  {i}. {rel_path}")

            if len(files) > 10:
                logging.info(f"  ... ({len(files) - 10} more files)")

            for i, file_path in enumerate(files[-5:], len(files) - 4):
                rel_path = get_relative_path(file_path)
                logging.info(f"  {i}. {rel_path}")

        logging.info("=" * 60)


class BinaryFileProcessor(FileProcessor):
    """Processor for binary files."""

    @handle_file_errors
    def process(self, file_path: Path) -> Tuple[str, int]:
        """Create representation of binary file."""
        file_size = file_path.stat().st_size
        content = []

        content.append(f"[BINARY FILE: {file_path.name}]")
        content.append(f"Size: {format_size(file_size)}")
        content.append("Type: Binary")
        content.append("MD5: [hash would be here]")
        content.append("Warning: Binary content not included in merge")
        content.append("")

        return '\n'.join(content), len('\n'.join(content))


# ============================================================================
# CLI Interface
# ============================================================================

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Advanced file merger with intelligent filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Merge all Python files in current directory
  %(prog)s --pattern "*.py" --output merged_code.txt

  # Merge files from multiple directories with preview
  %(prog)s src/ tests/ --pattern "*.py" --preview

  # Merge with line numbers and deduplication
  %(prog)s --pattern "*.txt" --add-line-numbers --deduplicate

  # Merge with size limits
  %(prog)s --pattern "*" --max-file-size 1MB --max-total-size 100MB

  # Merge without headers for cleaner output
  %(prog)s --pattern "*.log" --no-headers --no-metadata
        """
    )

    # Input sources
    input_group = parser.add_argument_group('Input Sources')
    input_group.add_argument(
        'directories',
        nargs='*',
        default=['.'],
        help='Directories to merge files from (default: current directory)'
    )
    input_group.add_argument(
        '-p', '--pattern',
        default='*',
        help='File pattern to match (e.g., "*.py", "*.txt")'
    )
    input_group.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Search directories recursively'
    )

    # Output configuration
    output_group = parser.add_argument_group('Output Configuration')
    output_group.add_argument(
        '-o', '--output',
        default='merged_output.txt',
        type=Path,
        help='Output file path (default: merged_output.txt)'
    )
    output_group.add_argument(
        '--encoding',
        default='utf-8',
        help='Output file encoding (default: utf-8)'
    )

    # Content processing
    content_group = parser.add_argument_group('Content Processing')
    content_group.add_argument(
        '--add-line-numbers',
        action='store_true',
        help='Add line numbers to each file'
    )
    content_group.add_argument(
        '--remove-empty-lines',
        action='store_true',
        help='Remove empty lines from files'
    )
    content_group.add_argument(
        '--deduplicate',
        action='store_true',
        dest='deduplicate_lines',
        help='Remove duplicate lines within each file'
    )
    content_group.add_argument(
        '--sort-files',
        action='store_true',
        help='Sort files by name before merging'
    )

    # Headers and metadata
    header_group = parser.add_argument_group('Headers and Metadata')
    header_group.add_argument(
        '--no-headers',
        action='store_false',
        dest='include_headers',
        help='Do not include file headers'
    )
    header_group.add_argument(
        '--no-metadata',
        action='store_false',
        dest='include_metadata',
        help='Do not include metadata section'
    )

    # Filtering
    filter_group = parser.add_argument_group('Filtering')
    filter_group.add_argument(
        '-ed', '--exclude-dir',
        action='append',
        dest='exclude_dirs',
        help='Exclude directory by name (can be repeated)'
    )
    filter_group.add_argument(
        '-en', '--exclude-name',
        action='append',
        dest='exclude_names',
        help='Exclude file by name/wildcard (can be repeated)'
    )
    filter_group.add_argument(
        '-ep', '--exclude-pattern',
        action='append',
        dest='exclude_patterns',
        help='Exclude by path pattern (can be repeated)'
    )
    filter_group.add_argument(
        '--max-depth',
        type=int,
        help='Maximum recursion depth'
    )

    # Size limits
    size_group = parser.add_argument_group('Size Limits')
    size_group.add_argument(
        '--max-file-size',
        help='Maximum individual file size (e.g., 10MB, 1GB)'
    )
    size_group.add_argument(
        '--max-total-size',
        help='Maximum total size of all files (e.g., 100MB, 1GB)'
    )

    # Gitignore
    gitignore_group = parser.add_argument_group('Gitignore')
    gitignore_group.add_argument(
        '-gi', '--gitignore',
        type=Path,
        help='Use specific .gitignore file'
    )
    gitignore_group.add_argument(
        '-ig', '--use-gitignore',
        action='store_true',
        help='Auto-discover and use .gitignore files'
    )
    gitignore_group.add_argument(
        '--no-gitignore',
        action='store_true',
        help='Ignore .gitignore files'
    )

    # Actions
    action_group = parser.add_argument_group('Actions')
    action_group.add_argument(
        '--preview',
        action='store_true',
        help='Preview what would be merged without actually merging'
    )

    # Performance
    perf_group = parser.add_argument_group('Performance')
    perf_group.add_argument(
        '--chunk-size',
        type=int,
        default=65536,
        help='Chunk size for reading large files (default: 64KB)'
    )

    args = parser.parse_args()

    # Parse size arguments
    if args.max_file_size:
        args.max_file_size = parse_size_string(args.max_file_size)

    if args.max_total_size:
        args.max_total_size = parse_size_string(args.max_total_size)

    return args


def parse_size_string(size_str: str) -> int:
    """Parse size string like '10MB', '1GB', '500KB' into bytes."""
    size_str = size_str.upper().strip()

    # Define multipliers
    multipliers = {
        'KB': 1024,
        'MB': 1024 * 1024,
        'GB': 1024 * 1024 * 1024,
        'TB': 1024 * 1024 * 1024 * 1024,
    }

    # Find unit
    for unit, multiplier in multipliers.items():
        if size_str.endswith(unit):
            number = float(size_str[:-len(unit)].strip())
            return int(number * multiplier)

    # If no unit, assume bytes
    try:
        return int(size_str)
    except ValueError:
        raise ValueError(f"Invalid size format: {size_str}. Use formats like '10MB', '1GB', '500KB'")


def create_config_from_args(args) -> MergerConfig:
    """Create configuration from command line arguments."""
    return MergerConfig(
        # Filtering
        exclude_dirs=set(args.exclude_dirs or []),
        exclude_names=set(args.exclude_names or []),
        exclude_patterns=set(args.exclude_patterns or []),
        include_pattern=args.pattern,
        max_depth=args.max_depth,

        # Gitignore
        use_gitignore=args.use_gitignore and not args.no_gitignore,
        custom_gitignore=args.gitignore,

        # Output
        output_file=args.output,
        encoding=args.encoding,

        # Content processing
        add_line_numbers=args.add_line_numbers,
        remove_empty_lines=args.remove_empty_lines,
        deduplicate_lines=args.deduplicate_lines,
        sort_files=args.sort_files,

        # Headers and metadata
        include_headers=args.include_headers,
        include_metadata=args.include_metadata,

        # Size limits
        max_file_size=args.max_file_size,
        max_total_size=args.max_total_size,

        # Actions
        preview_mode=args.preview,

        # Performance
        chunk_size=args.chunk_size,

        # File operations
        recursive=args.recursive,
        directories=args.directories
    )


def main():
    """Main entry point."""
    try:
        args = parse_arguments()
        config = create_config_from_args(args)

        merger = SmartFileMerger(config)

        if config.preview_mode:
            success = merger._preview_merge(merger.find_files())
        else:
            success = merger.merge_files()

        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        return 130
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        return 1
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
