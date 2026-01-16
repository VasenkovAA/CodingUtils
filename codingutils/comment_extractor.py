"""
Advanced comment extractor and remover with multi-language support.
Uses common utilities for file operations and filtering.
"""
from dataclasses import dataclass

import argparse
import re
import sys
import time
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import logging

from codingutils.common_utils import (
    FilterConfig,
    GitIgnoreParser,
    FileSystemWalker,
    FileContentDetector,
    FileType,
    safe_write,
    ProgressReporter,
    get_relative_path,
    handle_file_errors
)

try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class CommentExtractorConfig(FilterConfig):
    """Configuration for comment extraction."""
    comment_symbols: Optional[str] = None
    exclude_comment_pattern: Optional[str] = None
    language_filter: Optional[str] = None
    remove_comments: bool = False
    preview_mode: bool = False
    export_file: Optional[Path] = None
    log_file: Optional[Path] = None

    # Performance settings
    chunk_size: int = 8192
    use_cache: bool = True

    def __post_init__(self):
        """Validate configuration."""
        super().__post_init__()
        if self.language_filter and not LANGDETECT_AVAILABLE:
            logging.warning("langdetect not available. Install with: pip install langdetect")


# ============================================================================
# Comment Detection Engines
# ============================================================================

class CommentDetectionStrategy:
    """Base class for comment detection strategies."""

    def __init__(self, symbols: Dict[str, Any]):
        self.symbols = symbols

    def detect(self, line: str, context: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Detect comments in a line."""
        raise NotImplementedError


class LineCommentDetector(CommentDetectionStrategy):
    """Detect line comments (e.g., //, #)."""

    def detect(self, line: str, context: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        symbol = self.symbols.get('line')
        if not symbol:
            return False, None, context

        # Find comment symbol outside of strings
        comment_pos = self._find_comment_position(line, symbol)

        if comment_pos == -1:
            return False, None, context

        # Check if this is an excluded pattern
        if self._is_excluded_pattern(line, comment_pos, context.get('exclude_pattern')):
            return False, None, context

        comment_text = line[comment_pos + len(symbol):].strip()
        return True, comment_text, context

    def _find_comment_position(self, line: str, symbol: str) -> int:
        """Find position of comment symbol, ignoring string literals."""
        in_string = False
        string_char = None
        i = 0

        while i < len(line):
            # Handle escape sequences
            if line[i] == '\\' and i + 1 < len(line):
                i += 2
                continue

            # Track string boundaries
            if line[i] in ('"', "'"):
                if not in_string:
                    in_string = True
                    string_char = line[i]
                elif string_char == line[i]:
                    in_string = False
                    string_char = None

            # Check for comment symbol
            if not in_string and line[i:].startswith(symbol):
                return i

            i += 1

        return -1

    def _is_excluded_pattern(self, line: str, pos: int, exclude_pattern: Optional[str]) -> bool:
        """Check if comment matches exclusion pattern."""
        if not exclude_pattern:
            return False

        return line[pos:].startswith(exclude_pattern)


class BlockCommentDetector(CommentDetectionStrategy):
    """Detect block comments (e.g., /* */, <!-- -->)."""

    def __init__(self, symbols: Dict[str, Any]):
        super().__init__(symbols)
        self.block_start = symbols.get('block_start', '')
        self.block_end = symbols.get('block_end', '')

    def detect(self, line: str, context: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        in_block = context.get('in_block', False)
        block_content = context.get('block_content', '')

        # Check if we're inside a block comment
        if in_block:
            if self.block_end in line:
                end_pos = line.find(self.block_end) + len(self.block_end)
                full_comment = block_content + line[:end_pos]
                context['in_block'] = False
                context['block_content'] = ''
                return True, full_comment.strip(), context
            else:
                context['block_content'] = block_content + line + '\n'
                return True, None, context

        # Check for new block comment
        if self.block_start in line:
            start_pos = line.find(self.block_start)

            # Check if block ends on same line
            if self.block_end in line:
                end_pos = line.find(self.block_end) + len(self.block_end)
                comment_text = line[start_pos:end_pos]
                return True, comment_text.strip(), context
            else:
                context['in_block'] = True
                context['block_content'] = line[start_pos:] + '\n'
                return True, None, context

        return False, None, context


class MultiCommentDetector:
    """Combine multiple detection strategies."""

    def __init__(self, file_extension: str, exclude_pattern: Optional[str] = None):
        self.detectors = []
        self.exclude_pattern = exclude_pattern

        # Get comment style for file extension
        style = FileContentDetector.get_comment_style(Path(f"dummy{file_extension}"))

        if style:
            if 'line' in style:
                self.detectors.append(LineCommentDetector({'line': style['line']}))

            if 'block' in style:
                block_start, block_end = style['block']
                self.detectors.append(BlockCommentDetector({
                    'block_start': block_start,
                    'block_end': block_end
                }))

            # Some languages have alternative block comments (like Python)
            if 'alt_block' in style:
                alt_start, alt_end = style['alt_block']
                self.detectors.append(BlockCommentDetector({
                    'block_start': alt_start,
                    'block_end': alt_end
                }))

        # If no style detected, use default line comment
        if not self.detectors:
            self.detectors.append(LineCommentDetector({'line': '#'}))

    def process_line(self, line: str, context: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Process a line with all detectors."""
        context['exclude_pattern'] = self.exclude_pattern

        for detector in self.detectors:
            is_comment, comment_text, new_context = detector.detect(line, context)
            if is_comment:
                return True, comment_text, new_context

        return False, None, context


# ============================================================================
# Comment Processor
# ============================================================================

class CommentProcessor:
    """Main processor for comment extraction and removal."""

    def __init__(self, config: CommentExtractorConfig):
        self.config = config
        self._setup_logging()
        self._setup_file_walker()
        self._cache = {} if config.use_cache else None

    def _setup_logging(self) -> None:
        """Configure logging based on settings."""
        log_level = logging.DEBUG if self.config.preview_mode else logging.INFO

        handlers = []

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        handlers.append(console_handler)

        # File handler if specified
        if self.config.log_file:
            file_handler = logging.FileHandler(self.config.log_file, mode='w', encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter('%(message)s'))
            handlers.append(file_handler)

        # Configure root logger
        logging.basicConfig(
            level=log_level,
            handlers=handlers,
            force=True
        )

    def _setup_file_walker(self) -> None:
        """Initialize file system walker with gitignore support."""
        gitignore_parser = None

        if self.config.use_gitignore or self.config.custom_gitignore:
            gitignore_parser = GitIgnoreParser()

            if self.config.custom_gitignore:
                gitignore_parser.load_from_file(self.config.custom_gitignore)
            else:
                gitignore_parser.load_from_file()

        self.file_walker = FileSystemWalker(self.config, gitignore_parser)

    @handle_file_errors
    def process_file(self, file_path: Path) -> Tuple[int, List[Tuple[int, str]]]:
        """Process a single file for comments."""
        # Skip binary files
        if FileContentDetector.detect_file_type(file_path) != FileType.TEXT:
            logging.debug(f"Skipping binary file: {file_path}")
            return 0, []

        # Check cache
        cache_key = str(file_path)
        if self._cache and cache_key in self._cache:
            return self._cache[cache_key]

        # Create comment detector for this file type
        detector = MultiCommentDetector(
            file_path.suffix,
            self.config.exclude_comment_pattern
        )

        removed_count = 0
        comments_found = []
        new_lines = []
        context = {'in_block': False, 'block_content': ''}

        try:
            # Read file with detected encoding
            encoding = FileContentDetector.detect_encoding(file_path)

            with open(file_path, 'r', encoding=encoding) as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, 1):
                original_line = line
                line = line.rstrip('\n')

                is_comment, comment_text, context = detector.process_line(line, context)

                if is_comment and comment_text:
                    comments_found.append((line_num, comment_text))

                    if self._should_remove_comment(comment_text):
                        removed_count += 1

                        if self.config.remove_comments and not self.config.preview_mode:
                            # Remove comment from line
                            line = self._remove_comment_from_line(original_line.rstrip('\n'))
                            if line.strip():
                                new_lines.append(line + '\n')
                        else:
                            new_lines.append(original_line)
                    else:
                        new_lines.append(original_line)
                else:
                    new_lines.append(original_line)

            # Handle trailing block comment
            if context.get('in_block', False):
                logging.warning(f"Unclosed block comment in {file_path}")

            # Write changes if needed
            if removed_count > 0 and self.config.remove_comments and not self.config.preview_mode:
                self._write_file(file_path, new_lines, encoding)

            result = (removed_count, comments_found)

            # Cache result
            if self._cache is not None:
                self._cache[cache_key] = result

            return result

        except Exception as e:
            logging.error(f"Error processing {file_path}: {e}")
            return 0, []

    def _should_remove_comment(self, comment_text: str) -> bool:
        """Determine if a comment should be removed."""
        if not self.config.language_filter:
            return True

        if not LANGDETECT_AVAILABLE:
            logging.warning("langdetect not available. Skipping language filter.")
            return True

        try:
            # Clean comment text for language detection
            cleaned = re.sub(r'\b(def|class|function|var|let|const|import|from)\b', '', comment_text)
            cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
            cleaned = cleaned.strip()

            if not cleaned or len(cleaned) < 3:
                return True

            detected_lang = detect(cleaned)
            return detected_lang == self.config.language_filter

        except LangDetectException:
            return True

    def _remove_comment_from_line(self, line: str) -> str:
        """Remove comment from a line of code."""
        # Simple implementation - can be enhanced based on comment type
        # This handles common cases, but might need adjustment for edge cases

        # Remove line comments
        for comment_symbol in ['#', '//', '--']:
            if comment_symbol in line:
                # Check if it's in a string
                parts = line.split(comment_symbol)
                if len(parts) > 1:
                    # Count quotes in the part before comment
                    before_comment = parts[0]
                    if before_comment.count('"') % 2 == 0 and before_comment.count("'") % 2 == 0:
                        return before_comment.rstrip()

        return line

    def _write_file(self, file_path: Path, lines: List[str], encoding: str) -> None:
        """Safely write file with backup."""
        content = ''.join(lines)
        safe_write(file_path, content, encoding)

    def find_files(self) -> List[Path]:
        """Find files to process based on configuration."""
        root_dirs = []

        if self.config.directories:
            root_dirs = [Path(d).resolve() for d in self.config.directories]
        else:
            root_dirs = [Path('.').resolve()]

        files = self.file_walker.find_files(root_dirs, recursive=self.config.recursive)

        # Log statistics
        stats = self.file_walker.stats
        logging.info(f"Found {len(files)} files to process")
        logging.info(f"Excluded {stats['files_excluded']} files and {stats['directories_excluded']} directories")

        return files

    def process_files(self) -> Dict[str, Any]:
        """Process all found files."""
        files = self.find_files()

        if not files:
            logging.warning("No files found matching criteria")
            return {'total_files': 0, 'total_comments': 0, 'removed_comments': 0}

        # Print configuration
        self._log_configuration()

        total_removed = 0
        total_comments = 0
        all_comments = []

        # Process files with progress reporting
        with ProgressReporter(len(files), "Extracting comments") as progress:
            for file_path in files:
                try:
                    removed, comments = self.process_file(file_path)
                    total_removed += removed
                    total_comments += len(comments)

                    # Log found comments
                    for line_num, comment in comments:
                        rel_path = get_relative_path(file_path)
                        logging.info(f"{rel_path}:{line_num}: {comment}")
                        all_comments.append({
                            'file': str(file_path),
                            'line': line_num,
                            'comment': comment,
                            'relative_path': rel_path
                        })

                except Exception as e:
                    logging.error(f"Failed to process {file_path}: {e}")

                progress.update()

        # Log summary
        self._log_summary(total_removed, total_comments, len(files))

        # Export comments if requested
        if self.config.export_file and all_comments:
            self._export_comments(all_comments)

        return {
            'total_files': len(files),
            'total_comments': total_comments,
            'removed_comments': total_removed,
            'comments': all_comments
        }

    def _log_configuration(self) -> None:
        """Log configuration details."""
        logging.info("=" * 60)
        logging.info("COMMENT EXTRACTOR CONFIGURATION")
        logging.info("=" * 60)

        if self.config.directories:
            logging.info(f"Directories: {', '.join(str(d) for d in self.config.directories)}")
        else:
            logging.info("Directory: .")

        logging.info(f"Pattern: {self.config.include_pattern}")
        logging.info(f"Recursive: {self.config.recursive}")
        logging.info(f"Remove comments: {self.config.remove_comments}")
        logging.info(f"Preview mode: {self.config.preview_mode}")

        if self.config.language_filter:
            logging.info(f"Language filter: {self.config.language_filter}")

        if self.config.exclude_comment_pattern:
            logging.info(f"Exclude comment pattern: {self.config.exclude_comment_pattern}")

        # Log exclusions
        exclusions = []
        if self.config.exclude_dirs:
            exclusions.append(f"Directories: {', '.join(self.config.exclude_dirs)}")
        if self.config.exclude_names:
            exclusions.append(f"Names: {', '.join(self.config.exclude_names)}")
        if self.config.exclude_patterns:
            exclusions.append(f"Patterns: {', '.join(self.config.exclude_patterns)}")

        if exclusions:
            logging.info("Exclusions:")
            for exclusion in exclusions:
                logging.info(f"  - {exclusion}")

        if self.config.use_gitignore or self.config.custom_gitignore:
            logging.info("Gitignore: Enabled")

        logging.info("=" * 60)

    def _log_summary(self, removed: int, found: int, files: int) -> None:
        """Log processing summary."""
        logging.info("=" * 60)
        logging.info("PROCESSING SUMMARY")
        logging.info("=" * 60)

        action = "Would remove" if self.config.preview_mode else (
            "Removed" if self.config.remove_comments else "Found"
        )

        logging.info(f"{action} {removed} comments out of {found} total")
        logging.info(f"Processed {files} files")

        if self.config.remove_comments and not self.config.preview_mode:
            logging.info("⚠️  Comments have been removed from files")
            logging.info("   Backup files were created with .bak extension")

        logging.info("=" * 60)

    def _export_comments(self, comments: List[Dict[str, Any]]) -> None:
        """Export comments to file."""
        try:
            with open(self.config.export_file, 'w', encoding='utf-8') as f:
                f.write("EXTRACTED COMMENTS REPORT\n")
                f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total comments: {len(comments)}\n")
                f.write("=" * 60 + "\n\n")

                # Group by file
                comments_by_file = {}
                for comment in comments:
                    file_path = comment['relative_path']
                    if file_path not in comments_by_file:
                        comments_by_file[file_path] = []
                    comments_by_file[file_path].append(comment)

                # Write grouped comments
                for file_path, file_comments in comments_by_file.items():
                    f.write(f"\nFILE: {file_path}\n")
                    f.write("-" * 40 + "\n")

                    for comment in file_comments:
                        f.write(f"Line {comment['line']}: {comment['comment']}\n")

                    f.write(f"\nTotal in file: {len(file_comments)}\n")

                f.write("\n" + "=" * 60 + "\n")
                f.write(f"Total files: {len(comments_by_file)}\n")
                f.write(f"Total comments: {len(comments)}\n")

            logging.info(f"Comments exported to: {self.config.export_file}")

        except Exception as e:
            logging.error(f"Failed to export comments: {e}")


# ============================================================================
# CLI Interface
# ============================================================================

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Advanced comment extractor and remover",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract comments from Python files
  %(prog)s --pattern "*.py" --export comments.txt

  # Remove English comments from all source files
  %(prog)s --language en --remove-comments --recursive

  # Preview what would be removed
  %(prog)s --pattern "*.js" --remove-comments --preview

  # Process specific directories
  %(prog)s src/ tests/ --pattern "*.py" --use-gitignore
        """
    )

    # Input sources
    input_group = parser.add_argument_group('Input Sources')
    input_group.add_argument(
        'directories',
        nargs='*',
        default=['.'],
        help='Directories to process (default: current directory)'
    )
    input_group.add_argument(
        '-p', '--pattern',
        default='*',
        help='File pattern to match (e.g., "*.py", "*.js")'
    )
    input_group.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Search directories recursively'
    )

    # Comment detection
    comment_group = parser.add_argument_group('Comment Detection')
    comment_group.add_argument(
        '-c', '--comment-symbols',
        help='Override comment symbols (e.g., "#" or "//")'
    )
    comment_group.add_argument(
        '-e', '--exclude-comment-pattern',
        help='Pattern to exclude from comments (e.g., "##" for shebangs)'
    )
    comment_group.add_argument(
        '-l', '--language',
        help='Filter comments by language (e.g., "en", "ru", "es")'
    )

    # Actions
    action_group = parser.add_argument_group('Actions')
    action_group.add_argument(
        '--remove-comments',
        action='store_true',
        help='Remove comments from files (creates backups)'
    )
    action_group.add_argument(
        '--preview',
        action='store_true',
        help='Preview changes without modifying files'
    )
    action_group.add_argument(
        '--export-comments',
        type=Path,
        help='Export all comments to specified file'
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

    # Output
    output_group = parser.add_argument_group('Output')
    output_group.add_argument(
        '-o', '--output',
        type=Path,
        help='Output log file (default: stdout)'
    )
    output_group.add_argument(
        '--log-file',
        type=Path,
        help='Legacy alias for --output'
    )

    # Performance
    perf_group = parser.add_argument_group('Performance')
    perf_group.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable result caching'
    )
    perf_group.add_argument(
        '--chunk-size',
        type=int,
        default=8192,
        help='File reading chunk size'
    )

    args = parser.parse_args()

    # Handle legacy option
    if args.log_file and not args.output:
        args.output = args.log_file

    return args


def create_config_from_args(args) -> CommentExtractorConfig:
    """Create configuration from command line arguments."""
    return CommentExtractorConfig(
        # Filtering
        exclude_dirs=set(args.exclude_dirs or []),
        exclude_names=set(args.exclude_names or []),
        exclude_patterns=set(args.exclude_patterns or []),
        include_pattern=args.pattern,
        max_depth=args.max_depth,

        # Gitignore
        use_gitignore=args.use_gitignore and not args.no_gitignore,
        custom_gitignore=args.gitignore,

        # Comment settings
        comment_symbols=args.comment_symbols,
        exclude_comment_pattern=args.exclude_comment_pattern,
        language_filter=args.language,

        # Actions
        remove_comments=args.remove_comments,
        preview_mode=args.preview,
        export_file=args.export_comments,
        log_file=args.output,

        # Performance
        use_cache=not args.no_cache,
        chunk_size=args.chunk_size,

        # File operations
        recursive=args.recursive,
        directories=args.directories
    )


def main():
    """Main entry point."""
    try:
        args = parse_arguments()

        # Warn about langdetect if needed
        if args.language and not LANGDETECT_AVAILABLE:
            print("Warning: langdetect not installed. Language detection disabled.")
            print("Install with: pip install langdetect")
            args.language = None

        config = create_config_from_args(args)
        processor = CommentProcessor(config)

        result = processor.process_files()

        # Show quick summary
        if not config.log_file and not config.preview_mode:
            action = "Would remove" if config.preview_mode else (
                "Removed" if config.remove_comments else "Found"
            )
            print(f"\n{action} {result['removed_comments']} comments in {result['total_files']} files")

        return 0

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        return 130
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
