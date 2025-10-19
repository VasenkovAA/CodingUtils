"""
Script for automatic detection and removal of code comments.
Supports multiple file types and languages.
"""

import argparse
import fnmatch
import logging
import os
import re
from typing import List, Optional, Tuple

try:
    from langdetect import LangDetectException, detect

    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False


class CommentProcessor:
    """Process comments in code files based on configuration."""

    DEFAULT_COMMENT_SYMBOLS = {
        ".py": "#",
        ".cpp": "//",
        ".c": "//",
        ".h": "//",
        ".hpp": "//",
        ".java": "//",
        ".js": "//",
        ".ts": "//",
        ".rs": "//",
        ".go": "//",
        ".php": "//",
        ".rb": "#",
        ".sh": "#",
        ".pl": "#",
        ".pm": "#",
        ".r": "#",
        ".lua": "--",
        ".sql": "--",
        ".html": "<!--",
        ".css": "/*",
    }

    def __init__(self, config):
        self.config = config
        self.setup_logging()

    def setup_logging(self):
        """Setup logging based on configuration."""
        if self.config.log_file:
            logging.basicConfig(
                filename=self.config.log_file,
                level=logging.INFO,
                format="%(message)s",
            )
        else:
            logging.basicConfig(level=logging.INFO, format="%(message)s")

    def get_comment_symbol(self, file_path: str) -> str:
        """Get comment symbol for given file path."""
        if self.config.comment_symbols:
            return self.config.comment_symbols

        ext = os.path.splitext(file_path)[1].lower()
        symbol = self.DEFAULT_COMMENT_SYMBOLS.get(ext)

        if not symbol and not self.config.comment_symbols:
            raise ValueError(
                f"Cannot determine comment symbol for {file_path}. "
                f"Use --comment-symbols to specify it manually."
            )
        return symbol

    def is_comment_line(self, line: str, comment_symbol: str) -> Tuple[bool, Optional[str]]:
        """Check if line contains comments and return comment text if found."""
        line = line.rstrip()

        stripped = line.lstrip()
        if stripped.startswith(comment_symbol):
            comment_text = stripped[len(comment_symbol) :].lstrip()

            if self.config.exclude_pattern and stripped.startswith(self.config.exclude_pattern):
                return False, None
            return True, comment_text

        if comment_symbol in line:
            in_string = False
            string_char = None
            escaped = False

            for i, char in enumerate(line):
                if escaped:
                    escaped = False
                    continue

                if char == "\\":
                    escaped = True
                    continue

                if char in ['"', "'"]:
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif string_char == char:
                        in_string = False
                        string_char = None
                    continue

                if not in_string and line[i:].startswith(comment_symbol):
                    comment_text = line[i + len(comment_symbol) :].lstrip()

                    if self.config.exclude_pattern and line[i:].startswith(self.config.exclude_pattern):
                        return False, None
                    return True, comment_text

        return False, None

    def should_remove_comment(self, comment_text: str) -> bool:
        """Check if comment should be removed based on language settings."""
        if not self.config.language:
            return True

        if not LANGDETECT_AVAILABLE:
            logging.warning("langdetect not available. Installing: pip install langdetect")
            return True

        try:
            cleaned_text = re.sub(r"\b(def|class|function|var|let|const|import|from)\b", "", comment_text)
            cleaned_text = re.sub(r"[^\w\s]", " ", cleaned_text)
            cleaned_text = cleaned_text.strip()

            if not cleaned_text or len(cleaned_text) < 3:
                return True

            detected_lang = detect(cleaned_text)
            return detected_lang == self.config.language

        except LangDetectException:
            return True

    def process_file(self, file_path: str) -> int:
        """Process single file and return number of removed comments."""
        try:
            comment_symbol = self.get_comment_symbol(file_path)
        except ValueError as e:
            logging.error(f"ERROR: {e}")
            return 0

        removed_count = 0
        new_lines = []

        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            try:
                with open(file_path, encoding="latin-1") as f:
                    lines = f.readlines()
            except Exception as e:
                logging.error(f"Error reading {file_path}: {e}")
                return 0

        for line_num, line in enumerate(lines, 1):
            is_comment, comment_text = self.is_comment_line(line, comment_symbol)

            if is_comment and comment_text and self.should_remove_comment(comment_text):
                removed_count += 1
                logging.info(f"{file_path}:{line_num}: {comment_text.strip()}")

                if self.config.remove_comments:
                    if line.lstrip().startswith(comment_symbol):
                        continue
                    else:
                        comment_pos = line.find(comment_symbol)
                        new_line = line[:comment_pos].rstrip() + "\n"
                        new_lines.append(new_line)
                        continue

            new_lines.append(line)

        if self.config.remove_comments and removed_count > 0:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            except Exception as e:
                logging.error(f"Error writing {file_path}: {e}")

        return removed_count

    def find_files(self) -> List[str]:
        """Find files matching pattern in directory or single file."""
        files = []

        if os.path.isfile(self.config.directory):
            if self._file_matches_pattern(self.config.directory):
                files.append(self.config.directory)
            return files

        directory = self.config.directory

        if self.config.recursive:
            for root, _, filenames in os.walk(directory):
                for filename in filenames:
                    if self._file_matches_pattern(filename):
                        files.append(os.path.join(root, filename))
        else:
            for item in os.listdir(directory):
                if self._file_matches_pattern(item):
                    full_path = os.path.join(directory, item)
                    if os.path.isfile(full_path):
                        files.append(full_path)

        return files

    def _file_matches_pattern(self, filename: str) -> bool:
        """Check if filename matches the pattern."""
        return fnmatch.fnmatch(filename, self.config.pattern)

    def process_files(self):
        """Process all found files."""
        files = self.find_files()
        total_removed = 0

        if not files:
            logging.warning("No files found matching the criteria")
            return

        if os.path.isfile(self.config.directory):
            logging.info(f"Processing single file: {self.config.directory}")
        else:
            logging.info(f"Found {len(files)} files to process in directory: {self.config.directory}")

        for file_path in files:
            try:
                removed = self.process_file(file_path)
                total_removed += removed
            except Exception as e:
                logging.error(f"Error processing {file_path}: {e}")

        action = "Removed" if self.config.remove_comments else "Found"

        if os.path.isfile(self.config.directory):
            logging.info(f"{action} {total_removed} comments in file: {self.config.directory}")
        else:
            logging.info(f"{action} {total_removed} comments in {len(files)} files")


def main():
    parser = argparse.ArgumentParser(
        description="Auto-detector and remover of code comments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("directory", help="Directory to search files in or single file to process")

    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Search recursively in subdirectories (ignored for single file)",
    )

    parser.add_argument(
        "-p",
        "--pattern",
        default="*",
        help='File pattern to search (e.g., "*.py" or "model_*.cpp"). Ignored for single file',
    )

    parser.add_argument(
        "-c",
        "--comment-symbols",
        help='Comment symbols (e.g., "#" or "//"). If not specified, auto-detected by file extension',
    )

    parser.add_argument(
        "-e",
        "--exclude-pattern",
        help='Pattern to exclude from comments (e.g., "##" to exclude lines starting with ##)',
    )

    parser.add_argument(
        "-l",
        "--language",
        help='Language code for comments (e.g., "ru" for Russian, "en" for English)',
    )

    parser.add_argument(
        "--remove-comments",
        action="store_true",
        help="Actually remove comments (without this flag, only detection)",
    )

    parser.add_argument("-o", "--log-file", help="Log file to write results (default: console)")

    args = parser.parse_args()

    if not os.path.exists(args.directory):
        print(f"Error: Path '{args.directory}' does not exist")
        return 1

    if args.language and not LANGDETECT_AVAILABLE:
        print("Warning: langdetect not installed. Language detection disabled.")
        print("Install with: pip install langdetect")
        args.language = None

    processor = CommentProcessor(args)
    processor.process_files()

    return 0


if __name__ == "__main__":
    exit(main())
