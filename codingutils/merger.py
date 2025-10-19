"""
Script for merging multiple files into one with file headers.
"""

import argparse
import os
import fnmatch
import sys
from pathlib import Path
from typing import List, Optional


class FileMerger:
    """Merge multiple files into one with headers."""

    def __init__(self, config):
        self.config = config
        self.root_dir = Path.cwd()

    def get_relative_path(self, file_path: str) -> str:
        """Get relative path from project root."""
        try:
            absolute_path = Path(file_path).resolve()
            relative_path = absolute_path.relative_to(self.root_dir)
            return str(relative_path)
        except ValueError:
            return str(absolute_path)

    def find_files(self) -> List[str]:
        """Find files based on configuration."""
        files = []

        if self.config.files:
            for file_path in self.config.files:
                if os.path.isfile(file_path):
                    files.append(file_path)
                else:
                    print(
                        f"Warning: File '{file_path}' not found, skipping",
                        file=sys.stderr,
                    )
            return files

        search_path = Path(self.config.directory)

        if not search_path.exists():
            print(
                f"Error: Directory '{self.config.directory}' does not exist",
                file=sys.stderr,
            )
            return []

        if self.config.recursive:
            for file_path in search_path.rglob(self.config.pattern):
                if file_path.is_file():
                    files.append(str(file_path))
        else:
            for item in search_path.iterdir():
                if item.is_file() and fnmatch.fnmatch(item.name, self.config.pattern):
                    files.append(str(item))

        return sorted(files)

    def create_header(self, file_path: str) -> str:
        """Create header for file with relative path."""
        relative_path = self.get_relative_path(file_path)
        header = f"\n{'=' * 60}\n"
        header += f"FILE: {relative_path}\n"
        header += f"{'=' * 60}\n"
        return header

    def merge_files(self) -> bool:
        """Merge files into output file."""
        files = self.find_files()

        if not files:
            print("No files found to merge", file=sys.stderr)
            return False

        print(f"Found {len(files)} files to merge:")
        for file_path in files:
            print(f"  - {self.get_relative_path(file_path)}")

        try:
            output_path = Path(self.config.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as output_file:
                output_file.write(f"MERGED FILES: {len(files)} files\n")
                output_file.write(f"MERGE DATE: {os.popen('date').read().strip()}\n")
                output_file.write(f"ROOT DIRECTORY: {self.root_dir}\n")
                output_file.write("=" * 60 + "\n\n")

                for file_path in files:
                    try:
                        output_file.write(self.create_header(file_path))

                        with open(file_path, "r", encoding="utf-8") as input_file:
                            content = input_file.read()
                            output_file.write(content)

                            if content and not content.endswith("\n"):
                                output_file.write("\n")

                    except UnicodeDecodeError:
                        try:
                            with open(file_path, "r", encoding="latin-1") as input_file:
                                content = input_file.read()
                                output_file.write(self.create_header(file_path))
                                output_file.write(content)
                                if content and not content.endswith("\n"):
                                    output_file.write("\n")
                        except Exception as e:
                            print(f"Error reading {file_path}: {e}", file=sys.stderr)
                            output_file.write(f"\n[ERROR READING FILE: {e}]\n")

                    except Exception as e:
                        print(f"Error processing {file_path}: {e}", file=sys.stderr)
                        output_file.write(self.create_header(file_path))
                        output_file.write(f"[ERROR READING FILE: {e}]\n")

            relative_output = self.get_relative_path(str(output_path))
            print(f"\nSuccessfully merged {len(files)} files into: {relative_output}")
            print(f"Total output file size: {output_path.stat().st_size} bytes")

            return True

        except Exception as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            return False

    def preview_merge(self) -> bool:
        """Preview what files would be merged without actually merging."""
        files = self.find_files()

        if not files:
            print("No files found to merge", file=sys.stderr)
            return False

        print(f"PREVIEW - Found {len(files)} files that would be merged:")
        print("-" * 80)

        total_size = 0
        for file_path in files:
            relative_path = self.get_relative_path(file_path)
            size = os.path.getsize(file_path)
            total_size += size
            print(f"{relative_path} ({size} bytes)")

        print("-" * 80)
        print(f"Total: {len(files)} files, {total_size} bytes")
        print(f"Output would be written to: {self.config.output}")

        return True


def main():
    parser = argparse.ArgumentParser(
        description="Merge multiple files into one with file headers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "files",
        nargs="*",
        help="Explicit list of files to merge (overrides directory search)",
    )

    parser.add_argument(
        "-d",
        "--directory",
        default=".",
        help="Directory to search files in (default: current directory)",
    )

    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Search recursively in subdirectories",
    )

    parser.add_argument(
        "-p",
        "--pattern",
        default="*",
        help='File pattern to search (e.g., "*.py" or "model_*.txt")',
    )

    parser.add_argument(
        "-o",
        "--output",
        default="merged_files.txt",
        help="Output file for merged content (default: merged_files.txt)",
    )

    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview what would be merged without actually merging",
    )

    args = parser.parse_args()

    merger = FileMerger(args)

    if args.preview:
        return 0 if merger.preview_merge() else 1
    else:
        return 0 if merger.merge_files() else 1


if __name__ == "__main__":
    exit(main())
