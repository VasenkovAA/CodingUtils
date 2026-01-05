"""
Script for automatic detection and removal of code comments.
Supports multiple file types and languages with .gitignore support.
"""

import argparse
import os
import re
import fnmatch
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import logging

try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False


class GitIgnoreParser:
    """Parser for .gitignore files with support for patterns."""

    def __init__(self, gitignore_path: Optional[Path] = None):
        self.patterns = []
        if gitignore_path and gitignore_path.exists():
            self.parse_gitignore(gitignore_path)

    def parse_gitignore(self, gitignore_path: Path) -> None:
        """Parse .gitignore file and extract patterns."""
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    self.patterns.append(line)
        except Exception as e:
            print(f"Warning: Could not parse .gitignore file: {e}", file=sys.stderr)

    def should_ignore(self, path: Path, root_dir: Path) -> bool:
        """Check if path should be ignored based on .gitignore patterns."""
        if not self.patterns:
            return False

        try:
            relative_path = path.relative_to(root_dir)
        except ValueError:
            return False

        path_str = str(relative_path).replace('\\', '/')
        should_ignore_result = False

        for pattern in self.patterns:
            if pattern.startswith('!'):
                neg_pattern = pattern[1:]
                if self._pattern_matches(path, path_str, neg_pattern):
                    return False
                continue

            if self._pattern_matches(path, path_str, pattern):
                should_ignore_result = True

        return should_ignore_result

    def _pattern_matches(self, path: Path, path_str: str, pattern: str) -> bool:
        """Check if a pattern matches the given path."""
        if '**' in pattern:
            if pattern == '**':
                return True
            pattern = pattern.replace('**/', '').replace('/**', '/*')
            if pattern.startswith('**'):
                pattern = pattern[2:]

        if pattern.endswith('/'):
            dir_pattern = pattern.rstrip('/')
            if path.is_dir() and fnmatch.fnmatch(path_str, dir_pattern):
                return True
            if fnmatch.fnmatch(path_str, dir_pattern + '/*'):
                return True
        else:
            if fnmatch.fnmatch(path_str, pattern):
                return True
            if fnmatch.fnmatch(path.name, pattern):
                return True

        return False



class CommentProcessor:
    """Process comments in code files based on configuration."""

    DEFAULT_COMMENT_SYMBOLS = {
        '.py': '#',
        '.cpp': '//', '.c': '//', '.h': '//', '.hpp': '//',
        '.java': '//',
        '.js': '//', '.ts': '//',
        '.rs': '//',
        '.go': '//',
        '.php': '//',
        '.rb': '#',
        '.sh': '#',
        '.pl': '#', '.pm': '#',
        '.r': '#',
        '.lua': '--',
        '.sql': '--',
        '.html': '<!--',
        '.css': None,
    }

    BLOCK_COMMENT_START = {
        '.css': '/*',
        '.scss': '/*', '.sass': '/*',
        '.less': '/*',
        '.java': '/*',
        '.js': '/*', '.ts': '/*',
        '.cpp': '/*', '.c': '/*', '.h': '/*', '.hpp': '/*',
        '.php': '/*',
        '.sql': '/*',
    }

    BLOCK_COMMENT_END = {
        '.css': '*/',
        '.scss': '*/', '.sass': '*/',
        '.less': '*/',
        '.java': '*/',
        '.js': '*/', '.ts': '*/',
        '.cpp': '*/', '.c': '*/', '.h': '*/', '.hpp': '*/',
        '.php': '*/',
        '.sql': '*/',
    }

    def __init__(self, config):
        self.config = config
        self.gitignore_parser = None
        self.root_dir = Path.cwd()
        if self.config.gitignore:
            gitignore_path = Path(self.config.gitignore)
            if gitignore_path.exists():
                self.gitignore_parser = GitIgnoreParser(gitignore_path)
            else:
                print(f"Warning: Gitignore file '{self.config.gitignore}' not found", file=sys.stderr)
        elif self.config.use_gitignore:
            current_gitignore = Path('.gitignore')
            if current_gitignore.exists():
                self.gitignore_parser = GitIgnoreParser(current_gitignore)
                print(f"Auto-discovered .gitignore: {current_gitignore.resolve()}", file=sys.stderr)

        self.setup_logging()

    def setup_logging(self):
        """Setup logging based on configuration."""
        if self.config.output or self.config.log_file:
            log_file = self.config.output or self.config.log_file
            logging.basicConfig(
                filename=log_file,
                level=logging.INFO,
                format='%(message)s',
                filemode='w'
            )
        else:
            logging.basicConfig(level=logging.INFO, format='%(message)s')

    def should_exclude_path(self, file_path: Path) -> bool:
        """Check if file should be excluded based on all filters."""
        path_str = str(file_path)
        path_name = file_path.name

        if self.gitignore_parser:
            if self.gitignore_parser.should_ignore(file_path, self.root_dir):
                return True

        if self.config.exclude_dirs:
            for exclude_dir in self.config.exclude_dirs:
                if exclude_dir in path_str.split(os.sep):
                    parts = path_str.split(os.sep)
                    if exclude_dir in parts:
                        return True

        if self.config.exclude_names:
            for exclude_name in self.config.exclude_names:
                if fnmatch.fnmatch(path_name, exclude_name):
                    return True

        if self.config.exclude_patterns:
            for exclude_pattern in self.config.exclude_patterns:
                if fnmatch.fnmatch(path_name, exclude_pattern):
                    return True
                rel_path = str(file_path.relative_to(self.root_dir)) if file_path.is_relative_to(self.root_dir) else str(file_path)
                if fnmatch.fnmatch(rel_path, exclude_pattern):
                    return True

        if self.config.pattern != '*':
            if not fnmatch.fnmatch(path_name, self.config.pattern):
                return False

        return False

    def get_comment_symbol(self, file_path: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Get comment symbols for given file path."""
        if self.config.comment_symbols:
            return self.config.comment_symbols, None, None

        ext = os.path.splitext(file_path)[1].lower()
        line_symbol = self.DEFAULT_COMMENT_SYMBOLS.get(ext)
        block_start = self.BLOCK_COMMENT_START.get(ext)
        block_end = self.BLOCK_COMMENT_END.get(ext)

        if line_symbol is None and block_start is not None:
            return "", block_start, block_end

        if line_symbol is None and not self.config.comment_symbols:
            raise ValueError(
                f"Cannot determine comment symbol for {file_path}. "
                f"Use --comment-symbols to specify it manually."
            )

        return line_symbol, block_start, block_end

    def is_comment_line(self, line: str, comment_symbol: str,
                   in_block_comment: bool = False,
                   block_start: Optional[str] = None,
                   block_end: Optional[str] = None) -> Tuple[bool, Optional[str], bool]:
        """Check if line contains comments and return comment text if found."""
        line = line.rstrip()

        if block_start and block_end:
            if not in_block_comment and block_start in line:
                start_idx = line.find(block_start)
                if block_end in line:
                    end_idx = line.find(block_end) + len(block_end)
                    comment_text = line[start_idx:end_idx]
                    return True, comment_text, False
                else:
                    return True, None, True
            elif in_block_comment:
                if block_end in line:
                    end_idx = line.find(block_end) + len(block_end)
                    return True, line[:end_idx], False
                else:
                    return True, None, True

        if not comment_symbol:
            return False, None, in_block_comment

        in_string = False
        string_char = None
        i = 0

        while i < len(line):
            char = line[i]

            if char == '\\' and i + 1 < len(line):
                i += 2
                continue

            if char in ['"', "'"]:
                if not in_string:
                    in_string = True
                    string_char = char
                elif string_char == char:
                    in_string = False
                    string_char = None

            if not in_string and line[i:].startswith(comment_symbol):
                comment_text = line[i + len(comment_symbol):].lstrip()

                if self.config.exclude_pattern and line[i:].startswith(self.config.exclude_pattern):
                    return False, None, in_block_comment
                return True, comment_text, in_block_comment

            i += 1

        return False, None, in_block_comment

    def should_remove_comment(self, comment_text: str) -> bool:
        """Check if comment should be removed based on language settings."""
        if not self.config.language:
            return True

        if not LANGDETECT_AVAILABLE:
            logging.warning("langdetect not available. Installing: pip install langdetect")
            return True

        try:
            cleaned_text = re.sub(r'\b(def|class|function|var|let|const|import|from)\b', '', comment_text)
            cleaned_text = re.sub(r'[^\w\s]', ' ', cleaned_text)
            cleaned_text = cleaned_text.strip()

            if not cleaned_text or len(cleaned_text) < 3:
                return True

            detected_lang = detect(cleaned_text)
            return detected_lang == self.config.language

        except LangDetectException:
            return True

    def process_file(self, file_path: str) -> Tuple[int, List[Tuple[int, str]]]:
        """Process single file and return number of removed comments and comment list."""
        try:
            comment_symbol, block_start, block_end = self.get_comment_symbol(file_path)
        except ValueError as e:
            logging.error(f"ERROR: {e}")
            return 0, []

        removed_count = 0
        new_lines = []
        comments_found = []
        in_block_comment = False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()
            except Exception as e:
                logging.error(f"Error reading {file_path}: {e}")
                return 0, []

        for line_num, line in enumerate(lines, 1):
            is_comment, comment_text, block_state = self.is_comment_line(
                line, comment_symbol, in_block_comment, block_start, block_end
            )

            if block_state is not None:
                in_block_comment = block_state

            if is_comment and comment_text:
                should_remove = self.should_remove_comment(comment_text)
                comments_found.append((line_num, comment_text.strip()))

                if should_remove:
                    removed_count += 1

                    if self.config.remove_comments:
                        if line.lstrip().startswith(comment_symbol) or (block_start and block_start in line):
                            continue
                        else:
                            comment_pos = line.find(comment_symbol)
                            if comment_pos != -1:
                                new_line = line[:comment_pos].rstrip() + '\n'
                                new_lines.append(new_line)
                            elif block_start and block_start in line:
                                start_idx = line.find(block_start)
                                end_idx = line.find(block_end) + len(block_end) if block_end and block_end in line else len(line)
                                new_line = line[:start_idx] + line[end_idx:].lstrip()
                                if new_line.strip():
                                    new_lines.append(new_line)
                                else:
                                    continue
                            else:
                                new_lines.append(line)
                        continue

            new_lines.append(line)

        if self.config.remove_comments and removed_count > 0:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
            except Exception as e:
                logging.error(f"Error writing {file_path}: {e}")

        return removed_count, comments_found

    def find_files(self) -> List[str]:
        """Find files based on configuration."""
        files = []

        if self.config.files:
            for file_path in self.config.files:
                path = Path(file_path)
                if path.exists() and path.is_file():
                    if not self.should_exclude_path(path):
                        files.append(str(path))
                else:
                    print(f"Warning: File '{file_path}' not found, skipping", file=sys.stderr)
            return files

        search_paths = []
        if self.config.directories:
            for dir_path in self.config.directories:
                path = Path(dir_path)
                if path.exists() and path.is_dir():
                    search_paths.append(path)
                else:
                    print(f"Warning: Directory '{dir_path}' not found, skipping", file=sys.stderr)
        else:
            search_path = Path(self.config.directory)
            if search_path.exists():
                if search_path.is_file():
                    return [str(search_path)]
                else:
                    search_paths.append(search_path)
            else:
                print(f"Error: Directory '{self.config.directory}' does not exist", file=sys.stderr)
                return []

        for search_path in search_paths:
            if self.config.recursive:
                for file_path in search_path.rglob(self.config.pattern):
                    if file_path.is_file():
                        if not self.should_exclude_path(file_path):
                            files.append(str(file_path))
            else:
                for item in search_path.iterdir():
                    if item.is_file() and fnmatch.fnmatch(item.name, self.config.pattern):
                        if not self.should_exclude_path(item):
                            files.append(str(item))

        return sorted(set(files))

    def process_files(self):
        """Process all found files."""
        files = self.find_files()
        total_removed = 0
        total_comments = 0

        if not files:
            logging.warning("No files found matching the criteria")
            return

        logging.info("Comment Extractor Configuration:")
        if self.config.directories:
            logging.info(f"  Directories: {', '.join(self.config.directories)}")
        else:
            logging.info(f"  Directory: {self.config.directory}")

        logging.info(f"  Pattern: {self.config.pattern}")
        logging.info(f"  Recursive: {self.config.recursive}")

        if self.config.language:
            logging.info(f"  Language filter: {self.config.language}")

        if self.config.exclude_dirs or self.config.exclude_names or self.config.exclude_patterns:
            logging.info("  Exclusions applied:")
            if self.config.exclude_dirs:
                logging.info(f"    Directories: {', '.join(self.config.exclude_dirs)}")
            if self.config.exclude_names:
                logging.info(f"    Names: {', '.join(self.config.exclude_names)}")
            if self.config.exclude_patterns:
                logging.info(f"    Patterns: {', '.join(self.config.exclude_patterns)}")

        if self.gitignore_parser:
            if self.config.gitignore:
                logging.info(f"  Gitignore: {self.config.gitignore}")
            else:
                logging.info("  Gitignore: auto-discovered")

        logging.info("=" * 60)
        logging.info(f"Found {len(files)} files to process")
        logging.info("=" * 60)

        all_comments = []

        for file_path in files:
            try:
                removed, comments = self.process_file(file_path)
                total_removed += removed
                total_comments += len(comments)

                for line_num, comment in comments:
                    if self.config.preview or not self.config.remove_comments:
                        logging.info(f"{file_path}:{line_num}: {comment}")
                    all_comments.append((file_path, line_num, comment))

            except Exception as e:
                logging.error(f"Error processing {file_path}: {e}")

        logging.info("=" * 60)
        action = "Would remove" if self.config.preview else ("Removed" if self.config.remove_comments else "Found")
        logging.info(f"{action} {total_removed} comments out of {total_comments} total")
        logging.info(f"Processed {len(files)} files")

        if self.config.export_comments and all_comments:
            export_path = self.config.export_comments
            try:
                with open(export_path, 'w', encoding='utf-8') as f:
                    f.write(f"EXTRACTED COMMENTS: {len(all_comments)} comments from {len(files)} files\n")
                    f.write("=" * 60 + "\n\n")

                    for file_path, line_num, comment in all_comments:
                        f.write(f"FILE: {file_path}:{line_num}\n")
                        f.write(f"COMMENT: {comment}\n")
                        f.write("-" * 40 + "\n")

                logging.info(f"Comments exported to: {export_path}")
            except Exception as e:
                logging.error(f"Error exporting comments: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Auto-detector and remover of code comments",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'files',
        nargs='*',
        help='Explicit list of files to process (overrides directory search)'
    )

    parser.add_argument(
        'directory',
        nargs='?',
        default='.',
        help='Directory to search files in (default: current directory)'
    )

    parser.add_argument(
        '-d', '--directory',
        action='append',
        dest='directories',
        help='Directory to search files in (can be used multiple times)'
    )

    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Search recursively in subdirectories'
    )

    parser.add_argument(
        '-p', '--pattern',
        default='*',
        help='File pattern to search (e.g., "*.py" or "*.cpp")'
    )

    parser.add_argument(
        '-c', '--comment-symbols',
        help='Comment symbols (e.g., "#" or "//"). If not specified, auto-detected by file extension'
    )

    parser.add_argument(
        '-e', '--exclude-pattern',
        help='Pattern to exclude from comments (e.g., "##" to exclude lines starting with ##)'
    )

    parser.add_argument(
        '-l', '--language',
        help='Language code for comments (e.g., "ru" for Russian, "en" for English)'
    )

    parser.add_argument(
        '--remove-comments',
        action='store_true',
        help='Actually remove comments (without this flag, only detection)'
    )

    parser.add_argument(
        '--preview',
        action='store_true',
        help='Preview what would be done without actually removing comments'
    )

    parser.add_argument(
        '-o', '--output',
        help='Output file for results (replaces --log-file)'
    )

    parser.add_argument(
        '--log-file',
        help='Log file to write results (legacy, use --output instead)'
    )

    parser.add_argument(
        '--export-comments',
        help='Export all found comments to specified file'
    )

    parser.add_argument(
        '-ed', '--exclude-dir',
        action='append',
        dest='exclude_dirs',
        help='Exclude directory by name (can be used multiple times)'
    )

    parser.add_argument(
        '-en', '--exclude-name',
        action='append',
        dest='exclude_names',
        help='Exclude file by exact name or wildcard (can be used multiple times)'
    )

    parser.add_argument(
        '-ep', '--exclude-path-pattern',
        action='append',
        dest='exclude_patterns',
        help='Exclude by pattern (can be used multiple times, supports wildcards)'
    )

    parser.add_argument(
        '-gi', '--gitignore',
        help='Use specific .gitignore file for filtering'
    )

    parser.add_argument(
        '-ig', '--use-gitignore',
        action='store_true',
        help='Auto-discover and use .gitignore file in directory'
    )

    args = parser.parse_args()

    if args.exclude_dirs is None:
        args.exclude_dirs = []
    if args.exclude_names is None:
        args.exclude_names = []
    if args.exclude_patterns is None:
        args.exclude_patterns = []

    if args.directories is None:
        args.directories = []

    if args.language and not LANGDETECT_AVAILABLE:
        print("Warning: langdetect not installed. Language detection disabled.")
        print("Install with: pip install langdetect")
        args.language = None

    processor = CommentProcessor(args)
    processor.process_files()

    return 0


if __name__ == '__main__':
    exit(main())
